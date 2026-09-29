"""¿Es óptimo el glidepath oficial? Búsqueda del glidepath que maximiza la utilidad esperada de la pensión total.

Familia de trayectorias (participación en activos de crecimiento por edad):
    g(edad) = g0                                  si edad <= a1
            = g0 + (g1 − g0)·(edad − a1)/(retiro − a1)   hasta el retiro
Se replica con multifondos igual que el glidepath oficial (config.GLIDEPATH), extrapolando sobre el Fondo A.

Criterio: utilidad CRRA de la pensión total mensual (autofinanciada con cotización del trabajador y del empleador,
+ rentabilidad protegida + PGU), resumida como equivalente cierto: la pensión segura que deja igual de bien que
la lotería de pensiones. Aversión al riesgo gamma = 3 (base); sensibilidad 2 y 5.

Para no sobreajustar, la grilla se evalúa sobre escenarios de "entrenamiento" y el ganador se reporta sobre
escenarios independientes de "prueba" (otra semilla).
"""
import itertools

import numpy as np
import pandas as pd

from . import config, mortalidad, reforma, simulacion

GRILLA = {"g0": [0.6, 0.7, 0.8, 0.9, 0.95, 1.0], "a1": [30, 35, 40, 45, 50, 55],
          "g1": [0.08, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]}


def equivalente_cierto(x: np.ndarray, gamma: float) -> float:
    x = np.maximum(np.asarray(x, float), 1e-9)
    if abs(gamma - 1) < 1e-12:
        return float(np.exp(np.log(x).mean()))
    return float(np.mean(x ** (1 - gamma)) ** (1 / (1 - gamma)))


def crecimiento_parametrico(edades: np.ndarray, g0: float, a1: float, g1: float, retiro: int) -> np.ndarray:
    frac = np.clip((edades - a1) / max(retiro - a1, 1e-9), 0, 1)
    return g0 + (g1 - g0) * frac


class Evaluador:
    """Precalcula aportes y factores para evaluar muchos glidepaths sobre las mismas trayectorias."""

    def __init__(self, R: np.ndarray, sexo: str, p=config.SIM, r=config.REFORMA, con_reforma: bool = True):
        self.edades, sueldo, aporte10, self.retiro = simulacion.perfil(sexo, p)
        T = len(self.edades); self.R = R[:, :T]; self.sexo = sexo; self.r = r
        fechas = p["anio_inicio"] + np.arange(T) / 12
        base_cot = sueldo * p["densidad_cotizacion"]
        emp = base_cot * reforma.tasa_vigente(r["empleador_cci"], fechas) if con_reforma else 0 * base_cot
        crp = base_cot * reforma.tasa_vigente(r["crp"], fechas) if con_reforma else 0 * base_cot
        self.aporte = aporte10 + emp
        self.factor = mortalidad.cnu(self.retiro, sexo, p["anio_inicio"] + self.retiro - p["edad_inicio"])
        self.pension_crp = float((crp * (1 + r["tasa_crp_real"]) ** ((T - np.arange(T)) / 12)).sum()) / self.factor
        self.con_reforma = con_reforma
        self.sueldo_final = sueldo[-1]

    def pension(self, W: np.ndarray) -> np.ndarray:
        base = simulacion.acumular(self.R, W, self.aporte) / self.factor + self.pension_crp
        return base + reforma.pgu(base, self.r) if self.con_reforma else base

    def pension_glidepath(self, g: np.ndarray) -> np.ndarray:
        return self.pension(simulacion.pesos_desde_crecimiento(g))


