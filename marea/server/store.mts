import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { normalizePool, type OutcomeId, type Side } from "../src/domain/parimutuel";
import type { SettlementState } from "../src/domain/settlement";
import {
  CUENTAS_SISTEMA,
  asiento,
  conciliarTesoreria,
  cuadre,
  cuentaPozo,
  cuentaUsuario,
  saldos,
  type Asiento,
} from "../src/domain/contabilidad";

/**
 * Persistencia. Sin esto el producto no existe: alguien apuesta, cierra la app,
 * y su apuesta nunca existió. Es el agujero más grave que hemos tenido.
 *
 * Formato: un solo JSON en disco, escrito de forma **atómica** (archivo
 * temporal + rename) en cada mutación, antes de responderle al usuario. Si el
 * proceso se muere a media escritura, queda el archivo anterior íntegro; si el
 * usuario vio "listo", su apuesta ya está en disco.
 *
 * Sin base de datos a propósito: cero dependencias nativas, cero servicio extra
 * que se pueda caer, y un archivo que se puede leer con los ojos cuando algo
 * sale raro. Cuando el volumen lo pida, esto se cambia por SQLite sin tocar el
 * resto — todo pasa por este módulo.
 */

export interface Usuario {
  id: string;
  /** Como se llama a sí mismo. Único, sin distinguir mayúsculas. */
  usuario: string;
  /** Correo opcional, sólo para recuperar la cuenta. No se pide para entrar. */
  correo?: string;
  hash: string;
  salt: string;
  creado: string;
  puntos: number;
  /** Última recarga diaria reclamada, para no regalar puntos infinitos. */
  ultimaRecarga?: string;
  /** Hash del código de recuperación. El código en claro no se guarda nunca. */
  recuperacionHash?: string;
  recuperacionSalt?: string;
}

export interface Apuesta {
  id: string;
  usuarioId: string;
  marketId: string;
  side: Side;
  stake: number;
  /** Probabilidad del pozo al entrar, para poder mostrar a qué precio entró. */
  precio: number;
  at: string;
  /** Lo pagado al liquidar. `undefined` mientras el mercado siga vivo. */
  pagado?: number;
  pagadoAt?: string;
}

export interface PozoGuardado {
  marketId: string;
  /** Lo apostado a cada resultado, por id. El binario usa `si` y `no`. */
  outcomes: Record<OutcomeId, number>;
  feeBps: number;
}

/**
 * Tesorería: la comisión que se lleva la casa, mercado por mercado.
 *
 * Antes de esto, `settle()` calculaba la comisión y **nadie la recibía**: se
 * restaba del reparto y desaparecía. Con puntos no se nota; con dinero es la
 * forma exacta de perderle la pista al dinero. Aquí queda con su asiento, con
 * fecha y con el mercado que la generó, para poder cuadrarla contra el pozo
 * (R-064).
 */
export interface AsientoComision {
  marketId: string;
  monto: number;
  at: string;
}

/**
 * Versión del formato en disco.
 *
 *  - 1: el pozo era `{ marketId, si, no, feeBps }`, dos columnas fijas.
 *  - 2: el pozo es `{ marketId, outcomes, feeBps }`, un mapa por resultado.
 *  - 3: aparece el libro de partida doble, con su asiento de apertura.
 *
 * Se lee cualquiera de las dos y se escribe siempre la nueva. Un pozo que no
 * se sepa leer sería dinero de gente que desaparece, así que la migración
 * corre al abrir el archivo y no depende de que nadie se acuerde.
 */
export const VERSION_DATOS = 3;

interface Datos {
  version: number;
  usuarios: Usuario[];
  apuestas: Apuesta[];
  pozos: PozoGuardado[];
  liquidaciones: SettlementState[];
  comisiones: AsientoComision[];
  /**
   * Libro de partida doble. Convive con `comisiones`, que es el resumen que ya
   * usaba la tesorería: el libro es la fuente auditable y `conciliar()` grita
   * si los dos dejan de coincidir.
   */
  libro: Asiento[];
}

