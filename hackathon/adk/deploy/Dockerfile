# Cloud Run agent — build from repo root:
#   docker build -f hackathon/adk/deploy/Dockerfile -t helicon-agent .
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY helicon ./helicon
RUN pip install --no-cache-dir -e . google-cloud-firestore

COPY hackathon/adk/demo/helicon.db /app/demo/helicon.db
COPY hackathon/adk/agent/main.py /app/agent/main.py
COPY hackathon/adk/agent/firestore_store.py /app/agent/firestore_store.py

ENV HELICON_DEMO_DB=/app/demo/helicon.db
ENV HELICON_REPO=/app
EXPOSE 8080

WORKDIR /app/agent
CMD ["python3", "main.py"]
