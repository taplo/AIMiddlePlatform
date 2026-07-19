import functools
import time
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from src.monitoring.trace_store import TraceStore

_tracer: trace.Tracer | None = None
_default_attributes: dict[str, Any] = {}


def _safe_exporter() -> ConsoleSpanExporter:
    try:
        return ConsoleSpanExporter()
    except Exception:
        return None


def init_tracing(service_name: str = "aimiddleplatform") -> TracerProvider:
    global _tracer
    resource = Resource.create({"service.name": service_name, "service.version": "0.1.0"})
    provider = TracerProvider(resource=resource)
    exporter = _safe_exporter()
    if exporter:
        try:
            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)
        except Exception:
            pass
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)
    return provider


def add_trace_store_exporter(store: TraceStore) -> None:
    provider = trace.get_tracer_provider()
    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(BatchSpanProcessor(store))


def set_default_attributes(attrs: dict[str, Any]) -> None:
    _default_attributes.update(attrs)


def get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        _tracer = init_tracing()
    return _tracer


def trace_async(span_name: str | None = None, attributes: dict | None = None):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()
            name = span_name or func.__name__
            with tracer.start_as_current_span(name) as span:
                if attributes:
                    span.set_attributes(attributes)
                span.set_attribute("component", func.__module__)
                start = time.monotonic()
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("success", True)
                    return result
                except Exception as e:
                    span.set_attribute("success", False)
                    span.record_exception(e)
                    raise
                finally:
                    elapsed = (time.monotonic() - start) * 1000
                    span.set_attribute("duration_ms", elapsed)
        return wrapper
    return decorator
