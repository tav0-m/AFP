# Diccionario de datos

## Fuentes (data/raw)

| Archivo | Fuente | Cobertura | Cómo obtenerlo |
|---|---|---|---|
| `vcfA2002-2026.csv` … `vcfE…` | Superintendencia de Pensiones | Diario, ene/ago-2002 a sep-2026 | spensiones.cl/apps/valoresCuotaFondo/vcfAFP.php → pestaña del fondo → rango 2002–2026 → ícono CSV |
| `uf.csv` | Banco Central de Chile (BDE) | Diario, 2002–2026 | `scripts/descarga_bcentral.py` (serie F073.UFF.PRE.Z.D) |
| `afiliados_edad_afp.xls(x)` | SP, Series estadísticas → Afiliados → informe 4 | Trimestral, 1993–2026 | Descarga directa (serie completa) |
| `tablas_mortalidad_cmf.xlsx` | CMF, "Tablas de Mortalidad Histórica" (NCG 495) | CB-H-2020, RV-M-2020 y anteriores | cmfchile.cl → Tablas de Mortalidad |

## Procesados (data/processed)

| Archivo | Contenido |
|---|---|
| `valores_cuota_afp_real.csv.gz` | Base larga por fecha, fondo y AFP: valor cuota nominal y en UF, retornos ajustados por fusiones, afiliados, estado |
| `indice_sistema_real_diario.csv` | Índice real (base 100 = 01-08-2002) del sistema por fondo, ponderado por afiliados |
| `retornos_reales_mensuales.csv` | Retornos reales mensuales por fondo (insumo de la econometría) |
| `probabilidad_regimenes.csv` | Probabilidad suavizada de cada régimen por mes |
| `montecarlo_H.csv`, `montecarlo_M.csv` | Distribución de la pensión por estrategia |
| `desviaciones_36m_afp.csv` | Rentabilidad 36 meses de cada AFP menos la de sus pares |
