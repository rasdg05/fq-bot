import { randomUUID } from "node:crypto";
import type { IncomingMessage, ServerResponse } from "node:http";
import { DAILY_GRANT, WELCOME_GRANT } from "../src/domain/points";
import type { OwnMarketSeed } from "../src/adapters/ownMarkets/catalog";
import {
  cookieDeSesion,
  cookieVacia,
  firmarSesion,
  hashear,
  leerCookie,
  problemasDeAlta,
  sesionSegura,
  verificar,
  COOKIE,
} from "./auth.mts";
import { cotizar, listarMercados, posicionesDe } from "./mercados.mts";
import type { Store } from "./store.mts";

/**
 * La API. Poca superficie a propósito: cuenta, mercados, apostar, portafolio.
 *
 * Dos reglas que se ven en el código:
 *  - **Explorar no pide cuenta.** Los mercados se leen sin sesión, siempre
 *    (R-002). La cuenta sólo hace falta para apostar, que es cuando de verdad
 *    hay algo que guardar.
 *  - Todos los errores salen en español y accionables, nunca un stack (R-008).
 */

export interface Contexto {
  store: Store;
  seeds: () => OwnMarketSeed[];
  seguro: boolean;
}

function json(res: ServerResponse, code: number, cuerpo: unknown, cookie?: string) {
  const cabeceras: Record<string, string> = {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  };
  if (cookie) cabeceras["set-cookie"] = cookie;
  res.writeHead(code, cabeceras);
  res.end(JSON.stringify(cuerpo));
}

function error(res: ServerResponse, code: number, mensaje: string) {
  json(res, code, { error: mensaje });
}

async function cuerpoJson(req: IncomingMessage): Promise<Record<string, unknown>> {
  const trozos: Buffer[] = [];
  let total = 0;
  for await (const trozo of req) {
    total += (trozo as Buffer).length;
    // un cuerpo enorme no puede tumbar el proceso
    if (total > 64_000) throw new Error("cuerpo demasiado grande");
    trozos.push(trozo as Buffer);
  }
  if (trozos.length === 0) return {};
  return JSON.parse(Buffer.concat(trozos).toString("utf8"));
}

function texto(valor: unknown): string {
  return typeof valor === "string" ? valor.trim() : "";
}

/** Lo que el cliente sabe de ti. Nunca el hash, nunca la sal. */
function perfil(store: Store, usuarioId: string, seeds: OwnMarketSeed[]) {
  const usuario = store.usuarioPorId(usuarioId)!;
  return {
    usuario: usuario.usuario,
    puntos: usuario.puntos,
    correo: usuario.correo,
    recargaDisponible: recargaDisponible(usuario.puntos, usuario.ultimaRecarga),
    posiciones: posicionesDe(store, usuarioId, seeds),
  };
}

/** La recarga es para quien se quedó sin puntos, no un ingreso pasivo. */
function recargaDisponible(puntos: number, ultima: string | undefined): number {
  const hoy = new Date().toISOString().slice(0, 10);
  if (ultima === hoy) return 0;
  return puntos < DAILY_GRANT ? DAILY_GRANT - puntos : 0;
}

