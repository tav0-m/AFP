"""Figuras del proyecto. Paleta categórica validada (CVD y visión normal) con el
validador del método dataviz; el color sigue a la entidad (cada fondo mantiene su color)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import config  # noqa: E402

SUP, TXT, TXT2, GRID, EJE = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0", "#c3c2b7"
COLOR_FONDO = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a", "D": "#eda100", "E": "#e87ba4"}
COLOR_ESTRATEGIA = {"Por defecto (ley)": "#008300", "Ciclo de vida (aprox. FG)": "#4a3aa7",
                    "Reactivo (market timing)": "#e34948"}
FUENTE = "Fuente: Superintendencia de Pensiones, Banco Central de Chile, CMF. Elaboración propia."


def es(x, dec=1):
    """Número con coma decimal (formato chileno)."""
    return f"{x:.{dec}f}".replace(".", ",")


def _anios(ax, inicio=2004, fin=2026, paso=2):
    ax.set_xticks(pd.to_datetime([f"{y}-01-01" for y in range(inicio, fin + 1, paso)]))
    ax.set_xticklabels(range(inicio, fin + 1, paso))


def _base(figsize=(11, 5.6)):
    fig, ax = plt.subplots(figsize=figsize, facecolor=SUP)
    ax.set_facecolor(SUP)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(EJE)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.tick_params(colors=TXT2, length=0)
    return fig, ax


def _cerrar(fig, ax, titulo, nombre, nota=FUENTE):
    ax.set_title(titulo, loc="left", fontsize=12, color=TXT)
    fig.text(0.01, 0.01, nota, fontsize=8, color=TXT2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    ruta = config.FIGURAS / nombre
    fig.savefig(ruta, dpi=150, facecolor=SUP)
    plt.close(fig)
    return ruta


def indice_real(idx: pd.DataFrame):
    nivel = 100 * (1 + idx.fillna(0)).cumprod()
    anios = (nivel.index[-1] - nivel.index[0]).days / 365.25
    fig, ax = _base()
    for f in config.FONDOS:
        ax.plot(nivel.index, nivel[f], color=COLOR_FONDO[f], lw=2)
        r = (nivel[f].iloc[-1] / 100) ** (1 / anios) - 1
        ax.annotate(f"Fondo {f}  {es(r * 100)}% real/año", (nivel.index[-1], nivel[f].iloc[-1]),
                    xytext=(6, 0), textcoords="offset points", va="center", fontsize=9.5, color=TXT)
    ax.set_yscale("log"); ax.set_yticks([100, 150, 200, 300, 400]); ax.set_yticklabels(["100", "150", "200", "300", "400"])
    ax.set_xlim(nivel.index[0], nivel.index[-1] + pd.Timedelta(days=1400)); _anios(ax)
    return _cerrar(fig, ax, "Valor real (UF) del sistema por multifondo, base 100 = ago-2002 · ponderado por afiliados, escala log",
                   "01_indice_real_multifondos.png")


def regimenes(m: pd.DataFrame, gamma: np.ndarray, nombres: list):
    nivel = 100 * (1 + m).cumprod()
    fig, ax = _base()
    etiqueta = gamma.argmax(1)
    tonos = {1: ("#eda100", 0.18), 2: ("#e34948", 0.20)}
    for k, (col, a) in tonos.items():
        on = etiqueta == k
        for i in np.flatnonzero(on):
            ax.axvspan(m.index[i] - pd.offsets.MonthBegin(1), m.index[i], color=col, alpha=a, lw=0)
        ax.fill_between([], [], color=col, alpha=a + 0.1, label=f"Régimen: {nombres[k]}")
    for f in ("A", "E"):
        ax.plot(nivel.index, nivel[f], color=COLOR_FONDO[f], lw=2, label=f"Fondo {f} (valor real)")
    ax.set_yscale("log"); ax.set_yticks([100, 150, 200, 300, 400]); ax.set_yticklabels(["100", "150", "200", "300", "400"])
    ax.legend(frameon=False, loc="upper left", fontsize=9, labelcolor=TXT); _anios(ax)
    return _cerrar(fig, ax, "Regímenes de mercado detectados por el HMM (3 estados, elegido por BIC) · desde 2019 domina un régimen nuevo",
                   "02_regimenes_hmm.png")


def volatilidad(sigma: pd.DataFrame):
    fig, ax = _base()
    s = sigma.resample("ME").mean()
    for f in ("A", "C", "E"):
        ax.plot(s.index, s[f] * 100, color=COLOR_FONDO[f], lw=2)
        ax.annotate(f"Fondo {f}", (s.index[-1], s[f].iloc[-1] * 100), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9.5, color=TXT)
    ax.set_ylabel("Volatilidad anualizada (%)", color=TXT2)
    ax.set_xlim(s.index[0], s.index[-1] + pd.Timedelta(days=900)); _anios(ax)
    return _cerrar(fig, ax, "Volatilidad condicional GARCH(1,1) de los retornos reales diarios (promedio mensual)",
                   "03_volatilidad_garch.png")


def correlaciones(m: pd.DataFrame, ventana=36):
    fig, ax = _base()
    pares = (("C", "E", COLOR_FONDO["E"]), ("A", "E", COLOR_FONDO["A"]))
    for a, b, col in pares:
        c = m[a].rolling(ventana).corr(m[b]).dropna()
        ax.plot(c.index, c, color=col, lw=2)
        ax.annotate(f"{a} vs {b}: {es(c.iloc[-1], 2)}", (c.index[-1], c.iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9.5, color=TXT)
    ax.axhline(0, color=EJE, lw=1)
    ax.set_ylim(-0.6, 1.0)
    ax.set_xlim(c.index[0], c.index[-1] + pd.Timedelta(days=1000)); _anios(ax, 2006)
    return _cerrar(fig, ax, "Correlación móvil de 36 meses entre fondos (retornos reales mensuales) · el E dejó de diversificar",
                   "04_correlaciones.png")


def montecarlo(tab: pd.DataFrame, sexo: str, meta_uf: float):
    t = tab.sort_values("mediana")
    fig, ax = plt.subplots(figsize=(11, 5.6), facecolor=SUP); ax.set_facecolor(SUP)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(EJE); ax.grid(axis="x", color=GRID, lw=0.8); ax.tick_params(colors=TXT2, length=0)
    for i, r in enumerate(t.itertuples()):
        f = r.estrategia.replace("Fondo ", "")[:1] if r.estrategia.startswith("Fondo") else None
        col = COLOR_FONDO.get(f) if f else COLOR_ESTRATEGIA[r.estrategia]
        ax.plot([r.p5, r.p95], [i, i], color=col, lw=2, solid_capstyle="round")
        ax.plot([r.p25, r.p75], [i, i], color=col, lw=7, solid_capstyle="round")
        ax.plot(r.mediana, i, "o", ms=9, color=SUP, mec=col, mew=2.5)
        ax.annotate(f"mediana {es(r.mediana)}", (r.p95, i), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=9, color=TXT2,
                    bbox=dict(boxstyle="square,pad=0.15", fc=SUP, ec="none"))
    ax.axvline(meta_uf, color=TXT2, lw=1, ls=(0, (4, 3)))
    ax.set_ylim(-0.7, len(t) - 0.3)
    ax.annotate(f"meta: tasa de reemplazo 40% ({es(meta_uf)} UF)", (meta_uf, -0.55), xytext=(4, 0),
                textcoords="offset points", fontsize=8.5, color=TXT2)
    ax.set_yticks(range(len(t))); ax.set_yticklabels(t.estrategia, color=TXT)
    ax.set_xlabel("Pensión mensual (UF de hoy)", color=TXT2)
    quien = "Hombre, 25 a 65 años" if sexo == "H" else "Mujer, 25 a 60 años"
    return _cerrar(fig, ax, f"Pensión simulada por estrategia · {quien} · 10.000 escenarios\n"
                            "línea fina: percentil 5–95 · barra: 25–75 · círculo: mediana",
                   f"05_montecarlo_{sexo}.png")


def bandas(dev: pd.DataFrame, b=config.BANDAS):
    b_min, b_max = b["permanente"]; b_tr = b["transicion"]
    fig, ax = _base()
    x = dev.desviacion.values * 100
    ax.hist(x, bins=np.arange(-4.5, 4.55, 0.1), color=COLOR_FONDO["A"], edgecolor=SUP, lw=0.5)
    ymax = ax.get_ylim()[1]
    for s in (-1, 1):
        ax.axvspan(s * b_min * 100, s * b_max * 100, color="#e34948", alpha=0.15, lw=0)
        ax.axvline(s * b_min * 100, color="#e34948", lw=1)
        ax.axvline(s * b_tr * 100, color=TXT2, lw=1, ls=(0, (4, 3)))
    ax.annotate("permanente\n±2,4% a ±2,9%", (b_max * 100, ymax * 0.86), xytext=(4, 0),
                textcoords="offset points", fontsize=9, color=TXT)
    ax.annotate(f"transición\n±4,0%\n({b['transicion_vigencia']})", (b_tr * 100, ymax * 0.62), xytext=(-4, 0),
                textcoords="offset points", fontsize=9, color=TXT2, ha="right")
    p95 = np.percentile(np.abs(x), 95)
    ax.annotate(f"95% de los casos: |desviación| < {es(p95, 2)}%", (0, ymax * 0.97), ha="center", fontsize=9.5, color=TXT)
    ax.set_xlim(-4.6, 4.6)
    ax.set_xlabel("Rentabilidad anualizada 36m de la AFP menos la de sus pares (p.p.)", color=TXT2)
    ax.set_ylabel("AFP-meses", color=TXT2)
    return _cerrar(fig, ax, "¿Cuánto se desvían las AFP de sus pares? Distribución histórica vs bandas de premios y castigos",
                   "06_bandas_desviaciones.png")


def robustez(rob: pd.DataFrame):
    """Ventaja en mediana frente al fondo por defecto, por supuesto alternativo (un solo eje: %)."""
    t = rob.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(11, 6.2), facecolor=SUP); ax.set_facecolor(SUP)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(EJE); ax.grid(axis="x", color=GRID, lw=0.8); ax.tick_params(colors=TXT2, length=0)
    ax.axvline(0, color=TXT2, lw=1)
    series = (("cv_vs_defecto_mediana", "Ciclo de vida (aprox. FG)", "Ciclo de vida vs por defecto"),
              ("reactivo_vs_defecto_mediana", "Reactivo (market timing)", "Reactivo vs por defecto"))
    for col, estr, etiqueta in series:
        c = COLOR_ESTRATEGIA[estr]
        ax.scatter(t[col] * 100, t.index, s=70, color=c, edgecolor=SUP, linewidth=2, zorder=3, label=etiqueta)
    for i, r in t.iterrows():
        ax.plot([r.reactivo_vs_defecto_mediana * 100, r.cv_vs_defecto_mediana * 100], [i, i], color=GRID, lw=2, zorder=1)
        ax.annotate(f"{r.cv_vs_defecto_mediana * 100:+.0f}%".replace("+", "+"), (r.cv_vs_defecto_mediana * 100, i),
                    xytext=(9, 0), textcoords="offset points", va="center", fontsize=9, color=TXT)
        ax.annotate(f"{r.reactivo_vs_defecto_mediana * 100:+.1f}%".replace(".", ","), (r.reactivo_vs_defecto_mediana * 100, i),
                    xytext=(-9, 0), textcoords="offset points", va="center", ha="right", fontsize=9, color=TXT)
    ax.set_yticks(t.index); ax.set_yticklabels(t.caso, color=TXT)
    lo = min(t.reactivo_vs_defecto_mediana.min(), 0) * 100; hi = t.cv_vs_defecto_mediana.max() * 100
    ax.set_xlim(lo - 6, hi + 8)                # margen para las etiquetas a ambos lados
    ax.set_ylim(-1.4, len(t) - 0.5)          # fila libre abajo para la leyenda
    ax.set_xlabel("Pensión mediana frente al fondo por defecto (%)", color=TXT2)
    ax.legend(frameon=True, facecolor=SUP, edgecolor="none", framealpha=1, loc="lower center", ncol=2, fontsize=9.5, labelcolor=TXT)
    return _cerrar(fig, ax, "Robustez: la ventaja del ciclo de vida y el costo de reaccionar se mantienen con otros supuestos\n"
                            "10.000 escenarios por caso · mismas trayectorias para todas las estrategias",
                   "07_robustez.png")


def incertidumbre(pens: pd.DataFrame, puntual: float):
    """Cada punto = una historia alternativa (bootstrap estacionario): prima A–E vs ventaja del ciclo de vida."""
    fig, ax = _base()
    ax.grid(axis="x", color=GRID, lw=0.8)
    x = pens.prima_real_A_vs_E * 100; y = pens.cv_vs_defecto_mediana * 100
    gana = y > 0
    c = COLOR_ESTRATEGIA["Ciclo de vida (aprox. FG)"]
    ax.scatter(x[gana], y[gana], s=26, color=c, alpha=0.75, lw=0, label="el ciclo de vida gana en la mediana")
    ax.scatter(x[~gana], y[~gana], s=26, color=COLOR_ESTRATEGIA["Reactivo (market timing)"], alpha=0.75, lw=0,
               label="el fondo por defecto gana")
    ax.axhline(0, color=TXT2, lw=1); ax.axvline(0, color=TXT2, lw=1)
    ax.axhline(puntual * 100, color=c, lw=1, ls=(0, (4, 3)))
    ax.annotate(f"estimación puntual {puntual * 100:+.0f}%", (x.min(), puntual * 100), xytext=(0, 5),
                textcoords="offset points", fontsize=9, color=c)
    p5, p95 = np.percentile(y, [5, 95])
    ax.annotate(f"IC 90%: {p5:+.0f}% a {p95:+.0f}% · gana en {gana.mean():.0%} de las historias",
                (0.99, 0.04), xycoords="axes fraction", ha="right", fontsize=9.5, color=TXT)
    ax.set_xlabel("Prima real anual del Fondo A sobre el E en la historia remuestreada (p.p.)", color=TXT2)
    ax.set_ylabel("Ciclo de vida vs por defecto, pensión mediana (%)", color=TXT2)
    ax.legend(frameon=False, loc="upper left", fontsize=9, labelcolor=TXT)
    return _cerrar(fig, ax, f"¿Y si la historia 2002–2026 hubiera sido otra? {len(pens)} historias remuestreadas por bloques\n"
                            "la ventaja del ciclo de vida depende casi por completo de la prima de la renta variable",
                   "08_incertidumbre.png")


def glidepath(gp=config.GLIDEPATH, sexo="H"):
    """Exposición a activos de crecimiento por edad: oficial vs aproximación anterior vs ley vigente."""
    from . import simulacion
    edades = np.arange(20, 76)
    gm = np.array([gp["crecimiento_multifondos"][f] for f in config.FONDOS])
    retiro = config.EDAD_LEGAL[sexo]
    pos = np.clip((edades - 35) / (retiro - 35), 0, 1) * 3                    # aproximación anterior: A -> D
    antes = np.interp(pos, np.arange(5), gm)
    ley = simulacion.pesos_defecto(edades, sexo) @ gm
    oficial = simulacion.crecimiento_glidepath(edades, gp)
    consulta = simulacion.crecimiento_glidepath(edades, dict(gp, tope_inicial=0.90))
    fig, ax = _base()
    c_cv, c_def = COLOR_ESTRATEGIA["Ciclo de vida (aprox. FG)"], COLOR_ESTRATEGIA["Por defecto (ley)"]
    ax.plot(edades, oficial * 100, color=c_cv, lw=2.6)
    ax.plot(edades, consulta * 100, color=c_cv, lw=1.2, ls=(0, (4, 3)))
    ax.plot(edades, antes * 100, color=TXT2, lw=1.6, ls=(0, (1, 2)))
    ax.step(edades, ley * 100, where="post", color=c_def, lw=2)
    for f, g in zip(config.FONDOS, gm):
        ax.axhline(g * 100, color=GRID, lw=0.8, zorder=0)
        ax.annotate(f"Fondo {f}", (75.4, g * 100), va="center", fontsize=8.5, color=TXT2)
    etiquetas = ((21, oficial, "Fondos generacionales (SP, tope 95%)", c_cv, 5),
                 (21, consulta, "Consulta pública (tope 90%)", c_cv, -13),
                 (21, antes, "Aproximación anterior (A → D)", TXT2, -13),
                 (21, ley, "Ley de multifondos por defecto (B → C → D)", c_def, 5))
    for x, serie, txt, col, dy in etiquetas:
        ax.annotate(txt, (x, serie[x - 20] * 100), xytext=(0, dy), textcoords="offset points", fontsize=9, color=col)
    ax.axvline(retiro, color=EJE, lw=1); ax.annotate(f"retiro ({retiro})", (retiro, 3), xytext=(3, 0),
                                                     textcoords="offset points", fontsize=8.5, color=TXT2)
    ax.set_xlim(20, 78); ax.set_ylim(0, 100)
    ax.set_xlabel("Edad", color=TXT2); ax.set_ylabel("Activos de crecimiento (%)", color=TXT2)
    return _cerrar(fig, ax, "Trayectoria de inversión: exposición máxima a activos de crecimiento por edad\n"
                            "el glidepath oficial toma más riesgo que la ley actual durante toda la vida laboral",
                   "09_glidepath.png",
                   nota="Fuente: SP, minuta de consulta (jul-2026) y Res. Ex. 1195; cartera de multifondos a mar-2026. Elaboración propia.")


def escenarios_mercado(tab: pd.DataFrame, sexo="H"):
    """Pensión por escenario de mercado: fondo por defecto vs ciclo de vida (rango p5–p95, p25–p75, mediana)."""
    estr = ("Por defecto (ley)", "Ciclo de vida (aprox. FG)")
    t = tab[(tab.sexo == sexo) & tab.estrategia.isin(estr)]
    escen = list(dict.fromkeys(t.escenario))
    fig, ax = plt.subplots(figsize=(11, 5.6), facecolor=SUP); ax.set_facecolor(SUP)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(EJE); ax.grid(axis="x", color=GRID, lw=0.8); ax.tick_params(colors=TXT2, length=0)
    ticks, etiquetas = [], []
    for i, e in enumerate(escen[::-1]):
        for j, nombre in enumerate(estr):
            r = t[(t.escenario == e) & (t.estrategia == nombre)].iloc[0]
            y = i * 3 + (1 - j) * 0.9; col = COLOR_ESTRATEGIA[nombre]
            ax.plot([r.p5, r.p95], [y, y], color=col, lw=2, solid_capstyle="round")
            ax.plot([r.p25, r.p75], [y, y], color=col, lw=7, solid_capstyle="round")
            ax.plot(r.mediana, y, "o", ms=9, color=SUP, mec=col, mew=2.5)
            ax.annotate(f"{es(r.mediana)} UF", (r.p95, y), xytext=(8, 0), textcoords="offset points",
                        va="center", fontsize=9, color=TXT2)
        ticks.append(i * 3 + 0.45); etiquetas.append(e)
    ax.set_yticks(ticks); ax.set_yticklabels(etiquetas, color=TXT, fontsize=10)
    ax.plot([], [], color=COLOR_ESTRATEGIA[estr[0]], lw=7, label="Fondo por defecto (ley)")
    ax.plot([], [], color=COLOR_ESTRATEGIA[estr[1]], lw=7, label="Ciclo de vida (glidepath oficial)")
    ax.legend(frameon=False, loc="lower right", fontsize=9.5, labelcolor=TXT)
    ax.set_xlabel("Pensión mensual (UF de hoy)", color=TXT2)
    quien = "hombre, 25 a 65" if sexo == "H" else "mujer, 25 a 60"
    return _cerrar(fig, ax, f"¿Cuánto depende la pensión de los supuestos de mercado? ({quien}; 10.000 escenarios)\n"
                            "mismos regímenes, volatilidades y colas históricas; solo cambia el retorno esperado",
                   f"10_escenarios_mercado_{sexo}.png",
                   nota="Fuente: SP, BCCh (bono en UF a 10 años, 2,52%), J.P. Morgan LTCMA 2026 (MSCI ACWI 7,0% USD). Elaboración propia.")
