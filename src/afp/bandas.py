"""Riesgo de bandas del nuevo esquema de premios y castigos (fondos generacionales).

Regla oficial (SP, sep-2026): cada mes se compara la rentabilidad de 36 meses móviles del
fondo contra su cartera de referencia; fuera de una banda de ±2,4% a ±2,9% anual, la AFP
recibe una retribución (arriba) o debe aportar recursos propios (abajo).

Proxy histórico: como la cartera de referencia oficial aún no tiene historia, cada AFP se
compara contra el promedio ponderado por afiliados de las DEMÁS AFP del mismo fondo
(leave-one-out). Mide cuánto se han desviado históricamente las AFP de sus pares.
"""
import numpy as np
import pandas as pd

from . import config


def retornos_mensuales_afp(df: pd.DataFrame) -> pd.DataFrame:
    d = df[(df.estado == "confirmado") & (df.fecha >= config.INICIO_MULTIFONDOS)].copy()
    d["mes"] = d.fecha.dt.to_period("M")
    d["lr"] = np.log1p(d["retorno_real_ajustado"].fillna(0))
    g = d.groupby(["fondo", "afp", "mes"]).agg(lr=("lr", "sum"), w=("n_afiliados", "last"),
                                               n_dias=("fecha", "size")).reset_index()
    g = g[g.n_dias >= 20]      # meses completos
    g["r"] = np.expm1(g["lr"])
    return g[["fondo", "afp", "mes", "r", "w"]]


def desviaciones(men: pd.DataFrame, ventana: int = config.BANDAS["ventana_meses"]) -> pd.DataFrame:
    out = []
    for fondo, gf in men.groupby("fondo"):
        piv_r = gf.pivot(index="mes", columns="afp", values="r")
        piv_w = gf.pivot(index="mes", columns="afp", values="w").where(piv_r.notna())
        tot_rw = (piv_r * piv_w).sum(1); tot_w = piv_w.sum(1)
        for afp in piv_r.columns:
            r = piv_r[afp]
            bench = (tot_rw - (r * piv_w[afp]).fillna(0)) / (tot_w - piv_w[afp].fillna(0))
            ok = r.notna() & bench.notna()
            r, bench = r[ok], bench[ok]
            if len(r) < ventana:
                continue
            ann = lambda s: np.exp(np.log1p(s).rolling(ventana).sum() * 12 / ventana) - 1
            dev = (ann(r) - ann(bench)).dropna()
            out.append(pd.DataFrame({"fondo": fondo, "afp": afp, "mes": dev.index, "desviacion": dev.values}))
    return pd.concat(out, ignore_index=True)


def frecuencia_fuera_banda(dev: pd.DataFrame, anchos=config.BANDAS["anchos_anuales"]) -> pd.DataFrame:
    filas = []
    for fondo, g in dev.groupby("fondo"):
        for b in anchos:
            filas.append({"fondo": fondo, "banda": b,
                          "pct_meses_sobre": (g.desviacion > b).mean(),
                          "pct_meses_bajo": (g.desviacion < -b).mean(),
                          "pct_meses_fuera": (g.desviacion.abs() > b).mean(),
                          "desv_p95_abs": g.desviacion.abs().quantile(0.95),
                          "n_afp_meses": len(g)})
    return pd.DataFrame(filas)
