import type { Wallet } from "@/domain/types";
import { appError } from "@/domain/errors";

/**
 * Puerto de wallet. Embebida primero (crear), conectar como camino secundario.
 * Sin seed phrase ni KYC en la superficie: la custodia se resuelve por debajo (R-002).
 */
export interface WalletAdapter {
  createEmbedded(): Promise<Wallet>;
  connectExternal(): Promise<Wallet>;
  getBalance(address: string): Promise<number>;
  /** Abre el camino de depósito. `kind` decide on-ramp o transferencia. */
  startDeposit(input: {
    kind: "onramp" | "transfer";
    address: string;
  }): Promise<{ reference: string; instructions: string }>;
}

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

interface MockOptions {
  failCreate?: boolean;
  failConnect?: boolean;
  failBalance?: boolean;
  providerDown?: boolean;
  initialBalance?: number;
  latencyMs?: number;
}

export function createMockWalletAdapter(options: MockOptions = {}): WalletAdapter {
  const latency = options.latencyMs ?? 260;
  return {
    async createEmbedded() {
      await delay(latency);
      if (options.failCreate) throw appError("E_WALLET_CREATE_FAILED");
      return {
        address: "0x7Ac4e1f0B2d93C5a4E8b19Fd0c6A2b31D5e70F84",
        balance: options.initialBalance ?? 0,
        chain: "Polygon",
        origin: "embedded",
      };
    },
    async connectExternal() {
      await delay(latency);
      if (options.failConnect) throw appError("E_WALLET_CONNECT_FAILED");
      return {
        address: "0x19Bd3C77aE5410fD8b2c04E9a7135Fc6D2801Ee3",
        balance: options.initialBalance ?? 0,
        chain: "Polygon",
        origin: "connected",
      };
    },
    async getBalance(address) {
      await delay(latency / 3);
      if (options.failBalance) throw appError("E_BALANCE_FETCH_FAILED", { address });
      return options.initialBalance ?? 0;
    },
    async startDeposit({ kind, address }) {
      await delay(latency / 2);
      if (kind === "onramp" && options.providerDown) {
        throw appError("E_DEPOSIT_PROVIDER_UNAVAILABLE");
      }
      return {
        reference: `dep-${kind}-${address.slice(2, 8).toLowerCase()}`,
        instructions:
          kind === "onramp"
            ? "Te vamos a llevar con nuestro proveedor de pago para comprar USDC."
            : "Envía USDC a tu dirección de Marea en la red Polygon.",
      };
    },
  };
}

export const walletAdapter: WalletAdapter = createMockWalletAdapter();
