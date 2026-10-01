import Anthropic from "@anthropic-ai/sdk";
import { betaZodOutputFormat } from "@anthropic-ai/sdk/helpers/beta/zod";
import { z } from "zod";
import type { OwnMarketSeed } from "../src/adapters/ownMarkets/catalog";
import type { SettlementState } from "../src/domain/settlement";

/**
 * El juez: el único lugar donde un modelo de lenguaje participa en una
 * decisión (MEMORY/FILOSOFIA.md, principio 3 — *reglas primero, juicio
 * después*).
 *
 * Juzga **sólo** lo que una regla no alcanza:
 *
 *  1. **Antes de publicar** un mercado cuyo texto viene de datos de afuera (un
 *     espejo con nombres de Kalshi, un duelo con títulos de Wikipedia): ¿la
 *     pregunta se entiende?, ¿el criterio dice lo mismo que la pregunta?, ¿toca
 *     una muerte, un crimen o la violencia (R-078)? Puede **vetar**.
 *  2. **Antes de pagar** un mercado ya resuelto: ¿la evidencia citada sostiene
 *     el resultado? Si no, **señala**; quien retiene es el revisor, por regla.
 *
 * Lo que nunca hace: pagar, anular, elegir un resultado, crear un mercado. Y
 * sólo actúa con **confianza alta**: una duda del modelo no frena nada, se
 * registra.
 *
 * Sin `ANTHROPIC_API_KEY` (o `ANTHROPIC_AUTH_TOKEN`) el juez se apaga y todo lo
 * demás corre igual (principio 7, *falla seguro*). Una caída o un rechazo del
 * modelo tampoco frena nada: sin veredicto, deciden las reglas.
 */

/** El modelo que juzga. Se registra en la bitácora con esta cadena exacta. */
export const MODELO_JUEZ = "claude-opus-5-5";

export const VeredictoTexto = z.object({
  publicable: z.boolean(),
  problema: z.enum(["ninguno", "ambiguo", "criterio_contradice", "sensible", "ilegible"]),
  confianza: z.enum(["alta", "media", "baja"]),
  motivo: z.string(),
});
export type VeredictoTexto = z.infer<typeof VeredictoTexto>;

export const VeredictoResolucion = z.object({
  sostiene: z.boolean(),
  confianza: z.enum(["alta", "media", "baja"]),
  motivo: z.string(),
});
export type VeredictoResolucion = z.infer<typeof VeredictoResolucion>;

/** Lo que el juez necesita de un modelo. Se inyecta en pruebas. */
export interface ClienteJuez {
  modelo: string;
  juzgar<T>(input: {
    tarea: string;
    contenido: string;
    esquema: z.ZodType<T>;
  }): Promise<{ datos: T | null; entrada: number; salida: number; rechazo: boolean }>;
}

/**
 * El sistema es **estable** —no lleva fechas ni ids— para que se cachee: cada
 * llamada cambia sólo el mensaje del usuario.
 */
const SISTEMA = `Eres el juez editorial de Marea, un mercado de predicción en español para Latinoamérica.
No decides resultados ni mueves dinero: sólo dices si un texto se puede publicar, o si una evidencia sostiene un resultado. Las reglas automáticas del sistema ya validaron todo lo que es verificable por programa; tú juzgas lo que una regla no alcanza.

Al revisar un mercado ANTES de publicarlo, márcalo como no publicable sólo si:
- "ambiguo": una persona razonable no sabría qué está apostando, o dos lectores honestos resolverían distinto.
- "criterio_contradice": el criterio de resolución dice algo distinto de lo que pregunta el título o de lo que dicen las respuestas.
- "sensible": la pregunta gira en torno a la muerte de una persona, un crimen, la violencia, una tragedia, o expone a una persona privada. No se apuesta sobre una desgracia. Una elección, un partido, una película o una figura pública en su papel público no son sensibles.
- "ilegible": el texto está roto, en otro idioma sin razón, o con nombres cortados que lo vuelven incomprensible.
Nombres en inglés de canciones, series o personas no son un problema. Un mercado de política o geopolítica no es sensible por serlo.

Al revisar una RESOLUCIÓN, di si la evidencia citada sostiene el resultado elegido según el criterio. Si la evidencia es compatible con el resultado, sostiene. Sólo di que no sostiene cuando la evidencia, leída con el criterio, apunta a otra respuesta o no dice nada sobre la pregunta.

Usa confianza "alta" sólo cuando no tengas dudas razonables. En la duda, confianza "media" o "baja": el sistema no actúa sobre esas. Escribe el motivo en español, en una o dos frases.`;

