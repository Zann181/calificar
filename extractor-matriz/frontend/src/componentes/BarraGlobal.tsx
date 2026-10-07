// Barra fina en el borde superior de la ventana: avance de las extracciones en curso (promedio) o, mientras solo
// se convierte un PDF o se espera en cola, una franja que va y viene. Desaparece cuando no hay nada en marcha.
import { enCurso, porcentajeVisible, useAvance } from "../avance";

export function BarraGlobal({ pid }: { pid: string }) {
  const { porArticulo, enCola, ahora } = useAvance(pid);
  const activas = [...porArticulo.values()].filter(enCurso);
  if (activas.length === 0 && enCola.size === 0) return null;
  const pct = activas.length
    ? Math.round(activas.reduce((s, a) => s + porcentajeVisible(a, ahora), 0) / activas.length)
    : null;
  return (
    <div
      className={`barra-global ${pct === null ? "indeterminada" : ""}`}
      role="progressbar"
      aria-label="Avance de la extracción"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct ?? undefined}
    >
      <div className="barra-global-relleno" style={pct === null ? undefined : { width: `${pct}%` }} />
    </div>
  );
}
