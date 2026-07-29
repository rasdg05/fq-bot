import sharp from "sharp";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { Store } from "./store.mts";

/**
 * Tarjeta de resultado para redes.
 *
 * Una racha contada con palabras no se comparte; una imagen sí. Es el canal de
 * crecimiento más barato que tenemos, porque el usuario la manda al grupo por
 * su cuenta.
 *
 * **SVG a PNG sin navegador headless.** Levantar Chromium para dibujar una
 * imagen de 1200×630 costaría cientos de megas de memoria y varios segundos por
 * tarjeta, en un servicio que ya sirve el feed. `sharp` compone el SVG contra
 * el fondo de marca sin proceso extra.
 *
 * **Sólo datos propios y agregados** (R-058): el nombre que el usuario eligió,
 * cuántas veces le atinó y su racha. Nunca a qué apostó, nunca contra quién,
 * nunca cuánto. Quién apostó qué no sale de aquí.
 */

const ANCHO = 1200;
const ALTO = 630;

export interface LogroUsuario {
  usuario: string;
  /** Mercados resueltos en los que participó. */
  resueltos: number;
  /** Cuántos acertó. */
  aciertos: number;
  /** Racha actual de aciertos. */
  racha: number;
}

/**
 * Lo que se puede contar de alguien sin contar nada de nadie más.
 *
 * "Acertó" es que la apuesta pagó más de lo que puso: en parimutuel eso es
 * exactamente ganar, sin tener que mirar el resultado del mercado.
 */
export function logroDe(store: Store, usuario: string): LogroUsuario | null {
  const cuenta = store.usuarioPorNombre(usuario);
  if (!cuenta) return null;

  const apuestas = store
    .apuestasDe(cuenta.id)
    .filter((a) => a.pagado !== undefined)
    .sort((a, b) => Date.parse(a.pagadoAt ?? a.at) - Date.parse(b.pagadoAt ?? b.at));

  let aciertos = 0;
  let racha = 0;
  for (const apuesta of apuestas) {
    const acerto = (apuesta.pagado ?? 0) > apuesta.stake;
    if (acerto) {
      aciertos += 1;
      racha += 1;
    } else {
      racha = 0;
    }
  }
  return { usuario: cuenta.usuario, resueltos: apuestas.length, aciertos, racha };
}

/** Escapa lo que entra al SVG: el nombre lo eligió el usuario. */
function escapar(texto: string): string {
  return texto
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

/** `7 de 9` con la precisión al lado, o el texto de quien aún no resuelve nada. */
function precision(logro: LogroUsuario): string {
  if (logro.resueltos === 0) return "Todavía sin mercados resueltos";
  const pct = Math.round((logro.aciertos / logro.resueltos) * 100);
  return `${logro.aciertos} de ${logro.resueltos} · ${pct}% de precisión`;
}

function svgDe(logro: LogroUsuario): Buffer {
  const nombre = escapar(logro.usuario);
  const tieneCifra = logro.resueltos > 0;
  const racha = logro.racha >= 2 ? `Racha de ${logro.racha} seguidos` : "";

  // sin mercados resueltos no hay cifra que enseñar. Un guion gigante en el
  // hueco del número se ve como un error de render, no como un cero honesto
  const bloqueCifra = tieneCifra
    ? `<text x="72" y="404" class="cifra" font-size="150">${logro.aciertos}</text>
  <text x="72" y="452" class="t" font-size="26">mercados acertados</text>
  ${racha ? `<text x="72" y="502" class="racha" font-size="28">${escapar(racha)}</text>` : ""}`
    : `<text x="72" y="392" class="pronto" font-size="30">Va entrando. Aquí van a salir sus aciertos.</text>`;

  return Buffer.from(`<svg width="${ANCHO}" height="${ALTO}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <!-- velo bajo el texto: la ola tiene mucha línea fina y el aviso de abajo
         se perdía dentro. Un texto legal que no se lee no cumple su función -->
    <linearGradient id="velo" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0c1a1c" stop-opacity="0"/>
      <stop offset="55%" stop-color="#0c1a1c" stop-opacity="0.55"/>
      <stop offset="100%" stop-color="#0c1a1c" stop-opacity="0.92"/>
    </linearGradient>
  </defs>
  <rect x="0" y="${ALTO - 400}" width="${ANCHO}" height="400" fill="url(#velo)"/>
  <style>
    .marca { font-family: Georgia, 'Times New Roman', serif; font-weight: 700; fill: #eceae1; }
    .nombre { font-family: Georgia, 'Times New Roman', serif; font-weight: 700; fill: #eceae1; }
    .cifra { font-family: Georgia, 'Times New Roman', serif; font-weight: 700; fill: #4cbab2; }
    .t { font-family: Helvetica, Arial, sans-serif; font-weight: 500; fill: #b7c3c1; }
    .chico { font-family: Helvetica, Arial, sans-serif; font-weight: 600; fill: #b7c3c1; }
    /* clase propia, no atributo de presentacion: en SVG la regla CSS gana al
       fill en linea, y la racha salia gris pisada por la clase generica */
    .racha { font-family: Helvetica, Arial, sans-serif; font-weight: 700; fill: #e8a33d; }
    .pronto { font-family: Helvetica, Arial, sans-serif; font-weight: 500; fill: #4cbab2; }
  </style>
  <text x="72" y="88" class="marca" font-size="32">Marea</text>
  <text x="72" y="192" class="nombre" font-size="62">${nombre}</text>
  <text x="72" y="248" class="t" font-size="28">${escapar(precision(logro))}</text>
  ${bloqueCifra}
  <text x="72" y="582" class="chico" font-size="22">Se juega con puntos, no con dinero</text>
</svg>`);
}

/**
 * Compone la tarjeta sobre el fondo de marca. Si el fondo no está en disco, se
 * dibuja el color plano: una tarjeta sin ola sigue siendo una tarjeta, y caerse
 * por un adorno sería perder el canal entero por un detalle.
 */
export async function tarjetaPng(
  logro: LogroUsuario,
  raiz: string,
): Promise<Buffer> {
  // el fondo **sin** texto: `og.png` ya trae el nombre y la promesa impresos,
  // y componer la tarjeta encima dejaría los dos textos montados
  const fondo = join(raiz, "public", "marca", "fondo.png");
  const base = existsSync(fondo)
    ? sharp(readFileSync(fondo)).resize(ANCHO, ALTO, { fit: "cover" })
    : sharp({
        create: {
          width: ANCHO,
          height: ALTO,
          channels: 3,
          background: "#0c1a1c",
        },
      });

  return base
    .composite([{ input: svgDe(logro), top: 0, left: 0 }])
    // paleta de 8 bits: la ola son líneas de dos colores sobre un fondo plano,
    // así que 256 colores la reproducen igual y el archivo baja de ~890 kB a
    // menos de 200. Una vista previa que tarda en cargar no se ve
    .png({ compressionLevel: 9, palette: true, colours: 128 })
    .toBuffer();
}
