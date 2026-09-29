"""Microsimulación poblacional: pensiones de una cohorte heterogénea (ingreso, densidad, lagunas, sexo).

Diferencias con el afiliado tipo del Monte Carlo base:
* Cada persona tiene su propio ingreso (lognormal por sexo) y su propia densidad de cotización (Beta, correlacionada
  con el ingreso), y cotiza en RACHAS de empleo formal (cadena de Markov). No es lo mismo cotizar a los 25 que a los 60.
* Toda la cohorte enfrenta los MISMOS escenarios de mercado, porque el mercado es común a una generación.

Cálculo: el saldo es lineal en los aportes. Para una estrategia W y un escenario s, el factor de crecimiento de un aporte
del mes t hasta el retiro es G[s, t] = Π_{u>=t} (1 + r_s,u · W_u). El saldo de todas las personas en todos los escenarios
es entonces A @ G.T (personas x escenarios), con A la matriz de aportes: una multiplicación de matrices en vez de un
bucle por persona.
"""
import numpy as np
import pandas as pd
from scipy.stats import beta as dist_beta, norm

from . import config, mortalidad, reforma, simulacion

def generar_poblacion(n: int, rng: np.random.Generator, c=config.MICROSIM, sexo: str | None = None) -> pd.DataFrame:
    """Personas con sexo, sueldo de referencia (UF, a los 40 años) y densidad de cotización."""
    sx = np.full(n, sexo) if sexo else np.where(rng.random(n) < c["prop_mujeres"], "M", "H")
    z = rng.standard_normal((n, 2))
    z2 = c["rho_ingreso_densidad"] * z[:, 0] + np.sqrt(1 - c["rho_ingreso_densidad"] ** 2) * z[:, 1]
    sueldo = np.empty(n); dens = np.empty(n)
    for s in ("H", "M"):
        k = sx == s
        med, media = c["ingreso"][s]["mediana"] / c["uf_ingresos"], c["ingreso"][s]["media"] / c["uf_ingresos"]
        sigma = np.sqrt(2 * np.log(media / med))
        sueldo[k] = med * np.exp(sigma * z[k, 0])
        mu, kappa = c["densidad"][s], c["concentracion_densidad"]
        dens[k] = dist_beta.ppf(norm.cdf(z2[k]), mu * kappa, (1 - mu) * kappa)
    sueldo = np.clip(sueldo, c["piso_ingreso_uf"], c["tope_imponible_uf"])
    return pd.DataFrame({"sexo": sx, "sueldo_ref_uf": sueldo, "densidad": np.clip(dens, 0.01, 0.99)})


def rachas_formales(densidad: np.ndarray, T: int, racha: float, rng: np.random.Generator) -> np.ndarray:
    """Matriz (n, T) de meses cotizados: cadena de Markov de 2 estados con estacionaria = densidad."""
    salir = 1 / racha
    entrar = np.clip(densidad / (1 - densidad) * salir, 0, 1)
    estado = rng.random(len(densidad)) < densidad
    out = np.empty((len(densidad), T), bool)
    u = rng.random((len(densidad), T))
    for t in range(T):
        out[:, t] = estado
        estado = np.where(estado, u[:, t] >= salir, u[:, t] < entrar)
    return out


def factores_crecimiento(R: np.ndarray, W: np.ndarray) -> np.ndarray:
    """G[s, t] = producto de (1 + retorno de la cartera) desde el mes t hasta el retiro (incluido)."""
    rp = np.einsum("stf,tf->st", R, W)
    return np.ascontiguousarray(np.cumprod((1 + rp)[:, ::-1], axis=1)[:, ::-1])      # contiguo: matmul con BLAS


