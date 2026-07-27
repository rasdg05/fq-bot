import { Sheet } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { S } from "@/lib/strings";
import { usd } from "@/lib/format";
import { useApp } from "@/state/store";

/**
 * Confirmación post-operación. Dos salidas explícitas: portafolio o seguir
 * explorando. Nunca un callejón sin salida.
 */
export function PostTradeSheet() {
  const { state, actions } = useApp();
  const post = state.postTrade;

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
          <p className="text-[15px] leading-relaxed text-text2">
            {S.postTrade.body(
              post.side === "si" ? S.market.yes : S.market.no,
              usd(post.size),
              post.title,
            )}
          </p>
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
