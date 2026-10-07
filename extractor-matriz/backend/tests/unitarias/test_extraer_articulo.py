"""Caso de uso ExtraerArticulo (sección 8.3) con puertos falsos: sin base de datos, red ni modelo."""

from __future__ import annotations

import json
import uuid
from typing import Any, Self

import pytest

from app.compartido.dominio import NoEncontrado
from app.contextos.extraccion.adaptadores.modelo_grabado import ModeloGrabado
from app.contextos.extraccion.aplicacion.casos_de_uso import ExtraerArticulo, OpcionesDeExtraccion
from app.contextos.extraccion.dominio.extraccion import Auditor, EstadoExtraccion, EstadoHallazgo, Extraccion
from app.contextos.extraccion.eventos import ExtraccionCompletada, ExtraccionFallida
from app.contextos.extraccion.puertos import ArticuloParaExtraer, LibroVigente, ResultadoValidacion

PID, AID = uuid.uuid4(), uuid.uuid4()

DOCUMENTO = {"bloques": [
    {"id": "p03-b01", "pagina": 3, "tipo": "parrafo", "rect": [0, 0, 100, 20],
     "texto": "The study is based on a sample of 395 teachers.", "tabla": None},
    {"id": "p03-b02", "pagina": 3, "tipo": "parrafo", "rect": [0, 30, 100, 50],
     "texto": "A sample of 400 teachers was invited.", "tabla": None},
    {"id": "p04-b01", "pagina": 4, "tipo": "figura", "rect": [0, 0, 100, 100], "texto": "", "tabla": None},
    {"id": "p04-b02", "pagina": 4, "tipo": "parrafo", "rect": [0, 0, 100, 100], "texto": "", "tabla": None},
]}


def _salida(muestra: int, cita: str, bloque: str) -> list[dict[str, Any]]:
    return [{"fila": {"Documento": 1, "Estudio": 72, "Muestra": muestra, "Nivel": "Individual"},
             "trazabilidad": {"evidencia": {"Muestra": [
                 {"pagina_pdf": 3, "ubicacion": "Método", "fila_tabla": None, "columna_tabla": None,
                  "cita_textual": cita, "leido_de_figura": False, "bloque_id": bloque}]}}}]


SALIDA = _salida(395, "sample of 395 teachers", "p03-b01")


