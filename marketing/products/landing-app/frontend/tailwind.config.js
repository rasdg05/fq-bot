/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Marca unificada FQ: obsidiana + oro + Solana (violeta→menta).
        bg: '#050705',
        panel: '#0e1211',
        panel2: '#141a18',
        hairline: '#2a2b26',
        ink: '#eef1f4',
        muted: '#9aa3b1',
        faint: '#5e6775',
        accent: '#d4af37', // oro
        accent2: '#c8a12f', // oro oscuro
        solV: '#9945FF', // Solana violeta
        solM: '#14F195', // Solana menta
      },
      fontFamily: {
        sans: ['Inter', 'Helvetica Neue', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'ui-monospace', 'Menlo', 'Consolas', 'monospace'],
      },
      boxShadow: {
        glow: '0 8px 40px rgba(212,175,55,.22)',
      },
      maxWidth: {
        wrap: '760px',
      },
      keyframes: {
        glowPulse: {
          '0%, 100%': { opacity: '0.85', filter: 'drop-shadow(0 0 0 rgba(212,175,55,0))' },
          '50%': { opacity: '1', filter: 'drop-shadow(0 0 12px rgba(212,175,55,0.45))' },
        },
      },
      animation: {
        glowPulse: 'glowPulse 3.2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
