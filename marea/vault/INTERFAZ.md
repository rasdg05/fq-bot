# INTERFAZ — cómo se presenta un mercado

Análisis comparado contra Kalshi (28 jul 2026, capturas de `kalshi.com/browse`)
y decisiones que salen de ahí. No es admiración: es identificar qué resuelve su
interfaz que la nuestra no, y qué resolvemos nosotros que ellos no.

---

## 1. El defecto que encontramos: probabilidad de un solo lado

**Lo que hacíamos.** La card mostraba `54 % · Paga 1.8×`. Un número, un lado.

**Por qué está mal.** Quien va a apostar necesita ver **contra qué** apuesta. Con
un solo número, el No es invisible: no se sabe qué paga, ni cuánto cuesta estar
del otro lado. Es media pantalla de información para una decisión de dos lados.

**Lo que hace Kalshi.** Cada mercado muestra las dos (o más) opciones con su
probabilidad y su multiplicador, uno debajo del otro:

```
MIN Lynx   2.29x   42 %
LV Aces    5.56x   17 %
```

**Lo que hicimos.** La card muestra ahora los dos lados con su pago (R-063):

```
54 %                 46 %
Sí · paga 1.80×      No · paga 2.12×
```

Esto es más honesto y además hace el producto más entendible sin explicación:
la suma de los dos porcentajes se ve, y el pago de cada lado se compara de un
vistazo.

---

## 2. Lo que Kalshi resuelve y nosotros todavía no

Por orden de cuánto cambia la sensación de "esto es serio":

| Qué | Por qué importa | Costo |
|---|---|---|
| **Volumen por mercado** (`$1,910,826 vol`) | Es la prueba social. Un mercado con volumen dice "aquí hay gente"; sin él, todo parece vacío | Bajo — el pozo ya existe, falta mostrar cuánta gente |
| **Número de participantes** | Más honesto que el volumen para nosotros: "17 personas" dice más que "1,700 pts" | Bajo |
| **Mercados agrupados por evento** (`31 markets`) | Un evento con varias preguntas se lee como un tema, no como ruido suelto | Medio — falta el concepto de "evento" |
| **Más de dos resultados** ("¿A qué equipo va Kuminga?" con 4 opciones) | Muchas preguntas reales no son sí/no. Hoy sólo sabemos hacer binario | **Alto** — cambia el motor |
| **Escudos, fotos, banderas** | Un mercado con el escudo del América se reconoce en 200 ms; uno de puro texto, no | Medio |
| **LIVE con marcador en curso** (`6 4 0 · 55 %`) | Convierte la app en algo que se deja abierto durante el partido | Medio — ESPN ya da el marcador en vivo |
| **Fecha de cierre explícita** (`Aug 4 @ 6:00AM`) | "Cierra en 4 d" es vago cuando decides con calendario | Bajo |

## 3. Lo que nosotros hacemos y ellos no

No es poco, y es lo que hay que defender mientras copiamos lo de arriba:

- **El criterio de resolución se lee antes de apostar.** En Kalshi hay que
  buscarlo. En Marea está sobre el botón, con la fuente citada.
- **La evidencia del pago.** Cuando un mercado resuelve, mostramos la lectura
  exacta: "cierre 72,500 USD frente al umbral de 71,000". Cobrar no es un acto
  de fe.
- **El Edge con nombre.** Cuando comparamos contra otra casa, decimos cuál. No
  presentamos una lectura ajena como propia.
- **Español de Latam y mercados de aquí.** Ellos tienen tenis ITF y la WNBA;
  nosotros la Liga MX y la inflación de Brasil.

## 4. Regla de presentación

> Un mercado se presenta con **los dos lados visibles**, cada uno con su
> probabilidad y su pago, y con el criterio de resolución a un tap. Mostrar un
> solo lado es mostrar medio mercado (R-063).

---

## 5. Cómo entra el dinero y adónde va la comisión

Auditado el 28 de julio, y encontramos un agujero.

### Hoy, con puntos

```
bienvenida (1,000) → apuesta (sale del saldo, entra al pozo)
                   → liquidación: pozo × (1 − 3 %) a los ganadores
                   → 3 % a la tesorería
```

**El agujero que había:** el 3 % se calculaba, se restaba del reparto y **no lo
recibía nadie**. Desaparecía. Con puntos sólo era deflación invisible; con
dinero es exactamente la forma de perderle la pista al dinero.

**Corregido (R-064):** la comisión se asienta en tesorería con su mercado, su
monto y su fecha. Se puede cuadrar contra el pozo, y correr el ciclo dos veces
no cobra dos veces. Visible en `/salud`.

### Cuando entre dinero real

El camino, con lo que ya existe y lo que falta:

| Paso | Estado |
|---|---|
| El usuario conecta su wallet (EIP-1193) | ✓ construido, sin depender de nadie |
| El usuario deposita USDC a una dirección | Simulado — falta custodia real |
| El saldo se acredita al confirmarse en cadena | ✗ falta el lector de cadena |
| Apuesta → pozo, igual que hoy | ✓ el motor no cambia |
| Liquidación → pago a la wallet del usuario | ✗ falta firmar transacciones |
| Comisión → tesorería | ✓ la contabilidad ya existe |
| Retiro | ✗ falta, y es lo que más se revisa legalmente |

**La decisión de arquitectura que hay que tomar antes de escribir una línea:**

- **Custodial** (nosotros guardamos las llaves): la experiencia es la mejor —
  saldo instantáneo, sin gas, sin firmar nada. Pero somos custodios de dinero
  ajeno, lo cual dispara licencia, auditoría y responsabilidad penal.
- **No custodial** (cada quien firma): sin licencia de custodia, pero cada
  apuesta es una transacción firmada con su comisión de red, y la experiencia
  cae mucho.
- **Híbrido**: el pozo vive en un contrato y nosotros sólo operamos la
  resolución. Es lo que hace Polymarket, y es lo que mejor encaja con nuestra
  promesa de que la casa no es contraparte.

Ninguna se decide sin la opinión legal de `COMPLIANCE.md`. Lo que sí se puede
hacer sin esperar a nadie: dejar la contabilidad lista, que es lo que acabamos
de hacer.
