import type { Oracle, OracleQuery, OracleReading } from "@/domain/settlement";
import type { QuakeRule } from "@/domain/oracleRule";

/**
 * Oráculo de sismos contra el catálogo público del USGS (FDSN), sin llave.
 *
 * Cuándo se paga:
 *  - **Sí**, en cuanto aparece en la ventana un sismo que cuenta y el USGS ya
 *    lo revisó (`status: reviewed`). Un evento automático puede cambiar de
 *    magnitud: si existe pero no está revisado, se espera — hasta 72 h después
 *    de la ventana; pasado eso, vale lo que el USGS publique.
 *  - **No**, cuando la ventana terminó hace 24 h sin ningún sismo que cuente:
 *    el USGS agrega eventos tarde, y un día de margen lo cubre.
 *
 * «En México», medido el 2026-10-01 sobre 730 sismos M4.5+ de 5 años en la
 * caja: el USGS termina la descripción en «Mexico» (479) o en «MX» («Delta,
 * B.C., MX»). **«New Mexico» también termina en «Mexico»** y es Estados Unidos
 * (6 eventos): se excluye por nombre. No cuentan los que el USGS describe como
 * «Gulf of California» (2) ni «Revilla Gigedo Islands region» (20, océano
 * abierto). Así lo dice el criterio, para que nadie tenga que adivinar.
 */

export const USGS_API = "https://earthquake.usgs.gov/fdsnws/event/1/query";

/** La caja que se consulta. «En México» lo decide después la descripción del USGS. */
const CAJA = "minlatitude=13&maxlatitude=33.5&minlongitude=-119&maxlongitude=-85";

export function urlSismos(rule: Pick<QuakeRule, "desde" | "hasta" | "magnitudMin">): string {
  return (
    `${USGS_API}?format=geojson&starttime=${rule.desde}&endtime=${rule.hasta}` +
    `&minmagnitude=${rule.magnitudMin}&${CAJA}&orderby=time-asc`
  );
}

export interface SismoUsgs {
  id: string;
  properties: { mag: number; place: string | null; time: number; status: string; url?: string };
}

export async function cargarSismos(
  fetchImpl: typeof fetch,
  rule: Pick<QuakeRule, "desde" | "hasta" | "magnitudMin">,
): Promise<SismoUsgs[]> {
  const respuesta = await fetchImpl(urlSismos(rule));
  if (!respuesta.ok) throw new Error(`USGS respondió ${respuesta.status}`);
  const cuerpo = (await respuesta.json()) as { features?: SismoUsgs[] };
  return cuerpo.features ?? [];
}

/** ¿Cuenta como sismo «en México» para el USGS? */
export const enMexico = (sismo: SismoUsgs) => {
  const lugar = (sismo.properties.place ?? "").trim();
  return /(?<!New )\bMexico$/.test(lugar) || /, MX$/.test(lugar);
};

const H = 3_600_000;

/** La decisión, sin red. */
export function resolverSismo(rule: QuakeRule, sismos: SismoUsgs[], ahora: number): OracleReading {
  const desde = Date.parse(rule.desde);
  const hasta = Date.parse(rule.hasta);
  const cuentan = sismos.filter(
    (s) =>
      enMexico(s) &&
      s.properties.mag >= rule.magnitudMin &&
      s.properties.time >= desde &&
      s.properties.time < hasta,
  );
  const fuente = `Catálogo del USGS (${urlSismos(rule)})`;

  const revisado = cuentan.find((s) => s.properties.status === "reviewed");
  const cualquiera = cuentan[0];
  const elegido = revisado ?? (ahora >= hasta + 72 * H ? cualquiera : undefined);
  if (elegido) {
    const p = elegido.properties;
    return {
      status: "resuelto",
      outcome: "si",
      evidence: `Sismo M${p.mag.toFixed(1)} «${p.place}» el ${new Date(p.time).toISOString()} (USGS ${elegido.id}, ${p.status}). ${fuente}`,
      observedAt: new Date(p.time).toISOString(),
    };
  }
  if (cualquiera) {
    // un sismo que cuenta, todavía sin revisar: no se paga aún, pero tampoco
    // se acepta una apuesta más con el resultado casi a la vista
    return {
      status: "sin_dato",
      detenerApuestas: true,
      evidence: `El USGS registra un M${cualquiera.properties.mag.toFixed(1)} «${cualquiera.properties.place}» sin revisar todavía. Se espera la revisión.`,
    };
  }
  if (ahora >= hasta + 24 * H) {
    return {
      status: "resuelto",
      outcome: "no",
      evidence: `Ningún sismo de magnitud ${rule.magnitudMin.toFixed(1)} o mayor descrito en México por el USGS entre ${rule.desde} y ${rule.hasta}. ${fuente}`,
      observedAt: new Date(hasta).toISOString(),
    };
  }
  return { status: "sin_dato", evidence: `La ventana ${rule.desde} – ${rule.hasta} no ha terminado, o falta el día de margen.` };
}

export interface QuakeOracleOptions {
  fetchImpl?: typeof fetch;
  cargarSismos?: (rule: QuakeRule) => Promise<SismoUsgs[]>;
}

export function createQuakeOracle(options: QuakeOracleOptions = {}): Oracle {
  const cargar = options.cargarSismos ?? ((rule: QuakeRule) => cargarSismos(options.fetchImpl ?? fetch, rule));
  return {
    id: "usgs-sismo",
    handles: (query: OracleQuery) => query.rule?.kind === "sismo",
    async read(query: OracleQuery): Promise<OracleReading> {
      const rule = query.rule as QuakeRule;
      if (query.now < Date.parse(rule.desde)) {
        return { status: "sin_dato", evidence: "La ventana del sismo todavía no empieza." };
      }
      try {
        return resolverSismo(rule, await cargar(rule), query.now);
      } catch (error) {
        return { status: "sin_dato", evidence: `USGS: ${error instanceof Error ? error.message : String(error)}` };
      }
    },
  };
}
