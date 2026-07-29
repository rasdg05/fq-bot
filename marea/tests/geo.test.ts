import { describe, expect, it } from "vitest";
import {
  countryFromLocale,
  countryFromTimeZone,
  detectCountry,
} from "@/domain/geo";
import { eligibilityFor } from "@/domain/eligibility";
import {
  createInjectedWalletAdapter,
  type Eip1193Provider,
} from "@/adapters/wallet/injectedWallet";

describe("detección de país", () => {
  it("V35 infiere el país del dispositivo sin pedir permisos ni mandar nada afuera", () => {
    expect(countryFromTimeZone("America/Mexico_City")).toBe("MX");
    expect(countryFromTimeZone("America/Argentina/Cordoba")).toBe("AR");
    expect(countryFromTimeZone("America/Sao_Paulo")).toBe("BR");
    expect(countryFromTimeZone("America/Bogota")).toBe("CO");
    expect(countryFromTimeZone("America/Indiana/Indianapolis")).toBe("US");

    const guess = detectCountry({ timeZone: "America/Lima", locale: "en-US" });
    // la zona horaria manda: el idioma sólo dice cómo prefiere leer
    expect(guess).toEqual({
      country: "PE",
      source: "zona_horaria",
      signal: "America/Lima",
    });
  });

  it("V36 sin señal clara no adivina el país y deja explorar igual", () => {
    expect(countryFromLocale("es")).toBeUndefined();
    expect(countryFromLocale("es-MX")).toBe("MX");

    const guess = detectCountry({ timeZone: "Antarctica/Troll", locale: "no" });
    expect(guess.country).toBe("OTRO");
    expect(guess.source).toBe("desconocido");
    // explorar nunca depende del país (R-002)
    expect(eligibilityFor(guess.country).canExplore).toBe(true);
    expect(eligibilityFor(guess.country).canDeposit).toBe(false);
  });

  it("V37 el país inferido no abre permisos que la tabla legal no da", () => {
    // detectar México no vuelve a México elegible: eso lo decide la opinión
    // legal, no la zona horaria del teléfono
    const mx = eligibilityFor(detectCountry({ timeZone: "America/Mexico_City" }).country);
    expect(mx.status).toBe("pendiente");
    expect(mx.canDeposit).toBe(false);
    expect(eligibilityFor("US").status).toBe("bloqueado");
  });
});

describe("wallet conectada por el usuario", () => {
  function proveedorFalso(overrides: Partial<Record<string, unknown>> = {}) {
    const llamadas: string[] = [];
    const provider: Eip1193Provider = {
      async request({ method }) {
        llamadas.push(method);
        if (method in overrides) {
          const valor = overrides[method];
          if (valor instanceof Error) throw valor;
          return valor;
        }
        if (method === "eth_requestAccounts") return ["0xabc0000000000000000000000000000000000001"];
        // 12.5 USDC, con 6 decimales
        if (method === "eth_call") return "0xbebc20";
        return null;
      },
    };
    return { provider, llamadas };
  }

  it("V38 conecta una wallet real por EIP-1193 sin proveedor contratado", async () => {
    const { provider, llamadas } = proveedorFalso();
    const wallet = await createInjectedWalletAdapter(() => provider).connectExternal();

    expect(wallet.origin).toBe("connected");
    expect(wallet.address).toMatch(/^0x/);
    expect(wallet.balance).toBeCloseTo(12.5, 6);
    expect(llamadas).toContain("eth_requestAccounts");
  });

  it("V39 sin proveedor inyectado falla claro, no finge una wallet", async () => {
    const adapter = createInjectedWalletAdapter(() => undefined);
    await expect(adapter.connectExternal()).rejects.toMatchObject({
      code: "E_WALLET_CONNECT_FAILED",
    });
    // crear wallet embebida sí necesita proveedor de custodia (R-022)
    await expect(adapter.createEmbedded()).rejects.toMatchObject({
      code: "E_WALLET_CREATE_FAILED",
    });
  });

  it("estar en otra red no rompe la conexión", async () => {
    const { provider } = proveedorFalso({
      wallet_switchEthereumChain: new Error("usuario canceló"),
    });
    const wallet = await createInjectedWalletAdapter(() => provider).connectExternal();
    expect(wallet.address).toMatch(/^0x/);
  });
});
