import * as React from "react";
import { AppHeader } from "@/components/AppHeader";
import { BottomTabs } from "@/components/BottomTabs";
import { HomeScreen } from "@/screens/HomeScreen";
import { SearchScreen } from "@/screens/SearchScreen";
import { PortfolioScreen } from "@/screens/PortfolioScreen";
import { WalletScreen } from "@/screens/WalletScreen";
import { ProfileScreen } from "@/screens/ProfileScreen";
import { MarketDetailScreen } from "@/screens/MarketDetailScreen";
import { DepositSheet } from "@/screens/DepositSheet";
import { PostTradeSheet } from "@/screens/PostTradeSheet";
import { AccountSheet } from "@/screens/AccountSheet";
import { OnboardingFlow } from "@/screens/OnboardingFlow";
import { AppProvider, useApp, type Adapters, type AppState } from "@/state/store";

function CurrentScreen() {
  const { state } = useApp();

  const openMarket = React.useMemo(() => {
    if (!state.openMarketId || state.markets.status !== "data") return null;
    return state.markets.data.find((m) => m.id === state.openMarketId) ?? null;
  }, [state.openMarketId, state.markets]);

  if (openMarket) return <MarketDetailScreen market={openMarket} />;

  switch (state.tab) {
    case "search":
      return <SearchScreen />;
    case "portfolio":
      return <PortfolioScreen />;
    case "wallet":
      return <WalletScreen />;
    case "profile":
      return <ProfileScreen />;
    case "markets":
    default:
      return <HomeScreen />;
  }
}

function Shell() {
  const { state } = useApp();
  const onboarding = !state.onboardingCompleted;

  return (
    <div className="min-h-full bg-bg">
      {/* el chrome se monta detrás del onboarding: al terminar, el feed ya está */}
      <AppHeader />
      <main
        className="mx-auto w-full max-w-[520px]"
        style={{ paddingBottom: "calc(72px + var(--safe-b))" }}
      >
        <CurrentScreen />
      </main>
      <BottomTabs />
      <DepositSheet />
      <PostTradeSheet />
      <AccountSheet />
      {onboarding ? <OnboardingFlow /> : null}
    </div>
  );
}

export function App({
  adapters,
  overrides,
}: {
  adapters?: Adapters;
  overrides?: Partial<AppState>;
}) {
  return (
    <AppProvider adapters={adapters} overrides={overrides}>
      <Shell />
    </AppProvider>
  );
}
