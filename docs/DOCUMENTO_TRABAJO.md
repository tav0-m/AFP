# De multifondos a fondos generacionales: riesgo, regímenes y pensiones en Chile (2002–2026)

Documento de trabajo · 29 de septiembre de 2026 · Gustavo Moran

> Versión del repositorio. La versión viva, con comentarios, está en Claude Docs. Todas las cifras se regeneran con
> `python run_pipeline.py`; ante una diferencia, manda el pipeline.

## Resumen

Con supuestos de mercado actuales, el ciclo de vida de los fondos generacionales mejora en 12% la pensión mediana del fondo por defecto. La reforma de 2025 pesa mucho más: duplica la tasa de reemplazo de un hombre tipo, de 27% a 58%.

El 1 de abril de 2027 Chile reemplaza los cinco multifondos (A–E) por diez fondos generacionales. Este trabajo usa 24 años de valores cuota oficiales (ago-2002 a ago-2026) para medir qué enseñan los multifondos, cuánto cambia la pensión con la trayectoria oficial de inversión y qué agrega la Ley 21.735. Los métodos son un modelo oculto de Markov de regímenes y un GARCH(1,1) implementados desde cero, un bootstrap de escenarios condicionado al régimen, escenarios recentrados en expectativas de mercado de 2026 y una microsimulación de 20.000 personas.

Resultados principales:

- **Riesgo**: desde mayo de 2019 domina un régimen en que el Fondo E tiene volatilidad real de 8,9% al año (2,4% en calma). Su peor caída real (−24,3%) igualó a la del Fondo C.
- **Estrategia**: si se repite la historia, el ciclo de vida supera al fondo por defecto en 46%. Con el consenso de mercado 2026 la ventaja baja a 12% y gana en 68% de los escenarios. Remuestreando la historia, el intervalo de 90% va de −14% a +120%, porque la ventaja depende casi por completo de la prima de la renta variable.
- **Diseño**: el glidepath oficial queda a 0,3%–3,1% del óptimo por utilidad CRRA. Contando la PGU, el óptimo llega al retiro con más riesgo (70% en activos de crecimiento, contra 29% del oficial).
- **Reforma y población**: la tasa de reemplazo total mediana es 63% en hombres y 49% en mujeres (27% y 14% solo con el 10% del trabajador), y baja de 91% en el quintil de menores ingresos a 50% en el de mayores.
- **Género**: la pensión total de una mujer es 36% menor. La edad de pensión explica 41% de esa brecha, por sobre la densidad de cotización (27%) y el ingreso (18%).

Todo es reproducible desde los datos crudos con un solo comando.

## 1. Introducción

La Ley 21.735 cambia a la vez cómo se invierte el ahorro previsional y cuánto se ahorra. El efecto sobre la pensión de lo segundo es varias veces mayor que el de lo primero.

Desde el 1 de abril de 2027, los afiliados dejan de elegir entre cinco multifondos y quedan asignados por año de nacimiento a uno de diez fondos generacionales. Cada fondo sigue una trayectoria de inversión (glidepath) que parte con un máximo de 95% en activos de crecimiento y lo reduce al acercarse el retiro. Las AFP recibirán premios o pagarán castigos según su rentabilidad de 36 meses frente a una cartera de referencia, con bandas de 240 a 290 puntos base (SP, Res. Ex. 1195). En paralelo, la cotización del empleador sube gradualmente hasta 8,5% y la PGU llega a $250.000.

El trabajo responde tres preguntas:

1. ¿Qué enseñan 24 años de multifondos sobre rentabilidad real, riesgo y el costo de cambiarse de fondo?
2. ¿Un fondo de ciclo de vida con la trayectoria oficial da mejores pensiones que el esquema actual, y qué tan cerca está del óptimo?
3. ¿Cuánto cambia la pensión que recibe la persona con la reforma completa, y quiénes ganan más?

Las contribuciones son cuatro. Primero, una medición de regímenes de mercado que muestra que desde 2019 los fondos conservadores dejaron de ser un refugio. Segundo, una evaluación del glidepath oficial con escenarios históricos y con expectativas de mercado de 2026, que separa lo que depende de la historia de lo que es robusto. Tercero, la pensión total por capas (trabajador, empleador, rentabilidad protegida y PGU) para una cohorte heterogénea. Cuarto, una descomposición de Shapley de la brecha de género en pensiones.

