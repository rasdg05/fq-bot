import type { CountryCode } from "./eligibility";

/**
 * Detección de país.
 *
 * Lo que esto **sí** es: una forma de no preguntarle al usuario algo que el
 * dispositivo ya sabe, para mostrarle los mercados de su país y decirle en qué
 * estado está su mercado local. Se resuelve entero en el dispositivo — la zona
 * horaria y el idioma no salen de aquí — así que no hay dato personal que
 * cuidar ni proveedor que contratar.
 *
 * Lo que esto **no** es: un control de cumplimiento. Una zona horaria se cambia
 * en dos taps y una VPN la vuelve inútil. El día que se mueva dinero hace falta
 * geolocalización por IP con proveedor, señales de dispositivo y verificación
 * de identidad; está escrito en `vault/COMPLIANCE.md` §4 y no se sustituye con
 * esto. Por eso la detección **nunca abre** permisos: sólo puede informar y
 * preseleccionar, y el usuario siempre puede corregirla.
 */

export type CountrySource = "zona_horaria" | "idioma" | "declarado" | "desconocido";

export interface CountryGuess {
  country: CountryCode;
  source: CountrySource;
  /** Lo que el dispositivo dijo, para poder auditar la inferencia. */
  signal?: string;
}

/** Zonas horarias por prefijo: `America/Argentina/Salta` cae en `AR`. */
const POR_PREFIJO: [string, CountryCode][] = [
  ["America/Argentina/", "AR"],
  ["America/Indiana/", "US"],
  ["America/Kentucky/", "US"],
  ["America/North_Dakota/", "US"],
];

const POR_ZONA: Record<string, CountryCode> = {
  "America/Mexico_City": "MX",
  "America/Tijuana": "MX",
  "America/Monterrey": "MX",
  "America/Cancun": "MX",
  "America/Merida": "MX",
  "America/Hermosillo": "MX",
  "America/Chihuahua": "MX",
  "America/Mazatlan": "MX",
  "America/Matamoros": "MX",
  "America/Ojinaga": "MX",
  "America/Bahia_Banderas": "MX",
  "America/Buenos_Aires": "AR",
  "America/Cordoba": "AR",
  "America/Sao_Paulo": "BR",
  "America/Bahia": "BR",
  "America/Fortaleza": "BR",
  "America/Recife": "BR",
  "America/Manaus": "BR",
  "America/Belem": "BR",
  "America/Cuiaba": "BR",
  "America/Campo_Grande": "BR",
  "America/Porto_Velho": "BR",
  "America/Boa_Vista": "BR",
  "America/Rio_Branco": "BR",
  "America/Maceio": "BR",
  "America/Araguaina": "BR",
  "America/Santarem": "BR",
  "America/Noronha": "BR",
  "America/Santiago": "CL",
  "America/Punta_Arenas": "CL",
  "Pacific/Easter": "CL",
  "America/Bogota": "CO",
  "America/Lima": "PE",
  "America/Montevideo": "UY",
  "America/Guayaquil": "EC",
  "Pacific/Galapagos": "EC",
  "America/La_Paz": "BO",
  "America/Asuncion": "PY",
  "America/Caracas": "VE",
  "America/Costa_Rica": "CR",
  "America/Panama": "PA",
  "America/Santo_Domingo": "DO",
  "America/Guatemala": "GT",
  "Europe/Madrid": "ES",
  "Atlantic/Canary": "ES",
  "Africa/Ceuta": "ES",
  "America/New_York": "US",
  "America/Detroit": "US",
  "America/Chicago": "US",
  "America/Denver": "US",
  "America/Boise": "US",
  "America/Phoenix": "US",
  "America/Los_Angeles": "US",
  "America/Anchorage": "US",
  "America/Juneau": "US",
  "America/Sitka": "US",
  "America/Nome": "US",
  "America/Adak": "US",
  "America/Menominee": "US",
  "Pacific/Honolulu": "US",
};

const PAISES = new Set<string>([
  "MX", "AR", "BR", "CL", "CO", "PE", "UY", "EC", "BO", "PY",
  "VE", "CR", "PA", "DO", "GT", "US", "ES",
]);

export function countryFromTimeZone(zone: string | undefined): CountryCode | undefined {
  if (!zone) return undefined;
  const directa = POR_ZONA[zone];
  if (directa) return directa;
  const prefijo = POR_PREFIJO.find(([inicio]) => zone.startsWith(inicio));
  return prefijo?.[1];
}

/** `es-MX` → MX. `es` a secas no dice el país y no se adivina. */
export function countryFromLocale(locale: string | undefined): CountryCode | undefined {
  if (!locale) return undefined;
  const region = locale.split(/[-_]/)[1]?.toUpperCase();
  if (!region || !PAISES.has(region)) return undefined;
  return region as CountryCode;
}

export interface DetectEnvironment {
  timeZone?: string;
  locale?: string;
}

/** Lee el entorno sin tronar en navegadores viejos ni en pruebas. */
export function readEnvironment(): DetectEnvironment {
  let timeZone: string | undefined;
  try {
    timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    /* sin Intl seguimos: la detección es una comodidad, no un requisito */
  }
  const nav = globalThis.navigator as Navigator | undefined;
  return { timeZone, locale: nav?.language };
}

/**
 * La zona horaria manda sobre el idioma: un mexicano con el teléfono en inglés
 * sigue estando en México, y el idioma sólo dice cómo prefiere leer.
 */
export function detectCountry(env: DetectEnvironment = readEnvironment()): CountryGuess {
  const porZona = countryFromTimeZone(env.timeZone);
  if (porZona) {
    return { country: porZona, source: "zona_horaria", signal: env.timeZone };
  }
  const porIdioma = countryFromLocale(env.locale);
  if (porIdioma) {
    return { country: porIdioma, source: "idioma", signal: env.locale };
  }
  // no se adivina: `OTRO` es la respuesta honesta y deja explorar igual
  return { country: "OTRO", source: "desconocido" };
}