/** El cliente real: SDK oficial, salida estructurada validada con Zod. */
export function clienteAnthropic(env: Record<string, string | undefined>): ClienteJuez | undefined {
  if (!env.ANTHROPIC_API_KEY && !env.ANTHROPIC_AUTH_TOKEN) return undefined;
  const client = new Anthropic();
  return {
    modelo: MODELO_JUEZ,
    async juzgar<T>({ tarea, contenido, esquema }: { tarea: string; contenido: string; esquema: z.ZodType<T> }) {
      const respuesta = await client.beta.messages.parse({
        model: MODELO_JUEZ,
        max_tokens: 4000,
        // ante un rechazo del filtro de seguridad, el propio servidor reintenta
        // con el modelo de respaldo que corresponda a la categoría
        betas: ["server-side-fallback-2026-07-01"],
        fallbacks: "default",
        system: [{ type: "text", text: SISTEMA, cache_control: { type: "ephemeral" } }],
        // clasificar un texto corto no necesita pensar mucho
        output_config: { effort: "low", format: betaZodOutputFormat(esquema) },
        messages: [{ role: "user", content: `${tarea}\n\n${contenido}` }],
      });
      const rechazo = respuesta.stop_reason === "refusal";
      return {
        datos: rechazo ? null : ((respuesta.parsed_output as T | null) ?? null),
        entrada: respuesta.usage.input_tokens + (respuesta.usage.cache_read_input_tokens ?? 0),
        salida: respuesta.usage.output_tokens,
        rechazo,
      };
    },
  };
}

/** ¿El texto de este mercado viene de datos de afuera? Sólo ésos pasan por el juez. */
export function requiereJuicio(seed: OwnMarketSeed): boolean {
  return seed.rule?.kind === "espejo" || seed.rule?.kind === "tendencia";
}

export interface DecisionJuez {
  decision: "publicar" | "vetar" | "diferir";
  motivo: string;
  autor: "reglas" | `claude:${string}`;
}

export interface EstadoJuez {
  activo: boolean;
  modelo: string | null;
  llamadas: number;
  tokensEntrada: number;
  tokensSalida: number;
  vetos: number;
  senales: number;
  errores: number;
  ultimoError?: string;
}

function textoDe(seed: OwnMarketSeed): string {
  const respuestas = (seed.outcomes ?? [{ id: "si", label: "Sí" }, { id: "no", label: "No" }])
    .map((o) => `- ${o.label}`)
    .join("\n");
  return [
    `Título: ${seed.title}`,
    `Título corto: ${seed.shortTitle}`,
    `Respuestas:\n${respuestas}`,
    `Criterio de resolución: ${seed.resolution.criterion}`,
    `Fuente: ${seed.resolution.sourceName}`,
  ].join("\n");
}

export class Juez {
  private readonly textos = new Map<string, DecisionJuez>();
  private readonly resoluciones = new Map<string, { clave: string; veredicto: VeredictoResolucion }>();
  private presupuesto = 0;
  private readonly cuenta: EstadoJuez;

  constructor(
    private readonly cliente: ClienteJuez | undefined,
    /** Llamadas al modelo por ciclo. Lo que no alcanza, espera al siguiente. */
    private readonly porCiclo = 15,
  ) {
    this.cuenta = {
      activo: Boolean(cliente),
      modelo: cliente?.modelo ?? null,
      llamadas: 0,
      tokensEntrada: 0,
      tokensSalida: 0,
      vetos: 0,
      senales: 0,
      errores: 0,
    };
  }

  /** Se llama al empezar cada ciclo. */
  nuevoCiclo(): void {
    this.presupuesto = this.porCiclo;
  }

