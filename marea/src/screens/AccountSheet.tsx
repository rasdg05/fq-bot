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
 *
 * Al crear la cuenta se entrega **una sola vez** el código de recuperación, y
 * la hoja no se cierra hasta que el usuario dice que ya lo guardó. Es lo único
 * que le devuelve la cuenta si olvida su contraseña, y nosotros no lo tenemos.
 */

type Modo = "registro" | "entrar" | "recuperar";

const campo =
  "mt-1 h-12 w-full rounded-card border border-line2 bg-panel px-3 text-[16px] text-text outline-none focus:border-teal";

export function AccountSheet() {
  const { state, actions } = useApp();
  const [modo, setModo] = React.useState<Modo>(state.cuentaModo);
  const [usuario, setUsuario] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [codigo, setCodigo] = React.useState("");
  const [copiado, setCopiado] = React.useState(false);

  // quien abre por "Entrar" tiene que caer en Entrar. El modo se re-siembra en
  // cada apertura y no en cada render: dentro de la hoja el toggle manda, y un
  // valor controlado desde fuera lo dejaría clavado
  React.useEffect(() => {
    if (state.cuentaAbierta) setModo(state.cuentaModo);
  }, [state.cuentaAbierta, state.cuentaModo]);

  const limpiar = () => {
    setUsuario("");
    setPassword("");
    setCodigo("");
  };

  const enviar = async (evento: React.FormEvent) => {
    evento.preventDefault();
    const datos = { usuario: usuario.trim(), password };
    const ok =
      modo === "registro"
        ? await actions.registrar(datos)
        : modo === "entrar"
          ? await actions.entrar(datos)
          : await actions.recuperarCuenta({ ...datos, codigo });
    if (ok) limpiar();
  };

  const puedeEnviar =
    usuario.trim().length >= 3 &&
    password.length >= 8 &&
    (modo !== "recuperar" || codigo.trim().length >= 8);

  const titulo =
    state.codigoRecuperacion !== null
      ? S.cuenta.codigoTitulo
      : modo === "registro"
        ? S.cuenta.crearTitulo
        : modo === "entrar"
          ? S.cuenta.entrarTitulo
          : S.cuenta.recuperarTitulo;

  return (
    <Sheet
      open={state.cuentaAbierta}
      onOpenChange={(abierta) => actions.abrirCuenta(abierta)}
      title={titulo}
    >
      {state.codigoRecuperacion !== null ? (
        <div data-testid="account-code">
          <p className="text-[14px] leading-relaxed text-text2">
            {S.cuenta.codigoCuerpo}
          </p>
          <p
            data-testid="account-code-value"
            className="mt-4 rounded-card border border-teal bg-panel px-4 py-4 text-center font-mono text-[20px] font-bold tracking-wide text-text"
          >
            {state.codigoRecuperacion}
          </p>
          <button
            type="button"
            data-testid="account-code-copy"
            onClick={() => {
              void navigator.clipboard
                ?.writeText(state.codigoRecuperacion ?? "")
                .then(() => setCopiado(true))
                .catch(() => setCopiado(false));
            }}
            className="mt-3 min-h-[44px] w-full text-[14px] text-teal"
          >
            {copiado ? S.cuenta.codigoCopiado : S.cuenta.codigoCopiar}
          </button>
          <Button
            size="lg"
            data-testid="account-code-done"
            onClick={() => actions.codigoGuardado()}
          >
            {S.cuenta.codigoListo}
          </Button>
        </div>
      ) : (
        <div data-testid="account-sheet">
          <p className="text-[14px] leading-relaxed text-text2">
            {modo === "registro"
              ? S.cuenta.crearCuerpo
              : modo === "entrar"
                ? S.cuenta.entrarCuerpo
                : S.cuenta.recuperarCuerpo}
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
                className={campo}
                placeholder={
                  modo === "entrar"
                    ? S.cuenta.usuarioPlaceholderEntrar
                    : S.cuenta.usuarioPlaceholder
                }
              />
            </label>

            {modo === "recuperar" ? (
              <label className="block">
                <span className="text-[12px] uppercase tracking-wide text-muted">
                  {S.cuenta.codigo}
                </span>
                <input
                  data-testid="account-recovery-code"
                  value={codigo}
                  onChange={(evento) => setCodigo(evento.target.value)}
                  autoCapitalize="characters"
                  spellCheck={false}
                  className={`${campo} font-mono`}
                  placeholder={S.cuenta.codigoPlaceholder}
                />
              </label>
            ) : null}

            <label className="block">
              <span className="text-[12px] uppercase tracking-wide text-muted">
                {modo === "recuperar" ? S.cuenta.passwordNueva : S.cuenta.password}
              </span>
              <input
                data-testid="account-pass"
                type="password"
                value={password}
                onChange={(evento) => setPassword(evento.target.value)}
                autoComplete={modo === "entrar" ? "current-password" : "new-password"}
                className={campo}
                placeholder={
                  modo === "entrar"
                    ? S.cuenta.passwordPlaceholderEntrar
                    : S.cuenta.passwordPlaceholder
                }
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
                  : modo === "entrar"
                    ? S.cuenta.entrarCta
                    : S.cuenta.recuperarCta}
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

          {/* quien olvidó su contraseña no puede quedarse fuera para siempre */}
          {modo !== "recuperar" ? (
            <button
              type="button"
              data-testid="account-forgot"
              onClick={() => setModo("recuperar")}
              className="min-h-[44px] w-full text-[13px] text-muted"
            >
              {S.cuenta.olvide}
            </button>
          ) : null}
        </div>
      )}
    </Sheet>
  );
}
