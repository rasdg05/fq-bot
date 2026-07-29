import type { Wallet } from "@/domain/types";
import { appError } from "@/domain/errors";
import type { WalletAdapter } from "@/adapters/walletAdapter";

/**
 * Wallet conectada por el usuario, vía EIP-1193 — el estándar que hablan
 * MetaMask, Rabby, Trust y el navegador de casi cualquier wallet móvil.
 *
 * Esta es la mitad del camino de dinero que **no depende de nadie**: no hay
 * contrato que firmar ni llave de proveedor que esperar, porque la custodia es
 * del usuario y nosotros nunca vemos su llave. La wallet embebida (custodia
 * delegada a un proveedor MPC) sigue siendo otra cosa y sigue esperando su
 * cuenta.
 *
 * Lo que este adapter **no** hace: crear wallets. Si no hay proveedor inyectado
 * lo dice y no finge (R-022).
 */

/** El mínimo de EIP-1193 que necesitamos. */
export interface Eip1193Provider {
  request(args: { method: string; params?: unknown[] }): Promise<unknown>;
  on?(event: string, handler: (...args: unknown[]) => void): void;
}

/** Polygon, que es donde vive el USDC que usamos. */
const CADENA = { id: "0x89", nombre: "Polygon" };

const USDC_POLYGON = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359";
const DECIMALES_USDC = 6;

function proveedorInyectado(): Eip1193Provider | undefined {
  return (globalThis as { ethereum?: Eip1193Provider }).ethereum;
}

export function hasInjectedWallet(): boolean {
  return proveedorInyectado() !== undefined;
}

/** `balanceOf(address)` codificado a mano: no hace falta traer una librería. */
function balanceOfData(address: string): string {
  return `0x70a08231${address.replace(/^0x/, "").toLowerCase().padStart(64, "0")}`;
}

export function createInjectedWalletAdapter(
  getProvider: () => Eip1193Provider | undefined = proveedorInyectado,
): WalletAdapter {
  async function pedir<T>(method: string, params?: unknown[]): Promise<T> {
    const provider = getProvider();
    if (!provider) throw appError("E_WALLET_CONNECT_FAILED", { motivo: "sin_proveedor" });
    return (await provider.request({ method, params })) as T;
  }

  return {
    async createEmbedded(): Promise<Wallet> {
      // este camino necesita un proveedor de custodia; decirlo es más honesto
      // que devolver una wallet de mentira
      throw appError("E_WALLET_CREATE_FAILED", { motivo: "sin_proveedor_embebido" });
    },

    async connectExternal(): Promise<Wallet> {
      const cuentas = await pedir<string[]>("eth_requestAccounts");
      const address = cuentas?.[0];
      if (!address) throw appError("E_WALLET_CONNECT_FAILED", { motivo: "sin_cuenta" });

      // pedir la red correcta puede fallar sin que la conexión falle: el
      // usuario ya está conectado, sólo está en otra cadena
      try {
        await pedir("wallet_switchEthereumChain", [{ chainId: CADENA.id }]);
      } catch {
        /* se queda en su red; el depósito lo vuelve a pedir */
      }

      return {
        address,
        balance: await this.getBalance(address).catch(() => 0),
        chain: CADENA.nombre,
        origin: "connected",
      };
    },

    async getBalance(address: string): Promise<number> {
      try {
        const hex = await pedir<string>("eth_call", [
          { to: USDC_POLYGON, data: balanceOfData(address) },
          "latest",
        ]);
        if (!hex || hex === "0x") return 0;
        return Number(BigInt(hex)) / 10 ** DECIMALES_USDC;
      } catch (error) {
        throw appError("E_BALANCE_FETCH_FAILED", { address, cause: String(error) });
      }
    },

    async startDeposit({ kind, address }) {
      if (kind === "onramp") {
        // comprar con tarjeta exige proveedor de on-ramp contratado
        throw appError("E_DEPOSIT_PROVIDER_UNAVAILABLE");
      }
      return {
        reference: `dep-transfer-${address.slice(2, 8).toLowerCase()}`,
        instructions: `Envía USDC a tu dirección en la red ${CADENA.nombre}.`,
      };
    },
  };
}
