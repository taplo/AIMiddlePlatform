import time

from src.monitoring.trace_store import TraceStore


def test_trace_store_store_and_retrieve():
    store = TraceStore(maxlen=50)
    store.export([_make_span("00000000000000000000000000000001", "0000000000000001", "operation1", 0.1, True)])
    traces = store.get_traces()
    assert len(traces) >= 1
    assert traces[0]["trace_id"] == "00000000000000000000000000000001"


def test_trace_store_error_filter():
    store = TraceStore(maxlen=50)
    store.export([_make_span("0000000000000000000000000000000a", "00000000000000a1", "op1", 0.1, True)])
    store.export([_make_span("0000000000000000000000000000000b", "00000000000000b1", "op2", 0.1, False)])
    err_traces = store.get_traces(error_only=True)
    assert len(err_traces) == 1
    assert err_traces[0]["trace_id"] == "0000000000000000000000000000000b"


def test_trace_store_min_duration():
    store = TraceStore(maxlen=50)
    store.export([_make_span("00000000000000000000000000000010", "0000000000000010", "op1", 0.05, True)])
    store.export([_make_span("00000000000000000000000000000020", "0000000000000020", "op2", 0.2, True)])
    filtered = store.get_traces(min_duration_ms=100)
    assert len(filtered) == 1
    assert filtered[0]["trace_id"] == "00000000000000000000000000000020"


def test_get_trace_detail():
    store = TraceStore(maxlen=50)
    spans = [
        _make_span("000000000000000000000000000000ff", "00000000000000ff", "root_op", 0.5, True),
        _make_span("000000000000000000000000000000ff", "00000000000000fe", "child_op", 0.3, True),
    ]
    for s in spans:
        store.export([s])
    detail = store.get_trace_detail("000000000000000000000000000000ff")
    assert detail is not None
    assert detail["trace_id"] == "000000000000000000000000000000ff"
    assert len(detail["spans"]) == 2


def _make_span(trace_id: str, span_id: str, name: str, duration_s: float, success: bool):
    from opentelemetry.trace import SpanContext, SpanKind, TraceFlags

    _trace_id_int = int(trace_id, 16)
    _span_id_int = int(span_id, 16)

    class FakeSpan:
        def __init__(self):
            self._start_time = time.time_ns()
            self._end_time = self._start_time + int(duration_s * 1e9)
            self._attributes = {"success": success, "duration_ms": duration_s * 1000}
            self._status = None
            self._parent = None
            self._resource = None
            self._instrumentation_scope = None

        def get_span_context(self):
            return SpanContext(
                trace_id=abs(_trace_id_int),
                span_id=abs(_span_id_int),
                is_remote=False,
                trace_flags=TraceFlags(1),
            )

        @property
        def name(self): return name

        @property
        def start_time(self): return self._start_time

        @property
        def end_time(self): return self._end_time

        @property
        def kind(self): return SpanKind.INTERNAL

        @property
        def attributes(self): return self._attributes

        @property
        def status(self): return self._status

        @property
        def parent(self): return self._parent

        @property
        def resource(self): return self._resource

        @property
        def instrumentation_scope(self): return self._instrumentation_scope

    return FakeSpan()