def buscar(R_ent: np.ndarray, R_prueba: np.ndarray, sexo: str = "H", gamma: float = 3.0, p=config.SIM,
           con_reforma: bool = True, grilla=GRILLA) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Grilla sobre entrenamiento; comparación final (oficial, ley, mejor) sobre prueba."""
    ent = Evaluador(R_ent, sexo, p, con_reforma=con_reforma)
    filas = []
    for g0, a1, g1 in itertools.product(grilla["g0"], grilla["a1"], grilla["g1"]):
        if g1 > g0:
            continue
        x = ent.pension_glidepath(crecimiento_parametrico(ent.edades, g0, a1, g1, ent.retiro))
        filas.append({"g0": g0, "a1": a1, "g1": g1, "equivalente_cierto": equivalente_cierto(x, gamma),
                      "mediana": float(np.median(x)), "p5": float(np.percentile(x, 5))})
    tabla = pd.DataFrame(filas).sort_values("equivalente_cierto", ascending=False, ignore_index=True)
    mejor = tabla.iloc[0]
    pr = Evaluador(R_prueba, sexo, p, con_reforma=con_reforma)
    candidatos = {
        "Óptimo de la familia": pr.pension_glidepath(crecimiento_parametrico(pr.edades, mejor.g0, mejor.a1, mejor.g1, pr.retiro)),
        "Glidepath oficial (FG)": pr.pension(simulacion.pesos_ciclo_vida(pr.edades)),
        "Por defecto (ley)": pr.pension(simulacion.pesos_defecto(pr.edades, sexo)),
        "Fondo A fijo": pr.pension(simulacion.pesos_fijo("A", pr.edades)),
        "Fondo C fijo": pr.pension(simulacion.pesos_fijo("C", pr.edades)),
        "Fondo E fijo": pr.pension(simulacion.pesos_fijo("E", pr.edades)),
    }
    comp = pd.DataFrame([{"estrategia": k, "equivalente_cierto": equivalente_cierto(v, gamma),
                          "mediana": float(np.median(v)), "p5": float(np.percentile(v, 5)),
                          "tasa_reemplazo_mediana": float(np.median(v) / pr.sueldo_final)} for k, v in candidatos.items()])
    ref = comp.set_index("estrategia").loc["Glidepath oficial (FG)", "equivalente_cierto"]
    comp["ec_vs_oficial"] = comp.equivalente_cierto / ref - 1
    comp.attrs.update(g0=float(mejor.g0), a1=float(mejor.a1), g1=float(mejor.g1), gamma=gamma, sexo=sexo,
                      con_reforma=con_reforma)
    return tabla, comp


def _caso(tarea):
    m, modelo, objetivo, n, semillas, sexo, gamma, con_reforma = tarea
    from . import escenarios
    R_ent, R_prueba = (escenarios.simular(m, modelo, meses=480, n=n, semilla=s, objetivo=objetivo) for s in semillas)
    _, comp = buscar(R_ent, R_prueba, sexo, gamma, con_reforma=con_reforma)
    c = comp.set_index("estrategia")
    return {"sexo": sexo, "gamma": gamma, "con_reforma": con_reforma, **{k: comp.attrs[k] for k in ("g0", "a1", "g1")},
            "ec_oficial": c.loc["Glidepath oficial (FG)", "equivalente_cierto"],
            "ec_optimo": c.loc["Óptimo de la familia", "equivalente_cierto"],
            "ec_defecto": c.loc["Por defecto (ley)", "equivalente_cierto"],
            "optimo_vs_oficial": c.loc["Óptimo de la familia", "ec_vs_oficial"],
            "defecto_vs_oficial": c.loc["Por defecto (ley)", "ec_vs_oficial"]},         comp.assign(sexo=sexo, gamma=gamma, con_reforma=con_reforma)


def evaluar(m: pd.DataFrame, modelo: dict, objetivo: dict | None, n: int = 5000, semillas=(101, 202),
            gammas=(2.0, 3.0, 5.0), procesos: int = 1):
    """Óptimo por aversión al riesgo, con y sin la reforma (hombre). Cada proceso regenera sus escenarios
    (entrenamiento y prueba) desde las semillas. Devuelve (resumen, comparaciones)."""
    from .incertidumbre import _mapear
    tareas = [(m, modelo, objetivo, n, semillas, "H", g, ref) for ref in (True, False) for g in gammas]
    res = _mapear(_caso, tareas, procesos)
    return pd.DataFrame([r[0] for r in res]), pd.concat([r[1] for r in res], ignore_index=True)
