# Synthetic observability backends container (ARM64, non-root).
# Serves the tenant-scoped fixtures to the agents' tool calls. In P4 this is fronted by the
# AgentCore Gateway as MCP tools; the FastAPI app is the OpenAPI source for the MCP contract.
#
# Build (from PRODUCTION/use-cases/sre):
#   docker buildx build --platform linux/arm64 -f tools/Dockerfile -t sre-tools:latest .

FROM --platform=linux/arm64 python:3.12-slim-bookworm

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY tools/requirements.txt /app/tools/requirements.txt
RUN pip install --no-cache-dir -r /app/tools/requirements.txt

# App code + the fixtures it serves
COPY tools /app/tools
COPY synthetic-data /app/synthetic-data

RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

ENV PYTHONPATH=/app
ENV SRE_SYNTH_DATA_ROOT=/app/synthetic-data/tenants
EXPOSE 8080
CMD ["python3", "-m", "uvicorn", "tools.common.app:app", "--host", "0.0.0.0", "--port", "8080"]
