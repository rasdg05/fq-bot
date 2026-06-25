/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#080a0e',
        panel: '#11151c',
        panel2: '#161b24',
        hairline: '#222a35',
        ink: '#eef1f4',
        muted: '#9aa3b1',
        faint: '#5e6775',
        accent: '#19b88c',
        accent2: '#12a37f',
      },
      fontFamily: {
        sans: ['Inter', 'Helvetica Neue', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'ui-monospace', 'Menlo', 'Consolas', 'monospace'],
      },
      boxShadow: {
        glow: '0 8px 40px rgba(25,184,140,.22)',
      },
      maxWidth: {
        wrap: '760px',
      },
      keyframes: {
        glowPulse: {
          '0%, 100%': { opacity: '0.85', filter: 'drop-shadow(0 0 0 rgba(25,184,140,0))' },
          '50%': { opacity: '1', filter: 'drop-shadow(0 0 12px rgba(25,184,140,0.45))' },
        },
      },
      animation: {
        glowPulse: 'glowPulse 3.2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
