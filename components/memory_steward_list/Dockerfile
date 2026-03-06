# USAGE: Works for both CPU and GPU (CUDA 12.x) inference.
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# 1. Install Python 3.11, pip, and ffmpeg (required for audio)
#    We use deadsnakes PPA or standard apt depending on ubuntu version (22.04 has python3.10 default).
#    To get 3.11 explicitly on 22.04:
RUN apt-get update && DEBIAN_FRONTEND="noninteractive" TZ="America/Los_Angeles" apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && DEBIAN_FRONTEND="noninteractive" TZ="America/Los_Angeles" apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Bootstrap pip specifically for Python 3.11
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11
RUN ln -sf /usr/bin/python3.11 /usr/bin/python

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

# 3. Install dependencies
#    faster-whisper handles both CPU (int8) and GPU (float16) logic internally.
RUN pip install --no-cache-dir .

# 4. Expose port (Contract: 8001)
EXPOSE 8001

CMD ["python", "-m", "memory_steward_list.server"]
