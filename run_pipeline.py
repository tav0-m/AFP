"""Pipeline completo: datos crudos -> base consolidada -> retornos reales -> econometría
-> Monte Carlo -> bandas -> figuras -> reporte Excel -> datos para el simulador web.

Uso:  python run_pipeline.py            (≈1 minuto)
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from afp import (bandas, config, econometria, escenarios, etl_valores_cuota,  # noqa: E402
                 figuras, incertidumbre, microsimulacion, mortalidad, optimo, reforma, regimenes_macro, reporte_excel, retornos, robustez,
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

    paso("3c. Regímenes con variables macro (TVTP-HMM, walk-forward 2015-2026)")
    macro_ok = (config.DATA_RAW / "macro_mindicador.csv").exists() and modelo["K"] == 3
    tvtp = regimenes_macro.evaluar(m[config.FONDOS], modelo) if macro_ok else None

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

    paso("4b3. Pensión total con la reforma (Ley 21.735), supuestos de consenso")
    R_cons = escenarios.simular(m[config.FONDOS], modelo, meses=480, n=p["n_simulaciones"], semilla=p["semilla"],
                                objetivo=escenarios.retornos_objetivo(config.ESG["Consenso de mercado 2026"], config.GLIDEPATH))
    pt = {s: reforma.pension_total(R_cons, s) for s in ("H", "M")}
    paso("4b3b. Microsimulación poblacional (20.000 personas, mismos escenarios de mercado)")
    micro = microsimulacion.evaluar(R_cons)
    ref_res = pd.concat([reforma.resumen(pt[s]).assign(sexo=s) for s in ("H", "M")], ignore_index=True)
    ref_ing = pd.concat([reforma.por_ingreso(R_cons, s).assign(sexo=s) for s in ("H", "M")], ignore_index=True)
    del R_cons

    paso("4b4. Glidepath óptimo (utilidad CRRA de la pensión total, entrenamiento/prueba)")
    procesos = config.INCERTIDUMBRE.get("procesos") or max(1, (os.cpu_count() or 2) - 1)
    opt_res, opt_comp = optimo.evaluar(m[config.FONDOS], modelo,
                                       escenarios.retornos_objetivo(config.ESG["Consenso de mercado 2026"], config.GLIDEPATH),
                                       procesos=procesos)

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
    figuras.glidepath_optimo(opt_res)
    figuras.poblacion_quintiles(micro["quintil"])
    if tvtp is not None:
        figuras.prediccion_regimenes(tvtp["walk_forward"], tvtp["comparacion"])
    figuras.brecha_genero(micro["brecha"])
    for sexo in ("H", "M"):
        figuras.pilares(ref_ing[ref_ing.sexo == sexo], sexo)
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
    rr = ref_res.set_index(["sexo", "estrategia", "capa"])
    r10 = lambda s: rr.loc[(s, dflt, "Solo 10% del trabajador")]
    rtot = lambda s: rr.loc[(s, dflt, "+ PGU (pensión total)")]
    ri = ref_ing[ref_ing.sexo == "H"]
    oo = opt_res.set_index(["con_reforma", "gamma"])
    ms_s, ms_q, ms_b = micro["sexo"].set_index("sexo"), micro["quintil"], micro["brecha"]
    qH = ms_q[ms_q.sexo == "H"].set_index("quintil")
    top = ms_b.iloc[ms_b.aporte_pp_brecha.idxmax()]
    tc = tvtp["comparacion"].set_index("modelo") if tvtp is not None else None
    ef = tvtp["efectos"] if tvtp is not None else None
    n_pers = f"{config.MICROSIM['n_personas'] // 1000} mil"
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
        ("La reforma de 2025 cambia más la pensión que cualquier estrategia de inversión: la tasa de reemplazo se duplica.",
         f"Fondo por defecto, consenso 2026. Hombre: solo con el 10% del trabajador, tasa de reemplazo mediana {r10('H').tasa_reemplazo_mediana:.0%} "
         f"({r10('H').prob_tr_meta:.0%} llega a 40%); con cotización del empleador, rentabilidad protegida y PGU, "
         f"{rtot('H').tasa_reemplazo_mediana:.0%} ({rtot('H').prob_tr_meta:.0%} llega a 40%). Mujer (PGU desde los 65): "
         f"{r10('M').tasa_reemplazo_mediana:.0%} → {rtot('M').tasa_reemplazo_mediana:.0%}. La PGU es progresiva: con sueldo de "
         f"{ri.sueldo_inicial_uf.iloc[0]:.0f} UF la tasa total es {ri.tasa_reemplazo_total.iloc[0]:.0%} y con "
         f"{ri.sueldo_inicial_uf.iloc[-1]:.0f} UF, {ri.tasa_reemplazo_total.iloc[-1]:.0%}."),
        ("El glidepath oficial está muy cerca del óptimo, y la PGU justifica llegar al retiro con más riesgo.",
         f"Maximizando la utilidad CRRA de la pensión total (hombre, consenso 2026, escenarios de prueba), el mejor glidepath de la "
         f"familia supera al oficial en solo {opt_res.optimo_vs_oficial.min():+.1%} a {opt_res.optimo_vs_oficial.max():+.1%} de pensión "
         f"equivalente cierta (aversión γ de 2 a 5); el fondo por defecto de la ley queda {opt_res.defecto_vs_oficial.min():+.0%} a "
         f"{opt_res.defecto_vs_oficial.max():+.0%} bajo el oficial. Con γ = 3, el óptimo llega al retiro con "
         f"{oo.loc[(True, 3.0), 'g1']:.0%} en crecimiento si se cuenta la PGU y {oo.loc[(False, 3.0), 'g1']:.0%} sin ella "
         f"(el oficial, {simulacion.crecimiento_glidepath(np.array([config.EDAD_LEGAL['H'] - 1]))[0]:.0%}): la PGU actúa como un bono."),
        ("En la población real la pensión depende sobre todo del ingreso y de las lagunas: la PGU la vuelve muy progresiva.",
         f"Microsimulación de {n_pers} personas con ingreso y densidad calibrados con la SP (consenso 2026, fondo por defecto): "
         f"tasa de reemplazo total mediana {ms_s.loc['H', 'tr_total_mediana']:.0%} en hombres y {ms_s.loc['M', 'tr_total_mediana']:.0%} "
         f"en mujeres (solo con el 10%: {ms_s.loc['H', 'tr_10_mediana']:.0%} y {ms_s.loc['M', 'tr_10_mediana']:.0%}). Del quintil 1 al 5 "
         f"la tasa total baja de {qH.loc[1, 'tr_total_mediana']:.0%} a {qH.loc[5, 'tr_total_mediana']:.0%} (hombres). La PGU es más de la "
         f"mitad de la pensión en {ms_s.loc['M', 'pct_pgu_mayor_mitad']:.0%} de los casos de mujeres. El ciclo de vida sube la pensión total "
         f"{qH.loc[1, 'cv_vs_defecto_total']:+.0%} en el quintil 1 y {qH.loc[5, 'cv_vs_defecto_total']:+.0%} en el 5: la PGU amortigua su "
         f"efecto en los de menores ingresos."),
        ("La edad de pensión es la principal causa de la brecha de género, por sobre las lagunas y el sueldo.",
         f"La pensión total mediana de una mujer es {-ms_b.attrs['brecha']:.0%} menor que la de un hombre. Descomposición de Shapley: "
         + "; ".join(f"{r.factor.lower()} {r.aporte_pp_brecha * 100:.1f} pp" for r in ms_b.itertuples() if "Residuo" not in r.factor)
         + f". El factor más importante es «{top.factor}», con {top.aporte_pp_brecha / -ms_b.attrs['brecha']:.0%} de la brecha."),
    ] + ([
        ("Los regímenes mejoran la predicción del mes siguiente, pero las variables macro no ayudan a anticiparlos.",
         f"Validación fuera de muestra 2015-2026 ({int(tc.loc['HMM constante', 'meses'])} meses, reestimación anual): el HMM "
         f"supera a una normal sin regímenes en {tc.loc['HMM constante', 'log_score_promedio'] - tc.loc['Normal (sin regímenes)', 'log_score_promedio']:+.2f} de log-score por mes "
         f"(Diebold-Mariano p = {tc.loc['Normal (sin regímenes)', 'p_valor']:.3f}). Agregar IPC, TPM, dólar e Imacec a las transiciones "
         f"(TVTP) no mejora: {tc.loc['HMM constante', 'tvtp_menos_modelo']:+.3f} por mes (p = {tc.loc['HMM constante', 'p_valor']:.2f}). "
         f"Dentro de muestra, una TPM que sube 1 desviación estándar eleva la probabilidad de pasar de la calma a la crisis de "
         f"{ef[(ef.desde == 0) & (ef.hacia == 2) & ef.variable.str.startswith('Cambio de la TPM')].prob_base.iloc[0]:.0%} a "
         f"{ef[(ef.desde == 0) & (ef.hacia == 2) & ef.variable.str.startswith('Cambio de la TPM')]['prob_con_+1sd'].iloc[0]:.0%}, pero el "
         f"quiebre de 2019 ocurrió una sola vez: no hay transiciones suficientes para aprender qué lo gatilla."),
    ] if tvtp is not None else [])

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
        "Reforma de pensiones: Ley N.º 21.735; Subsecretaría de Previsión Social, Nota Técnica (ago-2025), tablas 1, 3 y 5. "
        "PGU y umbrales de pensión base: SP (vigentes desde el 01-02-2026).",
        "Variables macro (IPC, TPM, dólar observado, Imacec): API pública de mindicador.cl, que republica series del BCCh y el INE.",
    ]
    res = dict(rango_datos=f"{vc.fecha.min():%d-%m-%Y} a {vc.fecha.max():%d-%m-%Y}", hallazgos=hallazgos,
               uf_ultima=float(uf.uf.iloc[-1]), uf_fecha=f"{uf.fecha.iloc[-1]:%d-%m-%Y}",
               calidad=calidad, eventos=eventos, rentabilidad=rent, regimenes=reg,
               bic_texto="; ".join(f"K={int(r.K)}: BIC {r.BIC:,.1f}" for r in tabla_bic.itertuples()),
               transicion=modelo["A"], garch=garch, montecarlo=mc, sensibilidad=sens,
               backtest=pd.concat([b.assign(sexo=s) for s, b in back.items()]), bandas=fb, robustez=rob, esg=esg, reforma=ref_res, reforma_ingreso=ref_ing, optimo=opt_res,
               tvtp_comparacion=tvtp["comparacion"] if tvtp is not None else None,
               tvtp_efectos=tvtp["efectos"] if tvtp is not None else None,
               micro_sexo=micro["sexo"], micro_quintil=micro["quintil"], micro_brecha=micro["brecha"],
               incertidumbre=pd.concat([inc["resumen_pensiones"].assign(bloque="Pensiones (historia remuestreada)"),
                                        inc["resumen_hmm"].assign(bloque="HMM (paramétrico)"),
                                        inc["resumen_garch"].assign(bloque="GARCH (residuos filtrados)")], ignore_index=True),
               fuentes=fuentes)
    reporte_excel.construir(config.REPORTS / "reporte_proyecto_afp.xlsx", res)

    paso("9. Datos procesados y JSON para el simulador web")
    cols = ["fecha", "fondo", "afp", "valor_cuota", "patrimonio", "estado", "uf", "valor_cuota_uf",
            "retorno_ajustado", "retorno_real_ajustado", "n_afiliados"]
    df[cols].to_csv(config.DATA_PROC / "valores_cuota_afp_real.csv.gz", index=False, float_format="%.6f",
                   compression={"method": "gzip", "mtime": 0})   # sin marca de tiempo: salida reproducible
    (100 * (1 + idx_r).cumprod()).to_csv(config.DATA_PROC / "indice_sistema_real_diario.csv", float_format="%.4f")
    m.to_csv(config.DATA_PROC / "retornos_reales_mensuales.csv", float_format="%.6f")
    pd.DataFrame(modelo["gamma"], index=m.index, columns=nombres).to_csv(config.DATA_PROC / "probabilidad_regimenes.csv", float_format="%.4f")
    for sexo in ("H", "M"):
        mc[sexo].to_csv(config.DATA_PROC / f"montecarlo_{sexo}.csv", index=False, float_format="%.4f")
    rob.to_csv(config.DATA_PROC / "robustez.csv", index=False, float_format="%.5f")
    esg.to_csv(config.DATA_PROC / "escenarios_mercado.csv", index=False, float_format="%.5f")
    ref_res.to_csv(config.DATA_PROC / "pension_total_capas.csv", index=False, float_format="%.5f")
    opt_res.to_csv(config.DATA_PROC / "glidepath_optimo.csv", index=False, float_format="%.5f")
    for k in ("sexo", "quintil", "brecha"):
        micro[k].to_csv(config.DATA_PROC / f"microsimulacion_{k}.csv", index=False, float_format="%.5f")
    if tvtp is not None:
        tvtp["walk_forward"].to_csv(config.DATA_PROC / "regimenes_macro_walk_forward.csv", float_format="%.6f")
        tvtp["comparacion"].to_csv(config.DATA_PROC / "regimenes_macro_comparacion.csv", index=False, float_format="%.6f")
        tvtp["efectos"].to_csv(config.DATA_PROC / "regimenes_macro_efectos.csv", index=False, float_format="%.5f")
    opt_comp.to_csv(config.DATA_PROC / "glidepath_optimo_comparacion.csv", index=False, float_format="%.5f")
    ref_ing.to_csv(config.DATA_PROC / "pension_total_por_ingreso.csv", index=False, float_format="%.5f")
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
           "reforma": {"capas": ref_res.round(4).to_dict("records"), "ingreso": ref_ing.round(4).to_dict("records"),
                       "pgu": reforma.parametros_uf()},
           "optimo": opt_res.round(5).to_dict("records"),
           "microsimulacion": {"sexo": micro["sexo"].round(4).to_dict("records"),
                               "quintil": micro["quintil"].round(4).to_dict("records"),
                               "brecha": micro["brecha"].round(4).to_dict("records"),
                               "brecha_total": micro["brecha"].attrs["brecha"],
                               "n_personas": config.MICROSIM["n_personas"]},
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
