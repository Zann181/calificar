"""¿El enlace entrega de verdad un PDF, sin pagar ni iniciar sesión? (ADR 0013)

Pide solo los primeros bytes y mira que empiecen por `%PDF`: no descarga el artículo. Respeta `robots.txt`; si el sitio
lo prohíbe, pide una sesión o bloquea a los programas, la respuesta es «no» y no se busca otra forma de entrar.

Varios enlaces se prueban a la vez, pero a cada servidor se le sigue preguntando de uno en uno y con la misma pausa: eso
lo garantiza el cliente cortés.
"""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

from app.contextos.descubrimiento.adaptadores.cliente_http import ClienteCortes

INICIO_DE_PDF = b"%PDF"
SERVIDORES_A_LA_VEZ = 8


class ComprobadorDePdfEnLinea:
    def __init__(self, cliente: ClienteCortes) -> None:
        self._cliente = cliente

    def entrega(self, url: str) -> bool:
        inicio = self._cliente.primeros_bytes(url, 8)
        return inicio is not None and inicio.startswith(INICIO_DE_PDF)

    def entregan(self, urls: Sequence[str]) -> dict[str, bool]:
        unicas = list(dict.fromkeys(urls))
        with ThreadPoolExecutor(max_workers=SERVIDORES_A_LA_VEZ, thread_name_prefix="pdf") as hilos:
            return dict(zip(unicas, hilos.map(self.entrega, unicas), strict=True))
