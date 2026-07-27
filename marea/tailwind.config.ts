import type { Config } from "tailwindcss";

/**
 * Los colores NO se declaran aquí: viven en `src/styles/tokens.css` como custom
 * properties, y Tailwind sólo los referencia. Así el tema (claro/oscuro) es un
 * sistema real de tokens y no una inversión de clases (R-012).
 */
const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
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
      },
      fontFamily: {
        display: "var(--font-display)",
        sans: "var(--font-sans)",
        mono: "var(--font-mono)",
      },
      fontSize: {
        // escala tipográfica: la probabilidad (prob) es el nodo dominante (R-004)
        prob: ["44px", { lineHeight: "1", letterSpacing: "-0.02em" }],
        "prob-lg": ["64px", { lineHeight: "1", letterSpacing: "-0.025em" }],
        "prob-sm": ["30px", { lineHeight: "1", letterSpacing: "-0.015em" }],
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
          "50%": { opacity: "0.35" },
        },
      },
      animation: {
        shimmer: "shimmer 1.4s infinite",
        "sheet-in": "sheet-in .28s cubic-bezier(.22,1,.36,1)",
        "fade-in": "fade-in .2s ease-out",
        live: "pulse_live 1.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
