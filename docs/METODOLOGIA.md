# Metodología

## 1. Datos y calidad (etapa 1)

**Valores cuota** (SP, `vcfAFP.php`, un CSV por fondo, 2002–2026). El archivo se reinicia con bloques
`Valores Confirmados / Provisorios` y encabezados cuyo set de AFP cambia en el tiempo (Magíster, Santa María,
Summa Bansander y Bansander desaparecen; entran Capital, Modelo y Uno). El parser lo convierte a formato largo
`fecha | fondo | afp | valor_cuota | patrimonio | estado` (278.548 filas).

Validaciones: 0 duplicados, 0 días faltantes, 0 nulos, 560 registros provisorios marcados.
**Rebases por fusión**: un retorno diario > 10% el día siguiente a que otra AFP deja de informar se clasifica como
cambio de escala (PlanVital adopta la escala de Magíster el 01-03-2004: +83,7% en C y +75,4% en E) y se neutraliza.

## 2. Retornos reales y ponderación (etapa 2)

- Valor cuota en UF = valor cuota / UF del día (Banco Central, serie diaria).
- Índice del sistema por fondo = promedio de retornos diarios de las AFP **ponderado por afiliados**
  (SP, afiliados por edad y AFP, trimestral 1993–2026, asignado con *as-of join*).
- Control: la inflación implícita (nominal/real) resulta ≈3,9% anual en los cinco fondos.

## 3. Econometría (etapa 3)

**HMM gaussiano multivariado** sobre retornos reales mensuales de los 5 fondos (288 meses).
Baum-Welch con escalamiento logarítmico, 25 inicios aleatorios, estados ordenados por varianza.
Selección por BIC entre K = 1, 2, 3 → K = 3:

| Régimen | Interpretación | Duración esperada | E: vol. real anual |
|---|---|---|---|
| 0 | Calma | ~19 meses | 2,4% |
| 1 | Tasas volátiles (domina desde may-2019) | ~74 meses | 8,9% |
| 2 | Crisis bursátil (2008, 2011, 2020) | ~2,5 meses | 7,7% |

El régimen 1 no aparece antes de 2019: es más un **quiebre estructural** (estallido social, retiros de fondos,
alza de tasas 2022) que un régimen recurrente.

**GARCH(1,1)** gaussiano por QMLE sobre retornos reales diarios (6.259 días hábiles efectivos).
Persistencia α+β: 0,98 (A) a 0,999 (E); la casi integración en D y E es la huella del cambio de nivel.

## 4. Simulación (etapa 4)

**Escenarios**: cadena de Markov con la matriz de transición del HMM, partiendo del régimen actual; en cada mes
se sortea un mes histórico completo (5 fondos juntos) del mismo régimen. 10.000 trayectorias × 480 meses.

**Afiliado tipo**: inicia a los 25 años en 2026, sueldo 25 UF con crecimiento real 1,5% anual hasta los 50,
cotización 10%, densidad 60%. Se pensiona a la edad legal (H 65, M 60).

**Pensión** = saldo / CNU. CNU = Σ_k p_k · v^k (pago mensual anticipado), con p_k de las tablas CB-H-2020 /
RV-M-2020 proyectadas al año de retiro [qx(edad, año) = qx_2020 · Π(1 − AA_x,t), AA constante desde 2036]
y v con la TITRP de 3,45%.

**Estrategias**: fondos fijos A–E; por defecto (B ≤35, C hasta 55/50, D después); ciclo de vida (glidepath
oficial, abajo); reactivo (desde el por defecto, se va al E si su fondo cae >6% real en 3 meses, con un mes de
desfase; vuelve tras ≥6 meses si el A sube >5% en 3 meses).

**Glidepath oficial** (`config.GLIDEPATH`). El Régimen de Inversión fija, para cada edad, un máximo de *activos de
crecimiento* (renta variable, high yield, deuda emergente y alternativos). Se supone que el fondo invierte en ese máximo.

1. *Curva por edad*: gráfico de la minuta de consulta pública (SP, jul-2026), digitalizado con
   `scripts/digitalizar_glidepath.py`. Da 90% hasta los 38 años, baja a 29% a los 63 y sube a 32% hacia los 75.
   La versión definitiva (Res. Ex. 1195) parte en 95%; como la SP no publicó la curva definitiva por edad, la
   meseta y la bajada se reescalan linealmente entre el piso (29%) y el nuevo tope:
   g(x) = 29% + (g_consulta(x) − 29%) · (95% − 29%)/(90% − 29%), para x ≤ 63.
