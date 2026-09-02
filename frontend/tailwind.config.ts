import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "#0a0d14",
        card: "#121824",
        border: "#1e293b",
        accent: "#38bdf8",
        gain: "#22c55e",
        loss: "#ef4444",
      },
    },
  },
  plugins: [],
};
export default config;