def simular_sexo(pob: pd.DataFrame, R: np.ndarray, sexo: str, rng, p=config.SIM, r=config.REFORMA,
                 c=config.MICROSIM, sin_empleador: bool = False, edad_retiro: int | None = None,
                 sexo_mortalidad: str | None = None, umbral_pgu: float = np.inf) -> dict:
    """Pensiones (personas x escenarios) por capa y estrategia para las personas de un sexo.
    `umbral_pgu`: sueldo de referencia sobre el cual no hay PGU (focalización, calculado en toda la población)."""
    edades, perfil_sueldo, _, retiro = simulacion.perfil(sexo, dict(p, sueldo_inicial_uf=1.0), edad_retiro)
    T = len(edades); R = R[:, :T]
    i_ref = min((c["edad_ingreso_referencia"] - p["edad_inicio"]) * 12, T - 1)      # mes de la edad de referencia
    perfil_sueldo = perfil_sueldo / perfil_sueldo[i_ref]
    sueldos = np.minimum(pob.sueldo_ref_uf.values[:, None] * perfil_sueldo[None], c["tope_imponible_uf"])   # (n, T)
    formal = rachas_formales(pob.densidad.values, T, c["racha_formal_meses"], rng)
    base = sueldos * formal
    fechas = p["anio_inicio"] + np.arange(T) / 12
    t_emp = 0 * fechas if sin_empleador else reforma.tasa_vigente(r["empleador_cci"], fechas)
    t_crp = 0 * fechas if sin_empleador else reforma.tasa_vigente(r["crp"], fechas)
    anio_retiro = p["anio_inicio"] + retiro - p["edad_inicio"]
    cnu = mortalidad.cnu(retiro, sexo_mortalidad or sexo, anio_retiro)
    crp = (base * t_crp) @ ((1 + r["tasa_crp_real"]) ** ((T - np.arange(T)) / 12)) / cnu            # (n,)
    elegible = pob.sueldo_ref_uf.values <= umbral_pgu
    out = {"sueldo_final": sueldos[:, -1], "densidad_realizada": formal.mean(1), "retiro": retiro}
    for nombre in ("Por defecto (ley)", "Ciclo de vida (aprox. FG)"):
        W = simulacion.estrategias(edades, sexo)[nombre]
        G = factores_crecimiento(R, W)                                                       # (S, T)
        p10 = (base * p["tasa_cotizacion"]) @ G.T / cnu                                       # (n, S)
        pemp = (base * t_emp) @ G.T / cnu
        propia = p10 + pemp + crp[:, None]
        pg = reforma.pgu(propia, r) * elegible[:, None]
        out[nombre] = {"p10": p10, "emp": pemp, "crp": crp, "pgu": pg, "total": propia + pg}
    return out


