import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { Side } from "../src/domain/parimutuel";
import type { SettlementState } from "../src/domain/settlement";

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
  si: number;
  no: number;
  feeBps: number;
}

interface Datos {
  version: 1;
  usuarios: Usuario[];
  apuestas: Apuesta[];
  pozos: PozoGuardado[];
  liquidaciones: SettlementState[];
}

const VACIO: Datos = {
  version: 1,
  usuarios: [],
  apuestas: [],
  pozos: [],
  liquidaciones: [],
};

export class Store {
  private datos: Datos;
  private readonly archivo: string;

  constructor(readonly directorio: string) {
    mkdirSync(directorio, { recursive: true });
    this.archivo = join(directorio, "marea.json");
    this.datos = this.leer();
  }

  private leer(): Datos {
    if (!existsSync(this.archivo)) return structuredClone(VACIO);
    try {
      const leido = JSON.parse(readFileSync(this.archivo, "utf8")) as Datos;
      return { ...structuredClone(VACIO), ...leido };
    } catch (error) {
      // un archivo corrupto no se sobrescribe en silencio: se conserva para
      // poder mirarlo, y arrancamos vacíos declarándolo en el log
      const respaldo = `${this.archivo}.roto-${Date.now()}`;
      renameSync(this.archivo, respaldo);
      console.error(`store: archivo ilegible, respaldado en ${respaldo}`, error);
      return structuredClone(VACIO);
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

  usuarioPorId(id: string): Usuario | undefined {
    return this.datos.usuarios.find((u) => u.id === id);
  }

  crearUsuario(usuario: Usuario): Usuario {
    return this.mutar((datos) => {
      datos.usuarios.push(usuario);
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

  marcarRecarga(usuarioId: string, dia: string, monto: number): number {
    return this.mutar((datos) => {
      const usuario = datos.usuarios.find((u) => u.id === usuarioId);
      if (!usuario) throw new Error("usuario desconocido");
      usuario.ultimaRecarga = dia;
      usuario.puntos += monto;
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
      return pozo;
    });
  }

  /* ------------------------------ apuestas ------------------------------- */

  apuestasDe(usuarioId: string): Apuesta[] {
    return this.datos.apuestas.filter((a) => a.usuarioId === usuarioId);
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

      usuario.puntos -= input.stake;
      pozo[input.side] += input.stake;

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
          }
        }
      }
      return acreditado;
    });
  }

  resumen() {
    return {
      usuarios: this.datos.usuarios.length,
      apuestas: this.datos.apuestas.length,
      mercadosConPozo: this.datos.pozos.length,
      liquidados: this.datos.liquidaciones.filter(
        (l) => l.phase === "pagado" || l.phase === "devuelto",
      ).length,
    };
  }
}
