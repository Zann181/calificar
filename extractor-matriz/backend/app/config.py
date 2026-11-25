"""Configuración leída de variables de entorno (ver .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_REPO = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # env_ignore_empty: una variable vacía en .env (TOPE_TOKENS_MENSUAL=) toma el valor por defecto.
    model_config = SettingsConfigDict(env_file=(RAIZ_REPO / ".env", ".env"), extra="ignore", env_ignore_empty=True)

    # ADR 0009. «local»: la aplicación de escritorio de siempre. «nube»: réplica de solo lectura (sin despachador, sin
    # ejecutor de extracciones, sin conversión) con los archivos dentro de la base de datos.
    modo: Literal["local", "nube"] = "local"
    # True: los archivos van a la tabla biblioteca_archivos (bytea) en lugar de disco o S3. En modo nube siempre.
    almacen_en_base: bool = False

    # --- Solo MODO=nube (ADR 0009, sección 8). Falla cerrada: sin estos cuatro datos la nube no arranca. ---
    # Correos (separados por coma) que pueden entrar al visor con su cuenta de Google.
    lectores_permitidos: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    # Firma la cookie de sesión de los lectores (cadena larga y aleatoria).
    secreto_sesion: str = ""
    # SHA-256 (hex) del token de servicio del agente local: `python -m app.cli token-sync` lo genera.
    sync_token_hash: str = ""
    # URL pública de la nube (https://….onrender.com): el retorno de Google vuelve a ella.
    url_publica: str = ""

    database_url: str = "postgresql+psycopg://extractor:extractor@localhost:5432/extractor"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:9000"
    s3_endpoint_publico: str | None = None  # host que ve el navegador para las URL firmadas
    s3_bucket: str = "biblioteca"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    # Sin Docker (ADR 0003): si ALMACEN_DIR está definido, los archivos van a esa carpeta en lugar de S3.
    almacen_dir: Path | None = None

    mineru_url: str = "http://localhost:8001"
    mineru_tiempo_max: int = 1800
    # Entorno de Python de servicio-mineru; el lanzador lo arranca si existe.
    mineru_python: Path = RAIZ_REPO / "servicio-mineru" / ".venv" / "Scripts" / "python.exe"

    # Modelo de lenguaje: Claude Code CLI (ADR 0002). El portero elige el nivel de cada llamada (ADR 0005);
    # Opus no se admite.
    claude_cli: str = "claude"
    modelo_especializado: str = "claude-sonnet-5-5"
    modelo_ligero: str = "claude-haiku-5-5"

    concurrencia_extraccion: int = 2
    # Extracciones simultáneas lanzadas desde la interfaz (cada una cuesta ~7 USD y ~11 min); las demás esperan.
    extracciones_en_paralelo: int = 1
    # Cuánto espera un pedido de extraer a que su PDF se convierta (MinerU apagado u ocupado), en segundos.
    espera_conversion_max: int = 5400
    umbral_similitud: int = 95
    max_iteraciones_validador: int = 3
    umbral_acuerdo: float = 0.80
    tope_tokens_mensual: int | None = None

    # Usuario local: la API entra sola como este usuario (firma las revisiones). No hay login.
    admin_correo: str = "admin@local.test"
    admin_nombre: str = "Administrador"
    proyecto_nombre: str = "Felicidad y desempeño"

    recursos_dir: Path = RAIZ_REPO / "recursos"
    # Interfaz compilada (npm run build). Si existe, la API la sirve en "/" y basta un solo proceso.
    interfaz_dir: Path = RAIZ_REPO / "frontend" / "dist"
    cors_origenes: str = "http://localhost:5173"
    # Registro de eventos que muestra la interfaz (una línea JSON por evento).
    # El servidor corre el despachador de eventos en un hilo (conversión al cargar, filas al extraer).
    despachador_en_servidor: bool = True
    # False (por defecto): un PDF cargado queda en Nuevo hasta que la persona pulsa su estado; entonces se convierte
    # y se extrae de corrido. True: el despachador convierte cada PDF al cargarlo, sin esperar ese clic.
    convertir_al_cargar: bool = False
    registro_ruta: Path = RAIZ_REPO / "datos" / "registro.jsonl"

    @field_validator("database_url")
    @classmethod
    def _url_con_controlador(cls, v: str) -> str:
        """Neon y otros proveedores entregan «postgresql://» o «postgres://»; SQLAlchemy necesita el controlador psycopg."""
        for prefijo in ("postgres://", "postgresql://"):
            if v.startswith(prefijo):
                return "postgresql+psycopg://" + v[len(prefijo):]
        return v

    @property
    def lectores(self) -> set[str]:
        return {c.strip().lower() for c in self.lectores_permitidos.split(",") if c.strip()}

    def faltantes_de_nube(self) -> list[str]:
        """Variables que MODO=nube exige y no están (vacío si todo está o si el modo es local)."""
        if self.modo != "nube":
            return []
        pedidas = {"LECTORES_PERMITIDOS": bool(self.lectores), "GOOGLE_CLIENT_ID": bool(self.google_client_id),
                   "GOOGLE_CLIENT_SECRET": bool(self.google_client_secret),
                   "SECRETO_SESION": len(self.secreto_sesion) >= 32, "SYNC_TOKEN_HASH": bool(self.sync_token_hash),
                   "URL_PUBLICA": bool(self.url_publica)}
        return [k for k, ok in pedidas.items() if not ok]

    @property
    def libro_de_codigos(self) -> Path:
        return self.recursos_dir / "Libro_de_codigos_extraccion_v2.json"


@lru_cache
def settings() -> Settings:
    return Settings()