const VACIO: Datos = {
  version: VERSION_DATOS,
  usuarios: [],
  apuestas: [],
  pozos: [],
  liquidaciones: [],
  comisiones: [],
  libro: [],
};

/**
 * Lleva los datos leídos al formato vigente. Es idempotente: correrla sobre
 * datos ya migrados los deja igual, que es lo que permite arrancar el proceso
 * dos veces sin miedo.
 *
 * Sólo toca la forma del pozo. Usuarios, apuestas, liquidaciones y comisiones
 * no cambiaron de forma, y una migración que reescribe lo que no hace falta es
 * una migración con más superficie para equivocarse.
 */
function migrar(datos: Datos): Datos {
  const alDia =
    datos.version === VERSION_DATOS &&
    datos.pozos.every((p) => "outcomes" in p) &&
    !necesitaApertura(datos);
  if (alDia) return datos;

  const pozos = datos.pozos.map((guardado) => {
    const { marketId } = guardado;
    const pool = normalizePool(guardado);
    return { marketId, outcomes: pool.outcomes, feeBps: pool.feeBps };
  });
  const migrado = { ...datos, version: VERSION_DATOS, pozos };
  return necesitaApertura(migrado) ? conApertura(migrado) : migrado;
}

/** Hay saldos vivos pero el libro está vacío: falta el asiento de apertura. */
function necesitaApertura(datos: Datos): boolean {
  if (datos.libro.length > 0) return false;
  return datos.usuarios.length > 0 || datos.pozos.length > 0;
}

/**
 * Asiento de apertura.
 *
 * El libro nace después de que ya había gente con puntos y mercados con pozo.
 * Sin registrar ese punto de partida, la primera apuesta de un usuario viejo
 * dejaría su cuenta en negativo — parecería que le prestamos, y no hay crédito
 * jamás. Es lo mismo que hace cualquier contabilidad que empieza a llevarse
 * sobre un negocio que ya andaba: se abre con los saldos que había.
 */
function conApertura(datos: Datos): Datos {
  const patas: { cuenta: string; monto: number }[] = [];
  let total = 0;
  for (const usuario of datos.usuarios) {
    if (usuario.puntos === 0) continue;
    patas.push({ cuenta: cuentaUsuario(usuario.id), monto: usuario.puntos });
    total += usuario.puntos;
  }
  for (const pozo of datos.pozos) {
    const suma = Object.values(pozo.outcomes).reduce((s, v) => s + v, 0);
    if (suma === 0) continue;
    patas.push({ cuenta: cuentaPozo(pozo.marketId), monto: suma });
    total += suma;
  }
  if (patas.length === 0) return datos;
  // la contrapartida de todo lo que ya existía entra por `entrada`
  patas.push({ cuenta: CUENTAS_SISTEMA.entrada, monto: -total });
  return {
    ...datos,
    libro: [asiento("deposito", patas, "apertura")],
  };
}

export class Store {
  private datos: Datos;
  private readonly archivo: string;

  constructor(readonly directorio: string) {
    mkdirSync(directorio, { recursive: true });
    this.archivo = join(directorio, "marea.json");
    const { datos, migrado } = this.leer();
    this.datos = datos;
    // si hubo migración se escribe ya, no en la primera mutación que llegue:
    // un archivo que sigue en el formato viejo después de arrancar es una
    // migración que depende de que alguien apueste para completarse
    if (migrado && existsSync(this.archivo)) this.guardar();
  }

  private leer(): { datos: Datos; migrado: boolean } {
    if (!existsSync(this.archivo)) {
      return { datos: structuredClone(VACIO), migrado: false };
    }
    try {
      const leido = JSON.parse(readFileSync(this.archivo, "utf8")) as Datos;
      const completo = { ...structuredClone(VACIO), ...leido };
      const datos = migrar(completo);
      return { datos, migrado: datos !== completo };
    } catch (error) {
      // un archivo corrupto no se sobrescribe en silencio: se conserva para
      // poder mirarlo, y arrancamos vacíos declarándolo en el log
      const respaldo = `${this.archivo}.roto-${Date.now()}`;
      renameSync(this.archivo, respaldo);
      console.error(`store: archivo ilegible, respaldado en ${respaldo}`, error);
      return { datos: structuredClone(VACIO), migrado: false };
    }
  }

