# AgentCore Runtime container for the SRE agents (ARM64, non-root, port per protocol).
#
# One image builds any agent; AGENT_MODULE + PORT select which runtime to run:
#   supervisor (HTTP) : AGENT_MODULE=agents.supervisor.main           PORT=8080
#   investigator (A2A): AGENT_MODULE=agents.investigator.main         PORT=9000
#   telemetry (A2A)   : AGENT_MODULE=agents.telemetry.main            PORT=9000
#   change (A2A)      : AGENT_MODULE=agents.change_correlation.main   PORT=9000
#   remediation (A2A) : AGENT_MODULE=agents.remediation.main          PORT=9000
#
# Build (from PRODUCTION/use-cases/sre):
#   docker buildx build --platform linux/arm64 -f agents/Dockerfile \
#     --build-arg AGENT_MODULE=agents.supervisor.main --build-arg PORT=8080 \
#     -t sre-supervisor:latest .

FROM --platform=linux/arm64 python:3.12-slim-bookworm

# Security patches
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Deps first (layer caching)
COPY agents/requirements.txt /app/agents/requirements.txt
RUN pip install --no-cache-dir -r /app/agents/requirements.txt

# App code (agents + the synthetic-data loader is NOT needed in agents; tools run separately)
COPY agents /app/agents

# Non-root per AgentCore container contract
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

ENV PYTHONPATH=/app
ARG AGENT_MODULE=agents.supervisor.main
ARG PORT=8080
ENV AGENT_MODULE=${AGENT_MODULE}
ENV PORT=${PORT}
EXPOSE ${PORT}

# Each main.py exposes `app` (FastAPI) and binds 0.0.0.0:$PORT
CMD ["sh", "-c", "python3 -m uvicorn ${AGENT_MODULE}:app --host 0.0.0.0 --port ${PORT}"]
