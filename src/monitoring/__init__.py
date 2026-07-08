from src.monitoring.structured_log import setup_json_logging
from src.monitoring.tracing import init_tracing


def init_monitoring(service_name: str = "aimiddleplatform") -> None:
    setup_json_logging()
    init_tracing(service_name)
