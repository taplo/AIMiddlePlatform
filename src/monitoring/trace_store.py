from collections import deque
from typing import Any

from opentelemetry.sdk.trace.export import SpanExporter

_store: "TraceStore | None" = None


class TraceStore(SpanExporter):
    def __init__(self, maxlen: int = 200):
        self.maxlen = maxlen
        self._traces: dict[str, dict[str, Any]] = {}
        self._order: deque[str] = deque(maxlen=maxlen)

    def export(self, spans, timeout_millis=30000):
        for span in spans:
            ctx = span.get_span_context()
            trace_id = format(ctx.trace_id, "032x")
            span_id = format(ctx.span_id, "016x")
            attrs = dict(span.attributes or {})
            duration_ns = span.end_time - span.start_time
            duration_ms = duration_ns / 1_000_000
            success = attrs.get("success", True)
            error = not success

            if trace_id not in self._traces:
                self._traces[trace_id] = {
                    "trace_id": trace_id,
                    "start_time": span.start_time,
                    "duration_ms": duration_ms,
                    "span_count": 0,
                    "error": error,
                    "spans": [],
                }
                self._order.append(trace_id)
            else:
                existing = self._traces[trace_id]
                existing["start_time"] = min(existing["start_time"], span.start_time)
                existing["duration_ms"] = max(existing["duration_ms"], duration_ms)
                existing["error"] = existing["error"] or error

            self._traces[trace_id]["span_count"] += 1
            self._traces[trace_id]["spans"].append({
                "span_id": span_id,
                "name": span.name,
                "start_time": span.start_time,
                "duration_ms": duration_ms,
                "attributes": attrs,
                "error": error,
            })
        return True

    def shutdown(self):
        pass

    def get_traces(
        self,
        min_duration_ms: float = 0,
        error_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        result = []
        for tid in reversed(self._order):
            t = self._traces[tid]
            if error_only and not t["error"]:
                continue
            if t["duration_ms"] < min_duration_ms:
                continue
            result.append({
                "trace_id": t["trace_id"],
                "start_time": t["start_time"],
                "duration_ms": round(t["duration_ms"], 2),
                "span_count": t["span_count"],
                "error": t["error"],
            })
            if len(result) >= limit:
                break
        return result

    def get_trace_detail(self, trace_id: str) -> dict[str, Any] | None:
        t = self._traces.get(trace_id)
        if not t:
            return None
        return {
            "trace_id": t["trace_id"],
            "duration_ms": round(t["duration_ms"], 2),
            "span_count": t["span_count"],
            "error": t["error"],
            "spans": sorted(t["spans"], key=lambda s: s["start_time"]),
        }


def init_trace_store(maxlen: int = 200) -> TraceStore:
    global _store
    _store = TraceStore(maxlen=maxlen)
    return _store


def get_traces(min_duration_ms: float = 0, error_only: bool = False, limit: int = 50) -> list[dict]:
    global _store
    if _store is None:
        return []
    return _store.get_traces(min_duration_ms=min_duration_ms, error_only=error_only, limit=limit)


def get_trace_detail(trace_id: str) -> dict | None:
    global _store
    if _store is None:
        return None
    return _store.get_trace_detail(trace_id)