def resumir(pob: pd.DataFrame, res: dict, meta: float = config.SIM["tasa_reemplazo_meta"]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Resumen por sexo y por quintil de ingreso (dentro de cada sexo). Las métricas por persona usan la mediana
    sobre escenarios; las de población, el conjunto persona x escenario."""
    DEF, CV = "Por defecto (ley)", "Ciclo de vida (aprox. FG)"
    filas_sexo, filas_q = [], []
    for sexo, o in res.items():
        pb = pob[pob.sexo == sexo].reset_index(drop=True)
        sf = np.maximum(o["sueldo_final"], 1e-9)[:, None]
        d, cv = o[DEF], o[CV]
        tr_tot, tr10 = d["total"] / sf, d["p10"] / sf
        con = (d["total"] > 0).all(axis=1)                   # personas con pensión positiva en todo escenario
        ganancia = np.full(len(pb), np.nan)
        ganancia[con] = np.median(cv["total"][con] / d["total"][con], axis=1) - 1          # por persona
        filas_sexo.append({"sexo": sexo, "personas": len(pb), "densidad_media": o["densidad_realizada"].mean(),
                           "sueldo_ref_mediano_uf": pb.sueldo_ref_uf.median(),
                           "pension_10_mediana": np.median(d["p10"]), "pension_total_mediana": np.median(d["total"]),
                           "tr_10_mediana": np.median(tr10), "tr_total_mediana": np.median(tr_tot),
                           "prob_tr_meta_10": float((tr10 >= meta).mean()), "prob_tr_meta_total": float((tr_tot >= meta).mean()),
                           "pct_pgu_mayor_mitad": float((d["pgu"] > 0.5 * d["total"]).mean()),
                           "cv_vs_defecto_mediana": float(np.nanmedian(ganancia)),
                           "pct_personas_cv_gana": float(np.nanmean(ganancia > 0)),
                           "pct_sin_pension": float(1 - con.mean())})
        q = pd.qcut(pb.sueldo_ref_uf, 5, labels=[1, 2, 3, 4, 5])
        for k in range(1, 6):
            m = (q == k).values
            filas_q.append({"sexo": sexo, "quintil": k, "sueldo_ref_mediano_uf": pb.sueldo_ref_uf[m].median(),
                            "tr_10_mediana": np.median(tr10[m]), "tr_total_mediana": np.median(tr_tot[m]),
                            "prob_tr_meta_total": float((tr_tot[m] >= meta).mean()),
                            "pgu_mediana": np.median(d["pgu"][m]), "pension_total_mediana": np.median(d["total"][m]),
                            "cv_vs_defecto_total": float(np.nanmedian(ganancia[m])),
                            "cv_vs_defecto_propia": float(np.median(np.median(cv["total"] - cv["pgu"], axis=1)[m]) /
                                                          np.median(np.median(d["total"] - d["pgu"], axis=1)[m]) - 1)})
    return pd.DataFrame(filas_sexo), pd.DataFrame(filas_q)


FACTORES_BRECHA = {"densidad": "Densidad de cotización", "ingreso": "Nivel de ingreso",
                   "retiro": "Edad de pensión (60 vs 65)", "mortalidad": "Esperanza de vida (tabla de mortalidad)"}


def brecha_genero(R: np.ndarray, n: int, semilla: int, c=config.MICROSIM, umbral_pgu: float = np.inf) -> pd.DataFrame:
    """Descomposición de Shapley de la brecha de pensión total mediana mujer/hombre (fondo por defecto).
    v(S) = pensión mediana de las mujeres cuando se les asignan las características de los hombres del conjunto S.
    El aporte de cada factor es su efecto marginal promedio sobre todos los órdenes posibles: no depende del orden."""
    from itertools import combinations
    from math import factorial

    def valor(S: frozenset) -> float:
        cc = {**c, "ingreso": {**c["ingreso"], "M": c["ingreso"]["H" if "ingreso" in S else "M"]},
              "densidad": {**c["densidad"], "M": c["densidad"]["H" if "densidad" in S else "M"]}}
        rng = np.random.default_rng(semilla)                        # mismas personas y rachas en todos los casos
        pob = generar_poblacion(n, rng, cc, "M")
        o = simular_sexo(pob, R, "M", rng, c=cc, edad_retiro=65 if "retiro" in S else None,
                         sexo_mortalidad="H" if "mortalidad" in S else None, umbral_pgu=umbral_pgu)
        return float(np.median(o["Por defecto (ley)"]["total"]))

    F = list(FACTORES_BRECHA)
    v = {frozenset(S): valor(frozenset(S)) for k in range(len(F) + 1) for S in combinations(F, k)}
    rng = np.random.default_rng(semilla)
    hombre = float(np.median(simular_sexo(generar_poblacion(n, rng, c, "H"), R, "H", rng, c=c,
                                          umbral_pgu=umbral_pgu)["Por defecto (ley)"]["total"]))
    base, todo = v[frozenset()], v[frozenset(F)]
    filas = []
    for f in F:
        otros = [x for x in F if x != f]
        phi = sum(factorial(k) * factorial(len(F) - k - 1) / factorial(len(F)) * (v[frozenset(S) | {f}] - v[frozenset(S)])
                  for k in range(len(F)) for S in combinations(otros, k))
        filas.append({"factor": FACTORES_BRECHA[f], "aporte_uf": phi, "aporte_pp_brecha": phi / hombre})
    filas.append({"factor": "Residuo (fondo por defecto por sexo y muestreo)", "aporte_uf": hombre - todo,
                  "aporte_pp_brecha": (hombre - todo) / hombre})
    out = pd.DataFrame(filas)
    out.attrs.update(mujer=base, hombre=hombre, brecha=base / hombre - 1)
    return out


def evaluar(R: np.ndarray, c=config.MICROSIM) -> dict:
    rng = np.random.default_rng(c["semilla"])
    pob = generar_poblacion(c["n_personas"], rng, c)
    R = R[:c["n_escenarios"]]
    umbral = float(np.quantile(pob.sueldo_ref_uf, c["focalizacion_pgu"]))     # 10% de mayores ingresos: sin PGU
    res = {s: simular_sexo(pob[pob.sexo == s].reset_index(drop=True), R, s, rng, umbral_pgu=umbral) for s in ("H", "M")}
    sexo, quintil = resumir(pob, res)
    brecha = brecha_genero(R, n=min(6000, c["n_personas"]), semilla=c["semilla"] + 1, c=c, umbral_pgu=umbral)
    # distribución de la tasa de reemplazo total (persona x escenario) por sexo, para figuras
    dist = {s: np.percentile(res[s]["Por defecto (ley)"]["total"] / np.maximum(res[s]["sueldo_final"], 1e-9)[:, None],
                             np.arange(1, 100)) for s in res}
    return {"poblacion": pob, "sexo": sexo, "quintil": quintil, "brecha": brecha, "dist_tr": dist}