2. *Réplica con multifondos*: participación de crecimiento de cada multifondo a mar-2026 (renta variable +
   alternativos, SP): A 82,4%, B 61,2%, C 42,1%, D 21,3%, E 8,2%. Para cada edad se combinan los dos fondos vecinos
   que igualan g. Sobre el A (g > 82,4%) se extrapola por la recta A–E, lo que equivale a suponer que cada multifondo
   es una mezcla de un factor "crecimiento" y uno "protección": con g = 95% los pesos son 117% A y −17% E.

Supuestos con efecto medible (casos de robustez): tope de 90% (curva de consulta sin reescalar) y sin extrapolar
(tope de 100% A). Límite conocido: el glidepath no depende del sexo ni de la edad de retiro, así que una mujer que
se pensiona a los 60 lo hace con ~44% en crecimiento.

**Evaluación retrospectiva**: la misma mecánica sobre la historia real sep-2002 a ago-2026.

## 5. Bandas de premios y castigos

Regla oficial (SP, Res. Ex. 1195, 01-09-2026): evaluación mensual de la rentabilidad de 36 meses móviles contra la
cartera de referencia de cada fondo generacional; bandas de 240 a 290 puntos base anuales (±2,4% a ±2,9%).
Transición: banda de 400 p.b. (±4,0%) entre el 01-04-2028 y el 31-03-2031. Fuera de la banda, la AFP recibe una
retribución (arriba) o debe aportar recursos propios (abajo).

Proxy: cada AFP contra el promedio ponderado de las demás AFP del mismo fondo (*leave-one-out*). Se mide la
frecuencia histórica de AFP-meses fuera de cada ancho (1,0% a 4,0%).

## 6. Robustez

Se repite la simulación en 13 supuestos alternativos (`config.ROBUSTEZ`): mujer; sueldo sin crecimiento real o con
3% anual; inicio de cotizaciones a los 35; retornos castigados en 1 y 2 p.p. anuales; cadena de regímenes que parte
en calma o en crisis; regla reactiva más nerviosa (−4% en 3 meses) o más tolerante (−10%); y glidepath de la
consulta (tope 90%) o sin extrapolar sobre el Fondo A.

Además de comparar percentiles, como todas las estrategias usan las mismas trayectorias se calcula la probabilidad
de que una estrategia supere a otra *en el mismo escenario*. La densidad de cotización y el nivel del sueldo no se
incluyen porque no cambian el ranking: con saldo inicial cero la pensión es proporcional a los aportes.

## 7. Incertidumbre de parámetros (`incertidumbre.py`)

Intervalos de confianza de 90% (percentiles 5–95 de las réplicas; parámetros en `config.INCERTIDUMBRE`).

- **HMM, bootstrap paramétrico (200 réplicas)**: se simula una serie de 288 meses desde el HMM estimado, se reestima
  (arranque en caliente) y los estados se alinean con los originales por asignación húngara sobre log-volatilidades y
  medias estandarizadas, lo que evita el *label switching* entre los regímenes 1 y 2 (el orden por traza los
  intercambia a veces). Con cada modelo reestimado se reetiqueta la historia **real** para medir si el quiebre de 2019
  depende del ajuste puntual.
- **GARCH, simulación histórica filtrada (100 réplicas por fondo)**: se remuestrean los residuos estandarizados
  (sin suponer normalidad), se regenera la serie con la recursión estimada y se reestima. En los fondos D y E la
  persistencia α+β queda en el tope de 0,9999 en gran parte de las réplicas: volatilidad casi integrada, por lo que
  su vida media no está acotada.
- **Pensiones, bootstrap estacionario de la historia (200 historias)** (Politis y Romano, 1994): bloques de meses
  completos, con largo geométrico de media 12 y remuestreo circular. En cada historia se reestima el HMM, se regeneran
  2.000 escenarios que parten del régimen actual y se comparan las estrategias. Es la única fuente que captura la
  incertidumbre de la **prima de retorno**, que la estimación puntual toma como dada.
- **Correlación C–E**: IC de Fisher con n = 36. Supone observaciones independientes; con autocorrelación, el
  intervalo real es algo más ancho.

Lectura: la dispersión del bootstrap de la historia es mucho mayor que la de los 13 supuestos de robustez, porque
estos últimos reutilizan la misma historia. La ventaja del ciclo de vida es casi lineal en la prima real A − E
(correlación ≈0,95). El error Monte Carlo dentro de cada historia (2.000 escenarios) es pequeño frente a la
variación entre historias. Cada réplica tiene su propia semilla (`SeedSequence.spawn`), así que el resultado es
idéntico con 1 o con 8 procesos (se paraleliza con `ProcessPoolExecutor`).

