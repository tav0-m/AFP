"""Regímenes con probabilidades de transición variables (TVTP-HMM; Diebold, Lee y Weinbach, 1994).

La matriz de transición depende de variables macro observadas al cierre de cada mes:
    P(s_{t+1} = j | s_t = i, z_t) = softmax_j( b_ij + w_ij · z_t ),   con j = i como categoría de referencia.
Emisiones: normales multivariadas por régimen, igual que el HMM base (econometria.py).

Estimación por EM. El paso E es un forward-backward escalado con una matriz por mes; el paso M de las transiciones
es una regresión logística multinomial ponderada por las transiciones esperadas xi_t, con penalización ridge.

Evaluación honesta (walk-forward): se reestima cada 12 meses solo con datos pasados, se estandarizan las variables
con la media y la desviación de la ventana de entrenamiento, y se mide la densidad predictiva a un paso del mes
siguiente, log p(r_{t+1} | información hasta t). Se compara contra el HMM de transiciones constantes y una normal.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import multivariate_normal

from . import config, econometria

VARIABLES = {"inflacion_12m": "Inflación 12 meses (IPC, rezago 1 mes)",
             "delta_tpm_6m": "Cambio de la TPM en 6 meses",
             "dolar_3m": "Variación del dólar en 3 meses",
             "imacec": "Imacec anual (rezago 2 meses)"}


# ---------------------------------------------------------------------------
# Variables macro (sin mirar al futuro: cada una con el rezago de su publicación)
# ---------------------------------------------------------------------------
def cargar_macro(path=None) -> pd.DataFrame:
    df = pd.read_csv(path or config.DATA_RAW / "macro_mindicador.csv", parse_dates=["fecha"])
    df["mes"] = df.fecha.dt.to_period("M")
    ancho = (df.sort_values("fecha").groupby(["mes", "indicador"]).valor.last().unstack())
    ancho.index = ancho.index.to_timestamp("M")
    return ancho


def construir_variables(macro: pd.DataFrame, indice: pd.DatetimeIndex) -> pd.DataFrame:
    m = macro.reindex(pd.date_range(macro.index.min(), indice.max(), freq="ME")).ffill()
    z = pd.DataFrame(index=m.index)
    ipc = (1 + m["ipc"] / 100).rolling(12).apply(np.prod, raw=True) - 1
    z["inflacion_12m"] = ipc.shift(1)                       # el IPC de t se publica a inicios de t+1
    z["delta_tpm_6m"] = m["tpm"] - m["tpm"].shift(6)
    z["dolar_3m"] = np.log(m["dolar"]).diff(3)
    z["imacec"] = m["imacec"].shift(2)                      # el Imacec se publica con ~1 mes de rezago
    return z.reindex(indice).ffill().bfill()


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------
def matrices_transicion(b: np.ndarray, W: np.ndarray, Z: np.ndarray) -> np.ndarray:
    """A[t, i, j] a partir de los logits (la diagonal de b y W es la referencia y vale 0)."""
    logit = b[None] + np.einsum("ijp,tp->tij", W, Z)
    logit -= logit.max(axis=2, keepdims=True)
    e = np.exp(logit)
    return e / e.sum(axis=2, keepdims=True)


def _forward_backward_tv(logB: np.ndarray, pi: np.ndarray, A: np.ndarray):
    """Forward-backward escalado con A[t] = transición de t a t+1. Devuelve loglik, gamma y xi por mes."""
    T, K = logB.shape
    mx = logB.max(1, keepdims=True); B = np.exp(logB - mx)
    alpha = np.empty((T, K)); beta = np.ones((T, K)); c = np.empty(T)
    a = pi * B[0]; c[0] = a.sum(); alpha[0] = a / c[0]
    for t in range(1, T):
        a = (alpha[t - 1] @ A[t - 1]) * B[t]; c[t] = a.sum(); alpha[t] = a / c[t]
    Bb = np.empty((T, K)); Bb[-1] = B[-1]
    for t in range(T - 2, -1, -1):
        beta[t] = A[t] @ Bb[t + 1] / c[t + 1]
        Bb[t] = B[t] * beta[t]
    ll = float(np.log(c).sum() + mx.sum())
    xi = alpha[:-1, :, None] * A * Bb[1:, None, :] / c[1:, None, None]
    return ll, alpha * beta, xi, alpha


def _m_transiciones(xi: np.ndarray, Z: np.ndarray, b: np.ndarray, W: np.ndarray, ridge: float):
    """Regresión logística multinomial ponderada, fila por fila (una por régimen de origen)."""
    K, p = b.shape[0], Z.shape[1]
    for i in range(K):
        otros = [j for j in range(K) if j != i]
        n_t = xi[:, i, :].sum(1)

        def f(theta):
            bb = np.zeros(K); WW = np.zeros((K, p))
            bb[otros] = theta[:K - 1]; WW[otros] = theta[K - 1:].reshape(K - 1, p)
            logit = bb[None] + Z @ WW.T
            logit -= logit.max(1, keepdims=True)
            lse = np.log(np.exp(logit).sum(1))
            logp = logit - lse[:, None]
            nll = -(xi[:, i, :] * logp).sum() + 0.5 * ridge * (WW ** 2).sum()
            g = n_t[:, None] * np.exp(logp) - xi[:, i, :]
            gb = g.sum(0)[otros]; gW = (g.T @ Z + ridge * WW)[otros].ravel()
            return nll, np.concatenate([gb, gW])

        theta0 = np.concatenate([b[i, otros], W[i, otros].ravel()])
        res = minimize(f, theta0, jac=True, method="L-BFGS-B")
        b[i, otros] = res.x[:K - 1]; W[i, otros] = res.x[K - 1:].reshape(K - 1, p)
    return b, W


def ajustar_tvtp(X: np.ndarray, Z: np.ndarray, inicial: dict, max_iter: int = 200, tol: float = 1e-6,
                 ridge: float = 1.0, reg: float = 1e-6) -> dict:
    """EM del TVTP-HMM partiendo de un HMM constante ya ajustado (transiciones iniciales = log A, pesos 0)."""
    K = inicial["K"]; T, d = X.shape; p = Z.shape[1]
    mu, cov, pi = inicial["mu"].copy(), inicial["cov"].copy(), inicial["pi"].copy()
    logA = np.log(inicial["A"])
    b = logA - np.diag(logA)[:, None]                         # referencia: quedarse en el mismo régimen
    W = np.zeros((K, K, p))
    ll_prev = -np.inf
    for _ in range(max_iter):
        A = matrices_transicion(b, W, Z[:-1])
        logB = np.column_stack([econometria._logpdf_mvn(X, mu[k], cov[k]) for k in range(K)])
        ll, gamma, xi, _ = _forward_backward_tv(logB, pi, A)
        pi = gamma[0] + 1e-12; pi /= pi.sum()
        b, W = _m_transiciones(xi, Z[:-1], b, W, ridge)
        for k in range(K):
            w = gamma[:, k]; sw = w.sum()
            mu[k] = (w[:, None] * X).sum(0) / sw
            Xc = X - mu[k]
            cov[k] = (w[:, None] * Xc).T @ Xc / sw + reg * np.eye(d)
        if abs(ll - ll_prev) < tol * (1 + abs(ll)):
            break
        ll_prev = ll
    A = matrices_transicion(b, W, Z[:-1])
    logB = np.column_stack([econometria._logpdf_mvn(X, mu[k], cov[k]) for k in range(K)])
    ll, gamma, _, _ = _forward_backward_tv(logB, pi, A)
    n_par = (K - 1) + K * (K - 1) * (1 + p) + K * d + K * d * (d + 1) / 2
    return {"K": K, "mu": mu, "cov": cov, "pi": pi, "b": b, "W": W, "gamma": gamma, "loglik": ll,
            "bic": -2 * ll + n_par * np.log(T), "ridge": ridge}


# ---------------------------------------------------------------------------
# Densidad predictiva a un paso
# ---------------------------------------------------------------------------
def _log_densidades(X, mod):
    return np.column_stack([econometria._logpdf_mvn(X, mod["mu"][k], mod["cov"][k]) for k in range(mod["K"])])


def log_predictiva(X: np.ndarray, mod: dict, desde: int, hasta: int, Z: np.ndarray | None = None) -> np.ndarray:
    """log p(x_t | x_<t, z_<t) para t en [desde, hasta), filtrando con parámetros fijos."""
    K = mod["K"]; logB = _log_densidades(X[:hasta], mod)
    A = matrices_transicion(mod["b"], mod["W"], Z[:hasta - 1]) if "W" in mod else np.repeat(mod["A"][None], hasta - 1, 0)
    mx = logB.max(1, keepdims=True); B = np.exp(logB - mx)
    alpha = mod["pi"] * B[0]; alpha /= alpha.sum()
    out = []
    for t in range(1, hasta):
        pred = alpha @ A[t - 1]
        dens = pred * B[t]
        if t >= desde:
            out.append(np.log(dens.sum()) + mx[t, 0])
        alpha = dens / dens.sum()
    return np.array(out)


def diebold_mariano(d: np.ndarray, rezagos: int = 6) -> tuple[float, float]:
    """Media de la diferencia de log-scores y su estadístico t con varianza HAC (Newey-West)."""
    from scipy.stats import norm
    d = np.asarray(d); n = len(d); dc = d - d.mean()
    v = dc @ dc / n
    for k in range(1, rezagos + 1):
        v += 2 * (1 - k / (rezagos + 1)) * (dc[k:] @ dc[:-k]) / n
    t = d.mean() / np.sqrt(v / n)
    return float(t), float(2 * (1 - norm.cdf(abs(t))))


def walk_forward(m: pd.DataFrame, Zdf: pd.DataFrame, inicio_prueba: str = "2015-01-31", cada: int = 12,
                 K: int = 3, ridge: float = 1.0, semilla: int = 11) -> pd.DataFrame:
    X = m.values; fechas = m.index; T = len(X)
    t0 = int(np.searchsorted(fechas, pd.Timestamp(inicio_prueba)))
    filas = []
    for ini in range(t0, T, cada):
        fin = min(ini + cada, T)
        Xtr = X[:ini]
        mu_z, sd_z = Zdf.values[:ini].mean(0), Zdf.values[:ini].std(0) + 1e-12
        Z = (Zdf.values - mu_z) / sd_z                             # estandarización solo con el pasado
        const = econometria.ajustar_hmm(Xtr, K, n_inicios=10, semilla=semilla)
        tv = ajustar_tvtp(Xtr, Z[:ini], const, ridge=ridge)
        normal = {"K": 1, "mu": Xtr.mean(0)[None], "cov": np.cov(Xtr.T)[None] + 1e-6 * np.eye(X.shape[1]),
                  "pi": np.ones(1), "A": np.ones((1, 1))}
        lp = {"HMM constante": log_predictiva(X, const, ini, fin),
              "HMM con macro (TVTP)": log_predictiva(X, tv, ini, fin, Z),
              "Normal (sin regímenes)": log_predictiva(X, normal, ini, fin)}
        for k, t in enumerate(range(ini, fin)):
            filas.append({"fecha": fechas[t], **{n: v[k] for n, v in lp.items()}})
    return pd.DataFrame(filas).set_index("fecha")


def evaluar(m: pd.DataFrame, modelo_base: dict, macro: pd.DataFrame | None = None, ridge: float = 1.0) -> dict:
    macro = cargar_macro() if macro is None else macro
    Zdf = construir_variables(macro, m.index)[list(VARIABLES)]
    wf = walk_forward(m, Zdf, ridge=ridge)
    comp = []
    for n in wf.columns:
        d = wf["HMM con macro (TVTP)"] - wf[n]
        t, pv = diebold_mariano(d.values) if n != "HMM con macro (TVTP)" else (np.nan, np.nan)
        comp.append({"modelo": n, "log_score_promedio": wf[n].mean(), "meses": len(wf),
                     "tvtp_menos_modelo": d.mean(), "t_diebold_mariano": t, "p_valor": pv})
    # ajuste con toda la muestra, para interpretar los coeficientes
    Z = ((Zdf - Zdf.mean()) / Zdf.std()).values
    full = ajustar_tvtp(m.values, Z, modelo_base, ridge=ridge)
    efectos = efectos_marginales(full, Z)
    prob = pd.DataFrame(full["gamma"], index=m.index)
    return {"walk_forward": wf, "comparacion": pd.DataFrame(comp), "modelo": full, "efectos": efectos,
            "variables": Zdf, "prob_regimen": prob}


def efectos_marginales(mod: dict, Z: np.ndarray) -> pd.DataFrame:
    """Cambio en la probabilidad de pasar de un régimen a otro el mes siguiente si cada variable sube 1 desviación
    estándar (el resto en su media). Pares de interés: salir de la calma y entrar o salir del régimen de tasas."""
    K = mod["K"]; filas = []
    base = matrices_transicion(mod["b"], mod["W"], np.zeros((1, Z.shape[1])))[0]
    for v, var in enumerate(VARIABLES):
        z = np.zeros((1, Z.shape[1])); z[0, v] = 1.0
        alto = matrices_transicion(mod["b"], mod["W"], z)[0]
        for i in range(K):
            for j in range(K):
                if i != j:
                    filas.append({"variable": VARIABLES[var], "desde": i, "hacia": j, "prob_base": base[i, j],
                                  "prob_con_+1sd": alto[i, j], "cambio_pp": alto[i, j] - base[i, j]})
    return pd.DataFrame(filas)
