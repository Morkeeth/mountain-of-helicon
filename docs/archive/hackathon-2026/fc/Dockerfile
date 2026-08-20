# Function Compute custom-container image for Mount Helicon's read-only
# dashboard + API. Build context is the REPO ROOT (see deploy-fc.sh):
#   docker build -f fc/Dockerfile -t <image> .
# Lean by design — no torch/sentence-transformers (see fc/requirements.txt).
FROM python:3.12-slim

WORKDIR /app

# Deps first for layer caching.
COPY fc/requirements.txt ./fc/requirements.txt
RUN pip install --no-cache-dir -r fc/requirements.txt

# App code.
COPY helicon/ ./helicon/
COPY fc/config.fc.json ./fc/config.fc.json
COPY fc/entrypoint.sh ./fc/entrypoint.sh
RUN chmod +x ./fc/entrypoint.sh

# Prebuilt dashboard bundle (served by FastAPI from static/). Built locally with
# `cd web && npx vite build` — the image never runs Node.
COPY web/dist/ ./static/

# The SEEDED demo store (scripts/demo_seed.py), read-only baseline. entrypoint
# copies it to /tmp on boot so SQLite can open it writable.
#
# This is deliberately NOT data/helicon.db. The FC trigger is authType:anonymous
# and the URL is submitted publicly, so whatever is baked here is published to
# the open internet — and the real store holds journal, finance, wallet, health
# and passport memories that must never leave this machine. The image layer is
# the leak even behind an app password: anyone who pulls it has the file.
#
# "Zero fake data" is earned by the LOCAL run in the demo and by ROT.md, not by
# hosting a private life at an anonymous URL. The deploy is a DEPLOYMENT proof.
COPY data/helicon-demo.db ./data/helicon.db

# FC web function: container listens on this port, FC's http trigger forwards to
# it. Matches customContainerConfig.port in s.yaml.
ENV PORT=9000
EXPOSE 9000

ENTRYPOINT ["/app/fc/entrypoint.sh"]