## 8. Escenarios de mercado forward-looking (`config.ESG`)

El Monte Carlo base supone que el futuro se parece a 2002-2026. Aquí cada fondo se **recentra** en un retorno real
esperado construido por bloques:

  r_f = g_f · r_crecimiento + (1 − g_f) · r_protección,

donde g_f es la participación de activos de crecimiento del fondo (sección 4). Los meses sorteados se multiplican por
un factor constante por fondo, calibrado para que la media geométrica **simulada** sea exactamente r_f. Se conservan
regímenes, volatilidades, colas y correlaciones.

| Caso | r_protección | r_crecimiento | Fuente |
|---|---|---|---|
| Histórico 2002-2026 | — | — | sin recentrar |
| Consenso de mercado 2026 | 2,52% | 4,4% | Bono BCU/BTU en UF a 10 años (BCCh, jun-2026); MSCI ACWI 7,0% USD − inflación 2,5% (J.P. Morgan LTCMA 2026) |
| Prima de crecimiento nula | 2,52% | 2,52% | cota inferior |

Se supone paridad de poder de compra de largo plazo, es decir, que el retorno real en USD es aproximadamente el
retorno real en UF. No se descuentan comisiones, porque en Chile se cobran sobre el sueldo y no sobre el saldo.

## 9. Pensión total con la reforma (`reforma.py`, Ley N.º 21.735)

El Monte Carlo base mide la pensión **autofinanciada con el 10% del trabajador**, que es la que depende de la
estrategia. Esta sección suma, sobre las mismas trayectorias (supuestos de consenso 2026), lo que agrega la reforma:

1. **Cotización del empleador a la cuenta individual**, según la fecha de cada aporte (tabla 1 de la Nota Técnica):
   0,1% (ago-2025), 0,25% (2027), subiendo 0,7 p.p. al año hasta 4,5% (ago-2033), y 0,15 p.p. al año desde
   sep-2045 hasta 6% (sep-2054). Para el afiliado tipo promedia ~4,7% del sueldo en su vida laboral. Como la
   acumulación es lineal en los aportes, se calcula como una capa separable con la misma estrategia y los mismos retornos.
2. **Cotización con Rentabilidad Protegida** (0,9% en 2026, 1,5% desde 2027 y bajando desde 2045 hasta 0% en 2054):
   bono en UF que devenga la tasa de los bonos de Tesorería en UF (2,52% real). Al pensionarse se paga en 240 cuotas
   a la cuenta individual, así que en valor presente se suma al saldo al retiro.
3. **PGU**: $250.275 (feb-2026; UF de referencia 39.703,50) desde los 65 años. Es completa si la pensión base (capas
   1 a 3) es menor que la pensión inferior ($789.139) y decrece linealmente hasta cero en la pensión superior
   ($1.252.602). Se supone que la persona cumple la focalización.

No se modelan el Beneficio por Años Cotizados (rige para quienes se pensionan hasta ago-2055; el afiliado tipo se
pensiona en 2061-2066) ni la compensación por expectativa de vida (solo para quienes se pensionan desde los 65).

## 10. Glidepath óptimo (`optimo.py`)

Pregunta: ¿qué tan lejos está el glidepath oficial del mejor posible? Se busca en la familia "meseta y bajada
lineal" g(edad) = g0 hasta a1, luego lineal hasta g1 al retiro, con g0 ∈ {60%…100%}, a1 ∈ {30…55} y
g1 ∈ {8%…80%}. Sobre 100% se extrapola por la recta A–E, como en la sección 4.

- **Criterio**: utilidad CRRA de la pensión total mensual, reportada como **equivalente cierto**
  EC = (E[x^(1−γ)])^(1/(1−γ)). γ = 3 es la base; se prueba también con 2 y 5. Se evalúa con y sin la reforma (PGU incluida).
- **Sin sobreajuste**: la grilla se recorre sobre 5.000 escenarios de entrenamiento (semilla 101) y el ganador
  se compara con el oficial y la ley sobre 5.000 escenarios de prueba independientes (semilla 202), con supuestos
  de consenso 2026.
- **Lectura**: la superficie es plana cerca del óptimo, así que diferencias de menos de 1% no son relevantes. El
  resultado robusto es cualitativo: la PGU, que es una renta segura y decreciente en la pensión propia, desplaza el
  óptimo hacia más riesgo al retiro.