  /** Escritura atómica: o queda el archivo nuevo entero, o el viejo entero. */
  private guardar(): void {
    const temporal = `${this.archivo}.tmp`;
    writeFileSync(temporal, `${JSON.stringify(this.datos, null, 2)}\n`);
    renameSync(temporal, this.archivo);
  }

  /**
   * Toda mutación pasa por aquí y persiste **antes** de que el llamador pueda
   * responderle a nadie. Es la diferencia entre "se apostó" y "parecía que sí".
   */
  private mutar<T>(fn: (datos: Datos) => T): T {
    const resultado = fn(this.datos);
    this.guardar();
    return resultado;
  }

  /* ------------------------------ usuarios ------------------------------- */

  usuarioPorNombre(usuario: string): Usuario | undefined {
    const clave = usuario.trim().toLowerCase();
    return this.datos.usuarios.find((u) => u.usuario.toLowerCase() === clave);
  }

  /** Todos, para la tabla de posiciones. Sin hashes: eso no sale de aquí. */
  usuarios(): Usuario[] {
    return this.datos.usuarios;
  }

  usuarioPorId(id: string): Usuario | undefined {
    return this.datos.usuarios.find((u) => u.id === id);
  }

  crearUsuario(usuario: Usuario): Usuario {
    return this.mutar((datos) => {
      datos.usuarios.push(usuario);
      // los puntos de bienvenida entran por `entrada`, como entraría un
      // depósito. Sin asentarlos, el saldo contable del usuario no cuadraría
      // con sus puntos y la auditoría no serviría de nada
      if (usuario.puntos > 0) {
        datos.libro.push(
          asiento(
            "deposito",
            [
              { cuenta: CUENTAS_SISTEMA.entrada, monto: -usuario.puntos },
              { cuenta: cuentaUsuario(usuario.id), monto: usuario.puntos },
            ],
            usuario.id,
          ),
        );
      }
      return usuario;
    });
  }

  /**
   * Mueve puntos. Nunca deja un saldo negativo: sin crédito, jamás — es la
   * promesa de juego responsable y por eso vive en el código (R-026).
   */
  moverPuntos(usuarioId: string, delta: number): number {
    return this.mutar((datos) => {
      const usuario = datos.usuarios.find((u) => u.id === usuarioId);
      if (!usuario) throw new Error("usuario desconocido");
      const saldo = usuario.puntos + delta;
      if (saldo < 0) throw new Error("saldo insuficiente");
      usuario.puntos = saldo;
      return saldo;
    });
  }

  /** Cambia la contraseña. Se usa al recuperar la cuenta. */
  cambiarPassword(usuarioId: string, hash: string, salt: string): void {
    this.mutar((datos) => {
      const usuario = datos.usuarios.find((u) => u.id === usuarioId);
      if (!usuario) throw new Error("usuario desconocido");
      usuario.hash = hash;
      usuario.salt = salt;
    });
  }

  marcarRecarga(usuarioId: string, dia: string, monto: number): number {
    return this.mutar((datos) => {
      const usuario = datos.usuarios.find((u) => u.id === usuarioId);
      if (!usuario) throw new Error("usuario desconocido");
      usuario.ultimaRecarga = dia;
      usuario.puntos += monto;
      if (monto > 0) {
        datos.libro.push(
          asiento(
            "deposito",
            [
              { cuenta: CUENTAS_SISTEMA.entrada, monto: -monto },
              { cuenta: cuentaUsuario(usuarioId), monto },
            ],
            usuarioId,
          ),
        );
      }
      return usuario.puntos;
    });
  }

  /* ------------------------------- pozos --------------------------------- */

  pozo(marketId: string): PozoGuardado | undefined {
    return this.datos.pozos.find((p) => p.marketId === marketId);
  }

