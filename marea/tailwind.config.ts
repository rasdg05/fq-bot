import type { Config } from "tailwindcss";

/**
 * Los colores NO se declaran aquí: viven en `src/styles/tokens.css` como custom
 * properties, y Tailwind sólo los referencia. Así el tema (claro/oscuro) es un
 * sistema real de tokens y no una inversión de clases (R-012).
 */
const config: Config = {
  // en un teléfono no hay puntero fino: sin esto, `hover:` se queda pegado
  // después del toque y una pill parece elegida cuando nadie la eligió
  future: { hoverOnlyWhenSupported: true },
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      screens: {
        // teléfonos angostos de verdad: el iPhone SE va a 320 px, y ahí la
        // fila de badges de la card envuelve. Por debajo de este ancho el
        // adorno estorba, y el adorno es lo primero que se va
        angosto: "360px",
      },
      colors: {
        bg: "var(--bg)",
        panel: "var(--panel)",
        panel2: "var(--panel2)",
        line: "var(--line)",
        line2: "var(--line2)",
        text: "var(--text)",
        text2: "var(--text2)",
        muted: "var(--muted)",
        teal: "var(--teal)",
        "teal-deep": "var(--teal-deep)",
        "teal-soft": "var(--teal-soft)",
        "teal-ink": "var(--teal-ink)",
        up: "var(--up)",
        dn: "var(--dn)",
        hot: "var(--hot)",
        live: "var(--live)",
        // pills de la tarjeta: anillo de foco, contorno del rival y su lavado
        "pill-ring": "var(--pill-ring)",
        "pill-line": "var(--pill-line)",
        "pill-wash": "var(--pill-wash)",
        "flash-up": "var(--flash-up)",
        "flash-dn": "var(--flash-dn)",
      },
      fontFamily: {
        display: "var(--font-display)",
        sans: "var(--font-sans)",
        mono: "var(--font-mono)",
      },
      fontSize: {
        // escala tipográfica: la probabilidad es el nodo dominante (R-004). En
        // el detalle manda por tamaño absoluto (`prob`); en la tarjeta manda
        // por tamaño **y peso** — `prob-pill` es el único nodo en 700
        prob: ["44px", { lineHeight: "1", letterSpacing: "-0.02em" }],
        "prob-lg": ["64px", { lineHeight: "1", letterSpacing: "-0.025em" }],
        "prob-sm": ["30px", { lineHeight: "1", letterSpacing: "-0.015em" }],
        "prob-pill": ["30px", { lineHeight: "32px", letterSpacing: "-0.025em" }],
        "prob-riv": ["20px", { lineHeight: "22px", letterSpacing: "-0.015em" }],
        "prob-row": ["20px", { lineHeight: "22px", letterSpacing: "-0.015em" }],
        mult: ["12px", { lineHeight: "13px", letterSpacing: "0.01em" }],
      },
      spacing: {
        // targets táctiles (R-010)
        touch: "44px",
        "touch-lg": "48px",
        "safe-b": "var(--safe-b)",
        "safe-t": "var(--safe-t)",
      },
      borderRadius: { card: "18px", sheet: "24px", pill: "999px" },
      boxShadow: {
        card: "0 1px 2px var(--shadow-1), 0 10px 30px var(--shadow-2)",
        sheet: "0 -8px 40px var(--shadow-2)",
      },
      keyframes: {
        shimmer: { "100%": { transform: "translateX(100%)" } },
        "sheet-in": {
          from: { transform: "translateY(100%)" },
          to: { transform: "translateY(0)" },
        },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        pulse_live: {
          "0%,100%": { opacity: "1" },
          "50%": { opacity: "0.4" },
        },
        // destello de actualización: entra rápido y se va solo. El fondo vuelve
        // a `transparent`, así que la pill no queda teñida si el timer falla
        "flash-up": {
          "0%,100%": { backgroundColor: "transparent" },
          "35%": { backgroundColor: "var(--flash-up)" },
        },
        "flash-dn": {
          "0%,100%": { backgroundColor: "transparent" },
          "35%": { backgroundColor: "var(--flash-dn)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.4s infinite",
        "sheet-in": "sheet-in .22s cubic-bezier(.22,1,.36,1)",
        "fade-in": "fade-in .2s ease-out",
        live: "pulse_live 2s ease-in-out infinite",
        "flash-up": "flash-up .2s ease-out 1",
        "flash-dn": "flash-dn .2s ease-out 1",
      },
    },
  },
  plugins: [],
};

export default config;
