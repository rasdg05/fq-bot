import * as React from "react";
import { MarketCard } from "@/components/MarketCard";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/StateViews";
import { S } from "@/lib/strings";
import { useApp } from "@/state/store";
import { estadoVivo, mercadosVivos } from "@/domain/live";

/**
 * Ahora. Un solo trabajo: lo que se decide hoy.
 *
 * Dos grupos con nombres distintos porque son cosas distintas: `En juego` es
 * un evento que ya arrancó y `Se define pronto` es un mercado que está por
 * cerrar. Llamar LIVE a los dos sería inflar el único badge que la app usa
 * para decir urgencia de verdad.
 */
export function LiveScreen() {
  const { state, actions } = useApp();
  const { markets } = state;

  React.useEffect(() => {
    if (markets.status === "loading") void actions.loadMarkets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const todos = markets.status === "data" ? markets.data : [];
  const vivos = React.useMemo(() => mercadosVivos(todos), [todos]);
  const enJuego = vivos.filter((m) => estadoVivo(m) === "en_juego");
  const porCerrar = vivos.filter((m) => estadoVivo(m) === "por_cerrar");

  if (markets.status === "loading") {
    return (
      <div className="pt-4">
        <ListSkeleton rows={3} />
      </div>
    );
  }

  if (markets.status === "error") {
    return (
      <div className="pt-6">
        <ErrorState error={markets.error} onRetry={() => void actions.loadMarkets()} />
      </div>
    );
  }

  return (
    <div data-testid="live-screen" className="pb-6">
      <div className="px-4 pb-2 pt-5">
        <h1 className="font-display text-[24px] font-semibold leading-tight text-text">
          {S.live.title}
        </h1>
        <p className="pt-0.5 text-[13px] text-text2">{S.live.subtitle}</p>
      </div>

      {vivos.length === 0 ? (
        <div className="pt-2">
          <EmptyState
            title={S.live.empty}
            body={S.live.emptyBody}
            ctaLabel={S.live.emptyCta}
            onCta={() => actions.setTab("markets")}
            testId="live-empty"
          />
        </div>
      ) : (
        <>
          <Grupo titulo={S.live.enJuego} mercados={enJuego} testId="live-en-juego" />
          <Grupo titulo={S.live.porCerrar} mercados={porCerrar} testId="live-por-cerrar" />
        </>
      )}
    </div>
  );
}

function Grupo({
  titulo,
  mercados,
  testId,
}: {
  titulo: string;
  mercados: import("@/domain/types").Market[];
  testId: string;
}) {
  const { actions } = useApp();
  if (mercados.length === 0) return null;
  return (
    <section data-testid={testId} className="pt-2">
      <h2 className="px-4 pb-1.5 text-[12px] font-bold uppercase tracking-wide text-text2">
        {titulo}
      </h2>
      <div className="space-y-2 px-4">
        {mercados.map((market) => (
          <MarketCard key={market.id} market={market} onOpen={actions.openMarket} />
        ))}
      </div>
    </section>
  );
}
