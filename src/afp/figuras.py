"""Figuras del proyecto.

Sistema común: el TÍTULO es el hallazgo (con su número, calculado desde los datos), el SUBTÍTULO dice qué se grafica y
en qué unidad, y el color se usa solo en lo que cuenta la historia (el resto en gris), con etiquetas directas en vez de
leyendas cuando se puede. La paleta categórica está validada para daltonismo; cada fondo y cada estrategia mantiene su
color en todas las figuras.
"""
import textwrap

import matplotlib
import matplotlib.dates  # noqa: E402
import matplotlib.ticker  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from . import config  # noqa: E402

SUP, TXT, TXT2, GRID, EJE = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0", "#c3c2b7"
GRIS, GRIS_TXT = "#bdbcb4", "#8a897f"
COLOR_FONDO = {"A": "#2a78d6", "B": "#eb6834", "C": "#1baf7a", "D": "#eda100", "E": "#e87ba4"}
COLOR_ESTRATEGIA = {"Por defecto (ley)": "#008300", "Ciclo de vida (aprox. FG)": "#4a3aa7",
                    "Reactivo (market timing)": "#e34948"}
NOMBRE = {"Por defecto (ley)": "Fondo por defecto (ley actual)",
          "Ciclo de vida (aprox. FG)": "Ciclo de vida (fondos generacionales)",
          "Reactivo (market timing)": "Se cambia al E tras caídas"}
FUENTE = "Fuente: Superintendencia de Pensiones, Banco Central de Chile, CMF. Elaboración propia."
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def _fuente_disponible():
    nombres = {f.name for f in font_manager.fontManager.ttflist}
    return next((f for f in ("Segoe UI", "Helvetica Neue", "Arial", "Liberation Sans") if f in nombres), "DejaVu Sans")


plt.rcParams.update({"font.family": _fuente_disponible(), "font.size": 10.5, "axes.titlesize": 11,
                     "xtick.labelsize": 10, "ytick.labelsize": 10, "axes.labelcolor": TXT2})


def es(x, dec=1):
    """Número con coma decimal y signo menos tipográfico (formato chileno)."""
    return f"{x:.{dec}f}".replace(".", ",").replace("-", "−")


def _fmt_eje(v, _pos=None):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",").replace("-", "−")


def pct(x, dec=0, signo=False):
    s = f"{x * 100:+.{dec}f}" if signo else f"{x * 100:.{dec}f}"
    return s.replace(".", ",").replace("-", "−") + "%"


def nombre(estr: str) -> str:
    return NOMBRE.get(estr, estr)


def _anios(ax, inicio=2004, fin=2026, paso=2):
    ax.set_xticks(pd.to_datetime([f"{y}-01-01" for y in range(inicio, fin + 1, paso)]))
    ax.set_xticklabels(range(inicio, fin + 1, paso))


def _estilo(ax, grilla="y"):
    ax.set_facecolor(SUP)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(EJE)
    ax.grid(axis=grilla, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=TXT2, length=0)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_fmt_eje))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_fmt_eje))


def _repeler(ax, etiquetas, sep_px=15):
    """Etiquetas al final de las series sin superponerse: [(x, y, texto, dict de estilo)], y en datos."""
    tr = ax.transData
    num = lambda x: matplotlib.dates.date2num(x) if isinstance(x, (pd.Timestamp, np.datetime64)) else x
    pts = sorted(((tr.transform((num(x), y))[1], x, y, txt, est) for x, y, txt, est in etiquetas), key=lambda z: z[0])
    ys = [p[0] for p in pts]
    for i in range(1, len(ys)):
        ys[i] = max(ys[i], ys[i - 1] + sep_px)
    for (y0, x, y, txt, est), yn in zip(pts, ys):
        ax.annotate(txt, (x, y), xytext=(6, (yn - y0) * 72 / ax.figure.dpi), textcoords="offset points", va="center", **est)


def _base(figsize=(11, 6.0), grilla="y"):
    fig, ax = plt.subplots(figsize=figsize, facecolor=SUP)
    _estilo(ax, grilla)
    return fig, ax


def _cerrar(fig, ax, titulo, nombre_archivo, subtitulo="", nota=FUENTE):
    """Título (hallazgo) y subtítulo alineados al borde izquierdo de la figura; nota de fuente abajo."""
    alto = fig.get_figheight()
    lin_t = textwrap.wrap(titulo, 106)
    lin_s = textwrap.wrap(subtitulo, 150) if subtitulo else []
    y = 1 - 0.16 / alto
    fig.text(0.012, y, "\n".join(lin_t), fontsize=15, fontweight="bold", color=TXT, va="top", linespacing=1.15)
    y -= (0.30 * len(lin_t) + 0.08) / alto
    if lin_s:
        fig.text(0.012, y, "\n".join(lin_s), fontsize=10.5, color=TXT2, va="top", linespacing=1.3)
        y -= (0.20 * len(lin_s) + 0.04) / alto
    fig.text(0.012, 0.012, nota, fontsize=8.5, color=GRIS_TXT)
    fig.tight_layout(rect=(0, 0.035, 1, y))
    ruta = config.FIGURAS / nombre_archivo
    fig.savefig(ruta, dpi=160, facecolor=SUP)
    plt.close(fig)
    return ruta


def _uf_actual() -> float:
    try:
        return float(pd.read_csv(config.DATA_RAW / "uf.csv").uf.iloc[-1])
    except Exception:
        return float("nan")


def _caida_maxima(serie: pd.Series) -> tuple[float, pd.Timestamp]:
    dd = serie / serie.cummax() - 1
    return float(dd.min()), dd.idxmin()


def _mes(fecha) -> str:
    fecha = pd.Timestamp(fecha)
    return f"{MESES[fecha.month - 1]} de {fecha.year}"