export async function manejarApi(
  req: IncomingMessage,
  res: ServerResponse,
  ruta: string,
  ctx: Contexto,
): Promise<boolean> {
  const token = leerCookie(req.headers.cookie, COOKIE);
  const sesion = sesionSegura(ctx.store, token);
  const metodo = req.method ?? "GET";

  /* --------------------------------- cuenta -------------------------------- */

  if (ruta === "/api/cuenta/registro" && metodo === "POST") {
    const cuerpo = await cuerpoJson(req);
    const usuario = texto(cuerpo.usuario);
    const password = texto(cuerpo.password);
    const correo = texto(cuerpo.correo) || undefined;

    const problemas = problemasDeAlta(usuario, password);
    if (problemas.length > 0) return error(res, 400, problemas[0]), true;
    if (ctx.store.usuarioPorNombre(usuario)) {
      return error(res, 409, "Ese nombre de usuario ya está tomado. Prueba otro."), true;
    }

    const { hash, salt } = hashear(password);
    const creado = ctx.store.crearUsuario({
      id: randomUUID(),
      usuario,
      correo,
      hash,
      salt,
      creado: new Date().toISOString(),
      // la bienvenida se entrega al crear la cuenta, una sola vez por cuenta
      puntos: WELCOME_GRANT,
    });

    json(res, 201, perfil(ctx.store, creado.id, ctx.seeds()), cookieDeSesion(firmarSesion(creado.id), ctx.seguro));
    return true;
  }

  if (ruta === "/api/cuenta/entrar" && metodo === "POST") {
    const cuerpo = await cuerpoJson(req);
    const usuario = ctx.store.usuarioPorNombre(texto(cuerpo.usuario));
    // el mismo mensaje exista o no la cuenta: decir cuál falló regala usuarios
    const generico = "Usuario o contraseña incorrectos.";
    if (!usuario || !verificar(texto(cuerpo.password), usuario)) {
      return error(res, 401, generico), true;
    }
    json(res, 200, perfil(ctx.store, usuario.id, ctx.seeds()), cookieDeSesion(firmarSesion(usuario.id), ctx.seguro));
    return true;
  }

  if (ruta === "/api/cuenta/salir" && metodo === "POST") {
    json(res, 200, { ok: true }, cookieVacia());
    return true;
  }

  if (ruta === "/api/yo" && metodo === "GET") {
    if (!sesion) return json(res, 200, { usuario: null }), true;
    json(res, 200, perfil(ctx.store, sesion.id, ctx.seeds()));
    return true;
  }

  if (ruta === "/api/cuenta/recarga" && metodo === "POST") {
    if (!sesion) return error(res, 401, "Entra a tu cuenta para recargar."), true;
    const monto = recargaDisponible(sesion.puntos, sesion.ultimaRecarga);
    if (monto <= 0) {
      return error(res, 409, "Hoy ya recargaste. Vuelve mañana."), true;
    }
    ctx.store.marcarRecarga(sesion.id, new Date().toISOString().slice(0, 10), monto);
    json(res, 200, perfil(ctx.store, sesion.id, ctx.seeds()));
    return true;
  }

  /* -------------------------------- mercados ------------------------------- */

  // sin sesión: explorar el catálogo entero nunca cuesta ni pide nada (R-002)
  if (ruta === "/api/mercados" && metodo === "GET") {
    json(res, 200, { mercados: listarMercados(ctx.store, ctx.seeds()) });
    return true;
  }

  if (ruta.startsWith("/api/mercados/") && metodo === "GET") {
    const id = decodeURIComponent(ruta.slice("/api/mercados/".length));
    const mercado = listarMercados(ctx.store, ctx.seeds()).find((m) => m.id === id);
    if (!mercado) return error(res, 404, "Ese mercado ya no existe."), true;
    json(res, 200, mercado);
    return true;
  }

  if (ruta === "/api/apostar" && metodo === "POST") {
    if (!sesion) {
      return error(res, 401, "Crea tu cuenta para apostar. Toma diez segundos."), true;
    }
    const cuerpo = await cuerpoJson(req);
    const marketId = texto(cuerpo.marketId);
    const side = texto(cuerpo.side);
    const size = Math.floor(Number(cuerpo.size));

    if (side !== "si" && side !== "no") return error(res, 400, "Elige un lado."), true;
    if (!Number.isFinite(size) || size <= 0) {
      return error(res, 400, "El monto tiene que ser mayor a cero."), true;
    }

    const seed = ctx.seeds().find((s) => s.id === marketId);
    if (!seed) return error(res, 404, "Ese mercado ya no existe."), true;

    const estado = ctx.store.liquidacion(marketId);
    if (estado && estado.phase !== "abierto") {
      return error(res, 409, "Este mercado ya cerró: el resultado ya se conoce."), true;
    }
    if (new Date(seed.closesAt).getTime() <= Date.now()) {
      return error(res, 409, "Este mercado ya cerró."), true;
    }
    if (sesion.puntos < size) {
      return error(res, 409, "No te alcanzan los puntos. Recarga o baja el monto."), true;
    }

    const precio = cotizar(ctx.store, seed, side, size).probability;
    const apuesta = ctx.store.apostar({
      usuarioId: sesion.id,
      marketId,
      side,
      stake: size,
      precio,
    });
    json(res, 201, { positionId: apuesta.id, ...perfil(ctx.store, sesion.id, ctx.seeds()) });
    return true;
  }

  return false;
}
