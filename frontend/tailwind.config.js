/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        kb: {
          paper: "#F5F0E6", paper2: "#EDE4D3", card: "#FFFDF8", ink: "#14231F", pine: "#1F4D3F",
          pine2: "#2E6A57", brick: "#B4532A", brick2: "#8F3E1D", gold: "#C99A3C", muted: "#5F6159",
          line: "#DDD2BF", wa: "#128C4A",
        },
      },
      // Kribaat brand (brand-memory.md at the repo root is the source of truth).
      fontFamily: {
        display: ["Fraunces", "Georgia", "serif"],
        brand: ['"Hanken Grotesk"', '"Noto Sans Devanagari"', "system-ui", "sans-serif"],
        deva: ['"Noto Sans Devanagari"', '"Hanken Grotesk"', "sans-serif"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        // Horizontal marquees for the landing page. They translate a duplicated
        // track by exactly -50% / +50% so the loop is seamless. Transform-only
        // (compositor-friendly); paused for prefers-reduced-motion via CSS.
        "marquee-left": {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(-50%)" },
        },
        "marquee-right": {
          from: { transform: "translateX(-50%)" },
          to: { transform: "translateX(0)" },
        },
        "aurora-drift": {
          "0%, 100%": { transform: "translate3d(0,0,0) scale(1)" },
          "50%": { transform: "translate3d(2%, -3%, 0) scale(1.08)" },
        },
        "float-y": {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
        rise: {
          from: { opacity: "0", transform: "translateY(14px)" },
          to: { opacity: "1", transform: "none" },
        },
      },
      animation: {
        "marquee-left": "marquee-left var(--marquee-duration, 60s) linear infinite",
        "marquee-right": "marquee-right var(--marquee-duration, 60s) linear infinite",
        "aurora-drift": "aurora-drift 18s ease-in-out infinite",
        "float-y": "float-y 6s ease-in-out infinite",
        rise: "rise .7s cubic-bezier(.2,.7,.2,1) both",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
