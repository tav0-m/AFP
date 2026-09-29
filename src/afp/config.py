"""Parámetros centrales del proyecto. Todo supuesto vive aquí, no escondido en el código."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DATA_RAW = RAIZ / "data" / "raw"
DATA_PROC = RAIZ / "data" / "processed"
REPORTS = RAIZ / "reports"
FIGURAS = REPORTS / "figuras"

FONDOS = ["A", "B", "C", "D", "E"]

# --- Calidad de datos -------------------------------------------------------
UMBRAL_RETORNO_DIARIO = 0.10      # |retorno| diario sobre este valor => revisar (fusiones)
INICIO_MULTIFONDOS = "2002-08-01"  # fondos A, B y D parten en esta fecha

# --- Pensión -----------------------------------------------------------------
TITRP = 0.0345                    # Circular SP N.º 2417, vigente desde jul-2026
TITRP_VIGENCIA = "2026-07"
EDAD_LEGAL = {"H": 65, "M": 60}
EDAD_MAX_TABLA = 110

# --- Simulación Monte Carlo (escenario base; todo editable) ----------------
SIM = {
    "n_simulaciones": 10_000,
    "semilla": 20260927,
    "edad_inicio": 25,
    "anio_inicio": 2026,
    "sueldo_inicial_uf": 25.0,        # ~ $1,0 millón mensual con UF de sep-2026
    "crecimiento_real_sueldo": 0.015,  # anual, hasta los 50
    "edad_fin_crecimiento": 50,
    "tasa_cotizacion": 0.10,          # cotización obligatoria a la cuenta individual
    "densidad_cotizacion": 0.60,      # fracción de meses con cotización
    "ajuste_retorno_anual": 0.0,      # castigo uniforme a retornos históricos (sensibilidad)
    "tasa_reemplazo_meta": 0.40,
}

# Regla "reactiva" (market timing): lo que suele hacer un afiliado que reacciona a pérdidas
REACTIVO = {
    "umbral_caida_3m": -0.06,   # si el fondo actual cae más de 6% real en 3 meses -> se va al E
    "meses_minimos_en_E": 6,
    "umbral_recuperacion_3m": 0.05,  # vuelve cuando el fondo A sube más de 5% en 3 meses
    "desfase_meses": 1,         # el traspaso se ejecuta al mes siguiente de la señal
}

# Bandas de desempeño de los fondos generacionales. Oficial (SP, Res. Ex. 1195, sep-2026):
# evaluación mensual, ventana móvil de 36 meses, bandas de 240 a 290 p.b. anuales sobre la
# cartera de referencia. Transición: banda de 400 p.b. (±4,0%) entre el 01-04-2028 y el 31-03-2031.
# Aquí se usa como proxy el promedio ponderado de las demás AFP.
BANDAS = {"ventana_meses": 36,
          "anchos_anuales": [0.010, 0.015, 0.020, 0.024, 0.029, 0.040],
          "permanente": (0.024, 0.029),
          "transicion": 0.040, "transicion_vigencia": "abr-2028 a mar-2031"}

# Robustez: supuestos alternativos para verificar que las conclusiones no dependen del escenario base.
# Cada caso = (nombre, cambios a SIM, cambios a escenarios, cambios a la regla reactiva, sexo)
ROBUSTEZ = [
    ("Escenario base (hombre)", {}, {}, {}, "H"),
    ("Mujer (retiro a los 60)", {}, {}, {}, "M"),
    ("Sueldo sin crecimiento real", {"crecimiento_real_sueldo": 0.0}, {}, {}, "H"),
    ("Sueldo crece 3% real/año", {"crecimiento_real_sueldo": 0.03}, {}, {}, "H"),
    ("Empieza a cotizar a los 35", {"edad_inicio": 35}, {}, {}, "H"),
    ("Retornos −1 p.p. al año", {}, {"ajuste_retorno_anual": 0.01}, {}, "H"),
    ("Retornos −2 p.p. al año", {}, {"ajuste_retorno_anual": 0.02}, {}, "H"),
    ("Parte en régimen de calma", {}, {"regimen_inicial": 0}, {}, "H"),
    ("Parte en régimen de crisis", {}, {"regimen_inicial": 2}, {}, "H"),
    ("Reactivo más nervioso (−4%)", {}, {}, {"umbral_caida_3m": -0.04}, "H"),
    ("Reactivo más tolerante (−10%)", {}, {}, {"umbral_caida_3m": -0.10}, "H"),
    ("Glidepath de la consulta (tope 90%)", {"glidepath": {"tope_inicial": 0.90}}, {}, {}, "H"),
    ("Glidepath sin extrapolar (tope 100% A)", {"glidepath": {"extrapolar": False}}, {}, {}, "H"),
]

# Escenarios forward-looking (hoja de ruta 2.1): en vez de suponer que se repite la historia 2002-2026,
# cada fondo se recentra en un retorno real esperado r_f = g_f·r_crec + (1−g_f)·r_prot (g_f en GLIDEPATH).
# * r_prot: bono Banco Central/Tesorería en UF a 10 años, 2,52% (BCCh, mercado secundario, 08-06-2026).
# * r_crec: MSCI ACWI 7,0% nominal USD con inflación EE.UU. 2,5% (J.P. Morgan, LTCMA 2026) -> 4,4% real;
#   se supone paridad de poder de compra de largo plazo (retorno real en USD ≈ real en UF).
# Los casos acotan la prima de la renta variable, que es la variable que domina la incertidumbre (hallazgo 9).
ESG = {
    "Histórico 2002-2026": None,
    "Consenso de mercado 2026": {"real_crecimiento": 0.044, "real_proteccion": 0.0252},
    "Prima de crecimiento nula": {"real_crecimiento": 0.0252, "real_proteccion": 0.0252},
}

# Incertidumbre de parámetros (bootstrap). IC de 90% = percentiles 5-95 de las réplicas.
# bloque_medio: largo medio (meses) de los bloques del bootstrap estacionario de la historia.
INCERTIDUMBRE = {"B_hmm": 200, "B_garch": 100, "B_pensiones": 200, "n_escenarios": 2000,
                 "bloque_medio": 12, "semilla": 20260929,
                 "procesos": None}   # None = núcleos disponibles − 1

# Glidepath oficial de los fondos generacionales: límite máximo de activos de crecimiento por edad.
# * "curva_consulta": gráfico de la minuta de consulta pública (SP, jul-2026, "Trayectoria de Inversión,
#   exposición máxima a activos de crecimiento"), digitalizado píxel a píxel con
#   scripts/digitalizar_glidepath.py (error < 0,2 p.p.; todos los puntos caen en % enteros). Edades 18..75.
# * "tope_inicial": la versión definitiva (Res. Ex. 1195, 01-09-2026) parte en 95% en vez de 90%. La SP no
#   publicó la curva definitiva por edad en formato legible, así que el tramo de bajada se reescala para que
#   vaya de 95% al mismo piso (supuesto; el caso "Glidepath de la consulta (tope 90%)" mide su efecto).
# * Se supone que el fondo invierte en el máximo permitido (la cartera de referencia sigue esa trayectoria).
# Activos de crecimiento (Régimen de Inversión): renta variable nacional y extranjera, high yield, renta fija
# emergente y alternativos. Participación en cada multifondo = renta variable + alternativos de renta fija
# (SP, Reporte mensual de inversiones, cartera al 31-03-2026, tablas 16 y 18). El high yield y la deuda
# emergente dentro de fondos mutuos no se pueden separar: la cifra es una cota inferior.
# Edad -> participación de crecimiento g -> combinación de multifondos: interpolación lineal entre los dos
# fondos vecinos en g. Sobre el Fondo A (g > 82,4%) no existe multifondo equivalente: con "extrapolar" se
# replica con la recta A–E (posición >100% en A y corta en E, factor crecimiento/protección implícito);
# sin extrapolar, se topa en 100% A (caso de robustez).
GLIDEPATH = {
    "curva_consulta": {"edad_inicial": 18, "crecimiento": [
        0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90,   # 18-28
        0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90,         # 29-38
        0.89, 0.87, 0.86, 0.85, 0.83, 0.81, 0.80, 0.78, 0.76, 0.74, 0.71,   # 39-49
        0.69, 0.66, 0.64, 0.61, 0.58, 0.55, 0.52, 0.50, 0.47, 0.43,         # 50-59
        0.39, 0.36, 0.32, 0.29, 0.29, 0.29, 0.29, 0.29, 0.29, 0.29,         # 60-69
        0.30, 0.31, 0.31, 0.32, 0.32, 0.32]},                               # 70-75
    "tope_inicial": 0.95,
    "crecimiento_multifondos": {"A": 0.824, "B": 0.612, "C": 0.421, "D": 0.213, "E": 0.082},
    "extrapolar": True,
}
