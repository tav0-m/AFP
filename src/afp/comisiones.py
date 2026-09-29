"""Comisiones por AFP: ¿cuánto cuesta en pensión y la compensa la rentabilidad?

En Chile la comisión se cobra sobre el sueldo imponible, no sobre el saldo, así que no descuenta la pensión: reduce
el sueldo líquido. Para ponerla en la misma unidad que la pensión, se pregunta cuánta pensión daría ese dinero si se
ahorrara en la cuenta. Como la pensión es lineal en los aportes, una comisión c equivale a c / 10% de la pensión que
financia la cotización del 10% del trabajador:
    costo en pensión (frente a la AFP más barata) = (c − c_min) / 10% × pensión autofinanciada.

Luego se calcula la rentabilidad extra anual que una AFP más cara necesitaría para compensar su comisión (punto de
equilibrio), y se compara con la rentabilidad relativa que efectivamente tuvo cada AFP frente a sus pares.
"""
import numpy as np
import pandas as pd

from . import config, simulacion


def alfa_por_afp(men: pd.DataFrame, desde: str | None = None) -> pd.DataFrame:
    """Rentabilidad real anual de cada AFP menos la del promedio ponderado de las demás (leave-one-out), por fondo,
    en los meses en que ambas existen. `men` = bandas.retornos_mensuales_afp."""
    d = men if desde is None else men[men.mes >= pd.Period(desde, "M")]
    filas = []
    for fondo, gf in d.groupby("fondo"):
        r = gf.pivot(index="mes", columns="afp", values="r")
        w = gf.pivot(index="mes", columns="afp", values="w").where(r.notna())
        tot_rw, tot_w = (r * w).sum(1), w.sum(1)
        for afp in r.columns:
            bench = (tot_rw - (r[afp] * w[afp]).fillna(0)) / (tot_w - w[afp].fillna(0))
            ok = r[afp].notna() & bench.notna()
            if ok.sum() < 24:
                continue
            ann = lambda s: np.exp(np.log1p(s[ok]).mean() * 12) - 1
            dif = np.log1p(r[afp][ok]) - np.log1p(bench[ok])
            te = float(dif.std() * np.sqrt(12))                       # tracking error anual frente a los pares
            filas.append({"afp": afp, "fondo": fondo, "meses": int(ok.sum()), "alfa_anual": ann(r[afp]) - ann(bench),
                          "tracking_error": te, "error_estandar": te / np.sqrt(ok.sum() / 12)})
    return pd.DataFrame(filas)


def punto_equilibrio(R: np.ndarray, delta_c: float, sexo: str = "H", p=config.SIM, tol: float = 1e-6) -> float:
    """Rentabilidad real extra anual (sobre todos los fondos) que hace que el 10% rinda la misma pensión mediana
    que cotizar 10% + delta_c sin rentabilidad extra (fondo por defecto)."""
    edades, _, aporte, retiro = simulacion.perfil(sexo, p)
    T = len(edades); R = R[:, :T]
    W = simulacion.pesos_defecto(edades, sexo)
    base = np.median(simulacion.acumular(R, W, aporte))
    meta = base * (1 + delta_c / p["tasa_cotizacion"])
    lo, hi = 0.0, 0.03
    while hi - lo > tol:
        x = (lo + hi) / 2
        Rx = (1 + R) * (1 + x) ** (1 / 12) - 1
        if np.median(simulacion.acumular(Rx, W, aporte)) < meta:
            lo = x
        else:
            hi = x
    return (lo + hi) / 2


def evaluar(men: pd.DataFrame, R: np.ndarray, pension_10_mediana: float, c=None, p=config.SIM) -> dict:
    c = c or config.COMISIONES
    tasas = pd.Series(c["tasas"], name="comision")
    c_min = tasas.min()
    edades, sueldo, _, _ = simulacion.perfil("H", p)
    base_cot = sueldo * p["densidad_cotizacion"]                         # UF cotizadas por mes (sueldo × densidad)
    a_todo = alfa_por_afp(men)
    a_comun = alfa_por_afp(men, c["desde_comun"])
    filas = []
    for afp, com in tasas.items():
        dc = com - c_min
        be = punto_equilibrio(R, dc, "H", p) if dc > 0 else 0.0
        fila = {"afp": afp.title().replace("Planvital", "PlanVital"), "comision": com,
                "comision_mensual_clp_sueldo_1m": com * 1_000_000,
                "comision_total_vida_uf": float((base_cot * com).sum()),
                "costo_pension_uf_vs_mas_barata": dc / p["tasa_cotizacion"] * pension_10_mediana,
                "costo_pension_pct_vs_mas_barata": dc / p["tasa_cotizacion"],
                "rentabilidad_extra_para_compensar": be}
        for nombre, a in (("historico", a_todo), ("comun", a_comun)):
            s = a[a.afp == afp]
            fila[f"alfa_{nombre}"] = s.alfa_anual.mean() if len(s) else np.nan
            fila[f"meses_{nombre}"] = int(s.meses.max()) if len(s) else 0
            # error estándar del promedio de 5 fondos muy correlacionados: se usa el promedio de los errores (conservador)
            fila[f"ee_alfa_{nombre}"] = s.error_estandar.mean() if len(s) else np.nan
        filas.append(fila)
    tab = pd.DataFrame(filas).sort_values("comision", ignore_index=True)
    tab["alfa_menos_equilibrio"] = tab.alfa_comun - tab.rentabilidad_extra_para_compensar
    tab["t_vs_equilibrio"] = tab.alfa_menos_equilibrio / tab.ee_alfa_comun
    corr = float(np.corrcoef(tab.comision, tab.alfa_comun)[0, 1])
    return {"tabla": tab, "alfa_fondo": a_comun.assign(ventana=c["desde_comun"]), "corr_comision_alfa": corr}
