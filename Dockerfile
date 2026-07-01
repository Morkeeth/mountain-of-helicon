FROM node:22-slim AS frontend
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
COPY glaze/ glaze/
COPY config.example.json config.json
COPY scripts/ scripts/
COPY --from=frontend /app/web/dist /app/static

RUN mkdir -p data

EXPOSE 8420

CMD ["python3", "-m", "uvicorn", "glaze.api.app:app", "--host", "0.0.0.0", "--port", "8420"]
