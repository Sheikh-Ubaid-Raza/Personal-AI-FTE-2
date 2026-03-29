import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Heagent Futuristic Healthcare palette
        heagent: {
          // Core brand
          cyan:    "#06B6D4",
          blue:    "#0EA5E9",
          purple:  "#7C3AED",
          teal:    "#0D9488",
          // Surfaces (dark)
          void:    "#050B18",
          deep:    "#0A1628",
          surface: "#0F2340",
          panel:   "#162944",
          border:  "#1E3A5F",
          // Status
          online:  "#10B981",
          offline: "#EF4444",
          warn:    "#F59E0B",
          info:    "#3B82F6",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      backgroundImage: {
        "grid-pattern":
          "radial-gradient(circle, #1E3A5F 1px, transparent 1px)",
        "glow-cyan":
          "radial-gradient(ellipse 400px 300px at 50% 0%, rgba(6,182,212,0.15), transparent)",
        "glow-purple":
          "radial-gradient(ellipse 300px 200px at 100% 50%, rgba(124,58,237,0.1), transparent)",
      },
      animation: {
        "pulse-slow":   "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in":      "fadeIn 0.3s ease-in-out",
        "slide-in":     "slideIn 0.2s ease-out",
      },
      keyframes: {
        fadeIn:  { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideIn: { "0%": { transform: "translateY(-8px)", opacity: "0" }, "100%": { transform: "translateY(0)", opacity: "1" } },
      },
      boxShadow: {
        "glow-cyan":   "0 0 20px rgba(6,182,212,0.3)",
        "glow-purple": "0 0 20px rgba(124,58,237,0.3)",
        "card":        "0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(30,58,95,0.6)",
      },
    },
  },
  plugins: [],
};

export default config;
