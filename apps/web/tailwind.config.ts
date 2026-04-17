import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        serif: ["var(--font-lora)", "Georgia", "serif"],
      },
      colors: {
        // Palette "Claude-like light": neutri caldi, accenti bordeaux giuridico.
        ink: {
          DEFAULT: "#1a1a1a",
          muted: "#525252",
          subtle: "#8a8a8a",
        },
        paper: {
          DEFAULT: "#ffffff",
          panel: "#f7f5f2",      // sidebar beige leggerissimo
          hover: "#f0ede8",      // hover su voci sidebar
          border: "#e6e2dc",
          divider: "#eeeae4",
        },
        accent: {
          DEFAULT: "#8B1A1A",    // bordeaux giuridico
          soft: "#F9EEEE",
        },
      },
      typography: () => ({
        legal: {
          css: {
            "--tw-prose-body": "#1a1a1a",
            "--tw-prose-headings": "#1a1a1a",
            "--tw-prose-bold": "#1a1a1a",
            "--tw-prose-links": "#8B1A1A",
            "--tw-prose-bullets": "#8a8a8a",
            "--tw-prose-counters": "#8a8a8a",
            "--tw-prose-quotes": "#525252",
            "--tw-prose-quote-borders": "#e6e2dc",
            "--tw-prose-hr": "#e6e2dc",
            fontSize: "0.95rem",
            lineHeight: "1.65",
            p: { marginTop: "0.75em", marginBottom: "0.75em" },
            "ul, ol": { marginTop: "0.5em", marginBottom: "0.5em" },
            "li > p": { marginTop: "0.25em", marginBottom: "0.25em" },
            "li::marker": { color: "var(--tw-prose-counters)" },
            strong: { fontWeight: "600" },
            a: {
              textDecorationColor: "rgba(139, 26, 26, 0.35)",
              textUnderlineOffset: "3px",
              fontWeight: "500",
            },
            "a:hover": { textDecorationColor: "#8B1A1A" },
            code: {
              color: "#1a1a1a",
              backgroundColor: "#f0ede8",
              padding: "0.1rem 0.35rem",
              borderRadius: "3px",
              fontWeight: "400",
            },
            "code::before": { content: '""' },
            "code::after": { content: '""' },
            hr: { marginTop: "1.25em", marginBottom: "1.25em" },
          },
        },
      }),
    },
  },
  plugins: [typography],
} satisfies Config;
