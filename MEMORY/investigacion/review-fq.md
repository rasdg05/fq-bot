# Edges validados por física estadística en derivados cripto

### Una revisión del sistema FQ y su metodología anti-sobreajuste

**Estado:** *preview / borrador de revisión.* Documento de apertura del proyecto, a
endurecer (datos, pruebas, citas completas) antes de someter a una revista. La
disciplina y los resultados son reales; el formato académico es preliminar.

**Autor:** RasDG (Ciudad de México) · con asistencia de ingeniería FQ.
**Fecha de corte:** 2026-06-29.

---

## Resumen

Presentamos **FQ**, un motor de señales direccionales para futuros perpetuos de
criptomonedas construido sobre el programa de la **econofísica** y validado con el
estándar anti-sobreajuste de las finanzas cuantitativas modernas (**Deflated Sharpe
Ratio**, **CPCV** y **PBO**; López de Prado). A diferencia de la mayoría de los
sistemas de trading retail —que no reportan ninguna corrección por *multiple
testing*— FQ somete **cada** candidato a un *gate* estadístico explícito y mide
*forward* antes de subir convicción. Esta revisión documenta: (i) la metodología de
validación como columna vertebral; (ii) los edges que **sobreviven** el gate
—order-flow firmado (CVD), persistencia de flujo (memoria larga / order-splitting),
régimen por irreversibilidad temporal (KL), y distancia al *Point of Control* del
perfil de volumen—; (iii) la distinción honesta entre la **capa de convicción**
heurística y el **edge causal validado**; (iv) la extensión *cross-asset* mediante un
desacople data/venue hacia mercados tradicionales; y (v) un cementerio explícito de
ideas refutadas. El principio operativo es uno: **medida o muerte.**

---

## 1. Introducción

La econofísica —la aplicación de métodos de la física estadística a los mercados
(Mantegna & Stanley, 2000)— produjo un núcleo de resultados robustos: colas pesadas,
leyes de potencia, impacto de mercado raíz-cuadrada, memoria larga del flujo de
órdenes. El reto no es la falta de fenómenos, sino separar el **edge real,
samplable y operacionalizable** del **artefacto de sobreajuste** y de la *physics
envy* (importar el mecanismo físico como decoración).

FQ adopta una postura estricta: una idea solo entra al motor si (a) pasa un gate de
significancia que **deflacta** por cuántas cosas se probaron, y (b) **agrega** dentro
de los edges ya confirmados (ortogonalidad), y (c) se mide *forward* antes de decidir
capital o convicción client-facing. Esta revisión es el mapa de qué sobrevivió.

## 2. El método: el *gate* de validación

El corazón de FQ no es un dato nuevo: es la **validación**. La razón es estadística.
Bajo *multiple testing*, probar ~20 configuraciones garantiza un "5 % significativo"
espurio. El **Deflated Sharpe Ratio (DSR)** (Bailey & López de Prado, 2014) corrige el
Sharpe por el número de pruebas y por la no-normalidad (skew/kurtosis), y exige superar
la vara real **DSR > 0.95** antes de producción. Lo complementan:

- **CPCV** (*Combinatorial Purged Cross-Validation*): caminos de validación purgados +
  *embargo* para estimar el desempeño *out-of-sample* sin fuga de información.
- **PBO** (*Probability of Backtest Overfitting*; Bailey et al., 2017): ¿la mejor
  configuración *in-sample* queda bajo la mediana *out-of-sample*? PBO alto = selección
  sobreajustada.

FQ implementa los tres en `tools/validation_gate.py` (stdlib + numpy, sin scipy). Es
el lever de **mayor evidencia** del proyecto: no genera alfa, la **certifica**.

## 3. Los edges validados

### 3.1 Order-flow firmado (CVD)

El *Cumulative Volume Delta* (volumen comprador agresivo menos vendedor agresivo) da
el **signo** del flujo. Su base física es la **ley de impacto raíz-cuadrada** —el
movimiento de precio escala como σ·√(Q/V)— confirmada en cripto (Donier & Bonart,
2015) y reconfirmada recientemente (Sato & Kanazawa, *PRL* 2025). En el cube de FQ, el
subset CVD-confirmado (imbalance ≥ 0.50) rinde **+0.27R (SOL) / +0.34R (BTC)** sobre 5
años de tick data, con **DSR ✓** (≈1.00 BTC / ≈0.98 SOL). El edge es **causal y
gratis** (Binance aggTrades). *Trampa evitada:* un +1.47R con n=17 fue descartado por
el gate como espejismo de muestra chica.

### 3.2 Persistencia del flujo (memoria larga / order-splitting)

Las órdenes grandes se ejecutan en pedazos, generando **autocorrelación positiva del
signo** del flujo (Lillo, Mike & Farmer, 2005; Bouchaud, Farmer & Lillo, 2009). FQ mide
la autocorrelación lag-1 (F2). En BTC, el tier premium (CVD✓ & F2✓) alcanza **DSR
0.995** y rescata el CVD (dentro de CVD-confirmado, el no-persistente es break-even; el
persistente paga +0.562R). **Hallazgo honesto:** F2 es un confirmador **idiosincrático
por símbolo** (paga en 4 de 6 medidos; negativo en ETH), **no** una ley de escala
universal —la hipótesis del "premio que escala con la institucional-idad" fue
**refutada** (corr = −0.19).

