import json
import logging
from datetime import datetime, timezone


def configure_logging(service_name: str) -> None:
    logging.basicConfig(level=logging.INFO)
    root = logging.getLogger()
    if root.handlers:
        root.handlers[0].setFormatter(JsonFormatter(service_name))


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "service": self.service_name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            payload["trace_id"] = trace_id
        return json.dumps(payload, ensure_ascii=False)
