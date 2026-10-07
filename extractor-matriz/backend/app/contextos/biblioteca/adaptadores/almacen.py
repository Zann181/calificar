"""Adaptadores de AlmacenDeArchivos: S3 (MinIO), en disco (equipo sin Docker, ADR 0003) y en memoria (pruebas)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class AlmacenS3:
    def __init__(self, *, endpoint: str, bucket: str, access_key: str, secret_key: str,
                 endpoint_publico: str | None = None) -> None:
        import boto3
        from botocore.config import Config

        cfg = Config(signature_version="s3v4", s3={"addressing_style": "path"})
        self._bucket = bucket
        self._cliente: Any = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access_key,
                                          aws_secret_access_key=secret_key, config=cfg, region_name="us-east-1")
        # Las URL firmadas deben usar el host que ve el navegador, no el de la red de Docker.
        self._firmador: Any = self._cliente if not endpoint_publico else boto3.client(
            "s3", endpoint_url=endpoint_publico, aws_access_key_id=access_key, aws_secret_access_key=secret_key,
            config=cfg, region_name="us-east-1")

    def asegurar_bucket(self) -> None:
        existentes = {b["Name"] for b in self._cliente.list_buckets().get("Buckets", [])}
        if self._bucket not in existentes:
            self._cliente.create_bucket(Bucket=self._bucket)

    def guardar(self, clave: str, datos: bytes, tipo: str) -> None:
        self._cliente.put_object(Bucket=self._bucket, Key=clave, Body=datos, ContentType=tipo)

    def leer(self, clave: str) -> bytes:
        datos: bytes = self._cliente.get_object(Bucket=self._bucket, Key=clave)["Body"].read()
        return datos

    def existe(self, clave: str) -> bool:
        try:
            self._cliente.head_object(Bucket=self._bucket, Key=clave)
            return True
        except Exception:
            return False

    def url_temporal(self, clave: str, segundos: int = 900) -> str:
        url: str = self._firmador.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": clave}, ExpiresIn=segundos)
        return url


class AlmacenEnDisco:
    """Guarda cada objeto como archivo bajo una carpeta raíz. No emite URL web: la API sirve los bytes."""

    def __init__(self, raiz: Path) -> None:
        self._raiz = raiz.resolve()
        self._raiz.mkdir(parents=True, exist_ok=True)

    def _ruta(self, clave: str) -> Path:
        ruta = (self._raiz / clave).resolve()
        if not ruta.is_relative_to(self._raiz):
            raise ValueError(f"Clave fuera del almacén: {clave}")
        return ruta

    def guardar(self, clave: str, datos: bytes, tipo: str) -> None:
        ruta = self._ruta(clave)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(datos)

    def leer(self, clave: str) -> bytes:
        return self._ruta(clave).read_bytes()

    def existe(self, clave: str) -> bool:
        return self._ruta(clave).is_file()

    def url_temporal(self, clave: str, segundos: int = 900) -> str:
        return f"disco://{clave}"


class AlmacenEnMemoria:
    def __init__(self) -> None:
        self.objetos: dict[str, tuple[bytes, str]] = {}

    def guardar(self, clave: str, datos: bytes, tipo: str) -> None:
        self.objetos[clave] = (datos, tipo)

    def leer(self, clave: str) -> bytes:
        try:
            return self.objetos[clave][0]
        except KeyError as e:
            raise FileNotFoundError(clave) from e

    def existe(self, clave: str) -> bool:
        return clave in self.objetos

    def url_temporal(self, clave: str, segundos: int = 900) -> str:
        return f"memoria://{clave}?expira={segundos}"