# ---------------------------------------------------------------------------
def indice_real(idx: pd.DataFrame):
    nivel = 100 * (1 + idx.fillna(0)).cumprod()
    anios = (nivel.index[-1] - nivel.index[0]).days / 365.25
    rent = {f: (nivel[f].iloc[-1] / 100) ** (1 / anios) - 1 for f in config.FONDOS}
    fig, ax = _base()
    for f in ("B", "C", "D"):
        ax.plot(nivel.index, nivel[f], color=GRIS, lw=1.2)
        ax.annotate(f"Fondo {f}  {pct(rent[f], 1)}", (nivel.index[-1], nivel[f].iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9.5, color=GRIS_TXT)
    for f in ("A", "E"):
        ax.plot(nivel.index, nivel[f], color=COLOR_FONDO[f], lw=2.2)
        ax.annotate(f"Fondo {f}  {pct(rent[f], 1)} real/año", (nivel.index[-1], nivel[f].iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=10.5, color=TXT, fontweight="bold")
    for f, txt_y in (("A", -34), ("E", -30)):
        dd, t = _caida_maxima(nivel[f])
        ax.annotate(f"{t.year}: el Fondo {f} cae {pct(-dd, 0)}", (t, nivel[f].loc[t]), xytext=(0, txt_y),
                    textcoords="offset points", ha="center", fontsize=9.5, color=TXT2,
                    arrowprops=dict(arrowstyle="-", color=TXT2, lw=0.8))
    ax.set_yscale("log"); ax.set_yticks([100, 150, 200, 300, 400]); ax.set_yticklabels(["100", "150", "200", "300", "400"])
    ax.minorticks_off()
    ax.set_xlim(nivel.index[0], nivel.index[-1] + pd.Timedelta(days=1700)); _anios(ax)
    return _cerrar(fig, ax, f"$100 invertidos en 2002 en el Fondo A valen hoy ${nivel['A'].iloc[-1]:.0f} reales; "
                            f"en el Fondo E, ${nivel['E'].iloc[-1]:.0f}",
                   "01_indice_real_multifondos.png",
                   "Valor real (en UF, descontada la inflación) de 100 invertidos en agosto de 2002, promedio del sistema "
                   "ponderado por afiliados · escala logarítmica · rentabilidad real anual a la derecha")


def regimenes(m: pd.DataFrame, gamma: np.ndarray, nombres: list):
    nivel = 100 * (1 + m).cumprod()
    etiqueta = gamma.argmax(1)
    fig, ax = _base()
    tonos = {1: ("#eda100", 0.20), 2: ("#e34948", 0.20)}
    for k, (col, a) in tonos.items():
        for i in np.flatnonzero(etiqueta == k):
            ax.axvspan(m.index[i] - pd.offsets.MonthBegin(1), m.index[i], color=col, alpha=a, lw=0)
    for f in ("A", "E"):
        ax.plot(nivel.index, nivel[f], color=COLOR_FONDO[f], lw=2.2)
        ax.annotate(f"Fondo {f}", (nivel.index[-1], nivel[f].iloc[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=10.5, color=TXT, fontweight="bold")
    ax.set_yscale("log"); ax.set_yticks([100, 150, 200, 300, 400]); ax.set_yticklabels(["100", "150", "200", "300", "400"])
    ax.minorticks_off()
    quiebre = next((m.index[t] for t in range(len(etiqueta)) if etiqueta[t] == 1 and (etiqueta[t:] == 1).mean() > 0.8), None)
    if quiebre is not None and len(nombres) > 1:
        ax.annotate(f"Régimen de {nombres[1].split(' (')[0].lower()}\n(desde {_mes(quiebre)})",
                    (quiebre + pd.Timedelta(days=30), 420), fontsize=9.5, color="#9a6a00", va="top")
    if len(nombres) > 2:
        crisis = m.index[np.flatnonzero(etiqueta == 2)]
        c08 = crisis[(crisis.year >= 2008) & (crisis.year <= 2009)]
        if len(c08):
            ax.annotate(f"Meses de {nombres[2].lower()}", (c08[0], 420), fontsize=9.5, color="#b0302f", va="top", ha="right")
    ax.set_ylim(90, 440)
    ax.set_xlim(m.index[0], m.index[-1] + pd.Timedelta(days=900)); _anios(ax)
    titulo = (f"Desde {_mes(quiebre)} el mercado chileno vive un régimen nuevo, en el que los fondos conservadores "
              f"se volvieron volátiles") if quiebre is not None else "Regímenes de mercado 2002–2026"
    return _cerrar(fig, ax, titulo, "02_regimenes_hmm.png",
                   "Régimen más probable cada mes según un modelo de Markov oculto de 3 estados (sombreado) · "
                   "valor real de 100 invertidos en los Fondos A y E, escala logarítmica")


def volatilidad(sigma: pd.DataFrame, quiebre: str = "2019-05-01"):
    s = sigma.resample("ME").mean().rolling(3, min_periods=1).mean() * 100
    antes, despues = s.loc[:quiebre].mean(), s.loc[quiebre:].mean()
    fig, ax = _base()
    ax.axvspan(pd.Timestamp(quiebre), s.index[-1], color="#eda100", alpha=0.10, lw=0)
    ax.plot(s.index, s["A"], color=GRIS, lw=1.2)
    ax.plot(s.index, s["C"], color=COLOR_FONDO["C"], lw=1.6, alpha=0.8)
    ax.plot(s.index, s["E"], color=COLOR_FONDO["E"], lw=2.4)
    ax.set_xlim(s.index[0], s.index[-1] + pd.Timedelta(days=900))
    fig.canvas.draw()
    _repeler(ax, [(s.index[-1], s[f].iloc[-1], f"Fondo {f}", dict(fontsize=10.5, color=c, fontweight=w))
                  for f, c, w in (("A", GRIS_TXT, "normal"), ("C", COLOR_FONDO["C"], "normal"), ("E", TXT, "bold"))])
    ax.annotate(f"Fondo E: {es(antes['E'])}% promedio\nantes de 2019", (pd.Timestamp("2013-06-01"), antes["E"]),
                xytext=(0, 95), textcoords="offset points", ha="center", fontsize=9.5, color=TXT2,
                arrowprops=dict(arrowstyle="-", color=TXT2, lw=0.8))
    ax.annotate(f"{es(despues['E'])}% desde 2019\n(el Fondo C: {es(despues['C'])}%)", (pd.Timestamp("2023-06-01"), despues["E"]),
                xytext=(0, 60), textcoords="offset points", ha="center", fontsize=9.5, color=TXT2,
                arrowprops=dict(arrowstyle="-", color=TXT2, lw=0.8))
    ax.set_ylabel("Volatilidad anual (%)")
    ax.set_xlim(s.index[0], s.index[-1] + pd.Timedelta(days=900)); _anios(ax)
    return _cerrar(fig, ax, f"Desde 2019 el Fondo E, el más conservador, es {despues['E'] / antes['E']:.1f} veces más volátil "
                            f"y se mueve casi como el Fondo C".replace(".", ","),
                   "03_volatilidad_garch.png",
                   "Volatilidad anualizada de los retornos reales diarios, estimada con un modelo GARCH(1,1) · promedio "
                   "móvil de 3 meses · sombreado: régimen de tasas volátiles")


def correlaciones(m: pd.DataFrame, ventana=36):
    ce = m["C"].rolling(ventana).corr(m["E"]).dropna()
    ae = m["A"].rolling(ventana).corr(m["E"]).dropna()
    fig, ax = _base()
    ax.axhline(0, color=EJE, lw=1)
    ax.plot(ae.index, ae, color=GRIS, lw=1.4)
    ax.plot(ce.index, ce, color=COLOR_FONDO["E"], lw=2.4)
    ax.annotate(f"C y E: {es(ce.iloc[-1], 2)}", (ce.index[-1], ce.iloc[-1]), xytext=(6, 0), textcoords="offset points",
                va="center", fontsize=10.5, color=TXT, fontweight="bold")
    ax.annotate(f"A y E: {es(ae.iloc[-1], 2)}", (ae.index[-1], ae.iloc[-1]), xytext=(6, 0), textcoords="offset points",
                va="center", fontsize=10, color=GRIS_TXT)
    t_min = ce.idxmin()
    ax.annotate(f"{t_min.year}: el E compensaba\nlas caídas del C ({es(ce.min(), 2)})", (t_min, ce.min()), xytext=(40, -6),
                textcoords="offset points", fontsize=9.5, color=TXT2, va="center",
                arrowprops=dict(arrowstyle="-", color=TXT2, lw=0.8))
    ax.annotate("1 = se mueven igual\n0 = independientes", (ce.index[0], 0.97), fontsize=9, color=GRIS_TXT, va="top")
    ax.set_ylim(-0.6, 1.0)
    ax.set_xlim(ce.index[0], ce.index[-1] + pd.Timedelta(days=1000)); _anios(ax, 2006)
    return _cerrar(fig, ax, f"El Fondo E dejó de proteger: su correlación con el Fondo C subió de {es(ce.min(), 2)} a "
                            f"{es(ce.iloc[-1], 2)}",
                   "04_correlaciones.png",
                   "Correlación de los retornos reales mensuales en ventanas móviles de 36 meses · si ambos caen juntos, "
                   "cambiarse al E ya no amortigua las pérdidas")


def _rangos(ax, filas, xmax, destacar):
    """Filas (p5, p25, mediana, p75, p95) como rangos horizontales; las no destacadas en gris."""
    for i, r in enumerate(filas):
        col = r["color"] if r["estr"] in destacar else GRIS
        ax.plot([r["p5"], r["p95"]], [i, i], color=col, lw=2, solid_capstyle="round")
        ax.plot([r["p25"], r["p75"]], [i, i], color=col, lw=8, solid_capstyle="round")
        ax.plot(r["mediana"], i, "o", ms=9, color=SUP, mec=col, mew=2.5)
        ax.annotate(f"{es(r['mediana'])} UF", (r["p95"], i), xytext=(8, 0), textcoords="offset points", va="center",
                    fontsize=10 if r["estr"] in destacar else 9, color=TXT if r["estr"] in destacar else GRIS_TXT,
                    fontweight="bold" if r["estr"] in destacar else "normal")


def montecarlo(tab: pd.DataFrame, sexo: str, meta_uf: float):
    t = tab.sort_values("mediana").reset_index(drop=True)
    tb = tab.set_index("estrategia")
    cv, dflt = tb.loc["Ciclo de vida (aprox. FG)", "mediana"], tb.loc["Por defecto (ley)", "mediana"]
    fig, ax = _base((11, 6.0), grilla="x")
    destacar = set(COLOR_ESTRATEGIA)
    filas = [{"estr": r.estrategia, "color": COLOR_ESTRATEGIA.get(r.estrategia, GRIS), "p5": r.p5, "p25": r.p25,
              "mediana": r.mediana, "p75": r.p75, "p95": r.p95} for r in t.itertuples()]
    _rangos(ax, filas, t.p95.max(), destacar)
    ax.axvline(meta_uf, color=TXT2, lw=1, ls=(0, (4, 3)))
    ax.annotate(f"meta: 40% del último sueldo ({es(meta_uf)} UF)", (meta_uf, len(t) - 0.45), xytext=(5, 0),
                textcoords="offset points", fontsize=9, color=TXT2)
    ax.set_yticks(range(len(t)))
    ax.set_yticklabels([nombre(e) for e in t.estrategia])
    for lab, e in zip(ax.get_yticklabels(), t.estrategia):
        lab.set_color(TXT if e in destacar else GRIS_TXT); lab.set_fontweight("bold" if e in destacar else "normal")
    ax.set_ylim(-0.6, len(t) - 0.2)
    ax.set_xlabel("Pensión mensual (UF de hoy)")
    quien = "hombre de 25 a 65 años" if sexo == "H" else "mujer de 25 a 60 años"
    return _cerrar(fig, ax, f"Si se repite la historia, el ciclo de vida deja una pensión mediana de {es(cv)} UF, "
                            f"{pct(cv / dflt - 1, 0, True)} frente al fondo por defecto",
                   f"05_montecarlo_{sexo}.png",
                   f"Pensión financiada con el 10% del trabajador, {quien}, sueldo inicial de 25 UF, 10.000 escenarios basados "
                   "en 2002–2026 · barra: 50% central de los resultados · línea: 90% central · círculo: mediana")


def bandas(dev: pd.DataFrame, b=config.BANDAS):
    b_min, b_max = b["permanente"]; b_tr = b["transicion"]
    x = dev.desviacion.values * 100
    p95 = np.percentile(np.abs(x), 95)
    fig, ax = _base()
    ax.hist(x, bins=np.arange(-4.5, 4.55, 0.1), color=COLOR_FONDO["A"], edgecolor=SUP, lw=0.5)
    ymax = ax.get_ylim()[1] * 1.12
    for s in (-1, 1):
        ax.axvspan(s * b_min * 100, s * b_max * 100, color="#e34948", alpha=0.16, lw=0)
        ax.axvline(s * b_tr * 100, color=TXT2, lw=1, ls=(0, (4, 3)))
        ax.axvspan(s * p95 * 0, s * p95, color=COLOR_FONDO["A"], alpha=0.06, lw=0)
    ax.annotate("Zona de premio o castigo\n(desde ±2,4% a ±2,9%)", (b_min * 100 - 0.1, ymax * 0.80), fontsize=9.5,
                color="#b0302f", ha="right")
    ax.annotate(f"Transición ±{es(b_tr * 100, 0)}%\n({b['transicion_vigencia']})", (b_tr * 100 - 0.08, ymax * 0.55),
                fontsize=9.5, color=TXT2, ha="right")
    ax.annotate(f"95% de los casos:\nentre ±{es(p95, 2)} puntos", (0, ymax * 0.93), ha="center", fontsize=10.5,
                color=TXT, fontweight="bold", va="top")
    ax.set_ylim(0, ymax); ax.set_xlim(-4.6, 4.6)
    ax.set_xlabel("Rentabilidad de 36 meses de la AFP menos la de sus pares (puntos porcentuales al año)")
    ax.set_ylabel("Meses-AFP observados")
    return _cerrar(fig, ax, f"Las bandas de premios y castigos son {b_min * 100 / p95:.0f} veces más anchas que las "
                            "diferencias históricas entre AFP: casi ninguna habría pagado o cobrado",
                   "06_bandas_desviaciones.png",
                   "Distribución de cuánto se desvió cada AFP de sus pares en ventanas de 36 meses, 2005–2026 · "
                   "rojo: zona en que la reforma aplica premios o castigos")


def robustez(rob: pd.DataFrame):
    t = rob.iloc[::-1].reset_index(drop=True)
    fig, ax = _base((11, 7.0), grilla="x")
    ax.axvline(0, color=TXT2, lw=1)
    c_cv, c_re = COLOR_ESTRATEGIA["Ciclo de vida (aprox. FG)"], COLOR_ESTRATEGIA["Reactivo (market timing)"]
    for i, r in t.iterrows():
        ax.plot([r.reactivo_vs_defecto_mediana * 100, r.cv_vs_defecto_mediana * 100], [i, i], color=GRID, lw=2, zorder=1)
        ax.scatter(r.cv_vs_defecto_mediana * 100, i, s=80, color=c_cv, edgecolor=SUP, linewidth=2, zorder=3)
        ax.scatter(r.reactivo_vs_defecto_mediana * 100, i, s=80, color=c_re, edgecolor=SUP, linewidth=2, zorder=3)
        ax.annotate(pct(r.cv_vs_defecto_mediana, 0, True), (r.cv_vs_defecto_mediana * 100, i), xytext=(9, 0),
                    textcoords="offset points", va="center", fontsize=9.5, color=TXT)
        ax.annotate(pct(r.reactivo_vs_defecto_mediana, 1, True), (r.reactivo_vs_defecto_mediana * 100, i), xytext=(-9, 0),
                    textcoords="offset points", va="center", ha="right", fontsize=9.5, color=TXT)
    n = len(t)
    ax.annotate("Ciclo de vida (fondos generacionales)", (t.cv_vs_defecto_mediana.iloc[-1] * 100, n - 1), xytext=(0, 14),
                textcoords="offset points", ha="center", fontsize=10, color=c_cv, fontweight="bold")
    ax.annotate("Se cambia al E tras caídas", (t.reactivo_vs_defecto_mediana.iloc[-1] * 100, n - 1), xytext=(0, 14),
                textcoords="offset points", ha="center", fontsize=10, color=c_re, fontweight="bold")
    ax.set_yticks(t.index); ax.set_yticklabels(t.caso, color=TXT)
    lo = min(t.reactivo_vs_defecto_mediana.min(), 0) * 100; hi = t.cv_vs_defecto_mediana.max() * 100
    ax.set_xlim(lo - 8, hi + 8); ax.set_ylim(-0.6, n + 0.3)
    ax.set_xlabel("Pensión mediana frente al fondo por defecto (%)")
    gana = int((t.cv_vs_defecto_mediana > 0).sum()); pierde = int((t.reactivo_vs_defecto_mediana < 0).sum())
    titulo = (f"En los {n} supuestos probados, el ciclo de vida gana y cambiarse al E tras las caídas pierde"
              if gana == n and pierde == n else
              f"El ciclo de vida gana en {gana} de {n} supuestos, y cambiarse al E tras las caídas pierde en {pierde} de {n}")
    return _cerrar(fig, ax, titulo,
                   "07_robustez.png",
                   "Pensión mediana de cada estrategia frente al fondo por defecto, repitiendo la simulación con supuestos "
                   "alternativos · 10.000 escenarios por caso, los mismos para todas las estrategias")


def incertidumbre(pens: pd.DataFrame, puntual: float):
    x = pens.prima_real_A_vs_E * 100; y = pens.cv_vs_defecto_mediana * 100
    gana = y > 0
    c_cv, c_re = COLOR_ESTRATEGIA["Ciclo de vida (aprox. FG)"], COLOR_ESTRATEGIA["Reactivo (market timing)"]
    fig, ax = _base(grilla="both")
    ax.axhline(0, color=TXT2, lw=1); ax.axvline(0, color=TXT2, lw=1)
    ax.scatter(x[gana], y[gana], s=30, color=c_cv, alpha=0.75, lw=0)
    ax.scatter(x[~gana], y[~gana], s=30, color=c_re, alpha=0.85, lw=0)
    ax.axhline(puntual * 100, color=c_cv, lw=1, ls=(0, (4, 3)))
    ax.annotate(f"con la historia real 2002–2026: {pct(puntual, 0, True)}", (x.max(), puntual * 100), xytext=(0, 6),
                textcoords="offset points", fontsize=9.5, color=c_cv, ha="right")
    ax.annotate(f"Gana el ciclo de vida\n({gana.mean() * 100:.0f}% de las historias)", (0.4, y.max()), ha="left",
                va="top", fontsize=10.5, color=c_cv, fontweight="bold")
    ax.annotate("Gana el fondo por defecto:\ncuando las acciones rinden menos que los bonos", (0.4, -6), ha="left",
                va="top", fontsize=10, color=c_re, fontweight="bold")
    ax.set_ylim(y.min() - 40, y.max() + 15)
    ax.set_xlabel("Cuánto más rindió al año el Fondo A que el E en esa historia (puntos porcentuales)")
    ax.set_ylabel("Ciclo de vida vs fondo por defecto (%)")
    p5, p95 = np.percentile(y, [5, 95])
    return _cerrar(fig, ax, f"La ventaja del ciclo de vida es una apuesta a las acciones: va de {pct(p5 / 100, 0, True)} "
                            f"a {pct(p95 / 100, 0, True)} según cómo rindan",
                   "08_incertidumbre.png",
                   f"Cada punto es una historia alternativa de 24 años ({len(pens)} en total), armada reordenando bloques de "
                   "meses reales · intervalo de 90% de la ventaja en la pensión mediana")


def glidepath(gp=config.GLIDEPATH, sexo="H"):
    from . import simulacion
    edades = np.arange(20, 76)
    gm = np.array([gp["crecimiento_multifondos"][f] for f in config.FONDOS])
    retiro = config.EDAD_LEGAL[sexo]
    ley = simulacion.pesos_defecto(edades, sexo) @ gm
    oficial = simulacion.crecimiento_glidepath(edades, gp)
    fig, ax = _base()
    c_cv, c_def = COLOR_ESTRATEGIA["Ciclo de vida (aprox. FG)"], COLOR_ESTRATEGIA["Por defecto (ley)"]
    for f, g in zip(config.FONDOS, gm):
        ax.axhline(g * 100, color=GRID, lw=0.9, zorder=0)
        ax.annotate(f"Fondo {f} hoy", (75.4, g * 100), va="center", fontsize=9, color=GRIS_TXT)
    e_fina = np.linspace(20, 75, 1101)
    ley_f = simulacion.pesos_defecto(np.floor(e_fina).astype(int), sexo) @ gm
    ofi_f = np.interp(e_fina, edades, oficial)
    ax.fill_between(e_fina, ley_f * 100, ofi_f * 100, where=ofi_f > ley_f, color=c_cv, alpha=0.08, lw=0)
    ax.plot(edades, oficial * 100, color=c_cv, lw=2.8)
    ax.step(edades, ley * 100, where="post", color=c_def, lw=2.2)
    ax.annotate("Fondos generacionales (desde 2027)", (21, oficial[1] * 100), xytext=(0, 7), textcoords="offset points",
                fontsize=10.5, color=c_cv, fontweight="bold")
    ax.annotate("Fondo por defecto de la ley actual", (21, ley[1] * 100), xytext=(0, 7), textcoords="offset points",
                fontsize=10.5, color=c_def, fontweight="bold")
    i45 = 45 - 20
    ax.annotate(f"a los 45 años: {pct(oficial[i45])}\nvs {pct(ley[i45])} en acciones y similares", (45, (oficial[i45] + ley[i45]) * 50),
                ha="center", va="center", fontsize=9.5, color=TXT2)
    ax.axvline(retiro, color=EJE, lw=1)
    ax.annotate(f"edad legal de pensión ({retiro})", (retiro, 3), xytext=(4, 0), textcoords="offset points",
                fontsize=9, color=GRIS_TXT)
    ax.set_xlim(20, 80); ax.set_ylim(0, 105)
    ax.set_xlabel("Edad"); ax.set_ylabel("Activos de crecimiento (%)")
    return _cerrar(fig, ax, "Los fondos generacionales invertirán con más riesgo que el fondo por defecto actual "
                            "a toda edad, y lo bajarán de a poco hasta el retiro",
                   "09_glidepath.png",
                   "Máximo de activos de crecimiento (acciones, deuda de alto rendimiento y alternativos) por edad · "
                   "líneas grises: cuánto tiene hoy cada multifondo",
                   nota="Fuente: SP, Régimen de Inversión (Res. Ex. 1195) y minuta de consulta (jul-2026); cartera de "
                        "multifondos a mar-2026. Elaboración propia.")


def escenarios_mercado(tab: pd.DataFrame, sexo="H"):
    estr = ("Por defecto (ley)", "Ciclo de vida (aprox. FG)")
    t = tab[(tab.sexo == sexo) & tab.estrategia.isin(estr)]
    escen = list(dict.fromkeys(t.escenario))
    med = t.set_index(["escenario", "estrategia"]).mediana
    ventaja = {e: med[(e, estr[1])] / med[(e, estr[0])] - 1 for e in escen}
    fig, ax = _base((11, 6.2), grilla="x")
    ticks, etiquetas = [], []
    for i, e in enumerate(escen[::-1]):
        for j, n in enumerate(estr):
            r = t[(t.escenario == e) & (t.estrategia == n)].iloc[0]
            yy = i * 3 + (1 - j) * 0.9; col = COLOR_ESTRATEGIA[n]
            ax.plot([r.p5, r.p95], [yy, yy], color=col, lw=2, solid_capstyle="round")
            ax.plot([r.p25, r.p75], [yy, yy], color=col, lw=8, solid_capstyle="round")
            ax.plot(r.mediana, yy, "o", ms=9, color=SUP, mec=col, mew=2.5)
            ax.annotate(f"{es(r.mediana)} UF", (r.p95, yy), xytext=(8, 0), textcoords="offset points", va="center",
                        fontsize=9.5, color=TXT2)
        ax.annotate(f"ventaja del ciclo de vida: {pct(ventaja[e], 0, True)}", (0.995, i * 3 + 1.55),
                    xycoords=("axes fraction", "data"), ha="right", fontsize=10, color=TXT, fontweight="bold")
        ticks.append(i * 3 + 0.45); etiquetas.append(e)
    legibles = {"Histórico 2002-2026": "Se repite 2002–2026", "Consenso de mercado 2026": "Expectativas 2026\n(consenso)",
                "Prima de crecimiento nula": "Acciones rinden\nigual que bonos"}
    ax.set_yticks(ticks); ax.set_yticklabels([legibles.get(e, e) for e in etiquetas], color=TXT, fontsize=10.5)
    ax.plot([], [], color=COLOR_ESTRATEGIA[estr[0]], lw=8, label=nombre(estr[0]))
    ax.plot([], [], color=COLOR_ESTRATEGIA[estr[1]], lw=8, label=nombre(estr[1]))
    ax.legend(frameon=False, loc="lower right", fontsize=10, labelcolor=TXT)
    ax.set_ylim(-0.6, len(escen) * 3 - 0.9)
    ax.set_xlabel("Pensión mensual (UF de hoy)")
    h, c = ventaja.get("Histórico 2002-2026", np.nan), ventaja.get("Consenso de mercado 2026", np.nan)
    quien = "hombre de 25 a 65 años" if sexo == "H" else "mujer de 25 a 60 años"
    return _cerrar(fig, ax, f"Con expectativas de mercado de 2026, la ventaja del ciclo de vida cae de "
                            f"{pct(h, 0, True)} a {pct(c, 0, True)}",
                   f"10_escenarios_mercado_{sexo}.png",
                   f"Pensión financiada con el 10% del trabajador, {quien}, 10.000 escenarios con la volatilidad y las "
                   "crisis de 2002–2026; solo cambia el retorno esperado · barra: 50% central · línea: 90% central",
                   nota="Fuente: SP, BCCh (bono en UF a 10 años, 2,52%), J.P. Morgan LTCMA 2026 (acciones globales 7,0% en USD). "
                        "Elaboración propia.")


def pilares(tab: pd.DataFrame, sexo="H"):
    capas = (("autofinanciada_10", "Tu cotización (10%)", COLOR_FONDO["A"]),
             ("empleador_cci", "Cotización del empleador", COLOR_FONDO["C"]),
             ("crp", "Rentabilidad protegida", COLOR_FONDO["D"]),
             ("pgu", "PGU", COLOR_ESTRATEGIA["Ciclo de vida (aprox. FG)"]))
    tab = tab.reset_index(drop=True)
    fig, ax = _base()
    x = np.arange(len(tab)); base = np.zeros(len(tab))
    for col, n, color in capas:
        ax.bar(x, tab[col], bottom=base, width=0.58, color=color, edgecolor=SUP, linewidth=2, label=n)
        base += tab[col].values
    for i, r in tab.iterrows():
        ax.annotate(f"{es(r.total)} UF\n{pct(r.tasa_reemplazo_total)} del sueldo", (i, r.total), xytext=(0, 6),
                    textcoords="offset points", ha="center", fontsize=10, color=TXT, fontweight="bold")
    uf = _uf_actual()
    ax.set_xticks(x); ax.set_xticklabels([f"Sueldo de {es(s, 0)} UF\n(≈ ${es(s * uf / 1e6, 1)} millones)" for s in tab.sueldo_inicial_uf],
                                         color=TXT)
    ax.set_ylabel("Pensión mensual mediana (UF de hoy)")
    ax.set_ylim(0, tab.total.max() * 1.22)
    ax.legend(frameon=False, loc="upper left", fontsize=10, labelcolor=TXT, ncol=4)
    quien = "hombre de 25 a 65 años" if sexo == "H" else "mujer de 25 a 60 años (PGU desde los 65)"
    return _cerrar(fig, ax, f"La PGU hace progresiva la pensión: reemplaza {pct(tab.tasa_reemplazo_total.iloc[0])} del sueldo "
                            f"con {es(tab.sueldo_inicial_uf.iloc[0], 0)} UF y {pct(tab.tasa_reemplazo_total.iloc[-1])} con "
                            f"{es(tab.sueldo_inicial_uf.iloc[-1], 0)} UF",
                   f"11_pension_total_{sexo}.png",
                   f"Pensión total por capas con la reforma de 2025 (Ley 21.735), {quien}, fondo por defecto, expectativas "
                   "de mercado de 2026 · porcentaje = tasa de reemplazo sobre el último sueldo",
                   nota="Fuente: Ley 21.735 (Nota Técnica SPS, ago-2025), SP (PGU feb-2026), BCCh, J.P. Morgan LTCMA 2026. "
                        "Elaboración propia.")


def glidepath_optimo(res: pd.DataFrame, gamma: float = 3.0, sexo: str = "H"):
    from . import optimo, simulacion
    gp = config.GLIDEPATH; retiro = config.EDAD_LEGAL[sexo]
    edades = np.arange(20, retiro + 1)
    gm = np.array([gp["crecimiento_multifondos"][f] for f in config.FONDOS])
    c_cv, c_def, c_opt = COLOR_ESTRATEGIA["Ciclo de vida (aprox. FG)"], COLOR_ESTRATEGIA["Por defecto (ley)"], COLOR_FONDO["B"]
    fig, ax = _base()
    ofi = simulacion.crecimiento_glidepath(edades) * 100
    ley = simulacion.pesos_defecto(edades, sexo) @ gm * 100
    ax.step(edades, ley, where="post", color=GRIS, lw=1.8)
    ax.plot(edades, ofi, color=c_cv, lw=2.8)
    textos = [(ofi[-1], "Fondos generacionales (oficial)", c_cv, "bold"), (ley[-1], "Fondo por defecto actual", GRIS_TXT, "normal")]
    r_con = None
    for con, ls in ((True, "-"), (False, (0, (4, 3)))):
        r = res[(res.gamma == gamma) & (res.con_reforma == con) & (res.sexo == sexo)].iloc[0]
        g = optimo.crecimiento_parametrico(edades, r.g0, r.a1, r.g1, retiro) * 100
        ax.plot(edades, g, color=c_opt, lw=2.2 if con else 1.6, ls=ls)
        textos.append((g[-1], f"Óptimo {'contando' if con else 'sin contar'} la PGU", c_opt, "bold" if con else "normal"))
        if con:
            r_con = r
    for yv, txt, col, w in sorted(textos, key=lambda z: z[0]):
        ax.annotate(txt, (retiro, yv), xytext=(8, 0), textcoords="offset points", va="center", fontsize=10, color=col,
                    fontweight=w)
    ax.set_xlim(20, retiro + 16); ax.set_ylim(0, 105)
    ax.set_xlabel("Edad"); ax.set_ylabel("Activos de crecimiento (%)")
    lejos = res.optimo_vs_oficial.max()
    return _cerrar(fig, ax, f"El diseño oficial queda a no más de {pct(lejos, 1)} del óptimo; contando la PGU convendría "
                            f"llegar al retiro con {pct(r_con.g1)} en activos de crecimiento, no {pct(ofi[-1] / 100)}",
                   "12_glidepath_optimo.png",
                   f"Trayectoria que maximiza el bienestar de la pensión total (utilidad CRRA, aversión al riesgo γ = {gamma:g}), "
                   "evaluada en escenarios distintos a los usados para encontrarla · hombre, sueldo de 25 UF",
                   nota="Familia buscada: meseta hasta una edad y luego baja lineal hasta el retiro. Expectativas de mercado "
                        "2026. Elaboración propia.")


def poblacion_quintiles(q: pd.DataFrame, meta: float = config.SIM["tasa_reemplazo_meta"]):
    fig, axes = plt.subplots(1, 2, figsize=(11, 6.0), facecolor=SUP, sharey=True)
    for ax, sexo in zip(axes, ("H", "M")):
        _estilo(ax)
        t = q[q.sexo == sexo].reset_index(drop=True); x = np.arange(len(t))
        ax.bar(x - 0.2, t.tr_10_mediana * 100, 0.38, color=GRIS, label="Solo con tu 10%")
        ax.bar(x + 0.2, t.tr_total_mediana * 100, 0.38, color=COLOR_ESTRATEGIA["Ciclo de vida (aprox. FG)"],
               label="Con la reforma y la PGU")
        for i, r in t.iterrows():
            ax.annotate(pct(r.tr_total_mediana), (i + 0.2, r.tr_total_mediana * 100), xytext=(0, 4),
                        textcoords="offset points", ha="center", fontsize=10, color=TXT, fontweight="bold")
            ax.annotate(pct(r.tr_10_mediana), (i - 0.2, r.tr_10_mediana * 100), xytext=(0, 4),
                        textcoords="offset points", ha="center", fontsize=8.5, color=GRIS_TXT)
        ax.axhline(meta * 100, color=TXT2, lw=1, ls=(0, (4, 3)))
        ax.set_xticks(x); ax.set_xticklabels([f"{'Más pobre' if k == 1 else 'Más rico' if k == 5 else f'Q{k}'}\n{es(v, 0)} UF"
                                              for k, v in zip(t.quintil, t.sueldo_ref_mediano_uf)], color=TXT)
        ax.set_title("Hombres" if sexo == "H" else "Mujeres (PGU desde los 65)", loc="left", fontsize=12,
                     color=TXT, fontweight="bold")
    axes[0].set_ylabel("Tasa de reemplazo mediana (% del último sueldo)")
    axes[0].annotate("meta 40%", (-0.5, meta * 100), xytext=(0, 3), textcoords="offset points", fontsize=9, color=TXT2)
    axes[0].legend(frameon=False, loc="upper right", fontsize=10, labelcolor=TXT)
    h = q[q.sexo == "H"].set_index("quintil")
    return _cerrar(fig, axes[0], f"La reforma lleva la pensión del 20% más pobre de {pct(h.loc[1, 'tr_10_mediana'])} a "
                                 f"{pct(h.loc[1, 'tr_total_mediana'])} de su sueldo; al 20% más rico, de "
                                 f"{pct(h.loc[5, 'tr_10_mediana'])} a {pct(h.loc[5, 'tr_total_mediana'])}",
                   "13_poblacion_quintiles.png",
                   "Microsimulación de 20.000 personas con ingresos, lagunas y género calibrados con datos de la SP · "
                   "quintiles según el sueldo a los 40 años · fondo por defecto, expectativas de mercado de 2026",
                   nota="Fuente: SP (ingresos y densidad de cotización 2026), Ley 21.735, BCCh, J.P. Morgan LTCMA 2026. "
                        "Elaboración propia.")


def brecha_genero(b: pd.DataFrame):
    t = b.iloc[::-1].reset_index(drop=True)
    brecha = -b.attrs["brecha"]
    top = t.aporte_pp_brecha.idxmax()
    fig, ax = _base((11, 5.4), grilla="x")
    colores = [COLOR_ESTRATEGIA["Reactivo (market timing)"] if i == top else (EJE if "Residuo" in f else GRIS)
               for i, f in enumerate(t.factor)]
    ax.barh(t.index, t.aporte_pp_brecha * 100, 0.58, color=colores)
    for i, r in t.iterrows():
        ax.annotate(f"{es(r.aporte_pp_brecha * 100)} puntos ({pct(r.aporte_pp_brecha / brecha)} de la brecha)",
                    (r.aporte_pp_brecha * 100, i), xytext=(6, 0), textcoords="offset points", va="center",
                    fontsize=10.5 if i == top else 10, color=TXT if i == top else TXT2,
                    fontweight="bold" if i == top else "normal")
    ax.set_yticks(t.index)
    ax.set_yticklabels(["Residuo" if "Residuo" in f else f.split(" (")[0] for f in t.factor], color=TXT)
    ax.set_xlim(0, t.aporte_pp_brecha.max() * 100 * 1.55)
    ax.set_xlabel("Puntos porcentuales de la brecha de pensión total")
    f_top = t.factor.iloc[top].split(" (")[0].lower()
    return _cerrar(fig, ax, f"La {f_top} explica {pct(t.aporte_pp_brecha.iloc[top] / brecha)} de la brecha de género: "
                            f"la pensión de una mujer es {pct(brecha)} menor",
                   "14_brecha_genero.png",
                   "Aporte de cada diferencia entre mujeres y hombres a la brecha de pensión total mediana (descomposición "
                   "de Shapley: promedio sobre todos los órdenes posibles) · edad de pensión: 60 vs 65 años",
                   nota="Microsimulación de 20.000 personas, fondo por defecto, expectativas de mercado 2026. Mortalidad: tablas "
                        "CMF 2020. Elaboración propia.")


def prediccion_regimenes(wf: pd.DataFrame, comp: pd.DataFrame):
    base = wf["Normal (sin regímenes)"]
    fig, ax = _base()
    ax.axhline(0, color=TXT2, lw=1)
    estilos = {"HMM constante": (COLOR_FONDO["A"], "-", 2.6, "Modelo de regímenes"),
               "HMM con macro (TVTP)": (COLOR_FONDO["B"], (0, (4, 3)), 2.0, "Regímenes + macro (IPC, TPM, dólar, Imacec)")}
    for col, (c, ls, lw, lab) in estilos.items():
        s = (wf[col] - base).cumsum()
        ax.plot(s.index, s, color=c, lw=lw, ls=ls)
        ax.annotate(lab, (s.index[-1], s.iloc[-1]), xytext=(6, 10 if "macro" not in lab else -12),
                    textcoords="offset points", fontsize=10, color=c, fontweight="bold")
    ax.annotate("Modelo simple sin regímenes (= 0)", (base.index[-1], 0), xytext=(6, 5), textcoords="offset points",
                fontsize=9.5, color=TXT2)
    ax.set_xlim(base.index[0], base.index[-1] + pd.Timedelta(days=1700)); _anios(ax, 2015, 2026, 1)
    ax.set_ylabel("Ventaja predictiva acumulada (log-score)")
    t = comp.set_index("modelo")
    return _cerrar(fig, ax, "Los regímenes ayudan a predecir el mes siguiente, pero la macro chilena no agrega nada",
                   "15_regimenes_macro.png",
                   "Predicción fuera de muestra, 2015–2026: cada año se reestima con datos pasados y se predice el mes siguiente · "
                   f"regímenes vs modelo simple: p = {es(t.loc['Normal (sin regímenes)', 'p_valor'], 3)} · con macro vs sin macro: "
                   f"p = {es(t.loc['HMM constante', 'p_valor'], 2)}",
                   nota="Walk-forward con test de Diebold-Mariano. Macro: mindicador.cl (IPC, TPM, dólar, Imacec). Elaboración propia.")


def comisiones(tab: pd.DataFrame):
    t = tab.sort_values("comision").reset_index(drop=True)
    fig, ax = _base((11, 6.2), grilla="x")
    y = np.arange(len(t))[::-1]
    c_logro, c_nec = COLOR_FONDO["A"], COLOR_ESTRATEGIA["Reactivo (market timing)"]
    for yi, r in zip(y, t.itertuples()):
        lo, hi = (r.alfa_comun - 1.96 * r.ee_alfa_comun) * 100, (r.alfa_comun + 1.96 * r.ee_alfa_comun) * 100
        ax.plot([lo, hi], [yi, yi], color=c_logro, lw=2.5, alpha=0.3, solid_capstyle="round")
        ax.plot(r.alfa_comun * 100, yi, "o", ms=9, color=c_logro)
        if r.rentabilidad_extra_para_compensar > 0:
            ax.plot(r.rentabilidad_extra_para_compensar * 100, yi, "|", ms=20, mew=3, color=c_nec)
        costo = (f"cuesta {es(r.costo_pension_pct_vs_mas_barata * 100, 1)}% de tu pensión" if r.costo_pension_pct_vs_mas_barata > 0
                 else "la más barata")
        ax.annotate(f"comisión {es(r.comision * 100, 2)}% · {costo}", (0.995, yi), xycoords=("axes fraction", "data"),
                    ha="right", va="center", fontsize=9.5, color=TXT2)
    ax.axvline(0, color=TXT2, lw=1)
    ax.set_yticks(y); ax.set_yticklabels(t.afp, color=TXT, fontweight="bold")
    ax.set_xlim(-1.3, 2.3); ax.set_ylim(-0.6, len(t) - 0.4)
    ax.plot([], [], "o", ms=9, color=c_logro, label="Lo que rindió frente a las demás AFP (nov-2019 a ago-2026, rango de 95%)")
    ax.plot([], [], "|", ms=14, mew=3, color=c_nec, label="Lo que necesitaría rendir de más para compensar su comisión")
    ax.legend(frameon=False, loc="lower left", fontsize=10, labelcolor=TXT, bbox_to_anchor=(-0.08, 1.0), ncol=1)
    ax.set_xlabel("Rentabilidad real al año, en puntos porcentuales (promedio de los 5 fondos)")
    cara = t.iloc[t.comision.idxmax()]
    return _cerrar(fig, ax, f"Ninguna AFP rindió lo suficiente para compensar su comisión: estar en la más cara cuesta "
                            f"{es(cara.costo_pension_pct_vs_mas_barata * 100, 1)}% de la pensión",
                   "16_comisiones.png",
                   "La comisión se cobra sobre el sueldo, aparte del 10%; su costo en pensión es lo que ese dinero habría "
                   "financiado si se ahorrara · comparación contra la AFP más barata (Uno)",
                   nota="Fuente: SP (comisiones vigentes desde el 01-10-2025 y valores cuota). Hombre tipo, fondo por defecto, "
                        "expectativas de mercado 2026. Elaboración propia.")
