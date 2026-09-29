"""Generador de escenarios: bootstrap condicionado a régimen (regime-switching bootstrap).

1. Simula la cadena de Markov de regímenes con la matriz de transición del HMM.
2. En cada mes, sortea un mes histórico completo (los 5 fondos juntos) del mismo régimen.
   Así se preservan colas gruesas, asimetrías y la correlación entre fondos de cada régimen,
   sin suponer normalidad, y la persistencia la aporta la cadena.
"""
import numpy as np
import pandas as pd


def retornos_objetivo(esg: dict, gp: dict) -> dict:
    """Retorno real anual esperado de cada multifondo según su participación en activos de crecimiento:
    r_f = g_f · r_crecimiento + (1 − g_f) · r_protección (supuestos de mercado forward-looking)."""
    return {f: g * esg["real_crecimiento"] + (1 - g) * esg["real_proteccion"]
            for f, g in gp["crecimiento_multifondos"].items()}


def factores_recentrado(R: np.ndarray, objetivo: dict, fondos) -> list[float]:
    """Factor mensual por fondo que lleva la media geométrica de los escenarios R al retorno objetivo
    (lo mismo que simular(objetivo=...) aplica internamente; se exporta para el simulador web)."""
    geo = np.exp(np.log1p(R).mean(axis=(0, 1)))
    return [float((1 + objetivo[f]) ** (1 / 12) / g) for f, g in zip(fondos, geo)]


def simular(m: pd.DataFrame, modelo: dict, meses: int, n: int, semilla: int = 0,
            regimen_inicial: int | None = None, ajuste_retorno_anual: float = 0.0,
            objetivo: dict | None = None) -> np.ndarray:
    """Devuelve un arreglo (n, meses, 5) de retornos reales mensuales simulados.
    `objetivo` (fondo -> retorno real anual) recentra cada fondo en ese retorno geométrico esperado,
    conservando volatilidad, colas, correlaciones y regímenes históricos (bootstrap con media ajustada)."""
    rng = np.random.default_rng(semilla)
    gamma = modelo["gamma"]
    etiqueta = gamma.argmax(1)
    pools = [np.flatnonzero(etiqueta == k) for k in range(modelo["K"])]
    A = modelo["A"]
    K = modelo["K"]
    s = np.full(n, etiqueta[-1] if regimen_inicial is None else regimen_inicial)
    X = m.values
    out = np.empty((n, meses, X.shape[1]))
    cum = np.cumsum(A, axis=1)
    for t in range(meses):
        for k in range(K):
            sel = np.flatnonzero(s == k)
            if len(sel):
                out[sel, t] = X[rng.choice(pools[k], size=len(sel))]
        u = rng.random(n)
        s = (u[:, None] > cum[s]).sum(1)
        s = np.minimum(s, K - 1)
    if objetivo is not None:
        # factor multiplicativo por fondo: media geométrica SIMULADA -> objetivo (la cadena de regímenes
        # no sortea los meses con su frecuencia histórica, así que se calibra sobre lo simulado)
        geo = np.exp(np.log1p(out).mean(axis=(0, 1)))
        meta = np.array([(1 + objetivo[c]) ** (1 / 12) for c in m.columns])
        out = (1 + out) * (meta / geo) - 1
    if ajuste_retorno_anual:
        # castigo multiplicativo uniforme: resta ~h puntos de rentabilidad anual a todos los fondos
        out = (1 + out) * (1 - ajuste_retorno_anual) ** (1 / 12) - 1
    return out
