import type { Market } from "../src/domain/types";

/**
 * Vista previa de un enlace compartido.
 *
 * Es el canal de crecimiento más barato que tenemos: alguien manda un mercado
 * al grupo de WhatsApp y el que lo recibe ve la pregunta y la probabilidad
 * antes de tocar nada. Un enlace sin vista previa se ve como spam y no se abre.
 *
 * Las etiquetas se rellenan **en el servidor** porque los rastreadores de
 * WhatsApp, Telegram y X no ejecutan JavaScript: si esto se hiciera en el
 * cliente, la vista previa saldría vacía.
 */

function escapar(texto: string): string {
  return texto
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function descripcionDe(mercado: Market): string {
  const probabilidad = `${Math.round(mercado.probability * 100)}%`;
  // el Edge sólo se menciona si existe: prometerlo cuando no hay sería vender
  // humo justo en la superficie que más se comparte (R-001)
  const edge =
    mercado.edge !== null && mercado.edgeLabel
      ? ` · Edge de ${mercado.edge > 0 ? "+" : "−"}${Math.abs(mercado.edge)} pp contra ${mercado.edgeLabel}`
      : "";
  // en un mercado de tres respuestas no existe "que sí": decirlo sería
  // describir un mercado distinto del que se abre al tocar la liga, y la vista
  // previa es lo único que ve quien todavía no entró
  if (mercado.leadLabel) {
    return `Va ganando “${mercado.leadLabel}” con ${probabilidad}${edge}. Entra y di tú qué va a pasar.`;
  }
  return `El mercado dice ${probabilidad} que sí${edge}. Entra y di tú qué va a pasar.`;
}

/** La imagen de marca de la vista previa, servida desde `public/`. */
export const IMAGEN_MARCA = "/marca/og.png";

export function metaDeMercado(html: string, mercado: Market, origen: string): string {
  const titulo = `${mercado.title} · Marea`;
  const descripcion = descripcionDe(mercado);
  const enlace = `${origen}/m/${encodeURIComponent(mercado.id)}`;

  const etiquetas = [
    `<meta property="og:title" content="${escapar(titulo)}">`,
    `<meta property="og:description" content="${escapar(descripcion)}">`,
    `<meta property="og:url" content="${escapar(enlace)}">`,
    `<meta property="og:type" content="website">`,
    `<meta property="og:site_name" content="Marea">`,
    // sin `og:image`, WhatsApp y Telegram pintan la liga sin imagen: es la
    // única cara de Marea que ve quien todavía no la instaló, y estaba vacía.
    // La imagen es de marca y no lleva datos del mercado a propósito — una
    // imagen con la probabilidad dentro se quedaría vieja en cuanto alguien
    // apueste, y la vista previa se cachea durante días
    `<meta property="og:image" content="${escapar(`${origen}${IMAGEN_MARCA}`)}">`,
    `<meta property="og:image:width" content="1200">`,
    `<meta property="og:image:height" content="630">`,
    `<meta property="og:image:alt" content="Marea · mercados de predicción de Latinoamérica">`,
    `<meta property="og:locale" content="es_LA">`,
    // `summary_large_image` es lo que hace que la imagen se vea grande en vez
    // de como una miniatura al lado del texto
    `<meta name="twitter:card" content="summary_large_image">`,
    `<meta name="twitter:title" content="${escapar(titulo)}">`,
    `<meta name="twitter:description" content="${escapar(descripcion)}">`,
    `<meta name="twitter:image" content="${escapar(`${origen}${IMAGEN_MARCA}`)}">`,
  ].join("\n    ");

  // el HTML de la build conserva el formato del fuente, con atributos en
  // varias líneas: la sustitución tiene que tolerarlo o no reemplaza nada
  const conTitulo = html.replace(/<title>[\s\S]*?<\/title>/, `<title>${escapar(titulo)}</title>`);
  const conDescripcion = conTitulo.replace(
    /<meta\s+name="description"[\s\S]*?\/?>/,
    `<meta name="description" content="${escapar(descripcion)}" />`,
  );
  // y las etiquetas de vista previa se insertan antes de cerrar el head, que
  // es el único ancla que siempre existe
  return conDescripcion.replace("</head>", `  ${etiquetas}\n  </head>`);
}

/**
 * Etiquetas de vista previa de una tarjeta de logro. Usa la imagen generada,
 * no la de marca: aquí la imagen **sí** es el contenido.
 */
export function metaDeLogro(
  html: string,
  logro: { usuario: string; resueltos: number; aciertos: number; racha: number },
  origen: string,
): string {
  const titulo = `${logro.usuario} en Marea`;
  const descripcion =
    logro.resueltos === 0
      ? "Todavía sin mercados resueltos. Entra y di tú qué va a pasar."
      : `Le atinó a ${logro.aciertos} de ${logro.resueltos} mercados${
          logro.racha >= 2 ? `, con racha de ${logro.racha}` : ""
        }. Entra y di tú qué va a pasar.`;
  const imagen = `${origen}/tarjeta/${encodeURIComponent(logro.usuario)}.png`;
  const enlace = `${origen}/logro/${encodeURIComponent(logro.usuario)}`;

  const etiquetas = [
    `<meta property="og:title" content="${escapar(titulo)}">`,
    `<meta property="og:description" content="${escapar(descripcion)}">`,
    `<meta property="og:url" content="${escapar(enlace)}">`,
    `<meta property="og:type" content="website">`,
    `<meta property="og:site_name" content="Marea">`,
    `<meta property="og:image" content="${escapar(imagen)}">`,
    `<meta property="og:image:width" content="1200">`,
    `<meta property="og:image:height" content="630">`,
    `<meta property="og:locale" content="es_LA">`,
    `<meta name="twitter:card" content="summary_large_image">`,
    `<meta name="twitter:title" content="${escapar(titulo)}">`,
    `<meta name="twitter:description" content="${escapar(descripcion)}">`,
    `<meta name="twitter:image" content="${escapar(imagen)}">`,
  ].join("\n    ");

  const conTitulo = html.replace(
    /<title>[\s\S]*?<\/title>/,
    `<title>${escapar(titulo)}</title>`,
  );
  const conDescripcion = conTitulo.replace(
    /<meta\s+name="description"[\s\S]*?\/?>/,
    `<meta name="description" content="${escapar(descripcion)}" />`,
  );
  return conDescripcion.replace("</head>", `  ${etiquetas}\n  </head>`);
}
