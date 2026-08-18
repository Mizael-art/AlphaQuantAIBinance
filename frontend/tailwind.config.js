/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Dark institutional trading terminal (seção 60): preto/grafite/
        // branco/cinza com acentos teal/ciano; verde/vermelho só para estados.
        base: {
          950: "#0a0b0d",
          900: "#111317",
          800: "#181b20",
          700: "#22262c",
          600: "#2e333b",
        },
        ink: {
          100: "#f4f5f6",
          300: "#b8bec6",
          500: "#7c848f",
        },
        accent: {
          teal: "#2dd4bf",
          cyan: "#22d3ee",
        },
        state: {
          bullish: "#22c55e",
          bearish: "#ef4444",
          warn: "#eab308",
        },
      },
    },
  },
  plugins: [],
};
