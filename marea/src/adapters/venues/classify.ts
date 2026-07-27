import type { MarketCategory } from "@/domain/types";

/**
 * Clasificador de categoría. Los venues no publican una taxonomía compatible
 * con la nuestra (Polymarket no manda categoría y Kalshi la codifica en el
 * ticker), así que la derivamos del texto. Cuando no hay señal clara cae en
 * `otros`: preferimos decir "no sé" a inventar una categoría bonita.
 */
const RULES: [MarketCategory, RegExp][] = [
  [
    "cripto",
    /\b(bitcoin|btc|ethereum|eth|solana|sol|crypto|cripto|token|stablecoin|usdc|usdt|blockchain|defi|nft|binance|coinbase)\b/i,
  ],
  [
    "economia",
    /\b(inflation|inflacion|inpc|cpi|gdp|pib|fed|banxico|bcra|rate|tasa|interes|recession|recesion|unemployment|desempleo|dollar|dolar|peso|real|tipo de cambio|economy|economia|tariff|arancel)\b/i,
  ],
  [
    "deportes",
    /\b(nba|nfl|mlb|wnba|fifa|world cup|mundial|libertadores|liga|champions|soccer|futbol|f1|formula|tennis|tenis|olympic|olimpic|game|match|wins? by|playoff|season)\b/i,
  ],
  [
    "politica",
    /\b(election|eleccion|elecciones|president|presidente|senate|senado|congress|congreso|vote|voto|votacion|governor|gobernador|primary|primaria|candidate|candidato|impeach|nominee|parlament|referendum)\b/i,
  ],
  [
    "cultura",
    /\b(oscar|grammy|emmy|album|movie|pelicula|box office|netflix|spotify|celebrity|artist|artista|award|premio|series|serie|festival|billboard)\b/i,
  ],
];

/** Sin acentos y en minúsculas: los patrones se escriben una sola vez. */
function fold(texts: (string | undefined)[]): string {
  return texts
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

export function classifyCategory(...texts: (string | undefined)[]): MarketCategory {
  const haystack = fold(texts);
  for (const [category, pattern] of RULES) {
    if (pattern.test(haystack)) return category;
  }
  return "otros";
}

/**
 * Marca regional: los venues son globales, la etiqueta LATAM la ponemos
 * nosotros. Se evalúa sobre el texto ya sin acentos, así que aquí no hacen
 * falta variantes acentuadas. Las raíces llevan `\w*` porque "mexic" tiene que
 * alcanzar a "mexico" y a "mexican".
 */
const LATAM =
  /\b(?:mexic\w*|argentin\w*|brazil\w*|brasil\w*|chile\w*|colombia\w*|peru\w*|uruguay\w*|bolivia\w*|ecuador\w*|venezuel\w*|paraguay\w*|latam|latin america|america latina|banxico|bcra|inegi|conmebol|libertadores|copa america)\b/;

export function isLatam(...texts: (string | undefined)[]): boolean {
  return LATAM.test(fold(texts));
}
