# COMPLIANCE — custodia y marco legal

> **Esto no es asesoría legal.** Es el marco de decisión y el estado de cada
> pregunta abierta, para que cuando llegue la opinión legal de cada país se
> traduzca en una línea de `src/domain/eligibility.ts` y no en una discusión.
> Ninguna casilla pasa a `permitido` sin opinión escrita de un abogado local.

## 1. La decisión de custodia

Es la decisión más cara de revertir, así que se toma explícita.

| Modelo | Qué implica | Riesgo | Veredicto |
|---|---|---|---|
| **Custodial propio** — Marea guarda el saldo | Somos intermediario financiero: licencia, capital, auditoría, seguro. Un hackeo nos hunde | Máximo. Es el punto que `marca/vision_apuestas_wallet.md` §5 marca como "lo más peligroso del plan" | **No** para soft launch |
| **Non-custodial con wallet embebida** — la llave es del usuario, la UX la esconde | El usuario firma; Marea no puede mover fondos ajenos. Proveedor (Privy/Turnkey) gestiona la llave con MPC | Medio: dependencia del proveedor, no custodia | **Sí**, camino elegido |
| **Sólo conectar wallet externa** | Cero custodia y cero dependencia | Fricción alta para el neófito, que es justo nuestro público | Camino secundario |

**Decidido:** wallet embebida non-custodial como camino primario, conectar como
secundario. Marea nunca tiene poder unilateral sobre el saldo del usuario. El
código ya está estructurado así: `WalletAdapter` no expone ninguna operación
que mueva fondos sin el usuario.

Consecuencia que hay que aceptar: si el usuario pierde el acceso, Marea no
puede "devolverle" su dinero. El copy tiene que decirlo antes del primer
depósito, no en los términos y condiciones.

## 2. Ejecución: quién es la contraparte

Con `trade_execution_mode = "aggregated"`, Marea rutea a un mercado externo y
no toma el otro lado. Eso nos saca de ser casa de apuestas y nos deja como capa
de acceso — pero **el venue externo tiene sus propias restricciones de país**,
y las nuestras no las reemplazan. Antes de rutear a un venue hay que confirmar
que acepta usuarios del país del usuario.

Si algún día Marea crea sus propios mercados (camino parimutuel de la visión),
esta conclusión se cae entera y volvemos a ser el operador. Esa decisión
reabre todo este documento.

## 3. Preguntas abiertas por país

Cada fila necesita respuesta escrita de abogado local antes de habilitar
depósitos. El estado inicial de todas es `pendiente` en el código.

| País | Preguntas que hay que responder |
|---|---|
| México | ¿Un mercado de predicción cae bajo la Ley Federal de Juegos y Sorteos, bajo la ley fintech, o en ninguna? ¿El on-ramp local exige que seamos nosotros el sujeto obligado? |
| Argentina | Competencia provincial en juego: ¿hace falta habilitación por provincia? ¿Restricciones cambiarias sobre el on-ramp? |
| Brasil | ¿Aplica el marco de apuestas de cuota fija? ¿Qué exige el Banco Central sobre movimiento de cripto? |
| Chile, Colombia, Perú | ¿Autoridad de juego competente, o queda fuera por ser contrato de evento? |
| Uruguay, Paraguay, Costa Rica, Panamá | ¿Sirven como jurisdicción de constitución sin arrastrar obligación local? |
| Estados Unidos | **Resuelto: bloqueado.** Los contratos de evento exigen bolsa registrada ante el regulador de derivados. Sin esa licencia no hay camino. |

Además, transversal a todos: prevención de lavado (¿desde qué monto hay
obligación de identificar?), residencia fiscal, y si el geobloqueo por IP es
suficiente o hace falta declaración del usuario.

## 4. Lo que el producto ya hace

- `src/domain/eligibility.ts` — tabla por país con tres estados, tope de
  depósito acumulado y periodo de enfriamiento. **Explorar nunca se bloquea**;
  la elegibilidad sólo limita depositar y operar.
- `FLAGS.eligibility_enforced` — apagado en la build simulada, donde no se
  mueve dinero. **Encenderlo es requisito para cualquier build con dinero real**,
  y la validación lo verifica.
- Juego responsable: tope acumulado por país, enfriamiento activable por el
  usuario, y copy explícito de que la pérdida máxima es lo apostado y que nunca
  hay crédito ni apalancamiento.

## 5. Lo que falta y no puede resolverse desde el código

1. Opinión legal escrita por país (§3).
2. Constitución de la entidad y jurisdicción.
3. Contrato con el proveedor de wallet embebida y con el on-ramp, incluyendo
   quién es el sujeto obligado de cada obligación regulatoria.
4. Política de prevención de lavado y su umbral de identificación.
5. Términos y condiciones y política de privacidad revisadas localmente.
6. Seguro y plan de respuesta ante incidente de seguridad.

Hasta que 1 y 3 existan, la app se queda en datos simulados y sin depósitos.
