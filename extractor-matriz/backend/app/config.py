"""Configuración leída de variables de entorno (ver .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_REPO = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # env_ignore_empty: una variable vacía en .env (TOPE_TOKENS_MENSUAL=) toma el valor por defecto.
    model_config = SettingsConfigDict(env_file=(RAIZ_REPO / ".env", ".env"), extra="ignore", env_ignore_empty=True)

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

    @property
    def libro_de_codigos(self) -> Path:
        return self.recursos_dir / "Libro_de_codigos_extraccion_v2.json"


@lru_cache
def settings() -> Settings:
    return Settings()