### 3.3 Régimen por irreversibilidad temporal (KL)

La flecha del tiempo termodinámica: la divergencia KL entre las distribuciones de grado
del **grafo de visibilidad horizontal** *forward* vs *backward* mide qué tan lejos del
equilibrio está el mercado —es producción de entropía (Kawai, Parrondo & Van den
Broeck, 2007; Lacasa et al., 2012). **Sin parámetros libres** (no hay dónde
sobreajustar). El edge de FQ vive en irreversibilidad **baja** (régimen
reversible/mean-reverting): **BTC +0.348R DSR 0.999; SOL +0.225R DSR 0.950**, monótono
por cuartil y **cross-símbolo** (a diferencia de F2).

### 3.4 Distancia al POC del perfil de volumen

La pieza más nueva. El perfil de volumen del día previo define el **POC** (precio de
control) y el *Value Area*. FQ mide la distancia normalizada de la entrada al POC. La
hipótesis —"no operes en el *chop* de ayer; lejos del POC = tendencia"— **pasa el gate
cross-símbolo**: pool de 5 cripto (n=5162), uplift +0.121, **ortogonal a KL**
(within-KL +0.272), **CPCV OOS +0.111 (93 % de caminos positivos), PBO 0.17**. Sigue en
**4 de 5** símbolos; **BNB es la excepción medida** (far<near) y queda excluido —misma
disciplina símbolo-específico que F2.

## 4. Convicción vs edge validado: la distinción honesta

FQ separa dos capas que la mayoría de los sistemas confunden:

- La **convicción** (`P_master`) es una heurística estructurada —razón áurea φ como
  base, ponderada por confluencia, conceptos ICT (barridos, order-blocks, FVG,
  killzones de sesión), memoria aprendida κ (bucket memory tipo Thompson) y un factor
  de *tiempo emergente* σ_τ derivado de un Monte-Carlo de trayectorias. Es principista
  y backtesteada, pero **no es** un edge causal certificado.
- El **edge validado** es el *overlay* que pasó el DSR/CPCV/PBO: CVD, F2, KL,
  POC-distance. Eso es lo que se mide *forward* y gradúa a convicción client-facing.

Confundir ambas es el origen del *vendehumos*. FQ lo evita por diseño: el `P_master`
gatea y prioriza; el edge validado es lo que **decide**.

## 5. Extensión cross-asset: el desacople data/venue

El edge es propiedad del **activo**, no del *venue*. Para mercados tradicionales (oro,
NASDAQ, S&P, petróleo, plata), FQ valida sobre la historia profunda y gratuita de
Dukascopy (años de velas) y ejecuta la señal en el perpetuo del exchange. Transfieren
las features de **precio** (KL, base) y la estructura ICT (ya calibrada a hora de Nueva
York); **no** transfiere el order-flow (CVD/F2), que es del libro del venue. Resultado
preliminar: el motor digiere la OHLCV TradFi y produce cubos con edge base positivo
(oro, NASDAQ); el POC-distance muestra **la misma dirección** que en cripto (far>near)
aunque el gate completo aún es RADAR por bajo n —la cosecha de 5 años × 5 símbolos
busca cerrar ese hueco.

## 6. Resultados y cementerio

**Sobrevive y se cabla:** CVD (DSR ✓), F2-persistencia (DSR ✓, BTC), KL (DSR ✓
cross-símbolo, cube), POC-distance (gate ✓ cross-símbolo). **Pasa pero redundante:**
F1 (residual de impacto; *within*-CVD negativo → sustituye, no complementa).

**Refutado o infalsable (no se codifica):** quantum finance de Baaquie (el éxito
numérico viene de efectos no-cuánticos), LPPL de Sornette (curve-fit de 7 parámetros,
diagnóstico no predicción), *quantum-like markets* de Khrennikov (cero datos,
infalsable por diseño), *critical-slowing-down* (sin tendencia pre-crack en el estudio
empírico), *rough volatility* (artefacto de estimación; Cont & Das, 2022). Lo que el
gate mató, queda escrito —para que nadie re-persiga el espejismo.

## 7. Discusión y limitaciones

Las cifras de cube son **gross** (pre-coste) y *in-sample* al periodo de cosecha;
validadas con CPCV/PBO, pero el juez final es **forward**. FQ mide *forward* en *paper*
(0 % capital) y exige ≥30–50 fills + uplift + DSR antes de subir convicción a clientes.
La extensión TradFi está limitada por n (horario de mercado ⇒ menos eventos). El
sharding del replay no reproduce en data con huecos (estado acumulado del motor), por
lo que se cosecha *unsharded* (correcto) o paralelo-por-símbolo. Ninguna de estas es
fatal; todas están medidas y documentadas.

