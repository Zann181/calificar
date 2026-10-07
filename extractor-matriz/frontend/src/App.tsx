// Disposición responsiva (sección 9.1), sesión, migas y navegación con retorno (sección 9.5).
// Teléfono: patrones de iOS (barra de navegación con título grande y barra de pestañas).
// PC: herramienta de tabla (barra de herramientas, barra lateral, tabla e inspector).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { api, ErrorApi } from "./api";
import { Grilla } from "./componentes/Grilla";
import { Icono } from "./componentes/Icono";
import { PanelArticulos } from "./componentes/PanelArticulos";
import { Tarjetas } from "./componentes/Tarjetas";
import { VisorPdf } from "./componentes/VisorPdf";
import { describir, useNavegacion } from "./navegacion";
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

function Entrar() {
  const qc = useQueryClient();
  const [correo, setCorreo] = useState("admin@local.test");
  const [clave, setClave] = useState("");
  const entrar = useMutation({
    mutationFn: () => api.entrar(correo, clave),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sesion"] }),
  });
  return (
    <main className="entrar">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          entrar.mutate();
        }}
      >
        <div className="marca">
          <Icono nombre="tabla" tam={30} />
        </div>
        <h1>Extractor de matriz</h1>
        <p className="tenue">Felicidad en el trabajo y desempeño laboral</p>
        <div className="grupo">
          <input value={correo} onChange={(e) => setCorreo(e.target.value)} autoComplete="username" placeholder="Correo" aria-label="Correo" />
          <input
            type="password"
            value={clave}
            onChange={(e) => setClave(e.target.value)}
            autoComplete="current-password"
            placeholder="Contraseña"
            aria-label="Contraseña"
          />
        </div>
        {entrar.error && <p className="error">{(entrar.error as Error).message}</p>}
        <button className="primario grande" disabled={entrar.isPending || !clave}>
          Entrar
        </button>
      </form>
    </main>
  );
}