  private async llamar<T>(tarea: string, contenido: string, esquema: z.ZodType<T>): Promise<T | null | "sin_presupuesto"> {
    if (!this.cliente) return null;
    if (this.presupuesto <= 0) return "sin_presupuesto";
    this.presupuesto -= 1;
    try {
      const r = await this.cliente.juzgar({ tarea, contenido, esquema });
      this.cuenta.llamadas += 1;
      this.cuenta.tokensEntrada += r.entrada;
      this.cuenta.tokensSalida += r.salida;
      return r.datos;
    } catch (error) {
      this.cuenta.errores += 1;
      this.cuenta.ultimoError = error instanceof Error ? error.message : String(error);
      return null;
    }
  }

  /**
   * ¿Se publica? Sin juez, sin necesidad o sin veredicto claro, deciden las
   * reglas: se publica. Sólo un «no publicable» con confianza alta veta.
   */
  async revisarTexto(seed: OwnMarketSeed): Promise<DecisionJuez> {
    const previa = this.textos.get(seed.id);
    if (previa) return previa;
    if (!this.cliente || !requiereJuicio(seed)) {
      return { decision: "publicar", motivo: "Sin juicio editorial: lo deciden las reglas.", autor: "reglas" };
    }
    const r = await this.llamar(
      "Revisa este mercado ANTES de publicarlo.",
      textoDe(seed),
      VeredictoTexto,
    );
    if (r === "sin_presupuesto") {
      return { decision: "diferir", motivo: "El juez agotó sus llamadas de este ciclo.", autor: "reglas" };
    }
    const autor = `claude:${this.cliente.modelo}` as const;
    let decision: DecisionJuez;
    if (!r) {
      decision = { decision: "publicar", motivo: "El juez no dio veredicto; deciden las reglas.", autor: "reglas" };
    } else if (!r.publicable && r.confianza === "alta" && r.problema !== "ninguno") {
      this.cuenta.vetos += 1;
      decision = { decision: "vetar", motivo: `${r.problema}: ${r.motivo}`, autor };
    } else {
      decision = { decision: "publicar", motivo: r.motivo, autor };
    }
    this.textos.set(seed.id, decision);
    return decision;
  }

  /**
   * Revisa resoluciones en disputa (nunca velas: su regla es un número y su
   * ventana es de un minuto). Una vez por mercado y resultado.
   */
  async revisarResoluciones(
    pendientes: readonly { seed: OwnMarketSeed; estado: SettlementState }[],
  ): Promise<void> {
    if (!this.cliente) return;
    for (const { seed, estado } of pendientes) {
      if (estado.phase !== "en_disputa" || !estado.outcome || seed.rule?.kind === "vela") continue;
      const clave = `${estado.outcome}|${estado.evidence ?? ""}`;
      if (this.resoluciones.get(seed.id)?.clave === clave) continue;
      const etiqueta = seed.outcomes?.find((o) => o.id === estado.outcome)?.label ?? estado.outcome;
      const r = await this.llamar(
        "Revisa esta RESOLUCIÓN antes de pagarla.",
        `${textoDe(seed)}\n\nResultado elegido: ${etiqueta}\nEvidencia citada: ${estado.evidence ?? "(ninguna)"}`,
        VeredictoResolucion,
      );
      if (r === "sin_presupuesto") return;
      if (!r) continue;
      if (!r.sostiene && r.confianza === "alta") this.cuenta.senales += 1;
      this.resoluciones.set(seed.id, { clave, veredicto: r });
    }
  }

  /** Para el revisor: mercado → motivo, sólo las señales de confianza alta. */
  juiciosDeResolucion(): Record<string, string> {
    const salida: Record<string, string> = {};
    for (const [id, { veredicto }] of this.resoluciones) {
      if (!veredicto.sostiene && veredicto.confianza === "alta") {
        salida[id] = `El juez (${this.cliente?.modelo}) dice que la evidencia no sostiene el resultado: ${veredicto.motivo}`;
      }
    }
    return salida;
  }

  estado(): EstadoJuez {
    return { ...this.cuenta };
  }
}
