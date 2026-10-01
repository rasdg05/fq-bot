import * as React from "react";
import { Bot, ShieldCheck, ShieldAlert } from "lucide-react";
import { Card } from "@/components/ui/card";
import { EmptyState, ListSkeleton } from "@/components/StateViews";
import { S } from "@/lib/strings";
import { cn } from "@/lib/cn";
import { useApp } from "@/state/store";

/**
 * El director de mercados, a la vista (MEMORY/FILOSOFIA.md, principio 9).
 *
 * Un mercado de predicción que pide confianza tiene que enseñar cómo decide.
 * Esta pantalla pinta `/api/director` tal cual: lo que hay abierto, cuánto
 * tarda en pagar, lo que el revisor encontró y las últimas decisiones de la
 * bitácora, con quién las tomó —las reglas o el modelo, con su versión— y si la
 * cadena verifica. Se ve sin cuenta, como la tabla (R-002).
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

interface Reporte {
  catalogo: { abiertos: number; porFamilia: Record<string, number>; multiOpcion: number };
  resoluciones7d: { resueltos: number; medianaHoras: number | null };
  salud: { atorados: number; retenidos: number; hallazgos: Record<string, number> };
  hallazgos: { clave: string; severidad: string; sujeto: string; titulo?: string; detalle: string }[];
  decisiones: { total: number; cadena: { ok: boolean; en?: number; entradas?: number }; ultimas: Entrada[] };
  juez: { activo: boolean; modelo: string | null };
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
  const [error, setError] = React.useState(false);

  React.useEffect(() => {
    let vivo = true;
    if (!adapters.api) {
      setError(true);
      return;
    }
    fetch("/api/director", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((cuerpo) => vivo && setDatos(cuerpo as Reporte))
      .catch(() => vivo && setError(true));
    return () => {
      vivo = false;
    };
  }, [adapters.api]);

  if (error) {
    return (
      <div className="pt-4">
        <EmptyState title={S.director.error} body="" testId="director-error" />
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

      <section className="px-4">
        <h2 className="pb-2 text-[15px] font-semibold text-text">{S.director.hallazgos}</h2>
        {hallazgos.length === 0 ? (
          <p className="text-[13px] text-muted">{S.director.hallazgosVacio}</p>
        ) : (
          <Card className="divide-y divide-line2 p-0">
            {hallazgos.slice(0, 12).map((h) => (
              <div key={h.clave} className="flex items-start gap-2 px-3 py-2.5" data-testid="director-hallazgo">
                <span className={cn("mt-0.5 shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-semibold", TONO[h.severidad])}>
                  {S.director.severidad[h.severidad] ?? h.severidad}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-semibold text-text">{h.titulo ?? h.sujeto}</p>
                  <p className="text-[12px] leading-snug text-text2">{h.detalle}</p>
                </div>
              </div>
            ))}
          </Card>
        )}
      </section>

      <section className="px-4">
        <h2 className="pb-2 text-[15px] font-semibold text-text">{S.director.decisiones}</h2>
        <Card className="divide-y divide-line2 p-0">
          {decisiones.ultimas.slice(0, 25).map((e) => (
            <div key={e.n} className="px-3 py-2.5" data-testid="director-decision">
              <p className="flex items-baseline justify-between gap-2 text-[12px] text-muted">
                <span className="min-w-0 truncate">
                  <span className="font-semibold text-text">{S.director.tipo[e.tipo] ?? e.tipo}</span> · {e.titulo ?? e.sujeto}
                </span>
                <span className="shrink-0 tabular-nums">{hora(e.at)}</span>
              </p>
              <p className="pt-0.5 text-[13px] leading-snug text-text2">{e.motivo}</p>
              <p className="pt-0.5 text-[11px] text-muted">
                #{e.n} · {S.director.autor[e.autor] ?? e.autor}
                {e.regla ? ` · ${e.regla}` : ""}
              </p>
            </div>
          ))}
        </Card>
      </section>
    </div>
  );
}
