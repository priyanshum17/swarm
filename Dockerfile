FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications
COPY pyproject.toml README.md ./

# Install pip dependencies
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir .

# Copy application source code
COPY swarm/ ./swarm/
COPY benchmarks/ ./benchmarks/

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["swarm", "serve", "--host", "0.0.0.0", "--port", "8000"]
