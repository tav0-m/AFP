"""Pipeline completo: datos crudos -> base consolidada -> retornos reales -> econometría
-> Monte Carlo -> bandas -> figuras -> reporte Excel -> datos para el simulador web.

Uso:  python run_pipeline.py            (≈1 minuto)
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from afp import (bandas, config, econometria, escenarios, etl_valores_cuota,  # noqa: E402
                 figuras, incertidumbre, mortalidad, reporte_excel, retornos, robustez,
                 simulacion)

NOMBRES_REGIMEN = {3: ["Calma", "Tasas volátiles (post-2019)", "Crisis bursátil"],
                   2: ["Calma", "Estrés"], 1: ["Único"]}


def paso(msg, t0=[time.time()]):
    print(f"[{time.time() - t0[0]:6.1f}s] {msg}", flush=True)


def actualizar_readme(hallazgos):
    """Reescribe la tabla de hallazgos del README entre marcadores: las cifras nunca quedan desfasadas."""
    ruta = config.RAIZ / "README.md"
    txt = ruta.read_text(encoding="utf-8")
    ini, fin = "<!-- HALLAZGOS:INICIO -->", "<!-- HALLAZGOS:FIN -->"
    if ini not in txt or fin not in txt:
        return
    filas = "\n".join(f"| {i} | {a} | {b} |" for i, (a, b) in enumerate(hallazgos, 1))
    tabla = f"{ini}\n| # | Hallazgo | Evidencia |\n|---|---|---|\n{filas}\n{fin}"
    ruta.write_text(txt[:txt.index(ini)] + tabla + txt[txt.index(fin) + len(fin):], encoding="utf-8")


def main():
    for d in (config.DATA_PROC, config.FIGURAS):
        d.mkdir(parents=True, exist_ok=True)

    paso("1. ETL de valores cuota")
    vc, eventos = etl_valores_cuota.construir()
    calidad = etl_valores_cuota.validar(vc)

    paso("2. Retornos reales y ponderación por afiliados")
    uf = retornos.cargar_uf(); afil = retornos.cargar_afiliados()
    df = retornos.agregar_reales(vc, uf, afil)
    idx_r = retornos.indice_sistema(df)
    idx_n = retornos.indice_sistema(df, "retorno_ajustado")
    rr, rn = retornos.resumen_rentabilidad(idx_r), retornos.resumen_rentabilidad(idx_n)
    rent = pd.DataFrame({"fondo": config.FONDOS, "rent_nominal_anual": rn.rent_anual.values,
                         "rent_real_anual": rr.rent_anual.values,
                         "inflacion_implicita": ((1 + rn.rent_anual) / (1 + rr.rent_anual) - 1).values,
                         "max_caida_real": rr.max_caida.values,
                         "prima_real_vs_E": (rr.rent_anual - rr.rent_anual["E"]).values})
    m = retornos.a_mensual(idx_r)

    paso("3. Econometría: HMM de regímenes (K=1..3, BIC)")
    X = m[config.FONDOS].values
    modelo, tabla_bic = econometria.seleccionar_hmm(X, Ks=(1, 2, 3), n_inicios=25, semilla=11)
    nombres = NOMBRES_REGIMEN[modelo["K"]]
    reg = econometria.resumen_regimenes(modelo, config.FONDOS)
    reg.insert(1, "nombre", reg.regimen.map(dict(enumerate(nombres))))
    etiqueta = pd.Series(modelo["gamma"].argmax(1), index=m.index)
    inicio_quiebre = etiqueta[etiqueta == 1].index.min() if modelo["K"] == 3 else None

    paso("3b. GARCH(1,1) diario por fondo")
    habil = idx_r[(idx_r.index.dayofweek < 5) & (idx_r.abs().sum(axis=1) > 0)]
    filas, sig = [], {}
    for f in config.FONDOS:
        g = econometria.ajustar_garch(habil[f].values)
        sig[f] = pd.Series(g.pop("sigma_condicional"), index=habil.index)
        filas.append({"fondo": f, **g})
    garch = pd.DataFrame(filas).drop(columns=["omega", "loglik"])
    sigma = pd.DataFrame(sig)
    corr_ce = econometria.correlacion_movil(m, "C", "E").dropna()

    paso("4. Monte Carlo (bootstrap condicionado a régimen)")
    p = config.SIM
    R = escenarios.simular(m[config.FONDOS], modelo, meses=480, n=p["n_simulaciones"], semilla=p["semilla"])
    mc, pens = {}, {}
    for sexo in ("H", "M"):
        mc[sexo], pens[sexo] = simulacion.simular_estrategias(R, sexo)
    R2 = escenarios.simular(m[config.FONDOS], modelo, meses=480, n=p["n_simulaciones"], semilla=p["semilla"],
                            ajuste_retorno_anual=0.01)
    sens, _ = simulacion.simular_estrategias(R2, "H")
    back = {s: simulacion.backtest_historico(m, s) for s in ("H", "M")}

    paso(f"4b. Robustez: {len(config.ROBUSTEZ)} supuestos alternativos")
    rob = robustez.evaluar(m, modelo)

    paso("4b2. Escenarios de mercado forward-looking (histórico vs consenso 2026 vs prima nula)")
    esg, esg_pens = robustez.evaluar_esg(m, modelo)

    paso("4c. Incertidumbre de parámetros (bootstrap del HMM, GARCH e historia)")
    inc = incertidumbre.evaluar(m[config.FONDOS], modelo, habil[config.FONDOS],
                                desde_quiebre=inicio_quiebre)

    paso("5. Riesgo de bandas de los fondos generacionales")
    men = bandas.retornos_mensuales_afp(df)
    dev = bandas.desviaciones(men)
    fb = bandas.frecuencia_fuera_banda(dev)

    paso("6. Figuras")
    figuras.indice_real(idx_r)
    figuras.regimenes(m, modelo["gamma"], nombres)
    figuras.volatilidad(sigma)
    figuras.correlaciones(m)
    for sexo in ("H", "M"):
        t = mc[sexo]
        figuras.montecarlo(t, sexo, meta_uf=p["tasa_reemplazo_meta"] * t.attrs["sueldo_final"])
    figuras.bandas(dev)
    figuras.robustez(rob)
    figuras.glidepath()
    for sexo in ("H", "M"):
        figuras.escenarios_mercado(esg_pens, sexo)
    figuras.incertidumbre(inc["pensiones"], mc["H"].set_index("estrategia").pipe(
        lambda t: t.loc["Ciclo de vida (aprox. FG)", "mediana"] / t.loc["Por defecto (ley)", "mediana"] - 1))

    paso("7. Hallazgos (calculados, no escritos a mano)")
    H = mc["H"].set_index("estrategia"); M_ = mc["M"].set_index("estrategia")
    dflt, cv, rc = "Por defecto (ley)", "Ciclo de vida (aprox. FG)", "Reactivo (market timing)"
    e_reg = reg[(reg.regimen == 1) & (reg.fondo == "E")].iloc[0] if modelo["K"] == 3 else None
    e_calma = reg[(reg.regimen == 0) & (reg.fondo == "E")].iloc[0]
    b24 = fb[fb.banda == 0.024]; b40 = fb[fb.banda == 0.040]
    bh = back["H"].set_index("estrategia")
    robs = rob.set_index("caso")
    ip = inc["pensiones"]; ih = inc["hmm"]; iq = lambda s: tuple(np.percentile(s, [5, 95]))
    ci_cv, ci_re = iq(ip.cv_vs_defecto_mediana), iq(ip.reactivo_vs_defecto_mediana)
    ci_prima = iq(ip.prima_real_A_vs_E)
    ih1 = ih[ih.regimen == 1] if modelo["K"] == 3 else None
    ci_ce = incertidumbre.ic_correlacion(corr_ce.iloc[-1], 36)
    eg = esg[esg.sexo == "H"].set_index("escenario")
    cons, nula = eg.loc["Consenso de mercado 2026"], eg.loc["Prima de crecimiento nula"]
    hallazgos = [
        ("La inflación se lleva ~3,9 puntos al año: la rentabilidad real es mucho menor que la publicitada.",
         f"Fondo A: {rent.rent_nominal_anual[0]:.1%} nominal vs {rent.rent_real_anual[0]:.1%} real; "
         f"Fondo E: {rent.rent_nominal_anual[4]:.1%} vs {rent.rent_real_anual[4]:.1%} (ago-2002 a ago-2026)."),
        ("El Fondo E no es un refugio: su peor caída real fue mayor que la del D y similar a la del C.",
         f"Máx. caída real: C {rent.max_caida_real[2]:.1%}, D {rent.max_caida_real[3]:.1%}, E {rent.max_caida_real[4]:.1%}."),
        ("Desde 2019 el mercado chileno opera en un régimen nuevo, nunca visto antes.",
         (f"El HMM (3 estados, BIC) detecta un régimen que domina desde {inicio_quiebre:%m-%Y}; en él el Fondo E tiene "
          f"volatilidad real de {e_reg.vol_anual:.1%} (vs {e_calma.vol_anual:.1%} en calma) y la correlación C–E subió a "
          f"{corr_ce.iloc[-1]:.2f} (IC 90%: {ci_ce[0]:.2f} a {ci_ce[1]:.2f}). Bootstrap paramétrico ({ih1.replica.nunique()} réplicas): "
          f"volatilidad del E en ese régimen entre {ih1.vol_E.quantile(0.05):.1%} y {ih1.vol_E.quantile(0.95):.1%}; el régimen se "
          f"recupera (>50% de los meses desde el quiebre) en {(ih1.pct_meses_reg1_desde_quiebre > 0.5).mean():.0%} de las réplicas.")
         if e_reg is not None else "Ver hoja Regimenes_HMM."),
        ("Con la trayectoria oficial de los fondos generacionales, el ciclo de vida supera al fondo por defecto actual.",
         f"Hombre: mediana {H.loc[cv, 'mediana']:.1f} vs {H.loc[dflt, 'mediana']:.1f} UF "
         f"({H.loc[cv, 'mediana'] / H.loc[dflt, 'mediana'] - 1:+.0%}); percentil 5: {H.loc[cv, 'p5']:.1f} vs {H.loc[dflt, 'p5']:.1f} UF. "
         f"Sin extrapolar sobre el Fondo A: {robs.loc['Glidepath sin extrapolar (tope 100% A)', 'cv_vs_defecto_mediana']:+.0%}. "
         f"Con historias alternativas (bootstrap por bloques) el IC 90% es {ci_cv[0]:+.0%} a {ci_cv[1]:+.0%}: ver hallazgo 9."),
        ("Cambiarse de fondo reaccionando a las caídas no mejora la pensión esperada y suele costar.",
         f"Mediana {H.loc[rc, 'mediana'] / H.loc[dflt, 'mediana'] - 1:+.1%} y percentil 5 "
         f"{H.loc[rc, 'p5'] / H.loc[dflt, 'p5'] - 1:+.1%} vs el por defecto (≈{mc['H'].attrs['cambios_reactivo_mediana']:.0f} traspasos). "
         f"En la historia 2002-2026 la misma regla quedó en {bh.loc[rc, 'vs_defecto']:+.1%}: un solo camino no basta para juzgar. "
         f"Con historias alternativas el IC 90% es {ci_re[0]:+.1%} a {ci_re[1]:+.1%}."),
        ("La brecha de género es estructural, incluso con el mismo sueldo y la misma estrategia.",
         f"Por defecto: hombre {H.loc[dflt, 'mediana']:.1f} UF vs mujer {M_.loc[dflt, 'mediana']:.1f} UF "
         f"({M_.loc[dflt, 'mediana'] / H.loc[dflt, 'mediana'] - 1:+.0%}): 5 años menos de ahorro y mayor longevidad "
         f"(CNU {mc['M'].attrs['cnu']:.0f} vs {mc['H'].attrs['cnu']:.0f})."),
        ("Las bandas de premios y castigos son ~3 veces más anchas que la dispersión histórica entre AFP.",
         f"El 95% de las desviaciones de 36 meses vs pares es menor a {dev.desviacion.abs().quantile(0.95):.2%}; "
         f"con banda ±2,4% solo {b24.pct_meses_fuera.mean():.1%} de los AFP-meses habría quedado fuera, y con la banda de "
         f"transición de ±4,0% (abr-2028 a mar-2031), {b40.pct_meses_fuera.mean():.1%}. "
         "El incentivo dependerá de cuánto difiera la cartera de referencia de lo que hoy invierten las AFP."),
        (f"Las dos conclusiones sobre estrategias resisten {len(rob)} supuestos alternativos, y reaccionar más rápido cuesta más.",
         f"El ciclo de vida supera al por defecto en {rob.prob_cv_supera_defecto.min():.0%}–{rob.prob_cv_supera_defecto.max():.0%} "
         f"de los escenarios en todos los casos (mediana {rob.cv_vs_defecto_mediana.min():+.0%} a {rob.cv_vs_defecto_mediana.max():+.0%}). "
         f"La regla reactiva pierde en la mediana en los {int((rob.reactivo_vs_defecto_mediana < 0).sum())} casos: "
         f"{robs.loc['Reactivo más nervioso (−4%)', 'reactivo_vs_defecto_mediana']:+.1%} si reacciona ante caídas de 4% "
         f"(≈{robs.loc['Reactivo más nervioso (−4%)', 'traspasos_reactivo']:.0f} traspasos) y "
         f"{robs.loc['Reactivo más tolerante (−10%)', 'reactivo_vs_defecto_mediana']:+.1%} si espera caídas de 10%."),
        ("La ventaja del ciclo de vida es, en el fondo, una apuesta a la prima de la renta variable, y 24 años de historia no la aseguran.",
         f"Remuestreando la historia por bloques ({len(ip)} historias), la prima real del A sobre el E va de {ci_prima[0]:+.1%} a "
         f"{ci_prima[1]:+.1%} (IC 90%) y explica la ventaja del ciclo de vida (correlación "
         f"{ip.prima_real_A_vs_E.corr(ip.cv_vs_defecto_mediana):.2f}). El ciclo de vida gana en la mediana en "
         f"{(ip.cv_vs_defecto_mediana > 0).mean():.0%} de las historias; cuando la prima es negativa, pierde."),
        ("Con las expectativas de mercado actuales, la ventaja del ciclo de vida es real pero mucho menor que la histórica.",
         f"Recentrando los escenarios en el consenso 2026 (renta fija UF {config.ESG['Consenso de mercado 2026']['real_proteccion']:.2%}, "
         f"renta variable global {config.ESG['Consenso de mercado 2026']['real_crecimiento']:.1%} real): Fondo A {cons.retorno_real_A:.1%} "
         f"y E {cons.retorno_real_E:.1%} real/año; ciclo de vida vs por defecto {cons.cv_vs_defecto_mediana:+.0%} en la mediana "
         f"(vs {eg.loc['Histórico 2002-2026', 'cv_vs_defecto_mediana']:+.0%} con la historia), percentil 5 {cons.cv_vs_defecto_p5:+.0%}, "
         f"gana en {cons.prob_cv_supera_defecto:.0%} de los escenarios. Sin prima de crecimiento: {nula.cv_vs_defecto_mediana:+.0%}. "
         f"La probabilidad de alcanzar una tasa de reemplazo de 40% es {cons.prob_tr_meta_defecto:.0%} (por defecto) y "
         f"{cons.prob_tr_meta_cv:.0%} (ciclo de vida)."),
    ]

    import re
    hallazgos = [(re.sub(r"(\d)\.(\d)", r"\1,\2", a), re.sub(r"(\d)\.(\d)", r"\1,\2", b)) for a, b in hallazgos]

    paso("8. Reporte Excel")
    fuentes = [
        "Valores cuota y patrimonio: Superintendencia de Pensiones, spensiones.cl/apps/valoresCuotaFondo/vcfAFP.php (2002-2026).",
        "Afiliados por edad y AFP: SP, Series estadísticas del Sistema de Pensiones (trimestral).",
        "Tablas de mortalidad CB-H-2020 y RV-M-2020: CMF, NCG N.º 495 (feb-2023).",
        "TITRP 3,45%: SP, Circular N.º 2417 (07-07-2026).",
        "UF diaria: Banco Central de Chile, Base de Datos Estadísticos (API SieteRestWS).",
        "Régimen de inversión de los Fondos Generacionales: SP, Res. Ex. N.º 1195 (01-09-2026); bandas de 240 a 290 p.b. "
        "anuales, transición de 400 p.b. entre abr-2028 y mar-2031 (spensiones.cl/portal/institucional/594/w3-article-17131.html).",
        "Trayectoria de inversión (máximo de activos de crecimiento por edad): SP, minuta de la consulta pública (jul-2026, "
        "articles-11315_nt_561_minuta.pdf), digitalizada; tope inicial de 95% de la versión definitiva (Res. Ex. N.º 1195).",
        "Activos de crecimiento de cada multifondo: SP, Reporte mensual de inversiones, cartera al 31-03-2026 (tablas 16 y 18).",
        "Renta fija en UF: tasa de bonos BCU/BTU a 10 años, mercado secundario, 2,52% (BCCh, 08-06-2026).",
        "Renta variable global: MSCI ACWI 7,0% nominal USD e inflación EE.UU. 2,5% (J.P. Morgan AM, Long-Term Capital "
        "Market Assumptions 2026).",
    ]
    res = dict(rango_datos=f"{vc.fecha.min():%d-%m-%Y} a {vc.fecha.max():%d-%m-%Y}", hallazgos=hallazgos,
               uf_ultima=float(uf.uf.iloc[-1]), uf_fecha=f"{uf.fecha.iloc[-1]:%d-%m-%Y}",
               calidad=calidad, eventos=eventos, rentabilidad=rent, regimenes=reg,
               bic_texto="; ".join(f"K={int(r.K)}: BIC {r.BIC:,.1f}" for r in tabla_bic.itertuples()),
               transicion=modelo["A"], garch=garch, montecarlo=mc, sensibilidad=sens,
               backtest=pd.concat([b.assign(sexo=s) for s, b in back.items()]), bandas=fb, robustez=rob, esg=esg,
               incertidumbre=pd.concat([inc["resumen_pensiones"].assign(bloque="Pensiones (historia remuestreada)"),
                                        inc["resumen_hmm"].assign(bloque="HMM (paramétrico)"),
                                        inc["resumen_garch"].assign(bloque="GARCH (residuos filtrados)")], ignore_index=True),
               fuentes=fuentes)
    reporte_excel.construir(config.REPORTS / "reporte_proyecto_afp.xlsx", res)

    paso("9. Datos procesados y JSON para el simulador web")
    cols = ["fecha", "fondo", "afp", "valor_cuota", "patrimonio", "estado", "uf", "valor_cuota_uf",
            "retorno_ajustado", "retorno_real_ajustado", "n_afiliados"]
    df[cols].to_csv(config.DATA_PROC / "valores_cuota_afp_real.csv.gz", index=False, float_format="%.6f")
    (100 * (1 + idx_r).cumprod()).to_csv(config.DATA_PROC / "indice_sistema_real_diario.csv", float_format="%.4f")
    m.to_csv(config.DATA_PROC / "retornos_reales_mensuales.csv", float_format="%.6f")
    pd.DataFrame(modelo["gamma"], index=m.index, columns=nombres).to_csv(config.DATA_PROC / "probabilidad_regimenes.csv", float_format="%.4f")
    for sexo in ("H", "M"):
        mc[sexo].to_csv(config.DATA_PROC / f"montecarlo_{sexo}.csv", index=False, float_format="%.4f")
    rob.to_csv(config.DATA_PROC / "robustez.csv", index=False, float_format="%.5f")
    esg.to_csv(config.DATA_PROC / "escenarios_mercado.csv", index=False, float_format="%.5f")
    for k in ("hmm", "garch", "pensiones"):
        inc[k].to_csv(config.DATA_PROC / f"incertidumbre_{k}.csv", index=False, float_format="%.6f")
    dev.assign(mes=dev.mes.astype(str)).to_csv(config.DATA_PROC / "desviaciones_36m_afp.csv", index=False, float_format="%.6f")

    edades_gp = np.arange(18, 76)
    glidepath_web = {"edad_inicial": 18,
                     "crecimiento": np.round(simulacion.crecimiento_glidepath(edades_gp), 4).tolist(),
                     "pesos": np.round(simulacion.pesos_ciclo_vida(edades_gp), 6).tolist(),
                     "crecimiento_multifondos": config.GLIDEPATH["crecimiento_multifondos"]}
    web = {"generado": time.strftime("%Y-%m-%d"), "rango": res["rango_datos"], "uf": res["uf_ultima"],
           "uf_fecha": res["uf_fecha"], "titrp": config.TITRP, "sim": config.SIM,
           "hallazgos": [{"titulo": a, "detalle": b} for a, b in hallazgos],
           "rentabilidad": rent.round(5).to_dict("records"),
           "indice_mensual": {"fechas": [d.strftime("%Y-%m") for d in m.index],
                              **{f: np.round(100 * (1 + m[f]).cumprod().values, 2).tolist() for f in config.FONDOS}},
           "regimen": {"nombres": nombres, "etiqueta": etiqueta.tolist(),
                       "transicion": np.round(modelo["A"], 6).tolist()},
           "retornos_mensuales": np.round(m[config.FONDOS].values, 6).tolist(),
           "reactivo": config.REACTIVO, "glidepath": glidepath_web, "edad_legal": config.EDAD_LEGAL,
           "montecarlo": {s: mc[s].round(3).to_dict("records") for s in ("H", "M")},
           "backtest": {s: back[s].round(4).to_dict("records") for s in ("H", "M")},
           "bandas": {"p95": float(dev.desviacion.abs().quantile(0.95)), "x0": -4.5, "ancho_bin": 0.1,
                      "permanente": list(config.BANDAS["permanente"]), "transicion": config.BANDAS["transicion"],
                      "transicion_vigencia": config.BANDAS["transicion_vigencia"],
                      "hist": np.histogram(dev.desviacion * 100, bins=np.arange(-4.5, 4.55, 0.1))[0].tolist()},
           "robustez": rob.round(4).to_dict("records"),
           "escenarios_mercado": esg.round(4).replace({np.nan: None}).to_dict("records"),
           "escenarios_pensiones": esg_pens[["escenario", "estrategia", "sexo", "p5", "p25", "mediana", "p75", "p95"]]
                                   .round(3).to_dict("records"),
           "incertidumbre": inc["pensiones"][["prima_real_A_vs_E", "cv_vs_defecto_mediana",
                                              "reactivo_vs_defecto_mediana"]].round(4).to_dict("list"),
           "mortalidad": {}}
    for sexo in ("H", "M"):
        edades, anios, Mq = mortalidad.matriz_qx(sexo, range(2026, 2101))
        web["mortalidad"][sexo] = {"edades": edades, "anio0": anios[0],
                                   "qx": [[round(float(x), 7) for x in fila] for fila in Mq]}
    (config.RAIZ / "app" / "resultados.json").write_text(json.dumps(web, ensure_ascii=False), encoding="utf-8")
    import runpy
    runpy.run_path(str(config.RAIZ / "app" / "build_app.py"))
    runpy.run_path(str(config.RAIZ / "app" / "build_tablero.py"))
    actualizar_readme(hallazgos)
    paso("Listo.")
    for h, e in hallazgos:
        print(" -", h, "|", e)


if __name__ == "__main__":
    main()
