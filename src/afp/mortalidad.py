"""Tablas de mortalidad CB-H-2020 / RV-M-2020 (CMF-SP, NCG 495) y motor saldo -> pensión.

qx(edad, año) = qx_2020(edad) * prod_{t=2021..año} (1 - AA_{x,t})
Desde 2036 el factor AA se mantiene constante y sigue aplicándose (nota oficial de la tabla).
"""
from functools import lru_cache

import numpy as np

from . import config


def _extraer(ws, col_edad=12, col_qx=13, col_f=14, n_f=16):
    tabla = {}
    for row in ws.iter_rows(min_row=4, values_only=True):
        edad, q = row[col_edad], row[col_qx]
        if not isinstance(edad, (int, float)) or q is None:
            continue    # notas al pie
        tabla[int(edad)] = (float(q), [float(x) for x in row[col_f:col_f + n_f] if x is not None])
    return tabla


@lru_cache(maxsize=1)
def tablas(path=None) -> dict:
    import openpyxl
    wb = openpyxl.load_workbook(path or config.DATA_RAW / "tablas_mortalidad_cmf.xlsx", data_only=True)
    return {"H": _extraer(wb["Vejez-Hombres"]), "M": _extraer(wb["Vejez-Mujeres"])}


def qx(edad: int, anio: int, sexo: str) -> float:
    t = tablas()[sexo]
    if edad not in t:
        if edad > max(t):
            return 1.0
        edad = min(t)
    q0, fac = t[edad]
    n = max(anio - 2020, 0)
    if n == 0:
        return min(q0, 1.0)
    # factores 2021..2036 y luego el de 2036 constante
    prod = np.prod([1 - fac[min(i, len(fac) - 1)] for i in range(n)])
    return float(min(max(q0 * prod, 0.0), 1.0))


@lru_cache(maxsize=4096)
def cnu(edad: int, sexo: str, anio: int, tasa: float = config.TITRP) -> float:
    """Capital Necesario Unitario: VP de 1 UF mensual vitalicia, pago anticipado mensual.
    Simplificación: sin beneficiarios de sobrevivencia."""
    i_m = (1 + tasa) ** (1 / 12) - 1
    s, valor, k = 1.0, 0.0, 0
    for x in range(edad, config.EDAD_MAX_TABLA + 1):
        q_m = 1 - (1 - qx(x, anio + x - edad, sexo)) ** (1 / 12)
        for _ in range(12):
            valor += s / (1 + i_m) ** k
            s *= 1 - q_m
            k += 1
    return valor


def esperanza_vida(edad: int, sexo: str, anio: int) -> float:
    s, e = 1.0, 0.0
    for x in range(edad, config.EDAD_MAX_TABLA + 1):
        s *= 1 - qx(x, anio + x - edad, sexo)
        e += s
    return e + 0.5


def pension_mensual(saldo_uf: float, edad: int, sexo: str, anio: int, tasa: float = config.TITRP) -> float:
    return saldo_uf / cnu(edad, sexo, anio, tasa)


def matriz_qx(sexo: str, anios=range(2026, 2101)) -> tuple[list, list, np.ndarray]:
    """Matriz edad x año (para el simulador web y el Excel)."""
    edades = sorted(tablas()[sexo])
    M = np.array([[qx(e, a, sexo) for a in anios] for e in edades])
    return edades, list(anios), M
