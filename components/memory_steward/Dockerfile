FROM python:3.11-slim

ARG TARGETARCH
ARG CODEGRAPH_VERSION=0.20.1

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CODEGRAPH_VERSION=${CODEGRAPH_VERSION}
ENV CODEGRAPH_BINARY=/usr/local/bin/codegraph-server

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl git libstdc++6; \
    rm -rf /var/lib/apt/lists/*; \
    case "${TARGETARCH}" in \
         amd64) cg_asset="codegraph-server-linux-x64"; cg_sha256="32b26422fa5ffe0a130955b7f7df771f722b2d427d67f53f104d9907bdfb24a6" ;; \
         arm64) cg_asset="codegraph-server-linux-arm64"; cg_sha256="e549f2378f7911680b88ff4a86a66e783c7911d66b1d6ec09743d7afff53c1cf" ;; \
         *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
       esac; \
       curl -fsSLo /usr/local/bin/codegraph-server \
         "https://github.com/codegraph-ai/CodeGraph/releases/download/v${CODEGRAPH_VERSION}/${cg_asset}"; \
       echo "${cg_sha256}  /usr/local/bin/codegraph-server" | sha256sum -c -; \
       chmod 0755 /usr/local/bin/codegraph-server; \
       /usr/local/bin/codegraph-server --version

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir .

EXPOSE 8090 8092 8093

CMD ["python", "-m", "memory_steward.server"]
