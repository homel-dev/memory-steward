"""
Configuration for LIST service.
Defines model parameters and runtime settings.
"""

import os

def _env(name: str, default: str = None) -> str:
    return os.environ.get(name, default)

# Model Selection: tiny, base, small, medium, large-v2, large-v3
# Recommended: 'base' or 'small' for CPU responsiveness.
WHISPER_MODEL_SIZE = _env("WHISPER_MODEL_SIZE", "base")

# Compute Type: 'int8', 'float16', 'float32'
# On CPU, 'int8' is usually best. On GPU, 'float16'.
COMPUTE_TYPE = _env("COMPUTE_TYPE", "int8")

# Device: 'cpu' or 'cuda'
DEVICE = _env("DEVICE", "cpu")

# Telemetry / Service Info
APP_VERSION = "memory-steward-list/0.1.0"
