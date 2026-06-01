import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// VITE_API_BASE controls where the browser sends agent queries.
// Defaults to the local API in docker-compose / dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Convenience: in `npm run dev`, proxy /api -> backend so you can use
      // a same-origin base if you prefer. (The app uses VITE_API_BASE directly.)
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
