"""Etapa 4 - Simulación de la vida laboral y comparación de estrategias de inversión.

Estrategias:
  * Fondo fijo A..E toda la vida.
  * Por defecto (ley de multifondos): B hasta 35, C hasta 55 (H) / 50 (M), luego D.
  * Ciclo de vida (aprox. fondos generacionales): sigue el límite oficial de activos de crecimiento por
    edad (config.GLIDEPATH), replicado con la combinación de multifondos de igual exposición.
  * Reactivo (market timing): parte en el por defecto; tras una caída fuerte se cambia al E
    con un mes de desfase y vuelve solo cuando el mercado ya se recuperó.
"""
import numpy as np
import pandas as pd

from . import config, mortalidad

FONDOS = config.FONDOS


def pesos_fijo(fondo: str, edades: np.ndarray) -> np.ndarray:
    W = np.zeros((len(edades), 5)); W[:, FONDOS.index(fondo)] = 1; return W


def pesos_defecto(edades: np.ndarray, sexo: str) -> np.ndarray:
    corte = 55 if sexo == "H" else 50
    idx = np.where(edades <= 35, 1, np.where(edades <= corte, 2, 3))   # B, C, D
    W = np.zeros((len(edades), 5)); W[np.arange(len(edades)), idx] = 1; return W


def crecimiento_glidepath(edades: np.ndarray, gp=config.GLIDEPATH) -> np.ndarray:
    """Límite máximo de activos de crecimiento por edad (trayectoria oficial de los FG)."""
    cc = gp["curva_consulta"]
    g_c = np.asarray(cc["crecimiento"])
    eje = cc["edad_inicial"] + np.arange(len(g_c))
    g = np.interp(edades, eje, g_c)
    # reescala la meseta y la bajada al tope definitivo, manteniendo el piso (edad en que la curva toca su mínimo)
    piso, tope_c = g_c.min(), g_c.max()
    edad_piso = eje[g_c.argmin()]
    antes = np.asarray(edades) <= edad_piso
    g[antes] = piso + (g[antes] - piso) * (gp["tope_inicial"] - piso) / (tope_c - piso)
    return g


def pesos_desde_crecimiento(g: np.ndarray, gp=config.GLIDEPATH) -> np.ndarray:
    """Participación de crecimiento -> pesos en multifondos (T, 5). Pueden ser negativos si se extrapola."""
    gm = np.array([gp["crecimiento_multifondos"][f] for f in FONDOS])   # decreciente de A a E
    g = np.clip(g, gm[-1], None if gp["extrapolar"] else gm[0])
    W = np.zeros((len(g), 5))
    for t, x in enumerate(g):
        if x >= gm[0]:                       # sobre el Fondo A: recta A–E
            i, j = 0, 4
        else:                                # fondos vecinos que encierran x
            i = min(int(np.searchsorted(-gm, -x, side="right")) - 1, 3); j = i + 1
        w_i = (x - gm[j]) / (gm[i] - gm[j])
        W[t, i] += w_i; W[t, j] += 1 - w_i
    return W


def pesos_ciclo_vida(edades: np.ndarray, gp=config.GLIDEPATH) -> np.ndarray:
    return pesos_desde_crecimiento(crecimiento_glidepath(edades, gp), gp)


def perfil(sexo: str, p=config.SIM, edad_retiro: int | None = None):
    edad_retiro = edad_retiro or config.EDAD_LEGAL[sexo]
    T = (edad_retiro - p["edad_inicio"]) * 12
    edades = p["edad_inicio"] + np.arange(T) // 12
    anios_sueldo = np.minimum(edades, p["edad_fin_crecimiento"]) - p["edad_inicio"]
    sueldo = p["sueldo_inicial_uf"] * (1 + p["crecimiento_real_sueldo"]) ** anios_sueldo
    aporte = sueldo * p["tasa_cotizacion"] * p["densidad_cotizacion"]
    return edades, sueldo, aporte, edad_retiro


def acumular(R: np.ndarray, W: np.ndarray, aporte: np.ndarray) -> np.ndarray:
    """R: (n, T, 5) retornos; W: (T, 5) pesos; aporte: (T,). Saldo final (n,)."""
    rp = np.einsum("ntf,tf->nt", R, W)
    S = np.zeros(R.shape[0])
    for t in range(R.shape[1]):
        S = (S + aporte[t]) * (1 + rp[:, t])
    return S


