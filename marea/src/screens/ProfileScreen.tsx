import * as React from "react";
import { ChevronRight, PieChart, Trophy, Wallet } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { S } from "@/lib/strings";
import { cn } from "@/lib/cn";
import { isPointsMode } from "@/lib/flags";
import { useApp } from "@/state/store";

type Theme = "dark" | "light";

function currentTheme(): Theme {
  const attr = document.documentElement.getAttribute("data-theme");
  return attr === "light" ? "light" : "dark";
}

/**
 * Perfil. Aquí viven las dos cosas que la marca no negocia: cómo ganamos
 * dinero y el juego responsable. Ambas dichas en llano, sin letra chica.
 */
export function ProfileScreen() {
  const [copiada, setCopiada] = React.useState(false);
  const { state, actions } = useApp();
  const [theme, setTheme] = React.useState<Theme>(currentTheme);
  const puntos = isPointsMode();

  const apply = React.useCallback((next: Theme) => {
    document.documentElement.setAttribute("data-theme", next);
    setTheme(next);
  }, []);

  return (
    <div data-testid="profile-screen" className="space-y-4 px-4 pb-6">
      <h1 className="pb-1 pt-5 font-display text-[24px] font-semibold text-text">
        {S.profile.title}
      </h1>

      {/* la cuenta es lo primero del perfil: es lo que hace que tu saldo
          y tus posiciones sigan aquí mañana */}
      <Card className="p-5" data-testid="profile-account">
        <p className="text-[12px] font-bold uppercase tracking-wide text-muted">
          {state.cuenta ? S.cuenta.sesionDe(state.cuenta.usuario) : S.cuenta.sinCuenta}
        </p>
        <div className="mt-3">
          {state.cuenta ? (
            <button
              type="button"
              data-testid="profile-logout"
              onClick={() => void actions.salir()}
              className="min-h-[44px] text-[14px] text-teal"
            >
              {S.cuenta.salir}
            </button>
          ) : (
            /* dos puertas, las dos a la vista. Volver es tan normal como
               empezar: con una sola entrada, quien ya tenía cuenta y perdió la
               sesión no tenía cómo saber que "Crear cuenta" abre una hoja donde
               además se puede entrar */
            <div className="flex gap-2">
              <Button
                data-testid="profile-login"
                onClick={() => actions.abrirCuenta(true, "registro")}
                className="flex-1"
              >
                {S.cuenta.sinCuentaCta}
              </Button>
              <Button
                variant="secondary"
                data-testid="profile-entrar"
                onClick={() => actions.abrirCuenta(true, "entrar")}
                className="flex-1"
              >
                {S.cuenta.entrarCta}
              </Button>
            </div>
          )}
        </div>
      </Card>

      {/* Cartera y Tabla salieron de la barra inferior al bajar a cuatro
          destinos. Salir de la barra no puede significar desaparecer: viven
          aquí, que es donde se busca lo que se usa de vez en cuando */}
      <Card className="p-2" data-testid="profile-destinos">
        <p className="px-3 pb-1 pt-2 text-[12px] font-bold uppercase tracking-wide text-muted">
          {S.profile.destinos}
        </p>
        {(
          [
            puntos
              ? { id: "tabla" as const, label: S.tabla.title, Icon: Trophy }
              : { id: "wallet" as const, label: S.wallet.title, Icon: Wallet },
            { id: "portfolio" as const, label: S.portfolio.title, Icon: PieChart },
          ] as const
        ).map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            data-testid={`profile-ir-${id}`}
            onClick={() => actions.setTab(id)}
            className="flex min-h-touch w-full items-center gap-3 rounded-[12px] px-3 text-left text-[15px] font-medium text-text hover:bg-panel2"
          >
            <Icon aria-hidden className="h-[18px] w-[18px] text-teal" strokeWidth={2.2} />
            {label}
            <ChevronRight aria-hidden className="ml-auto h-4 w-4 text-muted" />
          </button>
        ))}
      </Card>

      {/* la tarjeta: una racha contada con palabras no se comparte, una imagen
          sí. Sólo sale con cuenta, porque sin cuenta no hay nada que contar */}
      {state.cuenta ? (
        <Card className="mt-3 p-5" data-testid="profile-logro">
          <p className="text-[12px] font-bold uppercase tracking-wide text-muted">
            {S.logro.titulo}
          </p>
          <p className="mt-1.5 text-[14px] leading-relaxed text-text2">
            {S.logro.cuerpo}
          </p>
          <button
            type="button"
            data-testid="profile-compartir-logro"
            onClick={() => void compartirLogro(state.cuenta!.usuario, setCopiada)}
            className="mt-3 min-h-[44px] text-[14px] font-semibold text-teal"
          >
            {copiada ? S.logro.copiada : S.logro.cta}
          </button>
        </Card>
      ) : null}

      <Card className="p-5">
        <p className="text-[12px] font-bold uppercase tracking-wide text-muted">
          {S.profile.theme}
        </p>
        <div className="mt-3 flex gap-2">
          {(["dark", "light"] as Theme[]).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={theme === option}
              onClick={() => apply(option)}
              className={cn(
                "min-h-touch flex-1 rounded-pill border text-[15px] transition-colors",
                theme === option
                  ? "border-teal bg-teal-soft font-bold text-teal"
                  : "border-line2 font-medium text-text2",
              )}
            >
              {option === "dark" ? S.profile.themeDark : S.profile.themeLight}
            </button>
          ))}
        </div>
      </Card>

      <Card className="p-5">
        <p className="text-[12px] font-bold uppercase tracking-wide text-muted">
          {S.profile.honesty}
        </p>
        <p className="mt-2 text-[14px] leading-relaxed text-text2">
          {S.profile.honestyBody}
        </p>
      </Card>

      <Card className="p-5">
        <p className="text-[12px] font-bold uppercase tracking-wide text-muted">
          {S.profile.responsible}
        </p>
        <p className="mt-2 text-[14px] leading-relaxed text-text2">
          {S.profile.responsibleBody}
        </p>
        <Button variant="secondary" size="lg" className="mt-4">
          {S.profile.pause}
        </Button>
      </Card>

      <p className="pt-2 text-center text-[12px] text-muted">
        {S.profile.version} 0.1.0
      </p>
    </div>
  );
}

/**
 * Comparte la tarjeta propia. Va la liga a `/logro/<usuario>`, que lleva la
 * imagen en sus etiquetas de vista previa — mandar el PNG suelto perdería el
 * título y el contexto.
 *
 * Sólo datos propios: el nombre que el usuario eligió y su precisión. Quién
 * apostó qué no sale de aquí (R-058).
 */
async function compartirLogro(usuario: string, avisar: (v: boolean) => void) {
  const enlace = `${globalThis.location?.origin ?? ""}/logro/${encodeURIComponent(usuario)}`;
  try {
    const nav = globalThis.navigator as Navigator & {
      share?: (d: { title: string; text: string; url: string }) => Promise<void>;
    };
    if (nav?.share) {
      await nav.share({ title: S.logro.titulo, text: S.logro.texto, url: enlace });
      return;
    }
    await nav.clipboard?.writeText(`${S.logro.texto}\n${enlace}`);
    avisar(true);
    setTimeout(() => avisar(false), 2_000);
  } catch {
    /* si cancela la hoja nativa no pasa nada */
  }
}
