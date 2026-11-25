# ADR 0009: imagen de la nube de solo lectura (MODO=nube). Contexto de construcción: esta carpeta (extractor-matriz).
# En Render: servicio Docker, «Root Directory» = extractor-matriz, plan Free. Variables en .env.nube.example.
# Sin probar todavía en un motor de contenedores (compuerta 0.2 pendiente de la cuenta de Render).

FROM node:22-slim AS interfaz
WORKDIR /interfaz
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MODO=nube
# La disposición /srv/{backend,recursos,frontend/dist} es la del repositorio: app/config.py deduce de ahí las rutas.
WORKDIR /srv/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir -e .
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY recursos /srv/recursos
COPY --from=interfaz /interfaz/dist /srv/frontend/dist

# Render inyecta PORT. Las migraciones corren al arrancar; el servidor queda detrás del proxy de Render.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
