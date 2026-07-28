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
  return `El mercado dice ${probabilidad} que sí${edge}. Entra y di tú qué va a pasar.`;
}

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
    `<meta name="twitter:card" content="summary">`,
    `<meta name="twitter:title" content="${escapar(titulo)}">`,
    `<meta name="twitter:description" content="${escapar(descripcion)}">`,
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