class Fuente:
    def __init__(self) -> None:
        self.eventos: list[str] = []

    def obtener(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> ArticuloParaExtraer:
        return ArticuloParaExtraer(articulo_id=articulo_id, nombre_archivo="a.pdf", pdf=b"%PDF", documento=DOCUMENTO)

    def iniciar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, *, confirmar_reextraccion: bool,
                motivo: str | None) -> None:
        self.eventos.append("EXTRAYENDO")

    def pasar_a_auditoria(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> None:
        self.eventos.append("AUDITANDO")

    def fallar(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID, paso: str, mensaje: str) -> None:
        self.eventos.append(f"ERROR en {paso}")


class Normas:
    def libro_activo(self, proyecto_id: uuid.UUID) -> LibroVigente:
        return LibroVigente(id=uuid.uuid4(), contenido={"prompt_para_el_extractor": "Documento = <n>, Estudio inicial = <n>",
                                                        "columnas": {"Muestra": {"instruccion_operativa": "N analizado"}}})


class Numeracion:
    def siguiente(self, proyecto_id: uuid.UUID) -> int:
        return 72


class Validador:
    """Devuelve los resultados en orden; después, sin errores."""

    def __init__(self, *errores: list[str]) -> None:
        self._errores = list(errores)
        self.validadas: list[list[dict[str, Any]]] = []

    def comprobar(self) -> None:
        pass

    def validar(self, salida: list[dict[str, Any]], libro: dict[str, Any], pdf: bytes | None) -> ResultadoValidacion:
        self.validadas.append(salida)
        return ResultadoValidacion(errores=self._errores.pop(0) if self._errores else [], avisos=[])


class Lector:
    def __init__(self) -> None:
        self.pedidos: dict[str, Any] = {}

    def textos_en_rect(self, pdf: bytes, rects: dict[str, Any]) -> dict[str, str]:
        self.pedidos = rects
        return {k: "texto de la capa" for k in rects}

    def renderizar(self, pdf: bytes, paginas: list[int], ppp: int = 110) -> dict[int, bytes]:
        return {p: b"PNG" for p in paginas}


class Repositorio:
    def __init__(self, udt: Udt) -> None:
        self._udt = udt

    def agregar(self, e: Extraccion) -> None:
        self._udt.seguidos.append(e)

    def obtener(self, proyecto_id: uuid.UUID, extraccion_id: uuid.UUID) -> Extraccion:
        try:
            return self._udt.guardadas[extraccion_id]
        except KeyError as err:
            raise NoEncontrado(str(extraccion_id)) from err

    def de_articulo(self, proyecto_id: uuid.UUID, articulo_id: uuid.UUID) -> list[Extraccion]:
        return [e for e in self._udt.guardadas.values() if e.articulo_id == articulo_id]


class Udt:
    def __init__(self) -> None:
        self.guardadas: dict[uuid.UUID, Extraccion] = {}
        self.publicados: list[Any] = []
        self.seguidos: list[Extraccion] = []
        self.extracciones = Repositorio(self)

    def __enter__(self) -> Self:
        self.seguidos = []
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def seguir(self, agregado: Any) -> None:
        self.seguidos.append(agregado)

    def confirmar(self) -> None:
        for e in self.seguidos:
            self.guardadas[e.id] = e
            self.publicados += e.extraer_eventos()

    def revertir(self) -> None:
        return None


def _caso(modelo: ModeloGrabado, validador: Validador) -> tuple[ExtraerArticulo, Udt, Fuente, Lector]:
    udt, fuente, lector = Udt(), Fuente(), Lector()
    caso = ExtraerArticulo(lambda: udt, fuente, Normas(), Numeracion(), modelo, validador, lector)
    return caso, udt, fuente, lector


PENDIENTE = json.dumps({"decision": "PENDIENTE", "razonamiento": "Los bloques no alcanzan"})


def test_extraccion_completa_sin_diferencias() -> None:
    modelo = ModeloGrabado(por_rol={"extractor": json.dumps(SALIDA), "auditor": "[]", "ciego": json.dumps(SALIDA)})
    caso, udt, fuente, lector = _caso(modelo, Validador())
    r = caso.ejecutar(PID, AID, OpcionesDeExtraccion(documento=1))
    assert r.estado == "COMPLETADA" and r.estudios == [72] and r.acuerdo == 1.0
    assert r.anclas["VERIFICADA"] == 1
    assert fuente.eventos == ["EXTRAYENDO", "AUDITANDO"]
    assert [type(e) for e in udt.publicados] == [ExtraccionCompletada]
    # El extractor recibió los datos del equipo, el texto etiquetado y la página con figura.
    sistema_y_mensaje = [m for rol, m in modelo.llamadas if rol == "extractor"][0]
    assert "[p03-b01 | parrafo] The study is based on a sample of 395 teachers." in sistema_y_mensaje
    assert "pag-04.png" in sistema_y_mensaje
    assert "[p04-b02 | parrafo] texto de la capa" in sistema_y_mensaje
    assert set(lector.pedidos) == {"p04-b02"}  # H1: solo el bloque vacío
    assert "Estudio inicial = 72" in [m for rol, m in modelo.llamadas if rol == "ciego"][0]


def test_errores_del_validador_se_reenvian_al_extractor() -> None:
    modelo = ModeloGrabado(por_rol={"extractor": [json.dumps(_salida(395, "inventada", "p03-b01")), json.dumps(SALIDA)],
                                    "auditor": "[]", "ciego": json.dumps(SALIDA)})
    caso, udt, _, _ = _caso(modelo, Validador(["V23 fila 1: la cita no aparece en el PDF"]))
    r = caso.ejecutar(PID, AID, OpcionesDeExtraccion(documento=1))
    assert r.estado == "COMPLETADA"
    ext = udt.guardadas[r.extraccion_id]
    assert ext.iteraciones_validador == 2 and ext.uso_tokens["extractor"]["llamadas"] == 2
    correccion = [m for rol, m in modelo.llamadas if rol == "extractor"][1]
    assert "ERRORES DEL VALIDADOR" in correccion and "V23 fila 1" in correccion


def test_errores_persistentes_dejan_la_extraccion_fallida_sin_escribir() -> None:
    modelo = ModeloGrabado(por_rol={"extractor": json.dumps(SALIDA)})
    caso, udt, fuente, _ = _caso(modelo, Validador(["V3"], ["V3"], ["V3"]))
    r = caso.ejecutar(PID, AID, OpcionesDeExtraccion(documento=1))
    assert r.estado == "FALLIDA" and r.errores == ["V3"]
    ext = udt.guardadas[r.extraccion_id]
    assert ext.iteraciones_validador == 3 and ext.paso_fallido == "VALIDANDO"
    assert fuente.eventos == ["EXTRAYENDO", "ERROR en EXTRAYENDO"]
    assert [type(e) for e in udt.publicados] == [ExtraccionFallida]
    assert not any(rol == "auditor" for rol, _ in modelo.llamadas)


def test_respuesta_sin_json_falla_y_marca_el_articulo() -> None:
    caso, _, fuente, _ = _caso(ModeloGrabado(por_rol={"extractor": "No pude leer el PDF"}), Validador())
    r = caso.ejecutar(PID, AID, OpcionesDeExtraccion(documento=1))
    assert r.estado == "FALLIDA" and "RespuestaInvalida" in r.errores[0]
    assert fuente.eventos[-1] == "ERROR en EXTRAYENDO"


def test_conciliador_cambia_valor_con_cita_anclada_y_se_revalida() -> None:
    extractor = _salida(400, "sample of 400 teachers", "p03-b02")
    decision = {"decision": "VALOR_ALTERNATIVO", "valor": 395, "bloque_id": "p03-b01",
                "cita_textual": "sample of 395 teachers", "razonamiento": "El N analizado es 395."}
    modelo = ModeloGrabado(por_rol={"extractor": json.dumps(extractor), "auditor": "[]", "ciego": json.dumps(SALIDA),
                                    "conciliador": json.dumps(decision)})
    validador = Validador()
    caso, udt, _, _ = _caso(modelo, validador)
    r = caso.ejecutar(PID, AID, OpcionesDeExtraccion(documento=1))
    ext = udt.guardadas[r.extraccion_id]
    assert r.estado == "COMPLETADA" and r.acuerdo == 1.0
    assert ext.salida[0]["fila"]["Muestra"] == 395
    assert ext.salida[0]["trazabilidad"]["evidencia"]["Muestra"][0]["bloque_id"] == "p03-b01"
    assert len(validador.validadas) == 2  # extractor + conciliación
    [h] = ext.hallazgos
    assert h.auditor == Auditor.CODIFICADOR_CIEGO and h.estado == EstadoHallazgo.RESUELTO
    assert "395" in (h.resolucion or "")


def test_conciliacion_rechazada_por_el_validador_queda_pendiente() -> None:
    extractor = _salida(400, "sample of 400 teachers", "p03-b02")
    decision = {"decision": "VALOR_ALTERNATIVO", "valor": 395, "bloque_id": "p03-b01",
                "cita_textual": "sample of 395 teachers", "razonamiento": "x"}
    modelo = ModeloGrabado(por_rol={"extractor": json.dumps(extractor), "auditor": "[]", "ciego": json.dumps(SALIDA),
                                    "conciliador": json.dumps(decision)})
    caso, udt, _, _ = _caso(modelo, Validador([], ["V9: Muestra no coincide"]))
    r = caso.ejecutar(PID, AID, OpcionesDeExtraccion(documento=1))
    ext = udt.guardadas[r.extraccion_id]
    assert r.estado == "COMPLETADA" and ext.salida[0]["fila"]["Muestra"] == 400
    assert r.acuerdo is not None and r.acuerdo < 1
    assert [h.estado for h in ext.hallazgos] == [EstadoHallazgo.PENDIENTE, EstadoHallazgo.PENDIENTE]
    assert "no pasó el validador" in ext.hallazgos[1].detalle


@pytest.mark.parametrize("decision", [
    {"decision": "PENDIENTE", "razonamiento": "No alcanza"},
    {"decision": "VALOR_ALTERNATIVO", "valor": 395, "bloque_id": "p03-b01", "cita_textual": "cita inventada por el modelo"},
])
def test_refutado_del_auditor_sin_decision_firme_queda_pendiente(decision: dict[str, Any]) -> None:
    auditoria = [{"estudio": 72, "columna": "Muestra", "veredicto": "REFUTADO", "hallazgo": "El N es otro",
                  "evidencia": {"bloque_id": "p03-b01"}},
                 {"estudio": 72, "columna": "Nivel", "veredicto": "CONFIRMADO", "hallazgo": ""}]
    modelo = ModeloGrabado(por_rol={"extractor": json.dumps(SALIDA), "auditor": json.dumps(auditoria),
                                    "ciego": json.dumps(SALIDA), "conciliador": json.dumps(decision)})
    caso, udt, _, _ = _caso(modelo, Validador())
    r = caso.ejecutar(PID, AID, OpcionesDeExtraccion(documento=1))
    ext = udt.guardadas[r.extraccion_id]
    assert r.estado == "COMPLETADA" and ext.salida[0]["fila"]["Muestra"] == 395
    assert [h.auditor for h in ext.hallazgos] == [Auditor.AUDITOR_EVIDENCIA, Auditor.CONCILIADOR]
    assert all(h.estado == EstadoHallazgo.PENDIENTE for h in ext.hallazgos)
    assert r.hallazgos_pendientes == 2


def test_estudio_inicial_indicado_por_el_equipo() -> None:
    salida = json.dumps([{**SALIDA[0], "fila": {**SALIDA[0]["fila"], "Estudio": 5}}])
    modelo = ModeloGrabado(por_rol={"extractor": salida, "auditor": "[]", "ciego": salida})
    caso, udt, _, _ = _caso(modelo, Validador())
    r = caso.ejecutar(PID, AID, OpcionesDeExtraccion(documento=3, estudio_inicial=5, covidence=671))
    assert r.estudios == [5] and udt.guardadas[r.extraccion_id].estudios_reservados == [5]
    assert EstadoExtraccion.COMPLETADA.value == r.estado
