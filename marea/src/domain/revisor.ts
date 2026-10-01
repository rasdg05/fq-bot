import type { SettlementState } from "./settlement";
import type { Pool } from "./parimutuel";
import type { MarketCategory } from "./types";

/**
 * El revisor autónomo de mercados (MEMORY/FILOSOFIA.md).
 *
 * Mira el sistema entero cada ciclo y contesta una pregunta: **¿algo se
 * resolvió mal, se rompió o está trabajando de forma errónea?** Lo que
 * encuentra son *hallazgos*, con ciclo de vida: se abren cuando aparecen y se
 * cierran cuando dejan de verse. La bitácora registra esos dos momentos, no las
 * cien veces que el revisor volvió a mirar.
 *
 * Es puro: recibe una foto y devuelve hallazgos. Lo que se hace con ellos —y
 * qué acción toma el agente solo— lo decide `accionDe`, también aquí, para que
 * se pueda probar sin servidor.
 *
 * Cada chequeo nació de un fallo real o de una invariante escrita:
 *
 * | Código | De dónde viene |
 * |---|---|
 * | `resultado_fuera_de_opciones` | un oráculo que contesta un id que el mercado no tiene pagaría a nadie, o a quien no debe |
 * | `resolucion_sin_evidencia` | R-025: lo que se paga se cita |
 * | `atorado` / `sin_leer` | el mes de agosto con apuestas congeladas y «0 errores» |
 * | `abierto_tras_cierre` | un mercado aceptando apuestas después de su hora |
 * | `fuente_con_fallas` | ESPN y Kalshi devolviendo 403/429 en silencio |
 * | `pozo_descuadrado` / `huerfanas` | L3 y R-024 |
 * | `pago_infinito` | un lado con pozo vacío paga infinito |
 * | `familia_vacia` | la reposición que no reponía nada |
 * | `titulo_largo` | títulos cortados en la tarjeta (medido en la densidad) |
 * | `categoria_dominante` | un feed que es sólo futbol no es un mercado de predicción |
 */

export type Severidad = "info" | "aviso" | "grave" | "critico";

export type CodigoHallazgo =
  | "resultado_fuera_de_opciones"
  | "resolucion_sin_evidencia"
  | "atorado"
  | "sin_leer"
  | "abierto_tras_cierre"
  | "fuente_con_fallas"
  | "pozo_descuadrado"
  | "huerfanas"
  | "pago_infinito"
  | "familia_vacia"
  | "titulo_largo"
  | "categoria_dominante"
  /** Lo señala el juez (Claude): la evidencia no sostiene el resultado. */
  | "evidencia_no_sostiene";

/** Lo único que el revisor hace solo cuando hay dinero de por medio. */
export type AccionRevisor = "retener";

export interface Hallazgo {
  /** `codigo:sujeto`. Un mismo problema sobre el mismo sujeto es un solo hallazgo. */
  clave: string;
  codigo: CodigoHallazgo;
  severidad: Severidad;
  /** Mercado, fuente, familia o «catalogo». */
  sujeto: string;
  detalle: string;
  /** Desde cuándo está abierto. */
  desde?: string;
  accion?: AccionRevisor;
}

export interface MercadoEnFoto {
  id: string;
  shortTitle: string;
  category: MarketCategory;
  closesAt: string;
  settlesAt: string;
  /** Ids de respuesta válidos. Un binario sin `outcomes` declarados es `si`/`no`. */
  outcomes: string[];
  /** Tipo de regla del oráculo (`espejo`, `tenis`…) o `sin_regla`. */
  fuente: string;
  estado?: SettlementState;
  pozo?: Pool;
  /** ¿Tiene apuestas de usuarios? */
  conApuestas: boolean;
  /** ¿Es una vela viva de minutos? No cuenta para el catálogo duradero. */
  vela: boolean;
}

export interface FamiliaEsperada {
  nombre: string;
  /** El mercado es de esta familia. */
  es: (m: MercadoEnFoto) => boolean;
}

export interface Foto {
  ahora: number;
  mercados: MercadoEnFoto[];
  /** `store.cuadre()`: debe ser 0. */
  descuadre: number;
  /** Pozos que quedaron con saldo tras liquidar. Vacío = sano. */
  pozosConSaldo: Record<string, number>;
  /** Contexto de cada uno, si se tiene: para distinguir herencia de bug vigente. */
  detallePozos?: Record<string, { liquidadoEl?: string; apuestas: number; sinPagar: number }>;
  /** Apuestas cuyo mercado ya no está en el catálogo. */
  huerfanas: Record<string, number>;
  familias?: FamiliaEsperada[];
  /** Señales del juez sobre resoluciones: id de mercado → motivo. */
  juicios?: Record<string, string>;
  tituloIdeal?: number;
}

