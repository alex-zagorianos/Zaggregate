import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// The app is served by Flask at /app (webui/__init__.py static routes), so every
// asset URL must be prefixed with /app/. Build output lands in ../static (i.e.
// webui/static/), which paths.static_dir() serves and which is COMMITTED so
// source users without Node still get the UI.
//
// Dev proxy sends /api to the Flask receiver on 127.0.0.1:5002 so `npm run dev`
// talks to a real backend without CORS gymnastics.
export default defineConfig({
  base: "/app/",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "../static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5002",
        changeOrigin: false,
      },
    },
  },
});
