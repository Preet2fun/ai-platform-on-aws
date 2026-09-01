# syntax=docker/dockerfile:1
# AgentCore runtime image for dev_cloudwatch_mcp (protocol MCP)
FROM public.ecr.aws/docker/library/python:3.11-slim

WORKDIR /app

# OpenTelemetry auto-instrumentation (traces -> X-Ray / Application Signals)
ENV PYTHONUNBUFFERED=1

# Install shared lib + this agent's deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code (shared lib + this agent package are copied by the build context)
COPY . .

# AgentCore invokes the entrypoint; opentelemetry-instrument wraps it for tracing.
CMD ["opentelemetry-instrument", "python", "-m", "agents.cloudwatch_mcp.cloudwatch_mcp"]
