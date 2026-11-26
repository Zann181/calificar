// Ancho de la ventana: decide la disposición (teléfono < 768, tableta < 1280, escritorio).
import { useEffect, useState } from "react";

export function useAncho() {
  const [ancho, setAncho] = useState(window.innerWidth);
  useEffect(() => {
    const f = () => setAncho(window.innerWidth);
    window.addEventListener("resize", f);
    return () => window.removeEventListener("resize", f);
  }, []);
  return ancho;
}
