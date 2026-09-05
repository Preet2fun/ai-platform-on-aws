# app/core/telemetry.py
"""
OpenTelemetry instrumentation for the MSP Assistant API backend.
Sends traces to the OTLP endpoint (e.g., AWS X-Ray via ADOT collector,
or any OTLP-compatible backend).
"""

import os
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


def configure_telemetry(app):
    """Configure OpenTelemetry tracing for FastAPI.

    Enabled when OTEL_ENABLED=true is set in the environment.
    Sends traces via OTLP/HTTP to the configured endpoint.

    Environment variables:
        OTEL_ENABLED: Set to 'true' to enable tracing (default: false)
        OTEL_EXPORTER_OTLP_ENDPOINT: OTLP collector endpoint
            (default: http://localhost:4318 for local, or ADOT sidecar)
        OTEL_SERVICE_NAME: Service name in traces (default: msp-assistant-backend)
        OTEL_RESOURCE_ATTRIBUTES: Additional resource attributes
    """
    otel_enabled = os.getenv("OTEL_ENABLED", "false").lower() == "true"

    if not otel_enabled:
        logger.info("OpenTelemetry disabled (set OTEL_ENABLED=true to enable)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        service_name = settings.OTEL_SERVICE_NAME
        otlp_endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT

        # Create resource with service info
        resource = Resource.create({
            "service.name": service_name,
            "service.version": "2.0.0",
            "deployment.environment": os.getenv("ENVIRONMENT", "production"),
            "cloud.provider": "aws",
            "cloud.region": settings.AWS_REGION,
        })

        # Set up tracer provider
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Instrument FastAPI
        FastAPIInstrumentor.instrument_app(app)

        # Instrument outgoing HTTP calls
        HTTPXClientInstrumentor().instrument()
        RequestsInstrumentor().instrument()

        # Try botocore instrumentation (optional)
        try:
            from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
            BotocoreInstrumentor().instrument()
        except Exception:
            pass  # botocore instrumentation is optional

        logger.info(f"OpenTelemetry enabled: service={service_name}, endpoint={otlp_endpoint}")

    except ImportError as e:
        logger.warning(f"OpenTelemetry packages not installed, skipping: {e}")
    except Exception as e:
        logger.error(f"Failed to configure OpenTelemetry: {e}")
