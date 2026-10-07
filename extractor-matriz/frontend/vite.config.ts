import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// La API corre en el puerto 8000; el proxy mantiene la cookie de sesión en el mismo origen.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
