import type { Config } from "tailwindcss";
import typography from "@tailwindcss/typography";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      typography: {
        DEFAULT: {
          css: {
            // Allow KaTeX display blocks to overflow gracefully
            ".katex-display": {
              overflowX: "auto",
              overflowY: "hidden",
            },
          },
        },
      },
    },
  },
  plugins: [typography],
};

export default config;
