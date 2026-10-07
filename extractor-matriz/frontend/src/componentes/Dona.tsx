// Dona de avance (pastel): porcentaje de la extracción en curso, un anillo que gira mientras no hay porcentaje
// (conversión o cola) y, sin actividad, un anillo del color de la salud de los servicios.
type Props = {
  pct: number | null; // 0 a 100; null = sin porcentaje
  trabajando: boolean; // hay algo en curso aunque aún no tenga porcentaje
  salud: "ok" | "aviso" | "error";
  tam?: number;
};

const R = 14;
const LONGITUD = 2 * Math.PI * R;

export function Dona({ pct, trabajando, salud, tam = 34 }: Props) {
  const conPorcentaje = pct !== null;
  const lleno = conPorcentaje
    ? (Math.min(100, Math.max(0, pct)) / 100) * LONGITUD
    : trabajando
      ? LONGITUD * 0.28
      : LONGITUD;
  return (
    <span
      className={`dona ${salud} ${trabajando && !conPorcentaje ? "girando" : ""} ${conPorcentaje ? "con-pct" : ""}`}
    >
      <svg width={tam} height={tam} viewBox="0 0 36 36" aria-hidden="true">
        <circle className="dona-pista" cx="18" cy="18" r={R} />
        <circle
          className="dona-arco"
          cx="18"
          cy="18"
          r={R}
          strokeDasharray={`${lleno} ${LONGITUD}`}
          transform="rotate(-90 18 18)"
        />
      </svg>
      <span className="dona-centro">
        {conPorcentaje ? `${Math.round(pct)}` : trabajando ? "" : <i className="dona-punto" />}
      </span>
    </span>
  );
}
