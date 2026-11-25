// Columnas de la matriz que importan y con qué prioridad (plan «Buscar», sección 5.1). Se guarda solo (en el perfil
// predeterminado) y la lista de candidatos se recalcula al instante: no vuelve a consultar ninguna fuente.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api";
import { mover, NIVELES, PRIORIDADES } from "../cobertura";
import type { ColumnaCatalogo, ColumnaElegida, Prioridad } from "../tipos";

type Borrador = { nombre: string; columnas: ColumnaElegida[] };

export function InsigniaNivel({ nivel }: { nivel: ColumnaCatalogo["nivel"] }) {
  return (
    <span className={`buscar-nivel nivel-${nivel}`} title={NIVELES[nivel]}>
      {nivel}
    </span>
  );
}

export function SelectorDeColumnas({ pid }: { pid: string }) {
  const cliente = useQueryClient();
  const catalogo = useQuery({ queryKey: ["busqueda-columnas", pid], queryFn: () => api.busquedaColumnas(pid), staleTime: 300_000 });
  const perfiles = useQuery({ queryKey: ["perfiles", pid], queryFn: () => api.perfiles(pid) });
  const [borrador, setBorrador] = useState<Borrador | null>(null);
  const [tocado, setTocado] = useState(false);
  const [filtro, setFiltro] = useState("");
  const [nuevoNombre, setNuevoNombre] = useState("");

  useEffect(() => {
    if (!borrador && perfiles.data) setBorrador({ nombre: perfiles.data.activo.nombre, columnas: perfiles.data.activo.columnas });
  }, [borrador, perfiles.data]);

  const refrescar = () => {
    cliente.invalidateQueries({ queryKey: ["perfiles", pid] });
    cliente.invalidateQueries({ queryKey: ["candidatos", pid] });
  };
  const guardar = useMutation({
    mutationFn: (v: Borrador) => api.guardarPerfil(pid, v.nombre, v.columnas, true),
    onSuccess: refrescar,
  });
  const borrar = useMutation({
    mutationFn: (id: string) => api.borrarPerfil(pid, id),
    onSuccess: () => {
      setBorrador(null);
      refrescar();
    },
  });

  // Autoguardado con una pequeña espera, para no mandar una petición por cada clic.
  useEffect(() => {
    if (!tocado || !borrador || !borrador.columnas.length) return;
    const t = setTimeout(() => guardar.mutate(borrador), 700);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [borrador, tocado]);

  const porClave = useMemo(() => new Map((catalogo.data?.columnas ?? []).map((c) => [c.clave, c])), [catalogo.data]);
  // Dos columnas del libro pueden compartir encabezado de Excel («Fiabilidad Alfa - Omega»): ahí se muestra la clave.
  const repetidos = useMemo(() => {
    const cuenta = new Map<string, number>();
    for (const c of catalogo.data?.columnas ?? []) cuenta.set(c.encabezado, (cuenta.get(c.encabezado) ?? 0) + 1);
    return new Set([...cuenta].filter(([, n]) => n > 1).map(([e]) => e));
  }, [catalogo.data]);
  const rotulo = (c: ColumnaCatalogo) => (repetidos.has(c.encabezado) ? c.clave : c.encabezado);
  const grupos = useMemo(() => {
    const q = filtro.trim().toLowerCase();
    return (catalogo.data?.grupos ?? []).map((g) => ({
      grupo: g,
      columnas: (catalogo.data?.columnas ?? []).filter(
        (c) => c.grupo === g && (!q || c.encabezado.toLowerCase().includes(q) || c.clave.toLowerCase().includes(q)),
      ),
    }));
  }, [catalogo.data, filtro]);

  if (catalogo.isLoading || perfiles.isLoading || !borrador) return <p className="centro tenue">Cargando columnas…</p>;
  if (catalogo.error || perfiles.error) return <p className="error">{((catalogo.error || perfiles.error) as Error).message}</p>;
  const lista = perfiles.data!;
  const elegidas = borrador.columnas;
  const editar = (columnas: ColumnaElegida[]) => {
    setBorrador({ ...borrador, columnas });
    setTocado(true);
  };
  const guardados = lista.perfiles.find((p) => p.nombre === borrador.nombre);
  const nombres = lista.perfiles.length ? lista.perfiles.map((p) => p.nombre) : [borrador.nombre];
  const estadoGuardado = guardar.isPending ? "Guardando…" : guardar.error ? (guardar.error as Error).message : tocado ? "Guardado" : "";

  return (
    <div className="buscar-columnas">
      <section className="buscar-tarjeta">
        <header>
          <strong>Perfil de columnas</strong>
          <span className={guardar.error ? "error" : "tenue"} aria-live="polite">{estadoGuardado}</span>
        </header>
        <div className="fila">
          <select
            aria-label="Perfil activo"
            value={borrador.nombre}
            onChange={(e) => {
              const p = lista.perfiles.find((x) => x.nombre === e.target.value);
              if (!p) return;
              setBorrador({ nombre: p.nombre, columnas: p.columnas });
              setTocado(false);
              guardar.mutate({ nombre: p.nombre, columnas: p.columnas });
            }}
          >
            {nombres.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          {guardados && lista.perfiles.length > 1 && (
            <button className="sin-borde" onClick={() => borrar.mutate(guardados.id)} disabled={borrar.isPending}>
              Borrar
            </button>
          )}
        </div>
        <div className="fila">
          <input
            placeholder="Guardar como… (p. ej. Solo identificación)"
            value={nuevoNombre}
            onChange={(e) => setNuevoNombre(e.target.value)}
            aria-label="Nombre del perfil nuevo"
          />
          <button
            disabled={!nuevoNombre.trim() || !elegidas.length || guardar.isPending}
            onClick={() => {
              const v = { nombre: nuevoNombre.trim(), columnas: elegidas };
              setBorrador(v);
              setNuevoNombre("");
              setTocado(false);
              guardar.mutate(v);
            }}
          >
            Guardar
          </button>
        </div>
        <button className="sin-borde" onClick={() => editar(lista.inicial.columnas)}>
          Volver a la propuesta inicial
        </button>
      </section>

      <section className="buscar-tarjeta">
        <header>
          <strong>Elegidas · {elegidas.length}</strong>
          <span className="tenue">en este orden</span>
        </header>
        {!elegidas.length && <p className="tenue">Marque al menos una columna abajo.</p>}
        <ol className="buscar-elegidas">
          {elegidas.map((c, i) => {
            const det = porClave.get(c.clave);
            return (
              <li key={c.clave} className={`p-${c.prioridad}`}>
                <span className="orden">
                  <button className="sin-borde" aria-label={`Subir ${c.clave}`} disabled={i === 0} onClick={() => editar(mover(elegidas, i, -1))}>
                    ▲
                  </button>
                  <button className="sin-borde" aria-label={`Bajar ${c.clave}`} disabled={i === elegidas.length - 1} onClick={() => editar(mover(elegidas, i, 1))}>
                    ▼
                  </button>
                </span>
                <span className="nombre" title={c.clave}>{det ? rotulo(det) : c.clave}</span>
                {det && <InsigniaNivel nivel={det.nivel} />}
                <select
                  aria-label={`Prioridad de ${c.clave}`}
                  value={c.prioridad}
                  onChange={(e) => editar(elegidas.map((x, j) => (j === i ? { ...x, prioridad: e.target.value as Prioridad } : x)))}
                >
                  {PRIORIDADES.map(([v, t]) => (
                    <option key={v} value={v}>
                      {t}
                    </option>
                  ))}
                </select>
                <button className="sin-borde" aria-label={`Quitar ${c.clave}`} onClick={() => editar(elegidas.filter((_x, j) => j !== i))}>
                  ✕
                </button>
              </li>
            );
          })}
        </ol>
        <p className="tenue">
          M metadato · R resumen · T solo el PDF. Una columna que solo el PDF puede juzgar queda «pendiente»: no cuenta
          como ausente.
        </p>
      </section>

      <section className="buscar-tarjeta">
        <header>
          <strong>Columnas de la matriz</strong>
        </header>
        <input type="search" placeholder="Filtrar columnas" value={filtro} onChange={(e) => setFiltro(e.target.value)} aria-label="Filtrar columnas" />
        {grupos.map(
          ({ grupo, columnas }) =>
            columnas.length > 0 && (
              <details key={grupo} open={!!filtro.trim() || grupo === "Datos bibliográficos"}>
                <summary>
                  {grupo} <span className="tenue">({columnas.filter((c) => elegidas.some((e) => e.clave === c.clave)).length}/{columnas.length})</span>
                </summary>
                <ul className="buscar-catalogo">
                  {columnas.map((c) => {
                    const marcada = elegidas.some((e) => e.clave === c.clave);
                    return (
                      <li key={c.clave}>
                        <label className="fila" title={c.elegible ? c.clave : "Interna: la asigna el equipo o el programa; no se elige"}>
                          <input
                            type="checkbox"
                            checked={marcada}
                            disabled={!c.elegible}
                            onChange={(e) =>
                              editar(e.target.checked ? [...elegidas, { clave: c.clave, prioridad: "DESEABLE" }] : elegidas.filter((x) => x.clave !== c.clave))
                            }
                          />
                          <span className="nombre">{rotulo(c)}</span>
                          <InsigniaNivel nivel={c.nivel} />
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </details>
            ),
        )}
      </section>
    </div>
  );
}
