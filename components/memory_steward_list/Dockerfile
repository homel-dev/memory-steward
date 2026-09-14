# USAGE: Works for both CPU and GPU (CUDA 12.x) inference.
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# Install Python 3.11, pip, and ffmpeg (required for audio).
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

RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11
RUN ln -sf /usr/bin/python3.11 /usr/bin/python

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir .

EXPOSE 8001

CMD ["python", "-m", "memory_steward_list.server"]
