import * as React from "react";
import { Bot, ShieldCheck, ShieldAlert } from "lucide-react";
import { Card } from "@/components/ui/card";
import { EmptyState, ListSkeleton } from "@/components/StateViews";
import { S } from "@/lib/strings";
import { cn } from "@/lib/cn";
import { useApp } from "@/state/store";

/**
 * El tablero del director (MEMORY/FILOSOFIA.md, principios 5 y 9). Interno:
 * sólo para `MAREA_ADMINS`.
 *
 * Pinta `/api/director` tal cual: lo que hay abierto, cuánto tarda en pagar, lo
 * que el revisor encontró, las últimas decisiones de la bitácora con quién las
 * tomó y si la cadena verifica; el **backtest** de sus priors contra lo que de
 * verdad pasó, y la **depuración**: sus últimas vueltas en vivo y la traza de
 * cualquier mercado al tocarlo.
 */

interface Entrada {
  titulo?: string;
  n: number;
  at: string;
  tipo: string;
  sujeto: string;
  motivo: string;
  autor: string;
  regla?: string;
}

interface Comparacion {
  media: number;
  ic95: [number, number];
  veredicto: "no_concluye" | "mejor" | "peor" | "indistinguible";
}

interface Calificacion {
  n: number;
  conPrior: number;
  conApuestas: number;
  brier: { parejo: number; director: number; gente: number };
  directorVsParejo: Comparacion;
  genteVsDirector: Comparacion;
}

interface Vuelta {
  at: string;
  duracionMs: number;
  intentados: number;
  acciones: { id: string; de: string; a: string; como: string; motivo: string }[];
  errores: string[];
}

interface Traza {
  mercado: { titulo: string; familia?: string; fuente: string; criterio: string; prior: Record<string, number> } | null;
  estado: { phase: string; outcome?: string; evidence?: string; stuckReason?: string; retenidoPor?: string } | null;
  apuestas: { n: number; sinPagar: number };
  hallazgos: { clave: string; codigo: string; detalle: string }[];
  decisiones: Entrada[];
}

interface Reporte {
  catalogo: { abiertos: number; porFamilia: Record<string, number>; multiOpcion: number };
  resoluciones7d: { resueltos: number; medianaHoras: number | null };
  salud: { atorados: number; retenidos: number; hallazgos: Record<string, number> };
  hallazgos: { clave: string; severidad: string; sujeto: string; titulo?: string; detalle: string }[];
  decisiones: { total: number; cadena: { ok: boolean; en?: number; entradas?: number }; ultimas: Entrada[] };
  juez: { activo: boolean; modelo: string | null };
  enVivo?: { cadaSegundos: number; acciones24h: number } | null;
  backtest?: { total: Calificacion; porFamilia: Record<string, Calificacion> };
  depuracion?: { vueltas: Vuelta[] };
}

const pct = (p: number) => `${Math.round(p * 100)} %`;
const tres = (x: number) => x.toFixed(3);

function veredicto(c: Comparacion, n: number, quien: string, contra: string): string {
  if (c.veredicto === "no_concluye") return S.director.noConcluye(n);
  const ic = `IC95 [${c.ic95[0] >= 0 ? "+" : ""}${tres(c.ic95[0])}, ${c.ic95[1] >= 0 ? "+" : ""}${tres(c.ic95[1])}]`;
  return `${S.director.veredicto[c.veredicto](quien, contra)} · ${ic}`;
}

