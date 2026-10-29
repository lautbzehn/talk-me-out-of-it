import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";
import { previewExport } from "./scripts/previews-plugin.mjs";

// Vite turns src/ into static files in dist/. Cloudflare Pages serves dist/ as-is.
// previewExport() only exists while `npm run dev` runs; it lets export.html save preview images.
export default defineConfig({
  plugins: [react(), tailwindcss(), previewExport()],
  resolve: {
    // "@/..." means "src/...". 21st.dev components are written against this alias.
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