El proyecto es educativo y de investigación. No constituye asesoría previsional ni financiera.

## 2. Datos

Todas las fuentes son oficiales y públicas; el pipeline parte de los archivos tal como se descargan.

| Dato | Fuente | Período | Uso |
| --- | --- | --- | --- |
| Valores cuota y patrimonio diarios por AFP y fondo | [Superintendencia de Pensiones](https://www.spensiones.cl) | ago-2002 a sep-2026 | Retornos reales, regímenes, bandas |
| UF diaria | [Banco Central de Chile](https://si3.bcentral.cl), BDE | 2002–2026 | Deflactar a términos reales |
| Afiliados por AFP y edad | SP, series estadísticas trimestrales | 2002–2026 | Ponderar el índice del sistema |
| Tablas CB-H-2020 y RV-M-2020 | CMF, NCG 495 | vigentes | Capital necesario unitario (CNU) |
| Cartera por fondo | SP, reporte mensual de inversiones | mar-2026 | Activos de crecimiento de cada multifondo |
| Trayectoria de inversión y bandas | [SP, Régimen de Inversión](https://www.spensiones.cl/portal/institucional/594/w3-article-17131.html) (Res. Ex. 1195) | sep-2026 | Glidepath oficial |
| Calendario de cotizaciones y PGU | [Nota Técnica Ley 21.735](https://previsionsocial.gob.cl/wp-content/uploads/2025/08/Nota-Tecnica-Reforma-de-Pensiones-Ley-N%C2%B021.735.pdf); SP (PGU feb-2026) | 2025–2054 | Pensión total |
| Ingreso imponible y densidad por sexo | SP (jun-2026; Informe de Género) | 2024–2026 | Calibrar la microsimulación |
| Expectativas de mercado | BCCh (bono UF 10 años, 2,52%); [J.P. Morgan LTCMA 2026](https://am.jpmorgan.com/us/en/asset-management/institutional/about-us/media/press-releases/jp-morgan-releases-2026-long-term-capital-market-assumptions/) (ACWI 7,0% USD) | 2026 | Escenarios forward-looking |

Dos problemas de calidad se resuelven antes de modelar. El archivo de valores cuota cambia de columnas cuando hay fusiones de AFP, y el pipeline las detecta automáticamente: la fusión Magíster–PlanVital produce un salto de +84% en un día que no es rentabilidad. Además, la trayectoria oficial por edad solo está publicada como gráfico en la minuta de la consulta pública, por lo que se digitalizó píxel a píxel con error menor a 0,2 puntos.

La serie mensual final tiene 288 meses reales por fondo, ponderados por afiliados.

## 3. Metodología

La cadena va de los retornos reales históricos a la pensión de cada persona, y cada eslabón tiene su propia medición de incertidumbre. El detalle está en [METODOLOGIA.md](METODOLOGIA.md).

**Regímenes de mercado.** Un modelo oculto de Markov gaussiano multivariado sobre los retornos reales mensuales de los cinco fondos, estimado por Baum-Welch escalado con 25 inicios aleatorios. El número de estados (K = 1, 2 o 3) se elige por BIC; gana K = 3. La volatilidad diaria se modela con un GARCH(1,1) por cuasi-máxima verosimilitud.

```latex
r_t \mid s_t = k \sim \mathcal{N}(\mu_k, \Sigma_k), \qquad P(s_{t+1}=j \mid s_t=i) = A_{ij}
```

**Escenarios.** Se simula la cadena de regímenes con la matriz A estimada y, en cada mes, se sortea un mes histórico completo (los cinco fondos juntos) del mismo régimen. Así se conservan colas gruesas y la correlación entre fondos sin suponer normalidad. Se generan 10.000 trayectorias de 480 meses.

**Escenarios forward-looking.** Cada fondo se recentra en un retorno real esperado según su participación g en activos de crecimiento, calibrado para que la media geométrica simulada coincida exactamente:

```latex
r_f = g_f \, r_{crec} + (1-g_f)\, r_{prot}, \quad r_{prot}=2{,}52\%, \; r_{crec}=4{,}4\%
```

**Estrategias.** Fondos fijos A–E; el fondo por defecto de la ley (B hasta 35, C hasta 55/50, D después); el ciclo de vida con el glidepath oficial, replicado combinando los dos multifondos cuya exposición rodea la de cada edad (sobre el Fondo A se extrapola por la recta A–E); y una regla reactiva que se va al E tras una caída de 6% en tres meses. Todas se evalúan sobre las mismas trayectorias.

**Pensión.** Saldo acumulado dividido por el capital necesario unitario (CNU) de las tablas CMF con la tasa de retiro programado vigente (3,45%). La pensión total suma, por capas, la cotización del empleador según su calendario, la cotización con rentabilidad protegida y la PGU focalizada.

**Glidepath óptimo.** Búsqueda en una familia de trayectorias (meseta g0 hasta la edad a1, luego baja lineal hasta g1) que maximiza el equivalente cierto de la utilidad CRRA de la pensión total, con escenarios de entrenamiento y prueba separados:

```latex
EC = \left( \mathbb{E}\left[ x^{1-\gamma} \right] \right)^{1/(1-\gamma)}, \qquad \gamma \in \{2, 3, 5\}
```

**Microsimulación.** Cohorte de 20.000 personas con ingreso lognormal y densidad de cotización Beta por sexo (calibrados con la SP), lagunas como rachas de empleo formal (cadena de Markov con racha media de 36 meses) y un mercado común. La brecha de género se descompone con valores de Shapley sobre cuatro factores.

**Incertidumbre.** Tres bootstraps: paramétrico para el HMM (200 réplicas, estados alineados por asignación húngara), residuos filtrados para el GARCH, y estacionario por bloques de la historia (200 historias, bloques de 12 meses en promedio) para los resultados de pensión.

## 4. Resultados

La estrategia de inversión mueve la pensión en decenas de por ciento según el supuesto de mercado; la reforma la mueve en más de 100% en cualquier supuesto.

### 4.1 Lo que enseñan los multifondos

La inflación se lleva cerca de 3,9 puntos al año: el Fondo A rindió 9,9% nominal y 5,8% real; el E, 6,8% y 2,8% (ago-2002 a ago-2026). El Fondo E no fue un refugio: su peor caída real (−24,3%) igualó a la del C (−24,4%) y superó a la del D (−21,9%).

El HMM detecta que desde mayo de 2019 domina un régimen nuevo, en que el E tiene volatilidad real de 8,9% al año frente a 2,4% en calma, y la correlación móvil C–E sube a 0,81 (IC 90%: 0,69 a 0,89). El régimen reaparece en 92% de las réplicas del bootstrap paramétrico. El GARCH muestra volatilidad casi integrada en los fondos D y E: los shocks de volatilidad de los fondos conservadores casi no se disipan.

![Regímenes](../reports/figuras/02_regimenes_hmm.png)

### 4.2 Estrategias: el tamaño de la ventaja depende del mercado

Pensión autofinanciada con el 10% del trabajador, hombre de 25 a 65 años, sueldo inicial 25 UF, 10.000 escenarios.

| Supuesto de mercado | Fondo A / E real al año | Ciclo de vida vs por defecto (mediana) | Percentil 5 | Gana en |
| --- | --- | --- | --- | --- |
| Se repite 2002–2026 | 5,8% / 2,8% | +46% | +20% | 93% |
| Consenso de mercado 2026 | 4,1% / 2,7% | +12% | −2% | 68% |
| Sin prima de crecimiento | 2,5% / 2,5% | −1% | −10% | 49% |

La ventaja histórica resiste 13 supuestos alternativos (entre +28% y +51%), pero todos ellos reutilizan la misma historia. Al remuestrear la historia por bloques, la prima real del A sobre el E va de −2,0% a +7,2% (IC 90%) y explica la ventaja del ciclo de vida con correlación 0,94: el ciclo de vida gana en 86% de las historias y pierde cuando la prima es negativa.

![Incertidumbre](../reports/figuras/08_incertidumbre.png)

Cambiarse al Fondo E después de cada caída no mejora la pensión esperada: cuesta 4,9% en la mediana con unos 15 traspasos, y 9,7% si la regla reacciona ante caídas de 4%. El intervalo con historias alternativas (−8,7% a +8,5%) incluye el cero, así que el costo es probable, no seguro.

### 4.3 El glidepath oficial está cerca del óptimo

El mejor glidepath de la familia supera al oficial en solo 0,3% a 3,1% de pensión equivalente cierta, según la aversión al riesgo; el fondo por defecto de la ley queda entre 1% y 9% bajo el oficial. Con γ = 3 y contando la PGU, el óptimo llega al retiro con 70% en activos de crecimiento; sin la PGU, con 40%. El oficial termina en 29%. La PGU funciona como un bono seguro y justifica más riesgo al final de la vida laboral.

![Glidepath óptimo](../reports/figuras/12_glidepath_optimo.png)

### 4.4 La reforma duplica la tasa de reemplazo

Hombre tipo, fondo por defecto, consenso 2026. Las capas se suman en orden.

| Capa | Pensión mediana (UF) | Tasa de reemplazo | Supera 40% |
| --- | --- | --- | --- |
| Solo 10% del trabajador | 9,7 | 27% | 10% |
| + cotización del empleador | 13,8 | 38% | 44% |
| + rentabilidad protegida | 14,6 | 40% | 51% |
| + PGU (pensión total) | 20,9 | 58% | 98% |

Para una mujer la tasa de reemplazo pasa de 17% a 43% (la PGU se recibe desde los 65). Con la pensión total, el ciclo de vida mejora la mediana del hombre en 7%, frente a 12% en la pensión autofinanciada: la PGU amortigua la diferencia entre estrategias.

### 4.5 Población y brecha de género

En la microsimulación de 20.000 personas, la tasa de reemplazo total mediana es 63% en hombres y 49% en mujeres; solo con el 10% sería 27% y 14%. La PGU es más de la mitad de la pensión en 56% de los casos de mujeres. El gráfico muestra cuánto sube cada quintil con la reforma: el salto es mayor mientras menor es el ingreso.

![Tasa de reemplazo por quintil](../reports/figuras/13_poblacion_quintiles.png)

La pensión total mediana de una mujer es 36% menor que la de un hombre. La descomposición de Shapley reparte la brecha así:

| Factor | Aporte a la brecha (pp) | Parte de la brecha |
| --- | --- | --- |
| Edad de pensión (60 vs 65) | 14,8 | 41% |
| Densidad de cotización | 9,7 | 27% |
| Nivel de ingreso | 6,6 | 18% |
| Esperanza de vida | 4,1 | 11% |
| Residuo | 0,7 | 2% |

### 4.6 Premios y castigos

Las bandas oficiales son unas tres veces más anchas que la dispersión histórica entre AFP: 95% de las desviaciones de 36 meses frente a los pares es menor a 0,83 puntos, contra bandas de ±2,4 a ±2,9 puntos (±4,0 en la transición). Con la referencia de pares, solo 0,2% de los meses-AFP habría quedado fuera de la banda más estrecha. El incentivo real dependerá de cuánto se aleje la cartera de referencia oficial de lo que hoy invierten las AFP.

## 5. Discusión e implicancias de política

El diseño de inversión de los fondos generacionales es bueno; las palancas que más mueven la pensión están fuera de él.

1. **El glidepath oficial no necesita cambios de fondo.** Queda a menos de 3,1% del óptimo en todos los casos y supera siempre al fondo por defecto actual. Una revisión menor sería mantener más activos de crecimiento cerca del retiro, porque la PGU ya aporta una renta segura; para una persona con la mitad de su pensión en PGU, un 29% en crecimiento al jubilar es conservador.
2. **Comunicar rangos, no promesas.** La ventaja del ciclo de vida va de −1% a +46% según la prima de la renta variable. Informar a los afiliados un solo número, sobre todo uno histórico, sobreestima lo que se puede esperar.
3. **Desincentivar los traspasos reactivos.** Cambiarse de fondo después de las caídas no mejora la pensión esperada, y la reforma lo limita al asignar el fondo por edad. El ahorro voluntario, que sí puede elegir fondo, merece la misma advertencia.
4. **La edad de pensión de las mujeres es la mayor palanca de género.** Explica 41% de la brecha de pensión total, más que las lagunas (27%) o el sueldo (18%). Incentivos a postergar voluntariamente el retiro, o información clara sobre su efecto, reducirían la brecha más que cualquier cambio en la inversión.
5. **La PGU es el pilar que sostiene la suficiencia.** Lleva al quintil de menores ingresos a una tasa de reemplazo de 91% y es más de la mitad de la pensión de la mayoría de las mujeres. Su financiamiento y su reajuste pesan más en la pensión de ese grupo que la rentabilidad de su fondo.
6. **Las bandas de premios y castigos pueden no morder.** Si la cartera de referencia se parece a lo que ya invierten las AFP, las desviaciones históricas son tres veces menores que las bandas y casi ninguna AFP pagaría o cobraría. Vale la pena monitorear desde abril de 2027 cuánto se separan las AFP de su referencia.

## 6. Limitaciones y trabajo futuro

La conclusión robusta es el signo y el orden de magnitud de cada efecto, no su decimal.

- **Glidepath aproximado.** La curva por edad es la de la consulta pública reescalada al tope definitivo de 95%, porque la SP no publicó la tabla definitiva en formato legible. Se replica con multifondos, lo que supone que cada fondo es una mezcla de un factor de crecimiento y uno de protección.
- **24 años para proyectar 40.** Por eso se reportan escenarios de consenso y un bootstrap de la historia; aun así, las expectativas de consenso son una sola fuente (J.P. Morgan) y cambian cada año.
- **Microsimulación estilizada.** Ingreso y densidad son estables durante la vida de cada persona, sin movilidad entre quintiles, trabajadores independientes ni ahorro voluntario. La focalización de la PGU se aproxima excluyendo al 10% de mayores ingresos.
- **Beneficios no modelados.** El Beneficio por Años Cotizados (no aplica a esta cohorte) y la compensación por expectativa de vida (solo desde los 65 años).
- **Bandas con referencia de pares.** La prueba usa el promedio de las demás AFP y no los índices de la cartera de referencia oficial.

Trabajo futuro: regímenes con probabilidades de transición que dependan de variables macro (tasa de política monetaria, IPC, dólar, cobre); la cartera de referencia oficial con índices de mercado; programación dinámica del glidepath óptimo; y un monitor mensual de las AFP frente a sus bandas desde abril de 2027.

## 7. Reproducibilidad y fuentes

Todas las cifras de este documento salen de un solo comando sobre los datos crudos, con pruebas automáticas e integración continua.

- **Repositorio:** [github.com/tav0-m/AFP](https://github.com/tav0-m/AFP): código, datos, metodología detallada ([METODOLOGIA.md](METODOLOGIA.md)), reporte Excel y figuras.
- **Ejecución:** `pip install -r requirements.txt` y luego `python run_pipeline.py` (unos 3 minutos con 8 núcleos).
- **Semillas fijas:** los resultados son idénticos al repetir la ejecución, con 1 o con 8 procesos.

Fuentes consultadas:

- Superintendencia de Pensiones, [Régimen de Inversión de los Fondos Generacionales](https://www.spensiones.cl/portal/institucional/594/w3-article-17131.html) (Res. Ex. 1195, 01-09-2026) y [minuta de la consulta pública](https://www.spensiones.cl/portal/institucional/594/articles-11315_nt_561_minuta.pdf).
- Superintendencia de Pensiones, [índices de mercado de las carteras de referencia](https://www.spensiones.cl/portal/institucional/594/articles-17148_recurso_1.pdf) (Res. Ex. 1244, 10-09-2026).
- Superintendencia de Pensiones, [reporte mensual de inversiones, marzo de 2026](https://www.spensiones.cl/portal/institucional/594/articles-17009_recurso_1.pdf).
- Subsecretaría de Previsión Social, [Nota Técnica Reforma de Pensiones Ley 21.735](https://previsionsocial.gob.cl/wp-content/uploads/2025/08/Nota-Tecnica-Reforma-de-Pensiones-Ley-N%C2%B021.735.pdf) (ago-2025).
- Superintendencia de Pensiones, [monto de la PGU desde febrero de 2026](https://www.spensiones.cl/portal/institucional/594/w3-article-16886.html) y [topes imponibles 2026](https://www.spensiones.cl/portal/institucional/594/w3-article-16921.html).
- Hacienda y SP, [datos de brecha de género en el sistema previsional](https://www.hacienda.cl/noticias-y-eventos/noticias/reforma-previsional-superintendencia-de-pensiones-presenta-datos-de-brecha-de).
- J.P. Morgan Asset Management, [Long-Term Capital Market Assumptions 2026](https://am.jpmorgan.com/us/en/asset-management/institutional/about-us/media/press-releases/jp-morgan-releases-2026-long-term-capital-market-assumptions/).
- Banco Central de Chile, [Base de Datos Estadísticos](https://si3.bcentral.cl) (UF y tasas de bonos en UF).

Métodos: Rabiner (1989) para el forward-backward escalado; Bollerslev (1986) para el GARCH; Politis y Romano (1994) para el bootstrap estacionario; Shapley (1953) para la descomposición de la brecha.
