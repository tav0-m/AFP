"""Incertidumbre de parámetros: intervalos de confianza por bootstrap para los hallazgos.

Tres fuentes de incertidumbre, cada una con su bootstrap:

* HMM (bootstrap paramétrico): se simulan series del HMM estimado, se reestima y se miden
  volatilidades, duraciones y probabilidades de cada régimen. Además se reetiqueta la historia REAL
  con cada modelo reestimado para ver si el quiebre de 2019 depende del ajuste puntual.
* GARCH (simulación histórica filtrada): se remuestrean los residuos estandarizados, se regenera la
  serie con la recursión GARCH estimada y se reestima. No supone normalidad.
* Pensiones (bootstrap estacionario de la historia, Politis y Romano 1994): se remuestrean bloques de
  meses completos (largo geométrico de media 12), se reestima el HMM y se repite el Monte Carlo. Mide
  cuánto dependen los hallazgos de que la historia 2002-2026 fue UNA muestra: incluye la incertidumbre
  de la prima de retorno del Fondo A, que es la que más pesa en la ventaja del ciclo de vida.

Los intervalos son percentiles 5-95 (IC de 90%).
"""
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from . import config, econometria, escenarios, simulacion

DEF, CV, RE = "Por defecto (ley)", "Ciclo de vida (aprox. FG)", "Reactivo (market timing)"


def _semillas(semilla: int, k: int) -> list:
    """Semillas independientes por réplica: el resultado no depende del número de procesos."""
    return np.random.SeedSequence(semilla).spawn(k)


