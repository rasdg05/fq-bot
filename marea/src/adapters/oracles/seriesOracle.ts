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
  inegiToken?: string;
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

/**
 * BCRA (Argentina) — `api.bcra.gob.ar`, público y sin llave. Cada variable
 * monetaria tiene su id numérico; la 7 es la BADLAR de bancos privados.
 *
 * Se eligió BADLAR y no "la tasa de política monetaria" porque la serie de
 * política monetaria del BCRA lleva parada desde julio de 2025, y un dato viejo
 * no resuelve un mercado nuevo (R-052). Citar una serie muerta habría sido
 * prometer una resolución que nunca llega.
 */
async function leerBcra(
  fetchImpl: typeof fetch,
  rule: SeriesRule,
): Promise<Observacion[]> {
  const url = `https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/${rule.serie}`;
  const respuesta = await fetchImpl(url);
  if (!respuesta.ok) throw new Error(`BCRA respondió ${respuesta.status}`);
  const cuerpo = (await respuesta.json()) as {
    results?: { idVariable: number; detalle?: { fecha: string; valor: number }[] }[];
  };
  // el BCRA envuelve las observaciones en `results[].detalle`, no las sirve
  // planas. La prueba con datos inyectados no lo habría visto nunca: esto salió
  // de mirar la respuesta real (AGENTE §1)
  const detalle = cuerpo.results?.[0]?.detalle ?? [];
  return detalle
    .map((fila) => ({
      fecha: Date.parse(`${fila.fecha}T00:00:00Z`),
      valor: Number(fila.valor),
    }))
    .filter((o) => Number.isFinite(o.fecha) && Number.isFinite(o.valor));
}

/** `Jun.2026` / `Jun26` → milisegundos. Es como el BCRP nombra sus períodos. */
const MESES_BCRP: Record<string, number> = {
  ene: 0, feb: 1, mar: 2, abr: 3, may: 4, jun: 5,
  jul: 6, ago: 7, sep: 8, oct: 9, nov: 10, dic: 11,
};

export function fechaBcrp(nombre: string): number {
  const limpio = nombre.trim().toLowerCase().replace(/\./g, "");
  const mes = MESES_BCRP[limpio.slice(0, 3)];
  const anio = Number(limpio.slice(3));
  if (mes === undefined || !Number.isFinite(anio)) return NaN;
  // el dato de un mes se publica al cerrar el mes: cuenta como fin de mes
  return Date.UTC(anio < 100 ? 2000 + anio : anio, mes + 1, 0);
}

/**
 * Recorta el primer objeto JSON completo de una respuesta.
 *
 * El BCRP a veces pega un bloque de HTML de depuración **después** del JSON
 * (`}<br /><font size='1'>…`), así que `response.json()` revienta a mitad. No
 * es un caso hipotético: la respuesta real lo traía y `curl` no lo mostraba,
 * porque el bloque sólo aparece en algunas peticiones.
 *
 * Se cuentan llaves respetando cadenas y escapes; nunca se corta por el primer
 * `<` porque un `<` puede vivir dentro de un texto legítimo.
 */
export function recortarJson(texto: string): string {
  const inicio = texto.indexOf("{");
  if (inicio < 0) return texto;
  let profundidad = 0;
  let enCadena = false;
  let escapado = false;
  for (let i = inicio; i < texto.length; i += 1) {
    const c = texto[i];
    if (enCadena) {
      if (escapado) escapado = false;
      else if (c === "\\") escapado = true;
      else if (c === '"') enCadena = false;
      continue;
    }
    if (c === '"') enCadena = true;
    else if (c === "{") profundidad += 1;
    else if (c === "}") {
      profundidad -= 1;
      if (profundidad === 0) return texto.slice(inicio, i + 1);
    }
  }
  return texto.slice(inicio);
}

/**
 * BCRP (Perú) — `estadisticas.bcrp.gob.pe`, público y sin llave. Las series
 * llevan código propio: `PN01279PM` es la inflación anual de Lima.
 */
async function leerBcrp(
  fetchImpl: typeof fetch,
  rule: SeriesRule,
): Promise<Observacion[]> {
  const url = `https://estadisticas.bcrp.gob.pe/estadisticas/series/api/${rule.serie}/json`;
  const respuesta = await fetchImpl(url);
  if (!respuesta.ok) throw new Error(`BCRP respondió ${respuesta.status}`);
  const cuerpo = JSON.parse(recortarJson(await respuesta.text())) as {
    periods?: { name: string; values: string[] }[];
  };
  return (cuerpo.periods ?? [])
    .map((periodo) => ({
      fecha: fechaBcrp(periodo.name),
      valor: Number(periodo.values?.[0]),
    }))
    .filter((o) => Number.isFinite(o.fecha) && Number.isFinite(o.valor));
}

/**
 * INEGI (México) — la API del BIE es gratis pero **pide token**, igual que
 * Banxico. Sin token no se adivina: el mercado espera confirmación y se dice
 * exactamente qué falta y dónde se saca (R-022).
 */
async function leerInegi(
  fetchImpl: typeof fetch,
  rule: SeriesRule,
  token: string,
): Promise<Observacion[]> {
  const url =
    `https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/INDICATOR/` +
    `${rule.serie}/es/0700/false/BIE/2.0/${token}?type=json`;
  const respuesta = await fetchImpl(url);
  if (!respuesta.ok) throw new Error(`INEGI respondió ${respuesta.status}`);
  const cuerpo = (await respuesta.json()) as {
    Series?: { OBSERVATIONS?: { TIME_PERIOD: string; OBS_VALUE: string }[] }[];
  };
  const observaciones = cuerpo.Series?.[0]?.OBSERVATIONS ?? [];
  return observaciones
    .map((o) => {
      // el BIE usa `2026/06` o `2026`
      const [anio, mes] = o.TIME_PERIOD.split("/").map(Number);
      return {
        fecha: Date.UTC(anio, Number.isFinite(mes) ? mes : 12, 0),
        valor: Number(o.OBS_VALUE),
      };
    })
    .filter((o) => Number.isFinite(o.fecha) && Number.isFinite(o.valor));
}

export function createSeriesOracle(options: SeriesOracleOptions = {}): Oracle {
  const fetchImpl = options.fetchImpl ?? fetch;
  const token = options.banxicoToken ?? process.env?.BANXICO_TOKEN;
  const tokenInegi = options.inegiToken ?? process.env?.INEGI_TOKEN;

  const cargar =
    options.cargar ??
    (async (rule: SeriesRule) => {
      if (rule.fuente === "bcb") return leerBcb(fetchImpl, rule);
      if (rule.fuente === "bcra") return leerBcra(fetchImpl, rule);
      if (rule.fuente === "bcrp") return leerBcrp(fetchImpl, rule);
      if (rule.fuente === "inegi") {
        if (!tokenInegi) throw new Error("sin token");
        return leerInegi(fetchImpl, rule, tokenInegi);
      }
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
      if (rule.fuente === "inegi" && !tokenInegi) {
        return {
          status: "requiere_humano",
          evidence:
            `Falta INEGI_TOKEN para leer ${rule.etiqueta} por programa. ` +
            `Se saca gratis en https://www.inegi.org.mx/servicios/api_indicadores.html ` +
            `y se pone en las variables del servicio. Mientras tanto, verificar en ${query.spec.sourceUrl}`,
        };
      }
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
