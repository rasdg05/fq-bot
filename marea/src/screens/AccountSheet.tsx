import * as React from "react";
import { Sheet } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { S } from "@/lib/strings";
import { useApp } from "@/state/store";

/**
 * Cuenta. Aparece cuando alguien quiere apostar y todavía no tiene dónde
 * guardarlo — nunca antes: explorar el catálogo entero no pide nada (R-002).
 *
 * Dos campos y un tap. Sin correo obligatorio, sin confirmación por mail, sin
 * esperar nada: cada paso que agregas aquí es gente que no vuelve.
 */
export function AccountSheet() {
  const { state, actions } = useApp();
  const [modo, setModo] = React.useState<"registro" | "entrar">("registro");
  const [usuario, setUsuario] = React.useState("");
  const [password, setPassword] = React.useState("");

  const enviar = async (evento: React.FormEvent) => {
    evento.preventDefault();
    const datos = { usuario: usuario.trim(), password };
    const ok =
      modo === "registro" ? await actions.registrar(datos) : await actions.entrar(datos);
    if (ok) {
      setUsuario("");
      setPassword("");
    }
  };

  const puedeEnviar = usuario.trim().length >= 3 && password.length >= 8;

  return (
    <Sheet
      open={state.cuentaAbierta}
      onOpenChange={(abierta) => actions.abrirCuenta(abierta)}
      title={modo === "registro" ? S.cuenta.crearTitulo : S.cuenta.entrarTitulo}
    >
      <div data-testid="account-sheet">
      <p className="text-[14px] leading-relaxed text-text2">
        {modo === "registro" ? S.cuenta.crearCuerpo : S.cuenta.entrarCuerpo}
      </p>

      <form className="mt-4 space-y-3" onSubmit={enviar}>
        <label className="block">
          <span className="text-[12px] uppercase tracking-wide text-muted">
            {S.cuenta.usuario}
          </span>
          <input
            data-testid="account-user"
            value={usuario}
            onChange={(evento) => setUsuario(evento.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            className="mt-1 h-12 w-full rounded-card border border-line2 bg-panel px-3 text-[16px] text-text outline-none focus:border-teal"
            placeholder={S.cuenta.usuarioPlaceholder}
          />
        </label>

        <label className="block">
          <span className="text-[12px] uppercase tracking-wide text-muted">
            {S.cuenta.password}
          </span>
          <input
            data-testid="account-pass"
            type="password"
            value={password}
            onChange={(evento) => setPassword(evento.target.value)}
            autoComplete={modo === "registro" ? "new-password" : "current-password"}
            className="mt-1 h-12 w-full rounded-card border border-line2 bg-panel px-3 text-[16px] text-text outline-none focus:border-teal"
            placeholder={S.cuenta.passwordPlaceholder}
          />
        </label>

        {/* el error del servidor ya viene accionable y en español (R-008) */}
        {state.cuentaError ? (
          <p data-testid="account-error" className="text-[13px] text-[color:var(--dn)]">
            {state.cuentaError}
          </p>
        ) : null}

        <Button
          type="submit"
          size="lg"
          data-testid="account-submit"
          disabled={!puedeEnviar || state.cuentaBusy}
        >
          {state.cuentaBusy
            ? S.cuenta.enviando
            : modo === "registro"
              ? S.cuenta.crearCta
              : S.cuenta.entrarCta}
        </Button>
      </form>

      <button
          type="button"
          data-testid="account-toggle"
        onClick={() => setModo(modo === "registro" ? "entrar" : "registro")}
        className="mt-3 min-h-[44px] w-full text-[14px] text-teal"
      >
        {modo === "registro" ? S.cuenta.yaTengo : S.cuenta.noTengo}
        </button>
      </div>
    </Sheet>
  );
}