  pozos(): PozoGuardado[] {
    return this.datos.pozos;
  }

  /** Siembra el pozo la primera vez que se ve el mercado, y sólo esa vez. */
  asegurarPozo(pozo: PozoGuardado): PozoGuardado {
    const existente = this.pozo(pozo.marketId);
    if (existente) return existente;
    return this.mutar((datos) => {
      datos.pozos.push(pozo);
      // la semilla es dinero de la casa que corre la misma suerte que el
      // usuario (R-057). Entra al pozo con su asiento, o el pozo terminaría
      // repartiendo más de lo que registró haber recibido
      const semilla = Object.values(pozo.outcomes).reduce((s, v) => s + v, 0);
      if (semilla > 0) {
        datos.libro.push(
          asiento(
            "semilla",
            [
              { cuenta: CUENTAS_SISTEMA.entrada, monto: -semilla },
              { cuenta: cuentaPozo(pozo.marketId), monto: semilla },
            ],
            pozo.marketId,
          ),
        );
      }
      return pozo;
    });
  }

  /* ------------------------------ apuestas ------------------------------- */

  apuestasDe(usuarioId: string): Apuesta[] {
    return this.datos.apuestas.filter((a) => a.usuarioId === usuarioId);
  }

  /**
   * Cuánta gente distinta hay en un mercado, no cuántas apuestas.
   *
   * Es la cifra que dice si el mercado está vivo: veinte apuestas de una
   * persona son una persona hablando sola, y R-059 ya anula ese caso al
   * liquidar. Mostrar el número de apuestas en vez del de personas sería
   * inflar la sensación de actividad con el mismo truco.
   */
  participantesDe(marketId: string): number {
    const gente = new Set<string>();
    for (const apuesta of this.datos.apuestas) {
      if (apuesta.marketId === marketId) gente.add(apuesta.usuarioId);
    }
    return gente.size;
  }

  apuestasDeMercado(marketId: string): Apuesta[] {
    return this.datos.apuestas.filter((a) => a.marketId === marketId);
  }

  /**
   * Apostar es una sola transacción: se descuenta el saldo, crece el pozo y
   * nace la apuesta. Se persiste una vez, al final: no puede quedar un usuario
   * con los puntos descontados y sin apuesta.
   */
  apostar(input: {
    usuarioId: string;
    marketId: string;
    side: Side;
    stake: number;
    precio: number;
  }): Apuesta {
    return this.mutar((datos) => {
      const usuario = datos.usuarios.find((u) => u.id === input.usuarioId);
      if (!usuario) throw new Error("usuario desconocido");
      if (usuario.puntos < input.stake) throw new Error("saldo insuficiente");
      const pozo = datos.pozos.find((p) => p.marketId === input.marketId);
      if (!pozo) throw new Error("mercado desconocido");

      if (!(input.side in pozo.outcomes)) {
        // un id que el mercado no declaró no crea un lado nuevo: sería dinero
        // apostado a un resultado que nunca va a poder ganar
        throw new Error("resultado desconocido");
      }

      usuario.puntos -= input.stake;
      pozo.outcomes[input.side] += input.stake;

      const apuesta: Apuesta = {
        id: `${input.marketId}-${datos.apuestas.length + 1}`,
        usuarioId: input.usuarioId,
        marketId: input.marketId,
        side: input.side,
        stake: input.stake,
        precio: input.precio,
        at: new Date().toISOString(),
      };
      datos.apuestas.push(apuesta);
      // el mismo movimiento, en el libro: sale del usuario y entra al pozo del
      // mercado. La casa no toca nada aquí (R-057)
      datos.libro.push(
        asiento(
          "apuesta",
          [
            { cuenta: cuentaUsuario(input.usuarioId), monto: -input.stake },
            { cuenta: cuentaPozo(input.marketId), monto: input.stake },
          ],
          input.marketId,
        ),
      );
      return apuesta;
    });
  }

  /* ---------------------------- liquidaciones ---------------------------- */

  liquidacion(marketId: string): SettlementState | undefined {
    return this.datos.liquidaciones.find((l) => l.marketId === marketId);
  }

