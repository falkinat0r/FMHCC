import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Entwicklung: /api wird an das Backend auf Loopback 8000 proxied.
// Produktion: nginx uebernimmt die Weiterleitung (deploy/nginx/hcc.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
  },
});
