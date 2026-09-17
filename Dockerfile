# AI CFO Platform — container image.
#
# SECURITY: this image NEVER contains real credentials. .env is excluded
# via .dockerignore, and secrets are injected at CONTAINER RUNTIME via
# docker-compose's env_file/environment, not baked into any image layer.
# Baking secrets into an image is a well-known bad practice — even a
# later "delete the file" step doesn't remove it from earlier layers.
# config/settings.py's load_dotenv() never overrides variables already
# present in the environment, so runtime-injected env vars work with
# zero code changes.
#
# This image is shared by both services in docker-compose.yml (the
# dashboard and the risk monitor) — same codebase, same dependencies,
# different entrypoints chosen at `docker run`/compose time.

FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (separate layer) so code changes don't
# force a full dependency reinstall on every rebuild.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Streamlit's default port. The risk-monitor service (see
# docker-compose.yml) doesn't serve HTTP at all — this EXPOSE is a
# no-op for that service, harmless either way.
EXPOSE 8501

# No default CMD — docker-compose.yml specifies the actual command per
# service (streamlit for the dashboard, python scripts/monitor_risk.py
# for the monitor). Running this image directly without a command will
# just show Python's own "no command" behavior, which is intentional:
# forces whoever runs this to be explicit about which service they mean.
