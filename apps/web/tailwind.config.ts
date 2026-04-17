import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        serif: ["var(--font-lora)", "Georgia", "serif"],
      },
      colors: {
        ink: {
          DEFAULT: "#0a0a0a",
          muted: "#525252",
          subtle: "#737373",
        },
        paper: {
          DEFAULT: "#fafaf9",
          elevated: "#ffffff",
          border: "#e7e5e4",
        },
        accent: {
          DEFAULT: "#8B1A1A", // bordeaux giuridico
          soft: "#F9E6E6",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
