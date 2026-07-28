import * as React from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { S } from "@/lib/strings";
import { cn } from "@/lib/cn";
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
  const { state, actions } = useApp();
  const [theme, setTheme] = React.useState<Theme>(currentTheme);

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
            <button
              type="button"
              data-testid="profile-login"
              onClick={() => actions.abrirCuenta(true)}
              className="min-h-[44px] text-[14px] text-teal"
            >
              {S.cuenta.sinCuentaCta}
            </button>
          )}
        </div>
      </Card>

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