/** La traza de un mercado: se pide al tocarlo, no antes. */
function TrazaMercado({ id }: { id: string }) {
  const [traza, setTraza] = React.useState<Traza | null | "error">(null);
  React.useEffect(() => {
    let vivo = true;
    fetch(`/api/director/traza?id=${encodeURIComponent(id)}`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((t) => vivo && setTraza(t as Traza))
      .catch(() => vivo && setTraza("error"));
    return () => {
      vivo = false;
    };
  }, [id]);
  if (traza === null) return <p className="px-3 pb-2.5 text-[12px] text-muted">…</p>;
  if (traza === "error") return <p className="px-3 pb-2.5 text-[12px] text-muted">{S.director.trazaError}</p>;
  const { mercado, estado, apuestas, hallazgos, decisiones } = traza;
  return (
    <div data-testid="director-traza" className="space-y-1 border-t border-line2 px-3 py-2.5 text-[12px] leading-snug text-text2">
      <p>
        <span className="font-semibold text-text">{S.director.fase}:</span> {estado?.phase ?? "abierto"}
        {estado?.outcome ? ` · ${estado.outcome}` : ""}
        {estado?.retenidoPor ? ` · ${S.director.retenidoPor(estado.retenidoPor)}` : ""}
        {` · ${S.director.apuestas(apuestas.n, apuestas.sinPagar)}`}
      </p>
      {estado?.evidence ? (
        <p>
          <span className="font-semibold text-text">{S.director.evidencia}:</span> {estado.evidence}
        </p>
      ) : null}
      {estado?.stuckReason ? <p>{estado.stuckReason}</p> : null}
      {mercado ? (
        <>
          <p>
            <span className="font-semibold text-text">{S.director.fuente}:</span> {mercado.fuente} ·{" "}
            {S.director.prior}{" "}
            {Object.entries(mercado.prior)
              .map(([o, p]) => `${o} ${pct(p)}`)
              .join(" · ")}
          </p>
          <p className="text-muted">{mercado.criterio}</p>
        </>
      ) : null}
      {hallazgos.map((h) => (
        <p key={h.clave}>⚑ {h.codigo}: {h.detalle}</p>
      ))}
      <ol className="space-y-0.5 pt-1">
        {decisiones.map((e) => (
          <li key={e.n} className="tabular-nums">
            #{e.n} {hora(e.at)} · <span className="font-semibold text-text">{S.director.tipo[e.tipo] ?? e.tipo}</span> · {e.motivo}
          </li>
        ))}
      </ol>
    </div>
  );
}

const TONO: Record<string, string> = {
  // color-mix, como las insignias: el modificador /15 no funciona con colores en var()
  critico: "bg-[color:color-mix(in_srgb,var(--dn)_14%,transparent)] text-dn",
  grave: "bg-[color:color-mix(in_srgb,var(--hot)_14%,transparent)] text-[color:var(--hot)]",
  aviso: "bg-line2 text-text2",
  info: "bg-line2 text-muted",
};

function hora(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("es-MX", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function Cifra({ valor, etiqueta }: { valor: string; etiqueta: string }) {
  return (
    <Card className="flex flex-col gap-0.5 p-3" data-testid="director-cifra">
      <span className="font-display text-[24px] font-bold tabular-nums leading-none text-text">{valor}</span>
      <span className="text-[12px] font-medium text-muted">{etiqueta}</span>
    </Card>
  );
}

export function DirectorScreen() {
  const { adapters } = useApp();
  const [datos, setDatos] = React.useState<Reporte | null>(null);
  /** El mercado cuya traza está abierta: `${lista}:${clave}`, una a la vez. */
  const [abierto, setAbierto] = React.useState<string | null>(null);
  const alternar = (clave: string) => setAbierto((actual) => (actual === clave ? null : clave));
  const [error, setError] = React.useState<"falla" | "interno" | null>(null);

  React.useEffect(() => {
    let vivo = true;
    if (!adapters.api) {
      setError("falla");
      return;
    }
    fetch("/api/director", { credentials: "include" })
      .then((r) => {
        // el panel es interno: sin permiso se dice así, no «no pudimos leer»
        if (r.status === 401 || r.status === 403) return Promise.reject(new Error("interno"));
        return r.ok ? r.json() : Promise.reject(new Error(String(r.status)));
      })
      .then((cuerpo) => vivo && setDatos(cuerpo as Reporte))
      .catch((e: unknown) => vivo && setError(e instanceof Error && e.message === "interno" ? "interno" : "falla"));
    return () => {
      vivo = false;
    };
  }, [adapters.api]);

  if (error) {
    return (
      <div className="pt-4">
        <EmptyState
          title={error === "interno" ? S.director.interno : S.director.error}
          body=""
          testId={error === "interno" ? "director-interno" : "director-error"}
        />
      </div>
    );
  }
  if (!datos) {
    return (
      <div className="pt-4">
        <ListSkeleton rows={4} />
      </div>
    );
  }

  const { catalogo, resoluciones7d, salud, hallazgos, decisiones, juez } = datos;
  const abiertosHallazgos = Object.values(salud.hallazgos).reduce((s, n) => s + n, 0);
  const familias = Object.entries(catalogo.porFamilia).sort((a, b) => b[1] - a[1]);

  return (
    <div data-testid="director-screen" className="space-y-4 pb-6">
      <header className="px-4 pt-5">
        <h1 className="flex items-center gap-2 font-display text-[26px] font-semibold text-text">
          <Bot aria-hidden className="h-6 w-6 text-teal" />
          {S.director.title}
        </h1>
        <p className="pt-1 text-[14px] leading-snug text-text2">{S.director.subtitle}</p>
      </header>

      <div className="grid grid-cols-2 gap-2 px-4">
        <Cifra valor={String(catalogo.abiertos)} etiqueta={S.director.abiertos} />
        <Cifra valor={String(resoluciones7d.resueltos)} etiqueta={S.director.resueltos} />
        <Cifra
          valor={resoluciones7d.medianaHoras === null ? S.director.sinDato : S.director.horas(resoluciones7d.medianaHoras)}
          etiqueta={S.director.mediana}
        />
        <Cifra valor={String(abiertosHallazgos)} etiqueta={S.director.hallazgos} />
      </div>

      <div className="space-y-1 px-4 text-[13px]">
        <p
          data-testid="director-cadena"
          className={cn("flex items-center gap-1.5 font-medium", decisiones.cadena.ok ? "text-up" : "text-dn")}
        >
          {decisiones.cadena.ok ? <ShieldCheck aria-hidden className="h-4 w-4" /> : <ShieldAlert aria-hidden className="h-4 w-4" />}
          {decisiones.cadena.ok ? S.director.cadenaOk(decisiones.total) : S.director.cadenaRota(decisiones.cadena.en ?? 0)}
        </p>
        <p data-testid="director-juez" className="text-text2">
          {juez.activo && juez.modelo ? S.director.juezActivo(juez.modelo) : S.director.juezApagado}
        </p>
        {datos.enVivo ? (
          <p data-testid="director-en-vivo" className="text-text2">
            {S.director.enVivo(datos.enVivo.cadaSegundos, datos.enVivo.acciones24h)}
          </p>
        ) : null}
      </div>

      {familias.length > 0 ? (
        <section className="px-4">
          <h2 className="pb-2 text-[15px] font-semibold text-text">{S.director.familias}</h2>
          <div className="flex flex-wrap gap-1.5">
            {familias.map(([familia, n]) => (
              <span key={familia} className="rounded-[10px] bg-line2 px-2.5 py-1 text-[13px] text-text2">
                {familia} <span className="font-semibold tabular-nums text-text">{n}</span>
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {datos.backtest ? (
        <section className="px-4" data-testid="director-backtest">
          <h2 className="pb-1 text-[15px] font-semibold text-text">{S.director.backtest}</h2>
          <p className="pb-2 text-[12px] leading-snug text-muted">{S.director.backtestNota}</p>
          <Card className="divide-y divide-line2 p-0">
            {[["Total", datos.backtest.total] as const, ...Object.entries(datos.backtest.porFamilia)].map(([familia, c]) => (
              <div key={familia} className="px-3 py-2.5 text-[12px] leading-snug text-text2" data-testid="director-backtest-fila">
                <p className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold text-text">{familia}</span>
                  <span className="tabular-nums text-muted">{S.director.muestra(c.n, c.conPrior, c.conApuestas)}</span>
                </p>
                {c.n > 0 ? (
                  <>
                    <p className="tabular-nums">
                      Brier · {S.director.parejo} {tres(c.brier.parejo)} · {S.director.elDirector} {tres(c.brier.director)} ·{" "}
                      {S.director.laGente} {tres(c.brier.gente)}
                    </p>
                    <p>{veredicto(c.directorVsParejo, c.n, S.director.elDirector, S.director.parejo)}</p>
                    <p>{veredicto(c.genteVsDirector, c.n, S.director.laGente, S.director.elDirector)}</p>
                  </>
                ) : null}
              </div>
            ))}
          </Card>
        </section>
      ) : null}

      {datos.depuracion ? (
        <section className="px-4" data-testid="director-vueltas">
          <h2 className="pb-2 text-[15px] font-semibold text-text">{S.director.vueltas}</h2>
          {datos.depuracion.vueltas.length === 0 ? (
            <p className="text-[13px] text-muted">{S.director.vueltasVacio}</p>
          ) : (
            <Card className="divide-y divide-line2 p-0">
              {datos.depuracion.vueltas.slice(0, 12).map((v) => (
                <div key={v.at} className="px-3 py-2 text-[12px] leading-snug text-text2" data-testid="director-vuelta">
                  <p className="flex justify-between gap-2 tabular-nums">
                    <span>
                      {hora(v.at)} · {S.director.vuelta(v.intentados, v.acciones.length, v.errores.length)}
                    </span>
                    <span className="text-muted">{v.duracionMs} ms</span>
                  </p>
                  {v.acciones.map((a) => (
                    <p key={a.id} className="truncate">
                      {a.como === "anular" ? "⊘" : "↻"} {a.id}: {a.de} → {a.a}
                    </p>
                  ))}
                  {v.errores.map((e) => (
                    <p key={e} className="text-dn">
                      {e}
                    </p>
                  ))}
                </div>
              ))}
            </Card>
          )}
        </section>
      ) : null}

      <section className="px-4">
        <h2 className="pb-2 text-[15px] font-semibold text-text">{S.director.hallazgos}</h2>
        {hallazgos.length === 0 ? (
          <p className="text-[13px] text-muted">{S.director.hallazgosVacio}</p>
        ) : (
          <Card className="divide-y divide-line2 p-0">
            {hallazgos.slice(0, 12).map((h) => (
              <div key={h.clave} data-testid="director-hallazgo">
                <button
                  type="button"
                  disabled={!h.titulo}
                  onClick={() => alternar(`h:${h.clave}`)}
                  className="flex w-full items-start gap-2 px-3 py-2.5 text-left"
                >
                  <span className={cn("mt-0.5 shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-semibold", TONO[h.severidad])}>
                    {S.director.severidad[h.severidad] ?? h.severidad}
                  </span>
                  <span className="block min-w-0">
                    <span className="block truncate text-[13px] font-semibold text-text">{h.titulo ?? h.sujeto}</span>
                    <span className="block text-[12px] leading-snug text-text2">{h.detalle}</span>
                  </span>
                </button>
                {abierto === `h:${h.clave}` ? <TrazaMercado id={h.sujeto} /> : null}
              </div>
            ))}
          </Card>
        )}
      </section>

      <section className="px-4">
        <h2 className="pb-2 text-[15px] font-semibold text-text">{S.director.decisiones}</h2>
        <Card className="divide-y divide-line2 p-0">
          {decisiones.ultimas.slice(0, 25).map((e) => (
            <div key={e.n} data-testid="director-decision">
              <button
                type="button"
                disabled={!e.titulo}
                onClick={() => alternar(`d:${e.n}`)}
                className="block w-full px-3 py-2.5 text-left"
              >
                <span className="flex items-baseline justify-between gap-2 text-[12px] text-muted">
                  <span className="min-w-0 truncate">
                    <span className="font-semibold text-text">{S.director.tipo[e.tipo] ?? e.tipo}</span> · {e.titulo ?? e.sujeto}
                  </span>
                  <span className="shrink-0 tabular-nums">{hora(e.at)}</span>
                </span>
                <span className="block pt-0.5 text-[13px] leading-snug text-text2">{e.motivo}</span>
                <span className="block pt-0.5 text-[11px] text-muted">
                  #{e.n} · {S.director.autor[e.autor] ?? e.autor}
                  {e.regla ? ` · ${e.regla}` : ""}
                </span>
              </button>
              {abierto === `d:${e.n}` ? <TrazaMercado id={e.sujeto} /> : null}
            </div>
          ))}
        </Card>
      </section>
    </div>
  );
}
