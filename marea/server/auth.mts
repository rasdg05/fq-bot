import { createHmac, randomBytes, scryptSync, timingSafeEqual } from "node:crypto";
import type { Store, Usuario } from "./store.mts";

/**
 * Cuentas. Usuario y contraseña, nada más: sin correo obligatorio, sin
 * confirmación, sin esperar un mail que puede caer en spam. Entrar tiene que
 * costar dos campos y un tap, o la gente no entra.
 *
 * El correo es opcional y sirve para una sola cosa: recuperar la cuenta si se
 * te olvida la contraseña. Se pide después, nunca en el camino de entrada.
 *
 * Criptografía con lo que trae Node: `scrypt` para la contraseña (lento a
 * propósito) y HMAC para firmar la sesión. Cero dependencias, cero proveedor.
 */

const ITERACIONES = { N: 16_384, r: 8, p: 1 };
const LARGO_HASH = 64;
/** Cuánto dura una sesión sin volver a entrar. */
export const SESION_DIAS = 90;

function secreto(): string {
  const valor = process.env.MAREA_SECRETO;
  if (valor && valor.length >= 16) return valor;
  // sin secreto configurado se genera uno por arranque: las sesiones no
  // sobreviven a un redeploy, pero nunca se firma con una llave adivinable
  globalThis.__mareaSecreto ??= randomBytes(32).toString("hex");
  return globalThis.__mareaSecreto as string;
}

declare global {
  // eslint-disable-next-line no-var
  var __mareaSecreto: string | undefined;
}

export function hashear(password: string, salt = randomBytes(16).toString("hex")) {
  const hash = scryptSync(password, salt, LARGO_HASH, ITERACIONES).toString("hex");
  return { hash, salt };
}

export function verificar(password: string, usuario: Usuario): boolean {
  const intento = scryptSync(password, usuario.salt, LARGO_HASH, ITERACIONES);
  const guardado = Buffer.from(usuario.hash, "hex");
  if (intento.length !== guardado.length) return false;
  // comparación de tiempo constante: una comparación normal filtra el hash
  return timingSafeEqual(intento, guardado);
}

/** `id.vencimiento.firma`. No lleva nada sensible y no se puede falsificar. */
export function firmarSesion(usuarioId: string, ahora = Date.now()): string {
  const vence = ahora + SESION_DIAS * 86_400_000;
  const cuerpo = `${usuarioId}.${vence}`;
  const firma = createHmac("sha256", secreto()).update(cuerpo).digest("hex");
  return `${cuerpo}.${firma}`;
}

export function leerSesion(token: string | undefined, ahora = Date.now()): string | null {
  if (!token) return null;
  const partes = token.split(".");
  if (partes.length !== 3) return null;
  const [usuarioId, vence, firma] = partes;
  const esperada = createHmac("sha256", secreto())
    .update(`${usuarioId}.${vence}`)
    .digest("hex");
  if (firma.length !== esperada.length) return null;
  if (!timingSafeEqual(Buffer.from(firma), Buffer.from(esperada))) return null;
  if (Number(vence) <= ahora) return null;
  return usuarioId;
}

export const COOKIE = "marea_sesion";

export function cookieDeSesion(token: string, seguro: boolean): string {
  const partes = [
    `${COOKIE}=${token}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    `Max-Age=${SESION_DIAS * 86_400}`,
  ];
  if (seguro) partes.push("Secure");
  return partes.join("; ");
}

export function cookieVacia(): string {
  return `${COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`;
}

export function leerCookie(header: string | undefined, nombre: string): string | undefined {
  if (!header) return undefined;
  for (const parte of header.split(";")) {
    const [clave, ...resto] = parte.trim().split("=");
    if (clave === nombre) return resto.join("=");
  }
  return undefined;
}

/** Qué es un nombre de usuario válido. Se dice claro para poder mostrarlo. */
export const REGLAS_USUARIO =
  "De 3 a 20 caracteres: letras, números, guion bajo o punto.";

export function problemasDeAlta(usuario: string, password: string): string[] {
  const problemas: string[] = [];
  if (!/^[a-zA-Z0-9_.]{3,20}$/.test(usuario.trim())) {
    problemas.push(`El nombre de usuario no sirve. ${REGLAS_USUARIO}`);
  }
  if (password.length < 8) {
    problemas.push("La contraseña necesita al menos 8 caracteres.");
  }
  return problemas;
}

export function sesionSegura(store: Store, token: string | undefined): Usuario | null {
  const id = leerSesion(token);
  if (!id) return null;
  return store.usuarioPorId(id) ?? null;
}