  liquidaciones(): SettlementState[] {
    return this.datos.liquidaciones;
  }

  guardarLiquidacion(estado: SettlementState): void {
    this.mutar((datos) => {
      const indice = datos.liquidaciones.findIndex((l) => l.marketId === estado.marketId);
      if (indice >= 0) datos.liquidaciones[indice] = estado;
      else datos.liquidaciones.push(estado);
    });
  }

  /**
   * Paga un mercado entero: acredita a cada ganador y marca las apuestas.
   * Idempotente por construcción — una apuesta ya pagada no se vuelve a pagar,
   * así que correr el ciclo dos veces no duplica dinero.
   */
  pagarMercado(marketId: string, pagos: Record<string, number>): number {
    return this.mutar((datos) => {
      const at = new Date().toISOString();
      let acreditado = 0;
      for (const apuesta of datos.apuestas) {
        if (apuesta.marketId !== marketId) continue;
        if (apuesta.pagado !== undefined) continue;
        const monto = pagos[apuesta.id] ?? 0;
        apuesta.pagado = monto;
        apuesta.pagadoAt = at;
        if (monto > 0) {
          const usuario = datos.usuarios.find((u) => u.id === apuesta.usuarioId);
          if (usuario) {
            usuario.puntos += monto;
            acreditado += monto;
            datos.libro.push(
              asiento(
                "liquidacion",
                [
                  { cuenta: cuentaPozo(marketId), monto: -monto },
                  { cuenta: cuentaUsuario(usuario.id), monto },
                ],
                marketId,
              ),
            );
          }
        }
      }
      return acreditado;
    });
  }

  /** Acredita la comisión de un mercado. Idempotente por mercado. */
  acumularComision(marketId: string, monto: number): number {
    if (monto <= 0) return this.tesoreria();
    return this.mutar((datos) => {
      // una comisión por mercado: correr el ciclo dos veces no cobra dos veces
      if (!datos.comisiones.some((c) => c.marketId === marketId)) {
        datos.comisiones.push({ marketId, monto, at: new Date().toISOString() });
        // y su asiento: la comisión sale del pozo y llega a tesorería. Una
        // comisión que se calcula y desaparece es perderle la pista al dinero
        datos.libro.push(
          asiento(
            "liquidacion",
            [
              { cuenta: cuentaPozo(marketId), monto: -monto },
              { cuenta: CUENTAS_SISTEMA.tesoreria, monto },
            ],
            marketId,
          ),
        );
      }
      return datos.comisiones.reduce((suma, c) => suma + c.monto, 0);
    });
  }

  tesoreria(): number {
    return this.datos.comisiones.reduce((suma, c) => suma + c.monto, 0);
  }

  comisiones(): AsientoComision[] {
    return this.datos.comisiones;
  }

  /* ---------------------------- contabilidad ----------------------------- */

  libro(): Asiento[] {
    return this.datos.libro;
  }

  /** Suma de todas las cuentas. Cero, o hay dinero perdido. */
  cuadre(): number {
    return cuadre(this.datos.libro);
  }

  saldosContables(): Record<string, number> {
    return saldos(this.datos.libro);
  }

  /**
   * La tesorería que reporta el resumen contra la que dice el libro. Si se
   * separan, alguien cobró comisión por fuera de contabilidad.
   */
  conciliar() {
    return conciliarTesoreria(this.datos.libro, this.tesoreria());
  }

  resumen() {
    const conciliacion = this.conciliar();
    return {
      tesoreria: Math.round(this.tesoreria()),
      /** Cero, o hay dinero perdido. Se mira en cada arranque. */
      cuadre: this.cuadre(),
      conciliaTesoreria: conciliacion.cuadra,
      usuarios: this.datos.usuarios.length,
      apuestas: this.datos.apuestas.length,
      mercadosConPozo: this.datos.pozos.length,
      liquidados: this.datos.liquidaciones.filter(
        (l) => l.phase === "pagado" || l.phase === "devuelto",
      ).length,
    };
  }
}
