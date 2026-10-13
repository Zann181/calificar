// Disposición responsiva (sección 9.1) y migas de la vista actual (sección 9.5).
// Teléfono: patrones de iOS (barra de navegación con título grande y barra de pestañas).
// PC: herramienta de tabla (barra de herramientas, barra lateral, tabla e inspector).
import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "./api";
import { BarraGlobal } from "./componentes/BarraGlobal";
import { Divisor, useAnchoPanel } from "./componentes/Divisor";
import { EstadoServicios } from "./componentes/EstadoServicios";
import { Grilla } from "./componentes/Grilla";
import { Icono } from "./componentes/Icono";
import { PanelArticulos } from "./componentes/PanelArticulos";
import { PanelRazonamiento } from "./componentes/PanelRazonamiento";
import { PanelRegistro } from "./componentes/PanelRegistro";
import { Tarjetas } from "./componentes/Tarjetas";
import { VisorPdf } from "./componentes/VisorPdf";
import { useNavegacion } from "./navegacion";
import { DialogoRevision } from "./revision";

function useAncho() {
  const [ancho, setAncho] = useState(window.innerWidth);
  useEffect(() => {
    const f = () => setAncho(window.innerWidth);
    window.addEventListener("resize", f);
    return () => window.removeEventListener("resize", f);
  }, []);
  return ancho;
}

function Migas() {
  const { actual, ir } = useNavegacion();
  return (
    <nav className="migas">
      <span className="ruta">
        <button onClick={() => ir({})}>Matriz</button>
        {actual.estudio && (
          <>
            <Icono nombre="adelante" tam={12} />
            <button
              onClick={() =>
                ir({ estudio: actual.estudio, articuloId: actual.articuloId })
              }
            >
              Estudio {actual.estudio}
            </button>
          </>
        )}
        {actual.columna && (
          <>
            <Icono nombre="adelante" tam={12} />
            <button onClick={() => ir({ ...actual, visor: undefined })}>
              {actual.columna}
            </button>
          </>
        )}
        {actual.visor && (
          <>
            <Icono nombre="adelante" tam={12} />
            <span>p. {actual.visor.pagina}</span>
          </>
        )}
      </span>
    </nav>
  );
}

// Exporta toda la matriz a una hoja de cálculo (.xlsx): el servidor la genera y el navegador la descarga.
function BotonExportar({ pid }: { pid: string }) {
  const exportar = useMutation({
    mutationFn: () => api.exportar(pid),
    onSuccess: (r) => {
      const a = document.createElement("a");
      a.href = r.descarga;
      a.download = "";
      document.body.appendChild(a);
      a.click();
      a.remove();
    },
  });
  return (
    <button
      className="sin-borde"
      onClick={() => exportar.mutate()}
      disabled={exportar.isPending}
      title={
        exportar.error
          ? `No se pudo exportar: ${(exportar.error as Error).message}`
          : exportar.isPending
            ? "Generando la hoja de cálculo…"
            : "Exportar la matriz a Excel (.xlsx)"
      }
      aria-label="Exportar la matriz a Excel"
    >
      <Icono nombre="bajar" tam={18} />
      {exportar.isPending ? "Exportando…" : exportar.error ? "Reintentar exportar" : "Exportar"}
    </button>
  );
}

type Pestana = "articulos" | "revision" | "visor";
const TITULOS: Record<Pestana, string> = {
  articulos: "Artículos",
  revision: "Revisión",
  visor: "Visor",
};

