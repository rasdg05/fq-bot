import type { Oracle, OracleQuery, OracleReading } from "@/domain/settlement";
import type { SeriesRule } from "@/domain/oracleRule";

/**
 * Oráculo de series estadísticas. Es lo que quita a la persona del camino en
 * los mercados de inflación y de tasa: el dato **sí** está en un endpoint, con
 * fecha y con valor, y decir lo contrario era pereza (AGENTE §2).
 *
 * Fuentes implementadas:
 *
 *  - **BCB (Brasil)** — `api.bcb.gov.br`, público, sin llave ni registro.
 *    Serie 432 = meta Selic. Serie 13522 = IPCA acumulado 12 meses.
 *  - **Banxico (México)** — `SieAPIRest`, gratis pero **con token**. Se saca en
 *    dos minutos en banxico.org.mx y se pone en `BANXICO_TOKEN`. Sin token no
 *    se inventa nada: el mercado queda esperando confirmación, con la
 *    instrucción exacta de qué falta.
 *
 * Regla de frescura: no basta con que la serie tenga un valor, tiene que tener
 * el valor **de la fecha del mercado**. Resolver una pregunta sobre la reunión
 * de agosto con el dato de julio sería inventar un resultado con pasos extra.
 */

const DIA_MS = 86_400_000;
/** Cuánto puede atrasarse la publicación antes de que dejemos de esperarla. */
const MARGEN_MS = 1.5 * DIA_MS;

export interface Observacion {
  fecha: number;
  valor: number;
}

export interface SeriesOracleOptions {
  fetchImpl?: typeof fetch;
  banxicoToken?: string;
  /** Se inyecta en pruebas para no depender de la red. */
  cargar?: (rule: SeriesRule) => Promise<Observacion[]>;
}

/** `dd/mm/yyyy` del BCB, y `dd/mm/yyyy` de Banxico: el mismo formato. */
function fechaLatam(texto: string): number {
  const [dia, mes, anio] = texto.split("/").map(Number);
  return Date.UTC(anio, mes - 1, dia);
}

async function leerBcb(
  fetchImpl: typeof fetch,
  rule: SeriesRule,
): Promise<Observacion[]> {
  const url = `https://api.bcb.gov.br/dados/serie/bcdata.sgs.${rule.serie}/dados/ultimos/6?formato=json`;
  const respuesta = await fetchImpl(url);
  if (!respuesta.ok) throw new Error(`BCB respondió ${respuesta.status}`);
  const filas = (await respuesta.json()) as { data: string; valor: string }[];
  return filas.map((fila) => ({ fecha: fechaLatam(fila.data), valor: Number(fila.valor) }));
}

async function leerBanxico(
  fetchImpl: typeof fetch,
  rule: SeriesRule,
  token: string,
): Promise<Observacion[]> {
  const url = `https://www.banxico.org.mx/SieAPIRest/service/v1/series/${rule.serie}/datos/oportuno?token=${token}`;
  const respuesta = await fetchImpl(url);
  if (!respuesta.ok) throw new Error(`Banxico respondió ${respuesta.status}`);
  const cuerpo = (await respuesta.json()) as {
    bmx?: { series?: { datos?: { fecha: string; dato: string }[] }[] };
  };
  const datos = cuerpo.bmx?.series?.[0]?.datos ?? [];
  return datos
    .filter((dato) => dato.dato !== "N/E")
    .map((dato) => ({ fecha: fechaLatam(dato.fecha), valor: Number(dato.dato) }));
}

export function createSeriesOracle(options: SeriesOracleOptions = {}): Oracle {
  const fetchImpl = options.fetchImpl ?? fetch;
  const token = options.banxicoToken ?? process.env?.BANXICO_TOKEN;

  const cargar =
    options.cargar ??
    (async (rule: SeriesRule) => {
      if (rule.fuente === "bcb") return leerBcb(fetchImpl, rule);
      if (!token) throw new Error("sin token");
      return leerBanxico(fetchImpl, rule, token);
    });

  return {
    id: "series",

    handles(query: OracleQuery): boolean {
      return query.rule?.kind === "serie";
    },

    async read(query: OracleQuery): Promise<OracleReading> {
      const rule = query.rule as SeriesRule;
      const settlesAt = new Date(query.spec.settlesAt).getTime();

      if (query.now < settlesAt) {
        return {
          status: "sin_dato",
          evidence: `${rule.etiqueta} se publica el ${new Date(settlesAt)
            .toISOString()
            .slice(0, 10)}.`,
        };
      }

      // sin credencial no se adivina: se dice exactamente qué falta (R-022)
      if (rule.fuente === "banxico" && !token) {
        return {
          status: "requiere_humano",
          evidence:
            `Falta BANXICO_TOKEN para leer ${rule.etiqueta} por programa. ` +
            `Se saca gratis en https://www.banxico.org.mx/SieAPIRest/service/v1/token ` +
            `y se pone en las variables del servicio. Mientras tanto, verificar en ${query.spec.sourceUrl}`,
        };
      }

      const observaciones = (await cargar(rule)).sort((a, b) => a.fecha - b.fecha);
      if (observaciones.length === 0) {
        return { status: "sin_dato", evidence: `${rule.etiqueta}: la fuente no devolvió datos.` };
      }

      const ultima = observaciones[observaciones.length - 1];
      // el dato tiene que ser el de la fecha del mercado, no uno anterior
      if (ultima.fecha < settlesAt - MARGEN_MS) {
        return {
          status: "sin_dato",
          evidence:
            `${rule.etiqueta}: el último dato publicado es del ` +
            `${new Date(ultima.fecha).toISOString().slice(0, 10)} y el mercado resuelve con ` +
            `el del ${new Date(settlesAt).toISOString().slice(0, 10)}.`,
        };
      }

      const fecha = new Date(ultima.fecha).toISOString().slice(0, 10);

      if (rule.comparacion === "menor" || rule.comparacion === "mayor") {
        const umbral = rule.umbral as number;
        const cumple =
          rule.comparacion === "menor" ? ultima.valor < umbral : ultima.valor > umbral;
        return {
          status: "resuelto",
          outcome: cumple ? "si" : "no",
          evidence: `${rule.etiqueta} del ${fecha}: ${ultima.valor} frente al umbral de ${umbral} (serie ${rule.serie}).`,
        };
      }

      const anterior = observaciones
        .slice(0, -1)
        .reverse()
        .find((observacion) => observacion.valor !== ultima.valor);
      if (!anterior) {
        // sin un valor distinto antes, no hubo cambio: la respuesta es No
        return {
          status: "resuelto",
          outcome: "no",
          evidence: `${rule.etiqueta} del ${fecha}: ${ultima.valor}, sin cambio frente a las observaciones previas (serie ${rule.serie}).`,
        };
      }

      const bajo = ultima.valor < anterior.valor;
      const cumple = rule.comparacion === "baja" ? bajo : !bajo;
      return {
        status: "resuelto",
        outcome: cumple ? "si" : "no",
        evidence:
          `${rule.etiqueta}: pasó de ${anterior.valor} (${new Date(anterior.fecha)
            .toISOString()
            .slice(0, 10)}) a ${ultima.valor} (${fecha}), serie ${rule.serie}.`,
      };
    },
  };
}
