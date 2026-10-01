import { describe, expect, it } from "vitest";
import { elegirDestacados, puntajeDestacado } from "@/domain/destacados";
import type { Market } from "@/domain/types";

const AHORA = Date.parse("2026-10-01T12:00:00Z");
const EN = (horas: number) => new Date(AHORA + horas * 3_600_000).toISOString();

function mercado(id: string, parcial: Partial<Market> = {}): Market {
  return {
    id,
    title: id,
    probability: 0.5,
    volume: 0,
    status: "open",
    category: "deportes",
    edge: null,
    closesAt: EN(72),
    // la semilla de siempre: por encima del umbral de «hot», como en producción
    pool: { outcomes: { si: 400, no: 400 }, feeBps: 300 },
    hot: true,
    ...parcial,
  } as Market;
}

describe("Destacados — el carrusel es una selección, no un listado", () => {
  it("el bug de producción: si todo es «hot», el carrusel NO se lleva todo", () => {
    // cincuenta mercados recién sembrados: todos con pozo sobre el umbral
    const todos = Array.from({ length: 50 }, (_, i) =>
      mercado(`m${i}`, { category: (["deportes", "cripto", "economia"] as const)[i % 3] }),
    );
    const elegidos = elegirDestacados(todos, { ahora: AHORA });
    expect(elegidos.length).toBeLessThanOrEqual(5);
    // y por lo tanto quedan 45+ para las secciones
    expect(todos.length - elegidos.length).toBeGreaterThanOrEqual(45);
  });

  it("variedad: como mucho dos de una misma categoría", () => {
    const todos = [
      ...Array.from({ length: 10 }, (_, i) => mercado(`d${i}`, { participantes: 50 })),
      mercado("c1", { category: "cripto" }),
      mercado("e1", { category: "economia" }),
      mercado("p1", { category: "politica" }),
    ];
    const elegidos = elegirDestacados(todos, { ahora: AHORA });
    const deportes = elegidos.filter((m) => m.category === "deportes");
    expect(deportes.length).toBe(2);
    expect(new Set(elegidos.map((m) => m.category)).size).toBeGreaterThanOrEqual(4);
  });

  it("una sola vela en vivo por activo: BTC a 5 y a 15 min son la misma noticia", () => {
    const vela = (id: string, activo: string) =>
      mercado(id, { category: "cripto", status: "live", activo, live: {} as Market["live"] });
    const elegidos = elegirDestacados(
      [vela("btc-5m", "BTC"), vela("btc-15m", "BTC"), vela("eth-5m", "ETH")],
      { ahora: AHORA, porCategoria: 5 },
    );
    expect(elegidos.map((m) => m.id)).toEqual(["btc-5m", "eth-5m"]);
  });

  it("lo que ya no acepta apuestas no se destaca", () => {
    const elegidos = elegirDestacados(
      [
        mercado("cerrado", { closesAt: EN(-1), participantes: 999 }),
        mercado("liquidando", { status: "settling", participantes: 999 }),
        mercado("resuelto", { status: "resolved", participantes: 999 }),
        mercado("abierto"),
      ],
      { ahora: AHORA },
    );
    expect(elegidos.map((m) => m.id)).toEqual(["abierto"]);
  });

  it("orden: en vivo y con gente adentro antes que un pozo grande vacío", () => {
    const vivo = mercado("vivo", { status: "live" });
    const conGente = mercado("con-gente", { participantes: 40 });
    const pozoGrande = mercado("pozo-grande", {
      pool: { outcomes: { si: 90_000, no: 90_000 }, feeBps: 300 },
    });
    expect(puntajeDestacado(vivo, AHORA)).toBeGreaterThan(puntajeDestacado(pozoGrande, AHORA));
    expect(puntajeDestacado(conGente, AHORA)).toBeGreaterThan(puntajeDestacado(pozoGrande, AHORA));
  });

  it("el carrusel es de una sola forma: con maxRespuestas 2 no entra una quiniela", () => {
    const quiniela = mercado("quiniela", {
      participantes: 500,
      outcomes: [
        { id: "gana", label: "Gana" },
        { id: "empata", label: "Empatan" },
        { id: "pierde", label: "Pierde" },
      ] as Market["outcomes"],
    });
    const binario = mercado("binario");
    expect(elegirDestacados([quiniela, binario], { ahora: AHORA }).map((m) => m.id)).toContain(
      "quiniela",
    );
    expect(
      elegirDestacados([quiniela, binario], { ahora: AHORA, maxRespuestas: 2 }).map((m) => m.id),
    ).toEqual(["binario"]);
  });

  it("es determinista: misma entrada, misma salida, sin azar", () => {
    const todos = Array.from({ length: 20 }, (_, i) => mercado(`m${i}`));
    const a = elegirDestacados(todos, { ahora: AHORA }).map((m) => m.id);
    const b = elegirDestacados([...todos], { ahora: AHORA }).map((m) => m.id);
    expect(a).toEqual(b);
    // con empate, manda el orden de llegada
    expect(a[0]).toBe("m0");
  });
});
