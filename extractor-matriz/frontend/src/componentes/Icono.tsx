// Íconos de trazo, al estilo de SF Symbols, dibujados en SVG (sin dependencias).
const TRAZOS: Record<string, string> = {
  documentos: "M7 3h7l5 5v12a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm7 0v5h5M9 13h6M9 17h6",
  revision: "M9 11l2 2 4-4M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z",
  visor: "M4 5a1 1 0 0 1 1-1h9l6 6v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5Zm6 8a2.5 2.5 0 1 0 5 0 2.5 2.5 0 1 0-5 0m4.3 1.8L17 17.5",
  tabla: "M4 5h16v14H4V5Zm0 5h16M4 15h16M10 5v14",
  atras: "M15 5l-7 7 7 7",
  adelante: "M9 5l7 7-7 7",
  mas: "M12 5v14M5 12h14",
  menos: "M5 12h14",
  cerrar: "M6 6l12 12M18 6L6 18",
  buscar: "M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 1 0 0 13Zm4.6-1.9L20 20",
  barra: "M4 5h16v14H4V5Zm5 0v14",
  salir: "M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10",
  subir: "M12 16V4M7 9l5-5 5 5M5 20h14",
  reloj: "M12 21a9 9 0 1 0 0-18 9 9 0 1 0 0 18Zm0-13v5l3 2",
  check: "M5 12.5l4.5 4.5L19 7.5",
  lapiz: "M4 20h4L19 9l-4-4L4 16v4Zm9-13l4 4",
  rechazo: "M12 21a9 9 0 1 0 0-18 9 9 0 1 0 0 18ZM8.5 8.5l7 7",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 1 0 0 18Zm0-10v6m0-9.5v.01",
};

export function Icono({ nombre, tam = 20, grosor = 1.8 }: { nombre: keyof typeof TRAZOS | string; tam?: number; grosor?: number }) {
  return (
    <svg
      width={tam}
      height={tam}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={grosor}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="icono"
    >
      <path d={TRAZOS[nombre] ?? ""} />
    </svg>
  );
}
