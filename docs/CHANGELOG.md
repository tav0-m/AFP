# Registro de cambios

## 2026-09-30 (tarde)
- Licencias: MIT para el código (`LICENSE`) y CC BY 4.0 para documentos, figuras y tablero (`LICENSE-CONTENIDO.md`).
- **Regímenes con variables macro** (hoja de ruta 2.2): `scripts/descarga_mindicador.py` (API pública, sin
  credenciales) y `regimenes_macro.py` (TVTP-HMM con EM propio, walk-forward 2015-2026, Diebold-Mariano HAC).
  Hallazgo 15 y figura 15: los regímenes predicen mejor que una normal (p < 0,001), pero la macro no agrega capacidad
  predictiva fuera de muestra (p = 0,98). Hojas Excel `Regimenes_macro` y `Regimenes_macro_efectos`.
- Pruebas: 39 (transiciones, equivalencia con el forward-backward constante, variables sin mirar al futuro, test DM).

## 2026-09-30
- **Microsimulación poblacional** (hoja de ruta 2.4): `microsimulacion.py`, una cohorte de 20.000 personas con ingreso
  y densidad calibrados con la SP, lagunas como rachas (Markov) y un mercado común; se calcula con una multiplicación de
  matrices. Hallazgos 13 (progresividad: TR total de 91% en Q1 a 50% en Q5, hombres) y 14 (Shapley de la brecha de
  género: la edad de pensión explica el 41%). Figuras 13 y 14; hojas Excel `Poblacion_sexo`, `Poblacion_quintil` y
  `Brecha_genero`; sección "Población y género" en el tablero.
- Rendimiento: `factores_crecimiento` devuelve un arreglo contiguo; la multiplicación usa BLAS (49 s → 7 s).
- Pruebas: 35 (calibración, rachas, matmul = acumulación mes a mes, eficiencia de Shapley).
- **Documento de trabajo** `docs/DOCUMENTO_TRABAJO.md` (resumen, datos, metodología, resultados, política, limitaciones) y `CITATION.cff`.

## 2026-09-29 (noche)
- Repositorio publicado en GitHub (`tav0-m/AFP`); `.gitattributes` normaliza los finales de línea (LF).
- **Pensión total con la reforma** (hoja de ruta 1.4): nuevo `reforma.py` (Ley 21.735: cotización del empleador por
  fecha, Cotización con Rentabilidad Protegida y PGU focalizada). Hallazgo 11; figura 11 (pilares por nivel de sueldo);
  hojas Excel `Pension_total` y `Pension_por_ingreso`; sección en el tablero. La tasa de reemplazo mediana del hombre
  pasa de 27% a 58% con la reforma completa.
- Workflow `pages.yml`: publica el tablero y el simulador en GitHub Pages en cada cambio de `app/`.
- Pruebas: 27 (calendarios de cotización, extinción de la CRP, focalización de la PGU, capas que suman el total).
- **Glidepath óptimo** (hoja de ruta 2.3): `optimo.py` busca la mejor trayectoria de la familia "meseta y bajada" por
  utilidad CRRA de la pensión total (γ 2, 3 y 5; con y sin reforma), con entrenamiento y prueba separados y en paralelo.
  Hallazgo 12, figura 12, hoja Excel `Glidepath_optimo` y línea en el tablero. El oficial queda a 0,3%-3,1% del óptimo.
- Salida `.csv.gz` reproducible (gzip sin marca de tiempo). Pruebas: 29.

## 2026-09-29 (tarde)
- **Escenarios forward-looking** (hoja de ruta 2.1): `escenarios.simular(objetivo=...)` recentra cada fondo en un retorno
  esperado calibrado sobre la media simulada. `config.ESG` define histórico, consenso 2026 (BCCh + J.P. Morgan LTCMA)
  y prima nula; `robustez.evaluar_esg`; hallazgo 10; figura 10; hoja Excel `Escenarios_mercado`.
  Resultado: la ventaja del ciclo de vida baja de +46% (historia) a +12% (consenso).