Limitación: es una familia paramétrica, no programación dinámica. El óptimo no reacciona al saldo acumulado ni al
régimen de mercado, igual que el glidepath oficial, así que la comparación es justa.

## 11. Microsimulación poblacional (`microsimulacion.py`)

Reemplaza al afiliado tipo por una **cohorte sintética de 20.000 personas** que empieza a cotizar a los 25 años en 2026.

- **Ingreso**: lognormal por sexo, calibrada con la mediana (SP, jun-2026: $1.076.628 H, $926.383 M) y la media
  (SP, abr-2026: $1.419.609 H, $1.263.282 M) del ingreso imponible de los cotizantes: σ = √(2·ln(media/mediana)).
  Se interpreta como el sueldo a los 40 años, se proyecta con el perfil de edad del proyecto y se trunca en el tope
  imponible (90 UF).
- **Densidad de cotización**: Beta(μκ, (1−μ)κ) con μ por sexo (57,9% H, 49,6% M; SP, Informe de Género) y κ = 2,
  correlacionada con el ingreso (ρ = 0,3, cópula gaussiana). κ y ρ son supuestos.
- **Lagunas como rachas**: el empleo formal es una cadena de Markov mensual con racha formal media de 36 meses y
  probabilidad estacionaria igual a la densidad de cada persona. No da lo mismo cotizar a los 25 que a los 60.
- **Mercado común**: las 20.000 personas enfrentan los mismos 400 escenarios de consenso 2026. Como el saldo es lineal
  en los aportes, el saldo de todas las personas en todos los escenarios es A·Gᵀ, con A la matriz de aportes
  (personas × meses) y G[s,t] el factor de crecimiento del mes t al retiro en el escenario s.
- **Pensión total**: capas de la sección 9. La PGU excluye al 10% de mayores ingresos de toda la población (aproximación
  de la focalización).
- **Brecha de género (Shapley)**: v(S) es la pensión total mediana de las mujeres cuando se les asignan las
  características de los hombres del conjunto S ⊆ {densidad, ingreso, edad de pensión, mortalidad}. El aporte de cada
  factor es su efecto marginal promedio sobre los 4! órdenes (16 evaluaciones, con las mismas personas y rachas). Los
  aportes suman exactamente la brecha; el residuo es el fondo por defecto por sexo y el muestreo.

Limitaciones: la densidad y el ingreso de cada persona son estables durante toda su vida (salvo el perfil de edad);
no hay movilidad entre quintiles. Tampoco se modelan cotizantes independientes ni ahorro voluntario.

## 12. Regímenes con variables macro (`regimenes_macro.py`)

Pregunta: ¿la macro chilena ayuda a anticipar los cambios de régimen?

- **Datos**: IPC (variación mensual), TPM, dólar observado e Imacec desde la API pública de mindicador.cl
  (`scripts/descarga_mindicador.py`), que republica series del BCCh y el INE. El cobre solo está desde 2013 y no se usa.
- **Variables sin mirar al futuro**: inflación de 12 meses con 1 mes de rezago (el IPC se publica a inicios del mes
  siguiente); cambio de la TPM en 6 meses; variación logarítmica del dólar en 3 meses; Imacec anual con 2 meses de
  rezago. Se estandarizan con la media y la desviación de la ventana de entrenamiento.
- **Modelo (TVTP-HMM; Diebold, Lee y Weinbach, 1994)**: P(s_{t+1}=j | s_t=i, z_t) = softmax_j(b_ij + w_ij·z_t), con
  j = i como referencia. EM completo: forward-backward escalado con una matriz por mes; en el paso M, cada fila es una
  regresión logística multinomial ponderada por las transiciones esperadas ξ_t, con penalización ridge (λ = 1) y
  L-BFGS con gradiente analítico. Parte del HMM constante estimado (pesos w = 0).
- **Evaluación walk-forward**: desde ene-2015 se reestima cada 12 meses solo con el pasado y se mide la densidad
  predictiva a un paso, log p(r_{t+1} | información hasta t), en 140 meses. Se compara contra el HMM constante y una
  normal multivariada sin regímenes, con el test de Diebold-Mariano con varianza HAC (Newey-West, 6 rezagos).

Resultado: los regímenes mejoran claramente la predicción frente a la normal, pero el TVTP no mejora al HMM constante.
El resultado se mantiene con λ = 0,1 (sobreajusta: −0,06 por mes) y λ = 10 (converge al constante). El BIC de la
muestra completa también prefiere el modelo constante. Lectura: el régimen de tasas volátiles se inició una sola
vez (2019), así que no hay transiciones suficientes para aprender sus gatillos.