const H = 3_600_000;
/** Una fuente con fallas: el mismo síntoma en al menos esto de mercados. */
const MINIMO_FALLAS = 2;
const FALLA_DE_RED = /respondi[óo] (4\d\d|5\d\d)|no respondi[óo]|fetch failed|ECONN|ETIMEDOUT|timeout|too many requests/i;

function hallazgo(
  codigo: CodigoHallazgo,
  severidad: Severidad,
  sujeto: string,
  detalle: string,
  accion?: AccionRevisor,
): Hallazgo {
  return { clave: `${codigo}:${sujeto}`, codigo, severidad, sujeto, detalle, ...(accion ? { accion } : {}) };
}

/** Todos los chequeos sobre una foto. Puro y determinista. */
export function revisar(foto: Foto): Hallazgo[] {
  const { ahora } = foto;
  const salida: Hallazgo[] = [];

  for (const m of foto.mercados) {
    const e = m.estado;
    const resuelto = e && (e.phase === "en_disputa" || e.phase === "pagado");

    // 1. un resultado que el mercado no tiene: nunca se paga, se retiene
    if (resuelto && e.outcome && !m.outcomes.includes(e.outcome)) {
      salida.push(
        hallazgo(
          "resultado_fuera_de_opciones",
          "critico",
          m.id,
          `La fuente resolvió «${e.outcome}», que no es una respuesta de este mercado (${m.outcomes.join(", ")}).`,
          e.phase === "en_disputa" ? "retener" : undefined,
        ),
      );
    }
    // 2. lo que se paga se cita (R-025)
    if (resuelto && !e.evidence?.trim()) {
      salida.push(hallazgo("resolucion_sin_evidencia", "grave", m.id, "Resuelto sin evidencia citable."));
    }
    // 3. el juez dice que la evidencia no sostiene el resultado
    const juicio = foto.juicios?.[m.id];
    if (juicio && e?.phase === "en_disputa") {
      salida.push(hallazgo("evidencia_no_sostiene", "critico", m.id, juicio, "retener"));
    }
    // 4. atorado: ya lo ve /salud; aquí tiene dueño y ciclo de vida
    if (e?.phase === "atorado" && !e.retenidoPor) {
      salida.push(hallazgo("atorado", e.incobrable ? "aviso" : "grave", m.id, e.stuckReason ?? "Atorado sin motivo escrito."));
    }
    // 5. pasó su fecha de resolución y nadie lo leyó todavía
    const settles = Date.parse(m.settlesAt);
    const sinLeer = !e || e.phase === "abierto" || e.phase === "cerrado" || e.phase === "leido";
    if (!m.vela && sinLeer && Number.isFinite(settles) && ahora > settles + 24 * H) {
      const horas = Math.floor((ahora - settles) / H);
      salida.push(
        hallazgo(
          "sin_leer",
          horas >= 72 ? "grave" : "aviso",
          m.id,
          `Lleva ${horas} h sin resolverse después de su fecha${e?.evidence ? `; última lectura: ${e.evidence.slice(0, 160)}` : ""}.`,
        ),
      );
    }
    // 6. sigue abierto media hora después de su cierre: el ciclo no lo cerró
    const closes = Date.parse(m.closesAt);
    if ((!e || e.phase === "abierto") && m.conApuestas && Number.isFinite(closes) && ahora > closes + 0.5 * H) {
      salida.push(hallazgo("abierto_tras_cierre", "grave", m.id, `Cerraba ${m.closesAt} y sigue en fase abierta.`));
    }
    // 7. un lado sin pozo paga infinito: el multiplicador no tiene sentido
    if (m.pozo && (!e || e.phase === "abierto") && Number.isFinite(closes) && ahora < closes) {
      const vacios = Object.entries(m.pozo.outcomes).filter(([, v]) => !(v > 0)).map(([k]) => k);
      if (vacios.length > 0) {
        salida.push(hallazgo("pago_infinito", "aviso", m.id, `Respuestas con pozo vacío: ${vacios.join(", ")}.`));
      }
    }
    // 8. el título que se corta en la tarjeta
    if (foto.tituloIdeal && !m.vela && m.shortTitle.length > foto.tituloIdeal && (!e || e.phase === "abierto")) {
      salida.push(
        hallazgo("titulo_largo", "info", m.id, `«${m.shortTitle}» mide ${m.shortTitle.length}; caben ${foto.tituloIdeal}.`),
      );
    }
  }

  // 9. fuentes con fallas de red repetidas, agrupadas por tipo de oráculo
  const fallas = new Map<string, string[]>();
  for (const m of foto.mercados) {
    const ev = m.estado?.evidence ?? "";
    const abiertoAun = !m.estado || ["abierto", "cerrado", "leido", "atorado"].includes(m.estado.phase);
    if (abiertoAun && FALLA_DE_RED.test(ev)) fallas.set(m.fuente, [...(fallas.get(m.fuente) ?? []), m.id]);
  }
  for (const [fuente, ids] of fallas) {
    if (ids.length >= MINIMO_FALLAS) {
      salida.push(
        hallazgo("fuente_con_fallas", "grave", fuente, `${ids.length} mercados con falla de red en la última lectura: ${ids.slice(0, 5).join(", ")}.`),
      );
    }
  }

  // 10. dinero: el libro cuadra y los pozos quedan en cero
  if (foto.descuadre !== 0) {
    salida.push(hallazgo("pozo_descuadrado", "critico", "libro", `El libro no cuadra por ${foto.descuadre} puntos.`));
  }
  for (const [id, saldo] of Object.entries(foto.pozosConSaldo)) {
    const d = foto.detallePozos?.[id];
    const contexto = d
      ? ` Liquidado ${d.liquidadoEl?.slice(0, 10) ?? "sin fecha"}; ${d.apuestas} apuestas, ${d.sinPagar} sin pagar.`
      : "";
    salida.push(
      hallazgo("pozo_descuadrado", "critico", id, `El pozo quedó con ${Math.round(saldo * 100) / 100} puntos tras liquidar.${contexto}`),
    );
  }
  for (const [id, n] of Object.entries(foto.huerfanas)) {
    salida.push(hallazgo("huerfanas", "grave", id, `${n} apuestas cuyo mercado ya no está en el catálogo.`));
  }

  // 11. familias que deberían tener algo abierto y no tienen nada
  const duraderosAbiertos = foto.mercados.filter(
    (m) => !m.vela && Date.parse(m.closesAt) > ahora && (!m.estado || m.estado.phase === "abierto"),
  );
  for (const familia of foto.familias ?? []) {
    if (!duraderosAbiertos.some(familia.es)) {
      salida.push(hallazgo("familia_vacia", "aviso", familia.nombre, `Ningún mercado abierto de ${familia.nombre}.`));
    }
  }

  // 12. un feed que es una sola cosa
  if (duraderosAbiertos.length >= 10) {
    const porCategoria = new Map<string, number>();
    for (const m of duraderosAbiertos) porCategoria.set(m.category, (porCategoria.get(m.category) ?? 0) + 1);
    for (const [categoria, n] of porCategoria) {
      if (n / duraderosAbiertos.length > 0.6) {
        salida.push(
          hallazgo(
            "categoria_dominante",
            "info",
            "catalogo",
            `${categoria} es el ${Math.round((100 * n) / duraderosAbiertos.length)} % de los ${duraderosAbiertos.length} mercados abiertos.`,
          ),
        );
      }
    }
  }

  return salida;
}