function Espacio({ pid }: { pid: string }) {
  const ancho = useAncho();
  const { actual } = useNavegacion();
  // El visor empieza plegado: vacío solo le quitaría ancho a la tabla. Se abre al elegir una celda o un PDF.
  const [visorAbierto, setVisorAbierto] = useState(false);
  const [marcados, setMarcados] = useState<Set<string>>(new Set()); // artículos con chulito
  // Tableta: la barra lateral va acoplada (no flotante) y se muestra u oculta.
  const [lateralTableta, setLateralTableta] = useState(true);
  const [pestana, setPestana] = useState<Pestana>("revision");
  const [pestanaTableta, setPestanaTableta] = useState<"matriz" | "visor">(
    "matriz",
  );
  const [enrollado, setEnrollado] = useState(false);
  // Paneles redimensionables: el tope deja siempre al menos 320 px a la tabla.
  const topeLateral = useCallback(
    () =>
      Math.max(
        200,
        Math.min(window.innerWidth * 0.5, window.innerWidth - 320 - 280),
      ),
    [],
  );
  const lateral = useAnchoPanel("lateral", 290, 200, topeLateral);
  const topeVisor = useCallback(
    () => Math.max(280, window.innerWidth - 320 - lateral.ancho),
    [lateral.ancho],
  );
  const panelVisor = useAnchoPanel(
    "visor",
    Math.round(window.innerWidth * 0.4),
    280,
    topeVisor,
  );

  const columnas = useQuery({
    queryKey: ["columnas", pid],
    queryFn: () => api.columnas(pid),
  });
  const filas = useQuery({
    queryKey: ["filas", pid],
    queryFn: () => api.filas(pid),
  });
  const articulos = useQuery({
    queryKey: ["articulos", pid],
    queryFn: () => api.articulos(pid),
  });

  const { documentoDe, conFilas, covidenceDe } = useMemo(() => {
    const documentoDe = new Map<string, number>();
    const conFilas = new Set<string>();
    const covidenceDe = new Map<number, number>(); // Documento → Covidence # ya registrado en la matriz
    for (const f of filas.data?.filas ?? []) {
      const covidence = Number(f.celdas["Covidence #"]?.valor);
      if (Number.isInteger(covidence) && covidence > 0)
        covidenceDe.set(f.documento, covidence);
      if (f.articulo_id) {
        documentoDe.set(f.articulo_id, f.documento);
        conFilas.add(f.articulo_id);
      }
    }
    return { documentoDe, conFilas, covidenceDe };
  }, [filas.data]);

  const nombreArticulo = articulos.data?.articulos.find(
    (a) => a.id === actual.visor?.articuloId,
  )?.nombre_archivo;

  useEffect(() => {
    if (!actual.visor) return;
    setVisorAbierto(true);
    setPestanaTableta("visor");
  }, [actual.visor]);
  // Elegir una celda sin PDF también abre el visor: ahí está «Por qué este valor».
  useEffect(() => {
    if (actual.estudio !== undefined && actual.columna) setVisorAbierto(true);
  }, [actual.estudio, actual.columna]);

  if (columnas.error || filas.error || articulos.error) {
    return (
      <p className="error centro">
        {((columnas.error || filas.error || articulos.error) as Error).message}
      </p>
    );
  }
  if (!columnas.data || !filas.data || !articulos.data)
    return <p className="centro tenue">Cargando matriz…</p>;

  const panel = (
    <PanelArticulos
      pid={pid}
      articulos={articulos.data.articulos}
      contadores={articulos.data.contadores}
      documentoDe={documentoDe}
      covidenceDe={covidenceDe}
      conFilas={conFilas}
      onAbrir={() => setPestana("visor")}
      marcados={marcados}
      setMarcados={setMarcados}
      onOcultar={
        ancho < 768
          ? undefined
          : ancho < 1280
            ? () => setLateralTableta(false)
            : () => lateral.fijar(0)
      }
    />
  );
  const grilla = (
    <div className="zona-matriz">
      <Grilla
        pid={pid}
        columnas={columnas.data}
        filas={filas.data.filas}
        articulosMarcados={marcados}
      />
      <PanelRegistro />
    </div>
  );
  const visor = actual.visor ? (
    <VisorPdf
      pid={pid}
      visor={actual.visor}
      nombre={nombreArticulo}
      onCerrar={ancho >= 1024 ? () => setVisorAbierto(false) : undefined}
    />
  ) : (
    <section className="visor">
      <div className="visor-vacio">
        <Icono nombre="visor" tam={40} grosor={1.2} />
        <p>
          Elija una celda con evidencia o un artículo convertido para ver el PDF
          con la cita resaltada.
        </p>
      </div>
      <PanelRazonamiento pid={pid} />
    </section>
  );

  // Teléfono (iOS): una vista a la vez, sin grilla.
  if (ancho < 768) {
    return (
      <div className="ios">
        <header className={`ios-nav ${enrollado ? "enrollado" : ""}`}>
          <span />
          <span className="ios-titulo-pequeno">{TITULOS[pestana]}</span>
          <span />
        </header>
        <div
          className="ios-contenido"
          onScroll={(e) =>
            setEnrollado((e.target as HTMLElement).scrollTop > 30)
          }
        >
          {pestana !== "visor" && (
            <h1 className="ios-titulo-grande">{TITULOS[pestana]}</h1>
          )}
          {pestana === "articulos" && panel}
          {pestana === "revision" && (
            <Tarjetas
              pid={pid}
              columnas={columnas.data}
              filas={filas.data.filas}
              onVerPdf={() => setPestana("visor")}
            />
          )}
          {pestana === "visor" && visor}
        </div>
        <nav className="ios-pestanas">
          {(["articulos", "revision", "visor"] as Pestana[]).map((p) => (
            <button
              key={p}
              className={pestana === p ? "activo" : ""}
              onClick={() => setPestana(p)}
            >
              <Icono
                nombre={p === "articulos" ? "documentos" : p}
                tam={24}
                grosor={pestana === p ? 2.1 : 1.7}
              />
              <span>{TITULOS[p]}</span>
            </button>
          ))}
        </nav>
      </div>
    );
  }

  // Tableta: barra lateral acoplada que se oculta; tabla e inspector lado a lado desde 1024 px, si no, alternados.
  if (ancho < 1280) {
    const lado = ancho >= 1024;
    const columnasCuerpo = [
      lateralTableta ? "var(--w-lateral-tableta)" : "",
      "minmax(0, 1fr)",
      lado && visorAbierto ? "0 var(--w-visor, 45%)" : "",
    ]
      .filter(Boolean)
      .join(" ");
    return (
      <div className="tableta">
        <div className="subbarra">
          <button
            className={lateralTableta ? "activo" : ""}
            onClick={() => setLateralTableta((v) => !v)}
            aria-pressed={lateralTableta}
            title={lateralTableta ? "Ocultar artículos" : "Mostrar artículos"}
          >
            <Icono nombre="barra" tam={18} /> Artículos
          </button>
          {!lado && (
            <div className="segmentado">
              <button
                className={pestanaTableta === "matriz" ? "activo" : ""}
                onClick={() => setPestanaTableta("matriz")}
              >
                Matriz
              </button>
              <button
                className={pestanaTableta === "visor" ? "activo" : ""}
                onClick={() => setPestanaTableta("visor")}
              >
                Visor
              </button>
            </div>
          )}
          {lado && !visorAbierto && (
            <button onClick={() => setVisorAbierto(true)}>
              <Icono nombre="visor" tam={18} /> Mostrar visor
            </button>
          )}
        </div>
        <div
          className="cuerpo"
          style={
            {
              "--w-visor": `${panelVisor.ancho}px`,
              gridTemplateColumns: columnasCuerpo,
            } as React.CSSProperties
          }
        >
          {lateralTableta && <div className="panel-lateral">{panel}</div>}
          {(lado || pestanaTableta === "matriz") && grilla}
          {lado && visorAbierto && (
            <Divisor
              etiqueta="Ancho del visor"
              ancho={panelVisor.ancho}
              lado="der"
              onCambio={panelVisor.fijar}
              onAlternar={panelVisor.alternar}
            />
          )}
          {((lado && visorAbierto) || (!lado && pestanaTableta === "visor")) &&
            visor}
        </div>
      </div>
    );
  }

  // Escritorio: barra lateral, tabla e inspector; los tres anchos se ajustan arrastrando los divisores.
  // Plegado, el panel deja una pestaña de 44 px para volver a mostrarlo; la grilla conserva sus cinco columnas.
  const estilo = {
    "--w-lateral": lateral.ancho > 0 ? `${lateral.ancho}px` : "44px",
    "--w-visor":
      visorAbierto && panelVisor.ancho > 0 ? `${panelVisor.ancho}px` : "44px",
  } as React.CSSProperties;
  return (
    <div
      className={`escritorio ${visorAbierto ? "con-visor" : "sin-visor"}`}
      style={estilo}
    >
      {lateral.ancho > 0 ? (
        <div className="panel-lateral">{panel}</div>
      ) : (
        <button
          className="desplegar-visor desplegar-lateral"
          onClick={lateral.restablecer}
          title="Mostrar artículos"
        >
          <Icono nombre="documentos" tam={18} />
          <span>Artículos</span>
        </button>
      )}
      <Divisor
        etiqueta="Ancho de artículos"
        ancho={lateral.ancho}
        lado="izq"
        onCambio={lateral.fijar}
        onAlternar={lateral.alternar}
      />
      {grilla}
      {visorAbierto ? (
        <>
          <Divisor
            etiqueta="Ancho del visor"
            ancho={panelVisor.ancho}
            lado="der"
            onCambio={panelVisor.fijar}
            onAlternar={panelVisor.alternar}
          />
          {panelVisor.ancho === 0 ? (
            <button
              className="desplegar-visor"
              onClick={panelVisor.restablecer}
              title="Mostrar visor"
            >
              <Icono nombre="visor" tam={18} />
              <span>Visor</span>
            </button>
          ) : (
            visor
          )}
        </>
      ) : (
        <button
          className="desplegar-visor"
          onClick={() => setVisorAbierto(true)}
          title="Mostrar visor"
        >
          <Icono nombre="visor" tam={18} />
          <span>Visor</span>
        </button>
      )}
    </div>
  );
}

export function App() {
  const ancho = useAncho();
  const proyectos = useQuery({
    queryKey: ["proyectos"],
    queryFn: api.proyectos,
  });
  const proyecto = proyectos.data?.[0];

  if (proyectos.isLoading) return <p className="centro tenue">Cargando…</p>;

  return (
    <div className="app">
      {proyecto && <BarraGlobal pid={proyecto.id} />}
      {ancho >= 768 && (
        <header className="herramientas">
          <div className="titulo-app">
            <span className="marca pequena">
              <Icono nombre="tabla" tam={16} />
            </span>
            <strong>Extractor de matriz</strong>
            <span className="tenue">{proyecto?.nombre}</span>
          </div>
          <Migas />
          <EstadoServicios pid={proyecto?.id ?? ""} />
          <div className="cuenta">
            {proyecto && <BotonExportar pid={proyecto.id} />}
          </div>
        </header>
      )}
      {proyecto ? (
        <Espacio pid={proyecto.id} />
      ) : (
        <p className="centro tenue">Sin proyectos. Ejecute la semilla.</p>
      )}
      {proyecto && <DialogoRevision pid={proyecto.id} />}
    </div>
  );
}