def acumular_reactivo(R: np.ndarray, W_base: np.ndarray, aporte: np.ndarray,
                      reg=config.REACTIVO) -> tuple[np.ndarray, np.ndarray]:
    n, T, _ = R.shape
    iE, iA = FONDOS.index("E"), FONDOS.index("A")
    en_E = np.zeros(n, bool); meses_E = np.zeros(n, int)
    pendiente = np.zeros(n, int)            # 0 nada, 1 ir a E, 2 volver
    espera = np.zeros(n, int)
    hist_p = np.zeros((n, 3)); hist_a = np.zeros((n, 3))
    S = np.zeros(n); cambios = np.zeros(n, int)
    for t in range(T):
        # ejecutar traspasos pendientes cuyo desfase venció
        listo = (pendiente > 0) & (espera == 0)
        ir = listo & (pendiente == 1); volver = listo & (pendiente == 2)
        en_E[ir] = True; meses_E[ir] = 0; en_E[volver] = False
        cambios += listo; pendiente[listo] = 0
        espera = np.maximum(espera - 1, 0)
        r_base = R[:, t] @ W_base[t]
        r = np.where(en_E, R[:, t, iE], r_base)
        S = (S + aporte[t]) * (1 + r)
        hist_p = np.column_stack([hist_p[:, 1:], r]); hist_a = np.column_stack([hist_a[:, 1:], R[:, t, iA]])
        meses_E += en_E
        if t >= 2:
            caida = (np.prod(1 + hist_p, 1) - 1) < reg["umbral_caida_3m"]
            recup = (np.prod(1 + hist_a, 1) - 1) > reg["umbral_recuperacion_3m"]
            nueva_ida = ~en_E & (pendiente == 0) & caida
            nueva_vuelta = en_E & (pendiente == 0) & (meses_E >= reg["meses_minimos_en_E"]) & recup
            pendiente[nueva_ida] = 1; pendiente[nueva_vuelta] = 2
            espera[nueva_ida | nueva_vuelta] = reg["desfase_meses"]
    return S, cambios


def estrategias(edades, sexo, gp=config.GLIDEPATH) -> dict:
    d = {f"Fondo {f} fijo": pesos_fijo(f, edades) for f in FONDOS}
    d["Por defecto (ley)"] = pesos_defecto(edades, sexo)
    d["Ciclo de vida (aprox. FG)"] = pesos_ciclo_vida(edades, gp)
    return d


def simular_estrategias(R: np.ndarray, sexo: str, p=config.SIM, edad_retiro=None,
                        reactivo=None, glidepath=None) -> pd.DataFrame:
    edades, sueldo, aporte, edad_retiro = perfil(sexo, p, edad_retiro)
    R = R[:, :len(edades)]
    anio_retiro = p["anio_inicio"] + edad_retiro - p["edad_inicio"]
    factor = mortalidad.cnu(edad_retiro, sexo, anio_retiro)
    res = {}
    for nombre, W in estrategias(edades, sexo, glidepath or config.GLIDEPATH).items():
        res[nombre] = acumular(R, W, aporte) / factor
    S, cambios = acumular_reactivo(R, pesos_defecto(edades, sexo), aporte, reactivo or config.REACTIVO)
    res["Reactivo (market timing)"] = S / factor
    pens = pd.DataFrame(res)
    tr = pens / sueldo[-1]
    filas = []
    for c in pens:
        x = pens[c].values
        filas.append({"estrategia": c, "sexo": sexo,
                      "p5": np.percentile(x, 5), "p25": np.percentile(x, 25), "mediana": np.median(x),
                      "p75": np.percentile(x, 75), "p95": np.percentile(x, 95), "media": x.mean(),
                      "cvar5": x[x <= np.percentile(x, 5)].mean(),
                      "tasa_reemplazo_mediana": np.median(tr[c]),
                      "prob_tr_meta": (tr[c] >= p["tasa_reemplazo_meta"]).mean()})
    out = pd.DataFrame(filas)
    out.attrs.update(cnu=factor, anio_retiro=anio_retiro, sueldo_final=sueldo[-1],
                     cambios_reactivo_mediana=float(np.median(cambios)))
    return out, pens


def backtest_historico(m: pd.DataFrame, sexo="H", p=config.SIM) -> pd.DataFrame:
    """Evaluación retrospectiva: un afiliado que cotizó en la historia real (sep-2002 a ago-2026)
    y se pensionó a la edad legal en 2026."""
    T = len(m); edad_retiro = config.EDAD_LEGAL[sexo]
    edad_ini = edad_retiro - T // 12
    q = dict(p, edad_inicio=edad_ini)
    edades = edad_ini + np.arange(T) // 12
    anios = np.minimum(edades, q["edad_fin_crecimiento"]) - 25
    sueldo = q["sueldo_inicial_uf"] * (1 + q["crecimiento_real_sueldo"]) ** anios
    aporte = sueldo * q["tasa_cotizacion"] * q["densidad_cotizacion"]
    R = m[FONDOS].values[None, :, :]
    factor = mortalidad.cnu(edad_retiro, sexo, 2026)
    filas = []
    for nombre, W in estrategias(edades, sexo).items():
        S = acumular(R, W, aporte)[0]
        filas.append((nombre, S, S / factor, 0))
    S, c = acumular_reactivo(R, pesos_defecto(edades, sexo), aporte)
    filas.append(("Reactivo (market timing)", S[0], S[0] / factor, int(c[0])))
    out = pd.DataFrame(filas, columns=["estrategia", "saldo_final_uf", "pension_mensual_uf", "n_traspasos"])
    base = out.set_index("estrategia").loc["Por defecto (ley)", "pension_mensual_uf"]
    out["vs_defecto"] = out["pension_mensual_uf"] / base - 1
    out.attrs.update(edad_inicio=edad_ini, aporte_total_uf=aporte.sum())
    return out
