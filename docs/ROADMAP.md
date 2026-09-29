# Hoja de ruta para escalar el proyecto

**Estado al 29-09-2026.** Ya hecho: pipeline reproducible, 21 pruebas, robustez (13 supuestos), glidepath oficial, intervalos por bootstrap,
banda de transición oficial incorporada, integración continua con ejecución semanal, `Makefile` y `Dockerfile`.

Priorizada por impacto sobre las conclusiones y esfuerzo. Horizonte: antes y después de la entrada
en vigencia de los fondos generacionales (01-04-2027).

## Fase 1 — Cerrar las limitaciones actuales (0–6 semanas)

| # | Mejora | Por qué importa | Esfuerzo |
|---|---|---|---|
| 1.1 | **Cartera de referencia oficial** (índices de mercado publicados por la SP el 10-09-2026) | Reemplaza el proxy "promedio de pares" y permite estimar la probabilidad real de premios y castigos por AFP | Medio |
| 1.2 | ✅ **Glidepath oficial de los 10 fondos generacionales** (límites de activos de crecimiento de la Res. Ex. 1195) | Hecho (29-09-2026): la ventaja mediana del ciclo de vida sube de +20% a +46%. Pendiente: reemplazar la curva de consulta reescalada por la tabla definitiva cuando la SP la publique en formato legible | Bajo |
| 1.3 | **Cartera de inversiones por fondo** (SP, estadísticas financieras mensuales desde 2000) | Atribución por clase de activo: explica *por qué* el E perdió su rol de refugio (duración, tasas) | Medio |
| 1.4 | ✅ **Pensión total**: PGU, aumento de cotización del empleador (Ley 21.735) y beneficiarios de sobrevivencia | Pasa de "pensión autofinanciada" a la pensión que recibe la persona | Medio |
| 1.5 | ✅ **Comisiones por AFP** | Pensión neta por administradora | Bajo |

## Fase 2 — Modelos de nivel investigación (1–3 meses)

| # | Mejora | Detalle |
|---|---|---|
| 2.1 | ✅ **Escenarios forward-looking** | Generador de escenarios económicos (ESG) con primas de riesgo de consenso y curva de tasas actual, para no extrapolar 2002–2026. Comparar con el bootstrap |
| 2.2 | ✅ **Regímenes con predictores macro** | Markov-switching con probabilidades de transición variables (TVTP) usando TPM, IPC, dólar y cobre (ya descargables con `descarga_bcentral.py`); contraste con gradient boosting / LSTM con validación *walk-forward* |
| 2.3 | ✅ **Glidepath óptimo** | Programación dinámica estocástica o aprendizaje por refuerzo que maximice utilidad CRRA o la probabilidad de alcanzar la meta; comparar contra el glidepath regulatorio |
| 2.4 | ✅ **Microsimulación poblacional** | Perfiles heterogéneos (densidad de cotización, ingresos, lagunas, género) desde las series de cotizantes de la SP, en vez de un afiliado tipo |
| 2.5 | ✅ **Incertidumbre de parámetros** | Robustez frente a 13 supuestos y bootstrap del HMM, del GARCH y de la historia (hallazgo 9, figura 08). Siguiente paso natural: 2.1, porque la prima de renta variable domina la incertidumbre |

## Fase 3 — Ingeniería y producto (en paralelo)

| # | Mejora | Detalle |
|---|---|---|
| 3.1 | **Ingesta automática** | La SP genera el CSV de valores cuota por petición HTTP directa; job diario con GitHub Actions o Prefect, que maneje valores provisorios vs confirmados |
| 3.2 | **Almacenamiento analítico** | Parquet + DuckDB; transformaciones versionadas con dbt y pruebas de calidad (unicidad, huecos, rebases) |
| 3.3 | **CI/CD y empaquetado** | ✅ GitHub Actions (pruebas + pipeline, semanal) y Docker. Pendiente: `pyproject.toml` y MLflow para versionar corridas |
| 3.4 | **API** | FastAPI con `/pension`, `/escenarios`, `/regimen-actual`; el simulador web la consume en vez de un JSON estático |
| 3.5 | **Dashboard corporativo** | Power BI conectado a la base procesada con actualización programada |
| 3.6 | **Asistente con IA** | Agente que explica al afiliado su proyección usando el motor como herramienta (educativo, sin recomendar decisiones individuales) |

## Fase 4 — Impacto y difusión

- **Publicación abierta**: repositorio en GitHub con datos reproducibles, más un artículo técnico (blog/Medium o
  documento de trabajo) con los 8 hallazgos.
- **Monitor de fondos generacionales**: desde abril de 2027, seguimiento mensual real de cada AFP frente a su
  banda: el primer tablero público de premios y castigos.
- **Audiencias**: afiliados (educación previsional), asesores previsionales (B2B), periodistas e investigadores.

## Métricas de éxito

- Reproducibilidad: pipeline completo verde en CI en < 5 minutos.
- Calidad: 0 días faltantes; cada rebase clasificado.
- Producto: simulador usado y citado; tablero de bandas actualizado dentro de 2 días hábiles tras la publicación de la SP.
