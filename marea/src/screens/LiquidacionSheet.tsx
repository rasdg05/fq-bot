import * as React from "react";
import { Sheet } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { S } from "@/lib/strings";
import { formatStake } from "@/lib/units";
import { useApp } from "@/state/store";
import type { Position } from "@/domain/types";

const VISTAS_KEY = "marea.liquidaciones.vistas";

function leerVistas(): string[] {
  try {
    const crudo = globalThis.localStorage?.getItem(VISTAS_KEY);
    return crudo ? (JSON.parse(crudo) as string[]) : [];
  } catch {
    return [];
  }
}

function guardarVistas(ids: string[]) {
  try {
    globalThis.localStorage?.setItem(VISTAS_KEY, JSON.stringify(ids.slice(-200)));
  } catch {
    /* sin almacenamiento el aviso se repite; peor sería no avisar */
  }
}

/**
 * El momento de cobrar.
 *
 * Un mercado que resuelve a favor de alguien no sirve de nada si esa persona
 * no se entera: el pago ya estaba acreditado, pero había que ir al portafolio
 * a descubrirlo. Aquí se lo decimos al volver a abrir, con la lectura del
 * oráculo que lo justifica — cobrar no es un acto de fe, y esa evidencia ya
 * vivía en `SettlementState` sin que nadie la viera (R-040).
 *
 * Sólo avisa una vez por posición: un aviso que vuelve cada vez que abres la
 * app deja de ser un aviso y pasa a ser ruido.
 */
export function LiquidacionSheet() {
  const { state, actions } = useApp();
  const [vistas, setVistas] = React.useState<string[]>(() => leerVistas());
  const [cerrado, setCerrado] = React.useState(false);

  const cobradas = React.useMemo(() => {
    if (state.positions.status !== "data") return [] as Position[];
    return state.positions.data.filter(
      (p) => p.payout !== undefined && p.payout > 0 && !vistas.includes(p.id),
    );
  }, [state.positions, vistas]);

  const abierto = cobradas.length > 0 && !cerrado;
  const total = cobradas.reduce((s, p) => s + (p.payout ?? 0), 0);

  const marcarVistas = React.useCallback(() => {
    const ids = [...vistas, ...cobradas.map((p) => p.id)];
    guardarVistas(ids);
    setVistas(ids);
    setCerrado(true);
  }, [vistas, cobradas]);

  return (
    <Sheet
      open={abierto}
      onOpenChange={(open) => {
        if (!open) marcarVistas();
      }}
      title={S.liquidado.title}
    >
      <div data-testid="liquidacion-aviso" className="space-y-4 pb-2">
        <div className="rounded-card border border-teal bg-teal-soft px-4 py-4 text-center">
          <p className="text-[12px] font-bold uppercase tracking-wide text-teal">
            {S.liquidado.total}
          </p>
          <p
            data-testid="liquidacion-total"
            data-total={total}
            className="mt-1 font-display text-[40px] font-semibold leading-none tabular-nums text-text"
          >
            {formatStake(total)}
          </p>
        </div>

        <p className="text-[14px] leading-relaxed text-text2">
          {cobradas.length === 1
            ? S.liquidado.unaSola(cobradas[0].marketTitle ?? cobradas[0].market_id)
            : S.liquidado.varias(cobradas.length)}
        </p>

        {/* la lectura que lo justifica: el pago no aparece de la nada */}
        {cobradas.map((p) =>
          p.evidence ? (
            <div
              key={p.id}
              data-testid="liquidacion-evidencia"
              className="rounded-card border border-line2 bg-panel px-4 py-3"
            >
              <p className="text-[12px] font-bold uppercase tracking-wide text-muted">
                {S.liquidado.comoSeSupo}
              </p>
              <p className="mt-1 text-[13px] leading-relaxed text-text2">
                {p.evidence}
              </p>
            </div>
          ) : null,
        )}

        <Button
          size="lg"
          data-testid="liquidacion-portafolio"
          onClick={() => {
            marcarVistas();
            actions.setTab("portfolio");
          }}
        >
          {S.liquidado.ver}
        </Button>
        <Button
          size="lg"
          variant="secondary"
          data-testid="liquidacion-cerrar"
          onClick={marcarVistas}
        >
          {S.liquidado.cerrar}
        </Button>
      </div>
    </Sheet>
  );
}