export interface Conciliacion {
  abiertos: Hallazgo[];
  abren: Hallazgo[];
  cierran: Hallazgo[];
}

/**
 * Lleva los hallazgos al estado nuevo: los que aparecen se abren con fecha, los
 * que siguen conservan la suya, y los que ya no se ven se cierran. Es lo que
 * hace que la bitácora registre cambios y no observaciones.
 */
export function conciliar(previos: readonly Hallazgo[], detectados: readonly Hallazgo[], ahora: number): Conciliacion {
  const antes = new Map(previos.map((h) => [h.clave, h]));
  const ahoraVistos = new Map<string, Hallazgo>();
  for (const h of detectados) if (!ahoraVistos.has(h.clave)) ahoraVistos.set(h.clave, h);

  const abiertos: Hallazgo[] = [];
  const abren: Hallazgo[] = [];
  for (const [clave, h] of ahoraVistos) {
    const previo = antes.get(clave);
    if (previo) {
      abiertos.push({ ...h, desde: previo.desde });
    } else {
      const nuevo = { ...h, desde: new Date(ahora).toISOString() };
      abiertos.push(nuevo);
      abren.push(nuevo);
    }
  }
  const cierran = previos.filter((h) => !ahoraVistos.has(h.clave));
  const orden: Record<Severidad, number> = { critico: 0, grave: 1, aviso: 2, info: 3 };
  abiertos.sort((a, b) => orden[a.severidad] - orden[b.severidad] || a.clave.localeCompare(b.clave));
  return { abiertos, abren, cierran };
}
