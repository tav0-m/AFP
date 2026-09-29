"""Pensión total con la reforma (Ley N.º 21.735): de la pensión autofinanciada al monto que recibe la persona.

Capas, en el orden en que se suman:
  1. Autofinanciada con la cotización del trabajador (10%): el caso base del proyecto.
  2. + cotización del empleador a la cuenta individual (0,1% -> 6%, según fecha).
  3. + Cotización con Rentabilidad Protegida (bono en UF a la tasa de Tesorería, devuelto al pensionarse).
  4. + PGU desde los 65 años, focalizada según la pensión base (capas 1 a 3).

Todo en UF de hoy. Las capas 1 y 2 dependen del mercado (misma trayectoria de retornos y estrategia);
la 3 es determinística; la 4 compensa más a quien tiene menos pensión propia.
"""
import numpy as np
import pandas as pd

from . import config, mortalidad, simulacion


def tasa_vigente(calendario: list, fechas: np.ndarray) -> np.ndarray:
    """Tasa de cotización vigente en cada fecha decimal (año + (mes-1)/12) según un calendario escalonado."""
    hitos = np.array([a + (m - 1) / 12 for (a, m), _ in calendario])
    tasas = np.array([t for _, t in calendario])
    i = np.searchsorted(hitos, fechas, side="right") - 1
    return np.where(i >= 0, tasas[np.clip(i, 0, None)], 0.0)


def parametros_uf(r=config.REFORMA) -> dict:
    uf = r["uf_referencia"]
    return {"pgu": r["pgu_pesos"] / uf, "inferior": r["pension_inferior_pesos"] / uf,
            "superior": r["pension_superior_pesos"] / uf}


def pgu(pension_base: np.ndarray, r=config.REFORMA) -> np.ndarray:
    """PGU en UF: completa bajo la pensión inferior, decreciente lineal hasta cero en la superior."""
    p = parametros_uf(r)
    factor = np.clip((p["superior"] - pension_base) / (p["superior"] - p["inferior"]), 0, 1)
    return p["pgu"] * factor


def pension_total(R: np.ndarray, sexo: str, p=config.SIM, r=config.REFORMA, estrategias=None) -> pd.DataFrame:
    """Pensión por capa y estrategia para cada escenario. Devuelve un DataFrame largo (escenario x estrategia)."""
    edades, sueldo, aporte10, edad_retiro = simulacion.perfil(sexo, p)
    T = len(edades); R = R[:, :T]
    fechas = p["anio_inicio"] + np.arange(T) / 12
    base_cot = sueldo * p["densidad_cotizacion"]
    aporte_emp = base_cot * tasa_vigente(r["empleador_cci"], fechas)
    crp = base_cot * tasa_vigente(r["crp"], fechas)
    anio_retiro = p["anio_inicio"] + edad_retiro - p["edad_inicio"]
    factor = mortalidad.cnu(edad_retiro, sexo, anio_retiro)
    saldo_crp = float((crp * (1 + r["tasa_crp_real"]) ** ((T - np.arange(T)) / 12)).sum())
    W_todas = simulacion.estrategias(edades, sexo)
    nombres = estrategias or ["Por defecto (ley)", "Ciclo de vida (aprox. FG)"]
    filas = []
    for nombre in nombres:
        W = W_todas[nombre]
        p10 = simulacion.acumular(R, W, aporte10) / factor
        pemp = simulacion.acumular(R, W, aporte_emp) / factor        # lineal en aportes: capa separable
        pcrp = np.full(len(p10), saldo_crp / factor)
        base = p10 + pemp + pcrp
        filas.append(pd.DataFrame({"estrategia": nombre, "escenario": np.arange(len(p10)),
                                   "autofinanciada_10": p10, "empleador_cci": pemp, "crp": pcrp,
                                   "pgu": pgu(base, r), "sueldo_final": sueldo[-1]}))
    out = pd.concat(filas, ignore_index=True)
    out["total"] = out[["autofinanciada_10", "empleador_cci", "crp", "pgu"]].sum(1)
    out.attrs.update(tasa_empleador_promedio=float(aporte_emp.sum() / base_cot.sum()), edad_retiro=edad_retiro)
    return out


def resumen(pt: pd.DataFrame, meta: float = config.SIM["tasa_reemplazo_meta"]) -> pd.DataFrame:
    """Medianas por capa (acumuladas) y probabilidad de alcanzar la tasa de reemplazo meta."""
    filas = []
    for nombre, g in pt.groupby("estrategia", sort=False):
        sf = g.sueldo_final.iloc[0]
        acum = {"Solo 10% del trabajador": g.autofinanciada_10,
                "+ cotización del empleador": g.autofinanciada_10 + g.empleador_cci,
                "+ rentabilidad protegida": g.autofinanciada_10 + g.empleador_cci + g.crp,
                "+ PGU (pensión total)": g.total}
        for capa, v in acum.items():
            filas.append({"estrategia": nombre, "capa": capa, "p5": np.percentile(v, 5), "mediana": np.median(v),
                          "p95": np.percentile(v, 95), "tasa_reemplazo_mediana": np.median(v) / sf,
                          "prob_tr_meta": float((v / sf >= meta).mean())})
    return pd.DataFrame(filas)


def por_ingreso(R: np.ndarray, sexo: str = "H", sueldos=None, p=config.SIM, r=config.REFORMA,
                estrategia: str = "Por defecto (ley)") -> pd.DataFrame:
    """Mediana de cada capa según el nivel de sueldo: muestra la progresividad de la PGU."""
    filas = []
    for s in sueldos or r["sueldos_uf"]:
        pt = pension_total(R, sexo, dict(p, sueldo_inicial_uf=s), r, [estrategia])
        med = pt[["autofinanciada_10", "empleador_cci", "crp", "pgu", "total"]].median()
        # capas en la mediana del total (ordenadas por total) para que sumen exactamente
        fila_med = pt.iloc[(pt.total - med.total).abs().argsort().iloc[0]]
        filas.append({"sueldo_inicial_uf": s, "sueldo_final_uf": pt.sueldo_final.iloc[0],
                      **{c: fila_med[c] for c in ["autofinanciada_10", "empleador_cci", "crp", "pgu", "total"]},
                      "tasa_reemplazo_total": fila_med.total / pt.sueldo_final.iloc[0],
                      "tasa_reemplazo_10": fila_med.autofinanciada_10 / pt.sueldo_final.iloc[0]})
    return pd.DataFrame(filas)
