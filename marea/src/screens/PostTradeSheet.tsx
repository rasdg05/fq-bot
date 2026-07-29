import * as React from "react";
import { Sheet } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { S } from "@/lib/strings";
import { formatStake } from "@/lib/units";
import { pct } from "@/lib/format";
import { formatMultiplier } from "@/domain/parimutuel";
import { useApp } from "@/state/store";

/**
 * Confirmación post-operación.
 *
 * Es uno de los dos únicos momentos con carga emocional del producto, y hasta
 * ahora era un cambio de número: nadie le cuenta a un amigo un cambio de
 * número. La cifra protagonista es **lo que cobra si acierta**, porque es la
 * promesa que el sistema tiene que cumplir después (I3).
 *
 * Dos salidas explícitas: portafolio o seguir explorando. Nunca un callejón
 * sin salida.
 */
export function PostTradeSheet() {
  const { state, actions } = useApp();
  const post = state.postTrade;
  const [compartido, setCompartido] = React.useState(false);

  const lado =
    post?.sideLabel ?? (post?.side === "si" ? S.market.yes : S.market.no);

  return (
    <Sheet
      open={Boolean(post)}
      onOpenChange={(open) => {
        if (!open) actions.dismissPostTrade();
      }}
      title={S.postTrade.title}
    >
      <div data-testid="post-trade" className="space-y-4 pb-2">
        {post ? (
          <>
            {/* lo que cobra si acierta, como número rey */}
            <div
              data-testid="post-trade-cobras"
              className="rounded-card border border-teal bg-teal-soft px-4 py-4 text-center"
            >
              <p className="text-[12px] font-bold uppercase tracking-wide text-teal">
                {S.postTrade.cobras}
              </p>
              <p
                data-role="payout"
                data-payout={post.toWin}
                className="mt-1 font-display text-[40px] font-semibold leading-none tabular-nums text-text"
              >
                {formatStake(post.toWin)}
              </p>
              <p className="mt-1.5 font-mono text-[13px] font-semibold text-text2">
                {formatMultiplier(post.multiplier)}
              </p>
            </div>

            <div className="flex items-center justify-between text-[14px]">
              <span className="font-semibold text-text">
                {S.postTrade.entraste(lado, pct(post.probability))}
              </span>
              <span className="tabular-nums text-text2">
                {S.postTrade.pusiste(formatStake(post.size))}
              </span>
            </div>

            <p className="text-[13px] leading-relaxed text-muted">
              {S.postTrade.body(lado, formatStake(post.size), post.title)}
            </p>

            {/* el punto natural para invitar a compartir: sólo lo propio, nunca
                datos de nadie más (R-058) */}
            <button
              type="button"
              data-testid="post-trade-share"
              onClick={() => void compartir(post, lado, setCompartido)}
              className="min-h-touch w-full rounded-card border border-line2 bg-panel text-[14px] font-semibold text-teal"
            >
              {compartido ? S.postTrade.compartido : S.postTrade.compartir}
            </button>
          </>
        ) : null}
        <Button
          size="lg"
          data-testid="post-trade-portfolio"
          onClick={() => {
            actions.dismissPostTrade();
            actions.closeMarket();
            actions.setTab("portfolio");
            void actions.loadPositions();
          }}
        >
          {S.postTrade.goPortfolio}
        </Button>
        <Button
          size="lg"
          variant="secondary"
          data-testid="post-trade-explore"
          onClick={() => {
            actions.dismissPostTrade();
            actions.closeMarket();
          }}
        >
          {S.postTrade.keepExploring}
        </Button>
      </div>
    </Sheet>
  );
}

/**
 * Comparte la apuesta propia. Va la pregunta y el lado elegido — nunca cuánto
 * puso ni el saldo, que son datos que no salen de aquí (R-020, R-058).
 */
async function compartir(
  post: { title: string; marketId: string },
  lado: string,
  avisar: (v: boolean) => void,
) {
  const enlace = `${globalThis.location?.origin ?? ""}/m/${encodeURIComponent(post.marketId)}`;
  const texto = S.postTrade.compartirTexto(lado, post.title);
  try {
    const nav = globalThis.navigator as Navigator & {
      share?: (d: { title: string; text: string; url: string }) => Promise<void>;
    };
    if (nav?.share) {
      await nav.share({ title: post.title, text: texto, url: enlace });
      return;
    }
    await nav.clipboard?.writeText(`${texto}\n${enlace}`);
    avisar(true);
    setTimeout(() => avisar(false), 2_000);
  } catch {
    /* si cancela la hoja nativa no pasa nada */
  }
}