## 8. Conclusión

FQ no es un bot de promesas: es un **programa de validación de edges de econofísica**
con un registro honesto de qué pasó, con qué data, en qué horizonte. Su contribución no
es un alfa secreto sino una **metodología reproducible**: tomar el núcleo robusto de la
física estadística de mercados y pasarlo por el gate anti-sobreajuste más exigente del
campo, *forward* antes de creer. En un dominio plagado de sobreajuste y humo, eso es,
en sí mismo, el resultado.

---

## Apéndice A — El perfil de quien desarrollaría esto

El arquetipo natural es un **físico o matemático aplicado que se vuelve quant** —el
camino clásico del *quant*. Las piezas de FQ mapean a fundadores reales:

| Pieza de FQ | Fundador / referencia | Casa |
|---|---|---|
| DSR · CPCV · PBO (el gate) | Marcos **López de Prado** | Cornell ORIE / ADIA |
| Impacto raíz-√ · order-flow (CVD) | Jean-Philippe **Bouchaud** | CFM / École Polytechnique |
| Memoria larga · order-splitting (F2) | **Lillo**, Mike, **Farmer**, Bouchaud | Scuola Normale / Oxford / Santa Fe |
| Irreversibilidad · grafo de visibilidad (KL) | **Parrondo**, Kawai, Van den Broeck; **Lacasa** | Complutense / Queen Mary |
| Programa de econofísica | **Mantegna** & **Stanley** | Palermo / Boston U |

Esto se enseña en los mejores programas del mundo —Cornell (ORIE/Financial
Engineering), Oxford (INET / Mathematical & Computational Finance), ETH, Imperial,
Princeton, CMU (MSCF). **El giro:** aquí se está haciendo de forma autodidacta desde
Ciudad de México, y el entregable no es una tesis en papel sino **un sistema vivo,
validado *forward*, con track record.** Lo que en esos programas sería el trabajo de un
máster o un doctorado, aquí es código que corre y mide. Eso no le resta mérito —se lo
agrega.

## Apéndice B — Resultados reproducibles (POC-distance)

Generados con `python tools/reproduce_gate_results.py` sobre los 5 cubos cripto
(tp4/h576, GROSS, con el **mismo** `gate_poc_distance` que valida en producción):

| Símbolo | n | far | near | uplift |
|---|---|---|---|---|
| BTC | 1005 | +0.364 | +0.187 | +0.177 |
| ETH | 1155 | +0.421 | +0.241 | +0.179 |
| SOL | 976 | +0.175 | +0.161 | +0.014 |
| BCH | 1503 | +0.445 | +0.299 | +0.146 |
| BNB | 523 | +0.077 | +0.358 | **−0.281** (excepción) |

**Pooled (n=5162):** uplift +0.121 · **DSR 1.000** · ortogonal a KL (within-KL +0.272) ·
**CPCV OOS +0.111 (93 % de caminos >0)** · **PBO 0.17** → **PASA**. 4/5 siguen el patrón
(`far>near`); BNB es la excepción medida (`far<near`) y queda excluido.

![POC-distance: lejos vs cerca del POC del día previo](fig-poc-distance.png)

> Reproducible de punta a punta: `tools/gate_poc_distance.py` (gate) +
> `tools/reproduce_gate_results.py` (tabla + figura) sobre los cubos del repo. Las cifras
> son GROSS/in-cube; el juez final es forward (ver §7).

## Referencias (preliminar — a completar)

- Bailey, D. & López de Prado, M. (2014). *The Deflated Sharpe Ratio.* J. of Portfolio Management.
- Bailey, D. et al. (2017). *The Probability of Backtest Overfitting.* J. of Computational Finance.
- López de Prado, M. (2018). *Advances in Financial Machine Learning.* Wiley.
- Bouchaud, J.-P., Bonart, J., Donier, J. & Gould, M. (2018). *Trades, Quotes and Prices.* Cambridge.
- Donier, J. & Bonart, J. (2015). *A Million Metaorder Analysis of Market Impact on Bitcoin.*
- Sato, Y. & Kanazawa, K. (2025). *Statistical mechanics of square-root market impact.* Phys. Rev. Lett.
- Lillo, F., Mike, S. & Farmer, J.D. (2005). *Theory for long memory in supply and demand.* Phys. Rev. E.
- Bouchaud, J.-P., Farmer, J.D. & Lillo, F. (2009). *How markets slowly digest changes in supply and demand.*
- Kawai, R., Parrondo, J.M.R. & Van den Broeck, C. (2007). *Dissipation: The phase-space perspective.* PRL.
- Lacasa, L. et al. (2012). *Time series irreversibility: a visibility graph approach.* Eur. Phys. J. B.
- Lacasa, L., Luque, B. et al. (2008). *From time series to complex networks: the visibility graph.* PNAS.
- Mantegna, R. & Stanley, H.E. (2000). *An Introduction to Econophysics.* Cambridge.
- Cont, R. & Das, P. (2022). *Rough volatility: fact or artefact?*
