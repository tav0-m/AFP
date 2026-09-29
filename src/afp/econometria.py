"""Etapa 3 - Econometría implementada desde cero (numpy/scipy).

* HMM gaussiano multivariado (Baum-Welch con escalamiento) -> regímenes de mercado
  conjuntos para los 5 fondos. Selección del número de estados por BIC.
* GARCH(1,1) por cuasi-máxima verosimilitud -> volatilidad condicional diaria.
* Correlaciones móviles entre fondos.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.signal import lfilter


# ---------------------------------------------------------------------------
# HMM gaussiano multivariado
# ---------------------------------------------------------------------------
def _logpdf_mvn(X, mu, cov):
    d = X.shape[1]
    L = np.linalg.cholesky(cov)
    z = np.linalg.solve(L, (X - mu).T)
    return -0.5 * (d * np.log(2 * np.pi) + 2 * np.log(np.diag(L)).sum() + (z ** 2).sum(0))


def _forward_backward(logB, log_pi, log_A):
    """Forward-backward escalado (Rabiner, 1989): cada paso se normaliza por c_t y
    loglik = Σ log c_t. Las emisiones se reescalan por fila (máximo = 1) para evitar underflow."""
    T, K = logB.shape
    m = logB.max(1, keepdims=True)
    B = np.exp(logB - m); A = np.exp(log_A)
    alpha = np.empty((T, K)); beta = np.ones((T, K)); c = np.empty(T)
    a = np.exp(log_pi) * B[0]; c[0] = a.sum(); alpha[0] = a / c[0]
    for t in range(1, T):
        a = (alpha[t - 1] @ A) * B[t]; c[t] = a.sum(); alpha[t] = a / c[t]
    Bb = np.empty((T, K)); Bb[-1] = B[-1]
    for t in range(T - 2, -1, -1):
        beta[t] = A @ Bb[t + 1] / c[t + 1]
        Bb[t] = B[t] * beta[t]
    ll = np.log(c).sum() + m.sum()
    gamma = alpha * beta
    xi = np.einsum("ti,ij,tj->ij", alpha[:-1] / c[1:, None], A, Bb[1:])
    return ll, gamma, xi


def ajustar_hmm(X: np.ndarray, K: int = 2, n_inicios: int = 20, max_iter: int = 500,
                tol: float = 1e-7, semilla: int = 0, reg: float = 1e-6, inicial: dict | None = None) -> dict:
    """Baum-Welch con varios inicios aleatorios; devuelve la mejor solución.
    `inicial` (un modelo ya ajustado) agrega un arranque en caliente, útil en el bootstrap."""
    rng = np.random.default_rng(semilla)
    T, d = X.shape
    mejor = None
    for i in range(n_inicios + (inicial is not None)):
        if inicial is not None and i == 0:
            mu, cov, A, pi = (inicial[k].copy() for k in ("mu", "cov", "A", "pi"))
        else:
            idx = rng.choice(T, size=K, replace=False)
            mu = X[idx] + rng.normal(0, X.std(0) * 0.1, (K, d))
            cov = np.array([np.cov(X.T) * rng.uniform(0.5, 1.5) + reg * np.eye(d) for _ in range(K)])
            A = np.full((K, K), 0.1 / max(K - 1, 1)); np.fill_diagonal(A, 0.9) if K > 1 else None
            pi = np.full(K, 1 / K)
        ll_prev = -np.inf
        try:
            for _ in range(max_iter):
                logB = np.column_stack([_logpdf_mvn(X, mu[k], cov[k]) for k in range(K)])
                ll, gamma, xi = _forward_backward(logB, np.log(pi), np.log(A))
                pi = gamma[0] + 1e-12; pi /= pi.sum()
                fila = xi.sum(1, keepdims=True)       # estado sin transiciones esperadas: conserva su fila
                A = np.where(fila > 0, xi / np.where(fila > 0, fila, 1), A) + 1e-12; A /= A.sum(1, keepdims=True)
                for k in range(K):
                    w = gamma[:, k]; sw = w.sum()
                    mu[k] = (w[:, None] * X).sum(0) / sw
                    Xc = X - mu[k]
                    cov[k] = (w[:, None] * Xc).T @ Xc / sw + reg * np.eye(d)
                if ll - ll_prev < tol:      # reg·I rompe la monotonía exacta del EM: también corta si baja
                    break
                ll_prev = ll
            # paso E final: gamma y loglik consistentes con los parámetros que se devuelven
            logB = np.column_stack([_logpdf_mvn(X, mu[k], cov[k]) for k in range(K)])
            ll, gamma, _ = _forward_backward(logB, np.log(pi), np.log(A))
        except np.linalg.LinAlgError:
            continue
        if mejor is None or ll > mejor["loglik"]:
            mejor = dict(loglik=ll, pi=pi.copy(), A=A.copy(), mu=mu.copy(), cov=cov.copy(), gamma=gamma.copy())
    # ordenar estados por volatilidad promedio (0 = calma, K-1 = estrés)
    orden = np.argsort([np.trace(c) for c in mejor["cov"]])
    for key in ("mu", "cov", "pi"):
        mejor[key] = mejor[key][orden]
    mejor["A"] = mejor["A"][np.ix_(orden, orden)]
    mejor["gamma"] = mejor["gamma"][:, orden]
    n_par = (K - 1) + K * (K - 1) + K * d + K * d * (d + 1) / 2
    mejor["bic"] = -2 * mejor["loglik"] + n_par * np.log(T)
    mejor["K"] = K
    return mejor


def posterior_hmm(X: np.ndarray, modelo: dict) -> np.ndarray:
    """Probabilidades filtradas-suavizadas de cada régimen para X dados los parámetros del modelo."""
    logB = np.column_stack([_logpdf_mvn(X, modelo["mu"][k], modelo["cov"][k]) for k in range(modelo["K"])])
    return _forward_backward(logB, np.log(modelo["pi"] + 1e-300), np.log(modelo["A"]))[1]


def simular_hmm(modelo: dict, T: int, rng: np.random.Generator) -> np.ndarray:
    """Serie gaussiana de largo T generada por el HMM (para el bootstrap paramétrico)."""
    K = modelo["K"]; cum = np.cumsum(modelo["A"], 1)
    s = np.empty(T, int); s[0] = rng.choice(K, p=modelo["pi"] / modelo["pi"].sum())
    u = rng.random(T)
    for t in range(1, T):
        s[t] = min(int((u[t] > cum[s[t - 1]]).sum()), K - 1)
    L = np.linalg.cholesky(modelo["cov"])
    z = rng.standard_normal((T, modelo["mu"].shape[1]))
    return modelo["mu"][s] + np.einsum("tij,tj->ti", L[s], z)


def seleccionar_hmm(X: np.ndarray, Ks=(1, 2, 3), **kw) -> tuple[dict, pd.DataFrame]:
    modelos = {K: ajustar_hmm(X, K, **kw) for K in Ks}
    tabla = pd.DataFrame([{"K": K, "loglik": m["loglik"], "BIC": m["bic"]} for K, m in modelos.items()])
    mejor = min(modelos.values(), key=lambda m: m["bic"])
    return mejor, tabla


def resumen_regimenes(modelo: dict, fondos: list, periodos=12) -> pd.DataFrame:
    filas = []
    for k in range(modelo["K"]):
        vol = np.sqrt(np.diag(modelo["cov"][k]))
        dur = 1 / (1 - modelo["A"][k, k]) if modelo["A"][k, k] < 1 else np.inf
        for j, f in enumerate(fondos):
            filas.append({"regimen": k, "fondo": f,
                          "retorno_anual": (1 + modelo["mu"][k, j]) ** periodos - 1,
                          "vol_anual": vol[j] * np.sqrt(periodos),
                          "duracion_esperada_meses": dur,
                          "prob_estacionaria": _estacionaria(modelo["A"])[k]})
    return pd.DataFrame(filas)


def _estacionaria(A):
    w, v = np.linalg.eig(A.T)
    p = np.real(v[:, np.argmin(np.abs(w - 1))]); return p / p.sum()


# ---------------------------------------------------------------------------
# GARCH(1,1) gaussiano (QMLE)
# ---------------------------------------------------------------------------
def _garch_nll(params, r):
    omega, alpha, beta = params
    if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 0.9999:
        return 1e10
    s2 = _varianza_condicional(r, omega, alpha, beta, r.var())
    return 0.5 * np.sum(np.log(2 * np.pi * s2) + r ** 2 / s2)


def _varianza_condicional(r, omega, alpha, beta, s0):
    """s2[t] = omega + alpha*r[t-1]^2 + beta*s2[t-1], vectorizado con un filtro IIR."""
    u = omega + alpha * r[:-1] ** 2
    resto = lfilter([1.0], [1.0, -beta], u, zi=[beta * s0])[0]
    return np.concatenate([[s0], resto])


def ajustar_garch(r: np.ndarray, periodos_anio: int = 252,
                  inicios=((0.05, 0.90), (0.10, 0.85), (0.03, 0.95))) -> dict:
    r = np.asarray(r, float); r = r - r.mean()
    v = r.var()
    mejor = None
    for a0, b0 in inicios:
        x0 = [v * (1 - a0 - b0), a0, b0]
        res = minimize(_garch_nll, x0, args=(r,), method="Nelder-Mead",
                       options={"maxiter": 4000, "xatol": 1e-10, "fatol": 1e-8})
        if mejor is None or res.fun < mejor.fun:
            mejor = res
    omega, alpha, beta = mejor.x
    s2 = _varianza_condicional(r, omega, alpha, beta, v)
    pers = alpha + beta
    return {"omega": omega, "alpha": alpha, "beta": beta, "persistencia": pers,
            "vida_media_dias": np.log(0.5) / np.log(pers) if 0 < pers < 1 else np.inf,
            "vol_largo_plazo_anual": np.sqrt(omega / (1 - pers) * periodos_anio),
            "vol_actual_anual": np.sqrt(s2[-1] * periodos_anio),
            "sigma_condicional": np.sqrt(s2 * periodos_anio), "loglik": -mejor.fun}


def correlacion_movil(m: pd.DataFrame, a: str, b: str, ventana: int = 36) -> pd.Series:
    return m[a].rolling(ventana).corr(m[b])
