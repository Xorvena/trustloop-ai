import type { Config } from "tailwindcss";

// Theme colours are CSS variables (see globals.css), so every class works in both light and dark mode.
const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;
const scale = (prefix: string, steps: number[]) => Object.fromEntries(steps.map((n) => [n, v(`${prefix}-${n}`)]));

const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: scale("navy", [950, 900, 850, 800, 700, 600]),   // surfaces and borders (grays)
        slate: scale("slate", [100, 200, 300, 400, 500, 600]), // text grays
        violet: scale("accent", [300, 400, 500, 600, 700]),    // accent; key name kept so existing classes keep working
        strong: v("strong"),                                   // headings and key figures
        inverse: v("inverse"),                                 // text on a "strong" background (primary button)
        ok: v("ok"), warn: v("warn"), bad: v("bad"),
      },
      fontFamily: { sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"] },
      boxShadow: { card: "var(--shadow-card)" },
    },
  },
  plugins: [],
};
export default config; 