import { eligibilityFor, type CountryCode } from "./eligibility";

/**
 * Depósitos y retiros como **solicitudes con estado**, no como llamadas que
 * pasan o fallan.
 *
 * Por qué así: mover dinero de verdad tarda. Una transferencia bancaria, una
 * confirmación en cadena o una revisión manual pueden tardar minutos u horas, y
 * durante todo ese rato el usuario tiene derecho a saber en qué punto va. Una
 * llamada síncrona que devuelve "listo" o "error" no puede representar eso, y
 * termina mintiendo en una de las dos direcciones.
 *
 * La cadena o el proveedor se enchufan después sin tocar nada de esto: lo que
 * cambia es quién mueve la solicitud de `confirmando` a `acreditado`.
 *
 * El retiro pasa además por `en_revision`. No es burocracia: es la única
 * defensa contra que una cuenta comprometida vacíe un saldo mientras nadie
 * mira.
 */

export const ESTADOS_DEPOSITO = [
  "pendiente",
  "confirmando",
  "acreditado",
  "rechazado",
] as const;

export const ESTADOS_RETIRO = [
  "pendiente",
  "en_revision",
  "confirmando",
  "acreditado",
  "rechazado",
] as const;

export type EstadoSolicitud =
  | "pendiente"
  | "en_revision"
  | "confirmando"
  | "acreditado"
  | "rechazado";

export type TipoSolicitud = "deposito" | "retiro";

export interface Solicitud {
  id: string;
  tipo: TipoSolicitud;
  usuarioId: string;
  monto: number;
  pais: CountryCode;
  estado: EstadoSolicitud;
  creada: string;
  /** Cada cambio de estado, con su hora. Es lo que se audita después. */
  historial: { estado: EstadoSolicitud; at: string }[];
  /** Por qué se rechazó, si se rechazó. Mostrable al usuario. */
  motivo?: string;
}

/** Qué estado puede seguir a cuál. Lo que no está aquí, no pasa. */
const TRANSICIONES: Record<TipoSolicitud, Record<EstadoSolicitud, EstadoSolicitud[]>> = {
  deposito: {
    pendiente: ["confirmando", "rechazado"],
    confirmando: ["acreditado", "rechazado"],
    en_revision: [],
    acreditado: [],
    rechazado: [],
  },
  retiro: {
    // un retiro nunca salta la revisión: es la puerta que protege el saldo
    pendiente: ["en_revision", "rechazado"],
    en_revision: ["confirmando", "rechazado"],
    confirmando: ["acreditado", "rechazado"],
    acreditado: [],
    rechazado: [],
  },
};

export class MovimientoNoPermitido extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "MovimientoNoPermitido";
  }
}

let contador = 0;

/**
 * Crea la solicitud. La puerta de elegibilidad se aplica **aquí**, antes de que
 * exista el registro: una solicitud creada en un país sin permiso ya sería un
 * camino de dinero abierto, aunque nunca avanzara (R-045).
 */
export function crearSolicitud(input: {
  tipo: TipoSolicitud;
  usuarioId: string;
  monto: number;
  pais: CountryCode;
  at?: string;
}): Solicitud {
  const elegibilidad = eligibilityFor(input.pais);
  if (!elegibilidad.canDeposit) {
    throw new MovimientoNoPermitido(
      `Todavía no podemos mover dinero desde tu país. ${elegibilidad.reason}`,
    );
  }
  if (!(input.monto > 0)) {
    throw new MovimientoNoPermitido("El monto tiene que ser mayor a cero.");
  }
  const at = input.at ?? new Date().toISOString();
  contador += 1;
  return {
    id: `${input.tipo}-${contador}-${Date.parse(at)}`,
    tipo: input.tipo,
    usuarioId: input.usuarioId,
    monto: input.monto,
    pais: input.pais,
    estado: "pendiente",
    creada: at,
    historial: [{ estado: "pendiente", at }],
  };
}

export function puedeAvanzar(solicitud: Solicitud, destino: EstadoSolicitud): boolean {
  if (solicitud.estado === destino) return true;
  return TRANSICIONES[solicitud.tipo][solicitud.estado].includes(destino);
}

/**
 * Mueve la solicitud. Avanzar al estado en el que ya está **no hace nada**: un
 * reintento del proveedor, o un doble tap, no puede duplicar un movimiento de
 * dinero (I5, R-016).
 */
export function avanzar(
  solicitud: Solicitud,
  destino: EstadoSolicitud,
  motivo?: string,
  at: string = new Date().toISOString(),
): Solicitud {
  if (solicitud.estado === destino) return solicitud;
  if (!puedeAvanzar(solicitud, destino)) {
    throw new MovimientoNoPermitido(
      `Una solicitud en ${solicitud.estado} no puede pasar a ${destino}.`,
    );
  }
  return {
    ...solicitud,
    estado: destino,
    motivo: motivo ?? solicitud.motivo,
    historial: [...solicitud.historial, { estado: destino, at }],
  };
}

/** ¿Terminó su camino? Sirve para saber qué ya no hay que mirar. */
export function esTerminal(solicitud: Solicitud): boolean {
  return solicitud.estado === "acreditado" || solicitud.estado === "rechazado";
}

/** Lo que necesita que alguien lo mire: retiros esperando revisión. */
export function requierenRevision(solicitudes: Solicitud[]): Solicitud[] {
  return solicitudes.filter(
    (s) => s.tipo === "retiro" && s.estado === "en_revision",
  );
}
