// Divisor arrastrable entre paneles: ratón, tacto y teclado. Doble clic alterna entre el ancho
// por defecto y el panel plegado. El ancho se recuerda entre sesiones.
import { useCallback, useEffect, useState } from "react";

export function useAnchoPanel(clave: string, defecto: number, min: number, max: () => number) {
  const leer = () => {
    try {
      const v = Number(localStorage.getItem(`extractor.ancho.${clave}`));
      return Number.isFinite(v) && v >= 0 && localStorage.getItem(`extractor.ancho.${clave}`) !== null ? v : defecto;
    } catch {
      return defecto;
    }
  };
  const [ancho, setAnchoCrudo] = useState(leer);
  const fijar = useCallback(
    (v: number) => {
      // Por debajo de la mitad del mínimo el panel se pliega (0) en lugar de quedar ilegible.
      const limitado = v < min / 2 ? 0 : Math.min(Math.max(v, min), max());
      setAnchoCrudo(limitado);
      try {
        localStorage.setItem(`extractor.ancho.${clave}`, String(Math.round(limitado)));
      } catch {
        /* sin almacenamiento: el ancho vale solo esta sesión */
      }
    },
    [clave, min, max],
  );
  // Si la ventana se achica, el panel nunca debe devorar la tabla.
  useEffect(() => {
    const f = () => setAnchoCrudo((a) => Math.min(a, max()));
    window.addEventListener("resize", f);
    return () => window.removeEventListener("resize", f);
  }, [max]);
  const alternar = useCallback(() => fijar(ancho === 0 ? defecto : 0), [ancho, defecto, fijar]);
  const restablecer = useCallback(() => fijar(defecto), [defecto, fijar]);
  return { ancho, fijar, alternar, restablecer };
}

type Props = {
  etiqueta: string;
  /** Ancho actual del panel que se redimensiona. */
  ancho: number;
  /** "izq": el panel está a la izquierda del divisor; "der": a la derecha. */
  lado: "izq" | "der";
  onCambio: (ancho: number) => void;
  onAlternar: () => void;
};

export function Divisor({ etiqueta, ancho, lado, onCambio, onAlternar }: Props) {
  const [activo, setActivo] = useState(false);
  const signo = lado === "izq" ? 1 : -1;

  const iniciar = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const x0 = e.clientX;
    const a0 = ancho;
    setActivo(true);
    const mover = (m: PointerEvent) => onCambio(a0 + signo * (m.clientX - x0));
    const soltar = () => {
      setActivo(false);
      window.removeEventListener("pointermove", mover);
      window.removeEventListener("pointerup", soltar);
      window.removeEventListener("pointercancel", soltar);
      document.body.classList.remove("redimensionando");
    };
    document.body.classList.add("redimensionando");
    window.addEventListener("pointermove", mover);
    window.addEventListener("pointerup", soltar);
    window.addEventListener("pointercancel", soltar);
  };

  const teclear = (e: React.KeyboardEvent) => {
    const paso = e.shiftKey ? 80 : 20;
    if (e.key === "ArrowLeft") onCambio(ancho - signo * paso);
    else if (e.key === "ArrowRight") onCambio(ancho + signo * paso);
    else if (e.key === "Enter" || e.key === " ") onAlternar();
    else return;
    e.preventDefault();
  };

  return (
    <div
      className={`divisor ${activo ? "activo" : ""}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={etiqueta}
      aria-valuenow={Math.round(ancho)}
      tabIndex={0}
      title={`${etiqueta}: arrastre para cambiar · doble clic para plegar o restablecer`}
      onPointerDown={iniciar}
      onDoubleClick={onAlternar}
      onKeyDown={teclear}
    />
  );
}
