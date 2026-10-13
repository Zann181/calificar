import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./estilos.css";

// El diseño (anchos, zoom, registro, monitor) ahora vive en sessionStorage y se restablece al cerrar la ventana.
// Se borra lo que versiones anteriores dejaron en localStorage para que no vuelva a cargarse.
try {
  Object.keys(localStorage)
    .filter((k) => k.startsWith("extractor."))
    .forEach((k) => localStorage.removeItem(k));
} catch {
  /* sin almacenamiento */
}

const cliente = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } } });

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <QueryClientProvider client={cliente}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