def _mapear(func, tareas: list, procesos: int) -> list:
    if procesos <= 1 or len(tareas) <= 1:
        return [func(t) for t in tareas]
    with ProcessPoolExecutor(max_workers=procesos) as ex:
        return list(ex.map(func, tareas, chunksize=max(1, len(tareas) // (4 * procesos))))


def _a_tabla(resultados: list[list[dict]]) -> pd.DataFrame:
    """Aplana las filas de cada réplica y numera las réplicas válidas."""
    return pd.DataFrame([{"replica": b, **fila} for b, filas in enumerate(resultados) for fila in filas])


def resumir(draws: pd.DataFrame, por: list[str], niveles=(0.05, 0.95)) -> pd.DataFrame:
    """Percentiles de cada métrica numérica, agrupando por las columnas `por`."""
    valores = [c for c in draws.columns if c not in por + ["replica"]]
    largo = draws.melt(id_vars=por + ["replica"], value_vars=valores, var_name="metrica")
    g = largo.groupby(por + ["metrica"], sort=False)["value"]
    out = pd.DataFrame({"p05": g.quantile(niveles[0]), "mediana": g.median(), "p95": g.quantile(niveles[1])})
    return out.reset_index()


# ---------------------------------------------------------------------------
# HMM
# ---------------------------------------------------------------------------
def alinear_estados(mod: dict, ref: dict) -> dict:
    """Reordena los estados de `mod` para que calcen con los de `ref` (evita el label switching).
    Asignación húngara sobre la distancia entre log-volatilidades y medias estandarizadas."""
    sd = lambda m_: np.log(np.sqrt(np.einsum("kii->ki", m_["cov"])))
    escala = np.sqrt(np.einsum("kii->ki", ref["cov"])).mean(0)
    costo = (((sd(mod)[:, None] - sd(ref)[None]) ** 2).sum(-1)
             + (((mod["mu"][:, None] - ref["mu"][None]) / escala) ** 2).sum(-1))
    fila, col = linear_sum_assignment(costo)
    orden = fila[np.argsort(col)]          # orden[j] = estado de mod que corresponde al estado j de ref
    out = dict(mod)
    for k in ("mu", "cov", "pi"):
        out[k] = mod[k][orden]
    out["A"] = mod["A"][np.ix_(orden, orden)]
    out["gamma"] = mod["gamma"][:, orden]
    return out

def _metricas_hmm(mod: dict, fondos: list, periodos=12) -> list[dict]:
    est = econometria._estacionaria(mod["A"])
    filas = []
    for k in range(mod["K"]):
        vol = np.sqrt(np.diag(mod["cov"][k])) * np.sqrt(periodos)
        fila = {"regimen": k, "persistencia": mod["A"][k, k],
                "duracion_meses": 1 / (1 - mod["A"][k, k]), "prob_estacionaria": est[k]}
        fila |= {f"vol_{f}": vol[j] for j, f in enumerate(fondos)}
        filas.append(fila)
    return filas


def _replica_hmm(tarea) -> list[dict]:
    X, modelo, fondos, post_quiebre, seed = tarea
    rng = np.random.default_rng(seed)
    Xb = econometria.simular_hmm(modelo, len(X), rng)
    try:
        mb = alinear_estados(econometria.ajustar_hmm(Xb, modelo["K"], n_inicios=1, semilla=int(rng.integers(2**31)),
                                                     inicial=modelo), modelo)
    except (np.linalg.LinAlgError, TypeError):
        return []
    extra = {}
    if post_quiebre is not None and modelo["K"] == 3:
        et = econometria.posterior_hmm(X, mb).argmax(1)
        extra["pct_meses_reg1_desde_quiebre"] = float((et[post_quiebre] == 1).mean())
    return [{**f, **extra} for f in _metricas_hmm(mb, fondos)]


def bootstrap_hmm(X: np.ndarray, modelo: dict, fondos: list, fechas: pd.DatetimeIndex,
                  B: int, semilla: int, desde_quiebre=None, procesos: int = 1) -> pd.DataFrame:
    post = None if desde_quiebre is None else np.asarray(fechas >= desde_quiebre)
    tareas = [(X, modelo, fondos, post, s) for s in _semillas(semilla, B)]
    return _a_tabla(_mapear(_replica_hmm, tareas, procesos))


# ---------------------------------------------------------------------------
# GARCH
# ---------------------------------------------------------------------------
def _simular_garch(z: np.ndarray, omega, alpha, beta, s0, rng, B: int) -> np.ndarray:
    """B series de largo len(z) con residuos remuestreados (vectorizado entre réplicas)."""
    T = len(z)
    e = z[rng.integers(0, T, (T, B))]
    r = np.empty((T, B)); s2 = np.full(B, s0)
    for t in range(T):
        r[t] = np.sqrt(s2) * e[t]
        s2 = omega + alpha * r[t] ** 2 + beta * s2
    return r


def _replica_garch(tarea) -> list[dict]:
    """Todas las réplicas de un fondo (la simulación está vectorizada entre réplicas)."""
    f, r, B, seed = tarea
    rng = np.random.default_rng(seed)
    r = r - r.mean()
    g = econometria.ajustar_garch(r)
    z = r / np.sqrt(g["sigma_condicional"] ** 2 / 252)
    sims = _simular_garch(z, g["omega"], g["alpha"], g["beta"], r.var(), rng, B)
    filas = []
    for b in range(B):
        gb = econometria.ajustar_garch(sims[:, b], inicios=((g["alpha"], g["beta"]),))
        filas.append({"replica": b, "fondo": f, "alpha": gb["alpha"], "beta": gb["beta"],
                      "persistencia": gb["persistencia"], "vida_media_dias": gb["vida_media_dias"],
                      "vol_largo_plazo_anual": gb["vol_largo_plazo_anual"]})
    return filas


def bootstrap_garch(retornos: pd.DataFrame, B: int, semilla: int, procesos: int = 1) -> pd.DataFrame:
    tareas = [(f, retornos[f].values.astype(float), B, s)
              for f, s in zip(retornos.columns, _semillas(semilla, retornos.shape[1]))]
    return pd.DataFrame([fila for filas in _mapear(_replica_garch, tareas, procesos) for fila in filas])


# ---------------------------------------------------------------------------
# Pensiones: bootstrap estacionario de la historia
# ---------------------------------------------------------------------------
def indices_bootstrap_estacionario(T: int, bloque_medio: float, rng) -> np.ndarray:
    """Índices del bootstrap estacionario circular: bloques de largo ~ Geométrica(1/bloque_medio)."""
    idx = np.empty(T, int)
    idx[0] = rng.integers(T)
    nuevo = rng.random(T) < 1 / bloque_medio
    inicio = rng.integers(0, T, T)
    for t in range(1, T):
        idx[t] = inicio[t] if nuevo[t] else (idx[t - 1] + 1) % T
    return idx


def _replica_pensiones(tarea) -> list[dict]:
    m, modelo, n, bloque_medio, sexo, reg0, seed = tarea
    rng = np.random.default_rng(seed)
    mb = m.iloc[indices_bootstrap_estacionario(len(m), bloque_medio, rng)]
    s = int(rng.integers(2**31))
    try:
        mod_b = alinear_estados(econometria.ajustar_hmm(mb.values, modelo["K"], n_inicios=2, semilla=s,
                                                        inicial=modelo), modelo)
    except (np.linalg.LinAlgError, TypeError):
        return []
    R = escenarios.simular(mb, mod_b, meses=480, n=n, semilla=s, regimen_inicial=reg0)
    tab, pens = simulacion.simular_estrategias(R, sexo)
    t = tab.set_index("estrategia")
    anual = lambda x: (1 + x).prod() ** (12 / len(mb))
    return [{"prima_real_A_vs_E": float(anual(mb["A"]) - anual(mb["E"])),
             "cv_vs_defecto_mediana": t.loc[CV, "mediana"] / t.loc[DEF, "mediana"] - 1,
             "cv_vs_defecto_p5": t.loc[CV, "p5"] / t.loc[DEF, "p5"] - 1,
             "prob_cv_supera_defecto": float((pens[CV] > pens[DEF]).mean()),
             "reactivo_vs_defecto_mediana": t.loc[RE, "mediana"] / t.loc[DEF, "mediana"] - 1,
             "mediana_defecto_uf": t.loc[DEF, "mediana"]}]


def bootstrap_pensiones(m: pd.DataFrame, modelo: dict, B: int, n: int, semilla: int,
                        bloque_medio: float = 12, sexo: str = "H", procesos: int = 1) -> pd.DataFrame:
    reg0 = int(modelo["gamma"][-1].argmax())
    tareas = [(m, modelo, n, bloque_medio, sexo, reg0, s) for s in _semillas(semilla, B)]
    return _a_tabla(_mapear(_replica_pensiones, tareas, procesos))


def ic_correlacion(r: float, n: int, z: float = 1.645) -> tuple[float, float]:
    """IC de 90% de Fisher para una correlación de n observaciones (supone independencia)."""
    f = np.arctanh(r); se = 1 / np.sqrt(n - 3)
    return float(np.tanh(f - z * se)), float(np.tanh(f + z * se))


def evaluar(m: pd.DataFrame, modelo: dict, retornos_diarios: pd.DataFrame, desde_quiebre=None,
            p=None) -> dict:
    p = p or config.INCERTIDUMBRE
    procesos = p.get("procesos") or max(1, (os.cpu_count() or 2) - 1)
    fondos = list(m.columns)
    hmm = bootstrap_hmm(m.values, modelo, fondos, m.index, p["B_hmm"], p["semilla"], desde_quiebre, procesos)
    garch = bootstrap_garch(retornos_diarios, p["B_garch"], p["semilla"], procesos)
    pens = bootstrap_pensiones(m, modelo, p["B_pensiones"], p["n_escenarios"], p["semilla"], p["bloque_medio"],
                               procesos=procesos)
    return {"hmm": hmm, "garch": garch, "pensiones": pens,
            "resumen_hmm": resumir(hmm, ["regimen"]), "resumen_garch": resumir(garch, ["fondo"]),
            "resumen_pensiones": resumir(pens, [])}