function Migas() {
  const { pila, actual, volver, irA, ir } = useNavegacion();
  const [lista, setLista] = useState(false);
  const ultimas = pila.map((v, i) => ({ v, i })).slice(-10).reverse();
  return (
    <nav className="migas">
      <div className="segmento">
        <button disabled={!pila.length} onClick={volver} title="Volver (Alt + ←)" aria-label="Volver">
          <Icono nombre="atras" tam={16} />
        </button>
        <button disabled={!pila.length} onClick={() => setLista(!lista)} aria-label="Historial de navegación" title="Historial">
          <Icono nombre="reloj" tam={16} />
        </button>
      </div>
      {lista && (
        <ul className="menu" onMouseLeave={() => setLista(false)}>
          {ultimas.map(({ v, i }) => (
            <li key={i}>
              <button
                onClick={() => {
                  setLista(false);
                  irA(i);
                }}
              >
                {describir(v)}
              </button>
            </li>
          ))}
        </ul>
      )}
      <span className="ruta">
        <button onClick={() => ir({})}>Matriz</button>
        {actual.estudio && (
          <>
            <Icono nombre="adelante" tam={12} />
            <button onClick={() => ir({ estudio: actual.estudio, articuloId: actual.articuloId })}>Estudio {actual.estudio}</button>
          </>
        )}
        {actual.columna && (
          <>
            <Icono nombre="adelante" tam={12} />
            <button onClick={() => ir({ ...actual, visor: undefined })}>{actual.columna}</button>
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

type Pestana = "articulos" | "revision" | "visor";
const TITULOS: Record<Pestana, string> = { articulos: "Artículos", revision: "Revisión", visor: "Visor" };

function Espacio({ pid, correo, onSalir }: { pid: string; correo: string; onSalir: () => void }) {
  const ancho = useAncho();
  const { actual, ir, pila, volver } = useNavegacion();
  const [visorAbierto, setVisorAbierto] = useState(true);
  const [cajon, setCajon] = useState(false);
  const [pestana, setPestana] = useState<Pestana>("revision");
  const [pestanaTableta, setPestanaTableta] = useState<"matriz" | "visor">("matriz");
  const [enrollado, setEnrollado] = useState(false);

  const columnas = useQuery({ queryKey: ["columnas", pid], queryFn: () => api.columnas(pid) });
  const filas = useQuery({ queryKey: ["filas", pid], queryFn: () => api.filas(pid) });
  const articulos = useQuery({ queryKey: ["articulos", pid], queryFn: () => api.articulos(pid) });

  const { documentoDe, conFilas } = useMemo(() => {
    const documentoDe = new Map<string, number>();
    const conFilas = new Set<string>();
    for (const f of filas.data?.filas ?? []) {
      if (f.articulo_id) {
        documentoDe.set(f.articulo_id, f.documento);
        conFilas.add(f.articulo_id);
      }
    }
    return { documentoDe, conFilas };
  }, [filas.data]);

  // Al abrir un artículo la grilla se filtra por su Documento.
  const documento = actual.articuloId ? documentoDe.get(actual.articuloId) : undefined;
  const nombreArticulo = articulos.data?.articulos.find((a) => a.id === actual.visor?.articuloId)?.nombre_archivo;

  useEffect(() => {
    if (!actual.visor) return;
    setVisorAbierto(true);
    setPestanaTableta("visor");
  }, [actual.visor]);

  if (columnas.error || filas.error || articulos.error) {
    return <p className="error centro">{((columnas.error || filas.error || articulos.error) as Error).message}</p>;
  }
  if (!columnas.data || !filas.data || !articulos.data) return <p className="centro tenue">Cargando matriz…</p>;

  const panel = (
    <PanelArticulos
      pid={pid}
      articulos={articulos.data.articulos}
      contadores={articulos.data.contadores}
      documentoDe={documentoDe}
      conFilas={conFilas}
      onAbrir={() => setPestana("visor")}
    />
  );
  const grilla = (
    <Grilla
      pid={pid}
      columnas={columnas.data}
      filas={filas.data.filas}
      documento={documento}
      onQuitarFiltro={() => ir({ ...actual, articuloId: undefined })}
    />
  );
  const visor = actual.visor ? (
    <VisorPdf pid={pid} visor={actual.visor} nombre={nombreArticulo} onCerrar={ancho >= 1024 ? () => setVisorAbierto(false) : undefined} />
  ) : (
    <section className="visor vacio">
      <Icono nombre="visor" tam={40} grosor={1.2} />
      <p>Elija una celda con evidencia o un artículo convertido para ver el PDF con la cita resaltada.</p>
    </section>
  );

  // Teléfono (iOS): una vista a la vez, sin grilla.
  if (ancho < 768) {
    return (
      <div className="ios">
        <header className={`ios-nav ${enrollado ? "enrollado" : ""}`}>
          {pila.length > 0 ? (
            <button className="ios-atras" onClick={volver}>
              <Icono nombre="atras" tam={22} grosor={2.2} />
              Atrás
            </button>
          ) : (
            <span />
          )}
          <span className="ios-titulo-pequeno">{TITULOS[pestana]}</span>
          {pestana === "articulos" ? (
            <button className="ios-texto" onClick={onSalir}>
              Salir
            </button>
          ) : (
            <span />
          )}
        </header>
        <div className="ios-contenido" onScroll={(e) => setEnrollado((e.target as HTMLElement).scrollTop > 30)}>
          {pestana !== "visor" && <h1 className="ios-titulo-grande">{TITULOS[pestana]}</h1>}
          {pestana === "articulos" && panel}
          {pestana === "revision" && (
            <Tarjetas pid={pid} columnas={columnas.data} filas={filas.data.filas} onVerPdf={() => setPestana("visor")} />
          )}
          {pestana === "visor" && visor}
        </div>
        <nav className="ios-pestanas">
          {(["articulos", "revision", "visor"] as Pestana[]).map((p) => (
            <button key={p} className={pestana === p ? "activo" : ""} onClick={() => setPestana(p)}>
              <Icono nombre={p === "articulos" ? "documentos" : p} tam={24} grosor={pestana === p ? 2.1 : 1.7} />
              <span>{TITULOS[p]}</span>
            </button>
          ))}
        </nav>
        <p className="ios-cuenta tenue">{correo}</p>
      </div>
    );
  }

  // Tableta: barra lateral como cajón; tabla e inspector lado a lado desde 1024 px, si no, alternados.
  if (ancho < 1280) {
    const lado = ancho >= 1024;
    return (
      <div className="tableta">
        <div className="subbarra">
          <button onClick={() => setCajon(true)}>
            <Icono nombre="barra" tam={18} /> Artículos
          </button>
          {!lado && (
            <div className="segmentado">
              <button className={pestanaTableta === "matriz" ? "activo" : ""} onClick={() => setPestanaTableta("matriz")}>
                Matriz
              </button>
              <button className={pestanaTableta === "visor" ? "activo" : ""} onClick={() => setPestanaTableta("visor")}>
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
        <div className={`cuerpo ${lado && visorAbierto ? "dos" : "uno"}`}>
          {(lado || pestanaTableta === "matriz") && grilla}
          {((lado && visorAbierto) || (!lado && pestanaTableta === "visor")) && visor}
        </div>
        {cajon && (
          <div className="velo" onMouseDown={(e) => e.target === e.currentTarget && setCajon(false)}>
            <div className="cajon" onClick={(e) => (e.target as HTMLElement).closest(".nombre") && setCajon(false)}>
              {panel}
            </div>
          </div>
        )}
      </div>
    );
  }

  // Escritorio: barra lateral, tabla e inspector (plegable).
  return (
    <div className={`escritorio ${visorAbierto ? "con-visor" : "sin-visor"}`}>
      {panel}
      {grilla}
      {visorAbierto ? (
        visor
      ) : (
        <button className="desplegar-visor" onClick={() => setVisorAbierto(true)} title="Mostrar visor">
          <Icono nombre="visor" tam={18} />
          <span>Visor</span>
        </button>
      )}
    </div>
  );
}

export function App() {
  const qc = useQueryClient();
  const ancho = useAncho();
  const sesion = useQuery({
    queryKey: ["sesion"],
    queryFn: api.quien,
    retry: (n, e) => !(e instanceof ErrorApi && e.estado === 401) && n < 2,
  });
  const proyectos = useQuery({ queryKey: ["proyectos"], queryFn: api.proyectos, enabled: !!sesion.data });
  const salir = useMutation({ mutationFn: api.salir, onSuccess: () => qc.clear() });

  if (sesion.isLoading) return <p className="centro tenue">Cargando…</p>;
  if (!sesion.data) return <Entrar />;
  const proyecto = proyectos.data?.[0];

  return (
    <div className="app">
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
          <div className="cuenta">
            <span className="tenue">{sesion.data.correo}</span>
            <button className="sin-borde" onClick={() => salir.mutate()} title="Cerrar sesión">
              <Icono nombre="salir" tam={18} />
            </button>
          </div>
        </header>
      )}
      {proyecto ? (
        <Espacio pid={proyecto.id} correo={sesion.data.correo} onSalir={() => salir.mutate()} />
      ) : (
        <p className="centro tenue">Sin proyectos. Ejecute la semilla.</p>
      )}
      {proyecto && <DialogoRevision pid={proyecto.id} />}
    </div>
  );
}