- Figura 09: glidepath oficial vs consulta vs aproximación anterior vs ley vigente.
- Bootstrap paralelo (`ProcessPoolExecutor`) con semillas por réplica: idéntico al secuencial, y el pipeline pasa de
  262 s a ~157 s.
- HMM: un estado sin transiciones esperadas ya no produce NaN en la matriz de transición.
- La tabla de hallazgos del README la reescribe el pipeline (marcadores `HALLAZGOS`), así que las cifras no quedan desfasadas.
- Pruebas: 23 (paralelo = secuencial; recentrado exacto en el objetivo).
- **Tablero de resultados** `app/tablero.html` (plantilla `tablero_plantilla.html` + `build_tablero.py`): 7 gráficos SVG
  interactivos con tooltips, modo claro/oscuro y tablas accesibles; lo regenera el pipeline.
- Hallazgo 5 reformulado: el intervalo del costo de reaccionar incluye el cero.

## 2026-09-29
- **Glidepath oficial** (hoja de ruta 1.2): el ciclo de vida sigue el máximo de activos de crecimiento por edad de la SP
  (curva de la consulta digitalizada, tope definitivo de 95%) en lugar de la aproximación 100% A → D. Se replica con
  multifondos según su participación de crecimiento a mar-2026. Ventaja mediana vs por defecto: +20% → +46% (hombre).
- Nuevo `scripts/digitalizar_glidepath.py` para auditar la curva desde el PDF oficial.
- Robustez: 2 casos nuevos (curva de consulta con tope 90%; sin extrapolar sobre el Fondo A). Total: 13.
- El simulador web usa pesos por edad precalculados por el pipeline (misma lógica que Python).
- Pruebas nuevas: tope y piso del glidepath, reproducción exacta de la curva de consulta, réplica de la exposición
  con multifondos. Total: 17.
- Corrección: `resultados.json` se escribe en UTF-8 (fallaba en Windows).
- **Incertidumbre de parámetros** (hoja de ruta 2.5): nuevo módulo `incertidumbre.py` con bootstrap paramétrico del HMM,
  simulación histórica filtrada del GARCH y bootstrap estacionario de la historia (reestimando el HMM). Intervalos de
  90% en los hallazgos 3, 4 y 5; hallazgo 9 nuevo; figura 08; hoja Excel `Incertidumbre`; CSV `incertidumbre_*.csv`.
- HMM: forward-backward escalado y vectorizado (48 s → 2,2 s por selección de modelo; pruebas de 194 s a 10 s),
  arranque en caliente (`inicial`), `posterior_hmm` y `simular_hmm`.
- Corrección: el HMM devolvía un `gamma` de un paso E anterior al último paso M (y el EM puede cortar antes porque
  `reg·I` rompe la monotonía). Ahora se hace un paso E final: parámetros, `gamma` y log-verosimilitud son consistentes.
  Los hallazgos no cambian a la precisión reportada.
- Figura 07: el eje se ajusta a los datos (antes cortaba los valores sobre +28%).
- Pruebas: 21 (alineación de estados, consistencia del posterior, bootstrap estacionario, IC de Fisher).

## 2026-09-28
- Nuevo módulo `robustez.py`: 11 supuestos alternativos y probabilidad de ganar camino a camino (hallazgo 8, figura 07, hoja Excel `Robustez`, tabla en el simulador web).
- Bandas: se incorpora la banda de transición oficial de ±4,0% (abr-2028 a mar-2031, SP Res. Ex. 1195) en configuración, figura 06, hallazgo 7, Excel y app.
- `simular_estrategias` acepta una regla reactiva distinta (parámetro `reactivo`).
- Pruebas nuevas: la regla reactiva sin señales replica al fondo por defecto; parámetros oficiales de bandas. Total: 14.
- Ingeniería: integración continua (GitHub Actions, con ejecución semanal), `Makefile` y `Dockerfile`.

## 2026-09-27
- Primera versión completa: ETL, retornos reales, HMM y GARCH desde cero, Monte Carlo por régimen, bandas (proxy), reporte Excel con simulador en fórmulas y simulador web.
