"""Análisis de robustez: ¿las conclusiones del Monte Carlo sobreviven a otros supuestos?

Para cada caso de config.ROBUSTEZ se vuelve a simular con los MISMOS escenarios de mercado
(misma semilla) salvo que el caso cambie el generador. Como todas las estrategias se evalúan
sobre las mismas trayectorias, además de comparar percentiles se mide la probabilidad
"camino a camino" de que una estrategia supere a otra.

Nota: la densidad de cotización y el nivel del sueldo NO cambian el ranking (la pensión es
lineal en los aportes cuando el saldo inicial es cero), por eso no se incluyen en la grilla.
"""
import numpy as np
import pandas as pd

from . import config, escenarios, simulacion

DEF, CV, RE = "Por defecto (ley)", "Ciclo de vida (aprox. FG)", "Reactivo (market timing)"


def evaluar(m: pd.DataFrame, modelo: dict, casos=config.ROBUSTEZ, n: int | None = None) -> pd.DataFrame:
    n = n or config.SIM["n_simulaciones"]
    cache = {}
    filas = []
    for nombre, cambios_sim, cambios_esc, cambios_re, sexo in casos:
        if cambios_esc.get("regimen_inicial", 0) >= modelo["K"]:
            continue    # el caso pide un régimen que el modelo elegido no tiene
        cambios_sim = dict(cambios_sim)
        gp = {**config.GLIDEPATH, **cambios_sim.pop("glidepath", {})}
        p = {**config.SIM, **cambios_sim}
        clave = tuple(sorted(cambios_esc.items()))
        if clave not in cache:
            cache[clave] = escenarios.simular(m[config.FONDOS], modelo, meses=480, n=n,
                                              semilla=config.SIM["semilla"], **cambios_esc)
        reg = {**config.REACTIVO, **cambios_re}
        tab, pens = simulacion.simular_estrategias(cache[clave], sexo, p, reactivo=reg, glidepath=gp)
        t = tab.set_index("estrategia")
        filas.append({
            "caso": nombre,
            "cv_vs_defecto_mediana": t.loc[CV, "mediana"] / t.loc[DEF, "mediana"] - 1,
            "cv_vs_defecto_p5": t.loc[CV, "p5"] / t.loc[DEF, "p5"] - 1,
            "prob_cv_supera_defecto": float((pens[CV] > pens[DEF]).mean()),
            "reactivo_vs_defecto_mediana": t.loc[RE, "mediana"] / t.loc[DEF, "mediana"] - 1,
            "reactivo_vs_defecto_p5": t.loc[RE, "p5"] / t.loc[DEF, "p5"] - 1,
            "prob_reactivo_pierde": float((pens[RE] < pens[DEF]).mean()),
            "mediana_defecto_uf": t.loc[DEF, "mediana"],
            "traspasos_reactivo": tab.attrs["cambios_reactivo_mediana"],
        })
    return pd.DataFrame(filas)


def evaluar_esg(m: pd.DataFrame, modelo: dict, casos=config.ESG, n: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pensión por estrategia bajo cada juego de supuestos de mercado (mismos escenarios, medias recentradas)."""
    n = n or config.SIM["n_simulaciones"]
    filas, pensiones = [], []
    for nombre, esg in casos.items():
        obj = escenarios.retornos_objetivo(esg, config.GLIDEPATH) if esg else None
        R = escenarios.simular(m[config.FONDOS], modelo, meses=480, n=n, semilla=config.SIM["semilla"], objetivo=obj)
        for sexo in ("H", "M"):
            tab, pens = simulacion.simular_estrategias(R, sexo)
            t = tab.set_index("estrategia")
            filas.append({"escenario": nombre, "sexo": sexo,
                          "retorno_real_A": obj["A"] if obj else np.nan, "retorno_real_E": obj["E"] if obj else np.nan,
                          "cv_vs_defecto_mediana": t.loc[CV, "mediana"] / t.loc[DEF, "mediana"] - 1,
                          "cv_vs_defecto_p5": t.loc[CV, "p5"] / t.loc[DEF, "p5"] - 1,
                          "prob_cv_supera_defecto": float((pens[CV] > pens[DEF]).mean()),
                          "reactivo_vs_defecto_mediana": t.loc[RE, "mediana"] / t.loc[DEF, "mediana"] - 1,
                          "mediana_defecto_uf": t.loc[DEF, "mediana"], "mediana_cv_uf": t.loc[CV, "mediana"],
                          "prob_tr_meta_defecto": t.loc[DEF, "prob_tr_meta"], "prob_tr_meta_cv": t.loc[CV, "prob_tr_meta"]})
            pensiones.append(tab.assign(escenario=nombre))
    return pd.DataFrame(filas), pd.concat(pensiones, ignore_index=True)
