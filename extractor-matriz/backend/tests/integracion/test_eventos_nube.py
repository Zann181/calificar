"""Eventos del servidor (SSE) de la nube, ADR 0009 Fase 2. Necesitan un lazo de asyncio (abre sockets internos), por
eso viven con las de integración y no con las unitarias, que corren sin red."""

from __future__ import annotations


# ------------------------------------------------------------------------- eventos del servidor (Fase 2)
def test_difusor_reparte_la_revision_mas_reciente_a_cada_conexion() -> None:
    import asyncio
    import threading

    from app.eventos_nube import Difusor

    async def prueba() -> None:
        d = Difusor()
        a, b = d.suscribir(), d.suscribir()
        assert d.conexiones == 2
        # Desde otro hilo, como un lote que se aplica en la nube.
        hilo = threading.Thread(target=lambda: [d.publicar(5), d.publicar(6)])
        hilo.start()
        hilo.join()
        await asyncio.sleep(0.05)
        assert await asyncio.wait_for(a.get(), 1) == 6 and await asyncio.wait_for(b.get(), 1) == 6  # solo la última
        d.desuscribir(a)
        d.publicar(7)
        await asyncio.sleep(0.05)
        assert a.empty() and await asyncio.wait_for(b.get(), 1) == 7 and d.conexiones == 1

    asyncio.run(prueba())


def test_flujo_manda_la_revision_actual_luego_los_cambios_y_latidos() -> None:
    import asyncio

    from app.eventos_nube import Difusor, flujo

    async def prueba() -> None:
        d = Difusor()

        async def actual() -> int:
            return 3

        async def desconectado() -> bool:
            return False

        g = flujo(d, actual, desconectado, latido_s=0.05)
        assert await g.__anext__() == "retry: 5000\n\n"
        assert (await g.__anext__()) == 'event: revision\ndata: {"revision": 3}\n\n'
        assert await g.__anext__() == ": latido\n\n"  # sin novedades: latido
        d.publicar(4)
        assert 'data: {"revision": 4}' in await g.__anext__()
        await g.aclose()
        assert d.conexiones == 0  # al cerrarse la conexión se da de baja

    asyncio.run(prueba())


def test_flujo_termina_si_el_cliente_se_desconecta() -> None:
    import asyncio

    from app.eventos_nube import Difusor, flujo

    async def prueba() -> None:
        d = Difusor()

        async def actual() -> int:
            return 1

        async def desconectado() -> bool:
            return True

        salida = [x async for x in flujo(d, actual, desconectado, latido_s=0.02)]
        assert len(salida) == 2 and d.conexiones == 0

    asyncio.run(prueba())
