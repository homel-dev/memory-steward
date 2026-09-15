FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ src/

RUN pip install --no-cache-dir .

ENV STEWARD_MCP_URL=http://memory-steward-mcp:8081/mcp/
ENTRYPOINT ["steward-tui"]
