// Barra de avance de una extracción: porcentaje, paso actual, tiempo transcurrido y costo.
import { formatoTiempo, porcentajeVisible } from "../avance";
import type { AvanceExtraccion, PendienteDeExtraccion } from "../tipos";

type Props = { avance?: AvanceExtraccion; pendiente?: PendienteDeExtraccion; ahora: number };

const TEXTO_FASE = {
  en_cola: (p: number) => `En cola · puesto ${p}: empieza cuando termine la anterior`,
  convirtiendo: () => "Convirtiendo el PDF con MinerU (unos 10 a 20 s por página); la extracción sigue sola",
  esperando_mineru: () => "Esperando a MinerU (no responde): la extracción empieza cuando esté activo",
};

export function BarraAvance({ avance, pendiente, ahora }: Props) {
  // Con extracción en marcha manda su porcentaje; antes, la fase del pedido (cola o conversión).
  if (!avance && pendiente) {
    const trabajando = pendiente.fase === "convirtiendo";
    return (
      <div className={`avance en-cola ${trabajando ? "convirtiendo" : ""}`} role="status">
        {trabajando && (
          <div className="avance-pista indeterminada">
            <div className="avance-relleno" />
          </div>
        )}
        <div className="avance-linea">
          <span className="avance-texto">{TEXTO_FASE[pendiente.fase](pendiente.posicion)}</span>
          {trabajando && (
            <span className="avance-tiempo">{formatoTiempo((ahora - Date.parse(pendiente.desde)) / 1000)}</span>
          )}
        </div>
      </div>
    );
  }
  if (!avance) return null;

  const fallida = avance.fallida;
  const lista = !!avance.terminada_en && !fallida;
  const pct = porcentajeVisible(avance, ahora);
  const fin = avance.terminada_en ? Date.parse(avance.terminada_en) : ahora;
  const tiempo = formatoTiempo((fin - Date.parse(avance.iniciada_en)) / 1000);
  const clase = fallida ? "fallida" : lista ? "lista" : avance.inactiva ? "inactiva" : "";
  const texto = fallida
    ? `Falló: ${avance.error ?? "error desconocido"}`
    : lista
      ? `Completada en ${tiempo} · ${avance.costo_usd.toLocaleString("es", { minimumFractionDigits: 2 })} USD equivalentes${avance.acuerdo !== null ? ` · acuerdo ${Math.round(avance.acuerdo * 100)} %` : ""}`
      : avance.inactiva
        ? "Sin avance hace más de 30 min: el proceso pudo detenerse"
        : avance.paso_texto;

  return (
    <div className={`avance ${clase}`} title={fallida ? (avance.error ?? "") : avance.paso_texto}>
      <div
        className="avance-pista"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label={`Avance de la extracción: ${pct} %`}
      >
        <div className="avance-relleno" style={{ width: `${pct}%` }} />
      </div>
      <div className="avance-linea">
        <b className="avance-pct">{fallida ? "—" : `${pct} %`}</b>
        <span className="avance-texto">{texto}</span>
        {!lista && !fallida && <span className="avance-tiempo">{tiempo}</span>}
      </div>
    </div>
  );
}
