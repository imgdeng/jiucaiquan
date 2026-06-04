/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}"],
  theme: {
    extend: {
      colors: {
        ink: "#17211d",
        leaf: "#176b4a",
        lime: "#d4f06a",
        rice: "#f7f3e8",
        line: "#d8ddcf"
      }
    }
  },
  plugins: []
};
