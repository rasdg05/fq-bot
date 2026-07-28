import * as React from "react";
import { Card } from "@/components/ui/card";
import { EmptyState, ListSkeleton } from "@/components/StateViews";
import { S } from "@/lib/strings";
import { formatStake } from "@/lib/units";
import { useApp } from "@/state/store";
import { cn } from "@/lib/cn";

/**
 * Tabla de posiciones. En un producto de predicción lo que se presume no es
 * cuánto apostaste sino **cuántas veces le atinaste**, así que la precisión y
 * la racha van al lado de los puntos.
 *
 * Se ve sin cuenta a propósito: es la prueba social que hace que alguien quiera
 * entrar, y explorar nunca pide nada (R-002).
 */

interface Fila {
  posicion: number;
  usuario: string;
  puntos: number;
  resueltas: number;
  aciertos: number;
  precision: number;
  racha: number;
}

export function TablaScreen() {
  const { state, adapters, actions } = useApp();
  const [datos, setDatos] = React.useState<{ filas: Fila[]; tuya?: Fila } | null>(null);
  const [error, setError] = React.useState(false);

  React.useEffect(() => {
    let vivo = true;
    const base = adapters.api ? "/api" : null;
    if (!base) {
      setDatos({ filas: [] });
      return;
    }
    fetch(`${base}/tabla`, { credentials: "include" })
      .then((respuesta) => respuesta.json())
      .then((cuerpo) => vivo && setDatos(cuerpo))
      .catch(() => vivo && setError(true));
    return () => {
      vivo = false;
    };
  }, [adapters.api]);

  if (!datos && !error) {
    return (
      <div className="pt-4">
        <ListSkeleton rows={4} />
      </div>
    );
  }

  const filas = datos?.filas ?? [];

  return (
    <div data-testid="tabla-screen" className="pb-6">
      <h1 className="px-4 pb-1 pt-5 font-display text-[24px] font-semibold text-text">
        {S.tabla.title}
      </h1>
      <p className="px-4 pb-3 text-[14px] text-text2">{S.tabla.subtitle}</p>

      {filas.length === 0 ? (
        <div className="pt-4">
          <EmptyState
            title={S.tabla.empty}
            body={S.tabla.emptyBody}
            ctaLabel={S.tabla.emptyCta}
            onCta={() => actions.setTab("markets")}
            testId="tabla-empty"
          />
        </div>
      ) : (
        <div className="space-y-2 px-4">
          {filas.map((fila) => {
            const esMia = state.cuenta?.usuario === fila.usuario;
            return (
              <Card
                key={fila.usuario}
                data-testid="tabla-row"
                className={cn("flex items-center gap-3 p-3", esMia && "border-teal")}
              >
                <span className="w-6 text-center font-mono text-[15px] font-bold tabular-nums text-muted">
                  {fila.posicion}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[15px] font-semibold text-text">
                    {fila.usuario}
                  </p>
                  <p className="mt-0.5 text-[12px] text-muted">
                    {/* la precisión va con su denominador: 2 de 3 dice más que 67 % */}
                    {S.tabla.precision} {Math.round(fila.precision * 100)}% ·{" "}
                    {fila.aciertos}/{fila.resueltas}
                    {fila.racha > 1 ? ` · ${S.tabla.racha} ${fila.racha}` : ""}
                  </p>
                </div>
                <span className="font-mono text-[15px] font-bold tabular-nums text-text">
                  {formatStake(fila.puntos)}
                </span>
              </Card>
            );
          })}
        </div>
      )}

      {datos?.tuya ? (
        <p className="px-4 pt-4 text-[13px] text-text2" data-testid="tabla-tuya">
          {S.tabla.tuPosicion(datos.tuya.posicion)}
        </p>
      ) : state.cuenta ? (
        <p className="px-4 pt-4 text-[13px] text-muted">{S.tabla.fueraDeTabla}</p>
      ) : null}
    </div>
  );
}
