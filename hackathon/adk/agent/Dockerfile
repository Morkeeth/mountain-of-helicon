# Stub only — deployment wiring belongs to a later slice.
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY helicon ./helicon
RUN pip install --no-cache-dir -e .

COPY hackathon/adk/demo/helicon.db /app/demo/helicon.db
COPY hackathon/adk/agent/main.py /app/agent/main.py

ENV HELICON_DEMO_DB=/app/demo/helicon.db
ENV HELICON_REPO=/app
EXPOSE 8080

CMD ["python3", "/app/agent/main.py"]
