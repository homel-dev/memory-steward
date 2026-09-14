from memory_router.config import POSTGRES_DSN
from memory_router.telemetry import TelemetryWriter

telemetry = TelemetryWriter(POSTGRES_DSN)
