FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 1000 rebalancer \
    && useradd --system --uid 1000 --gid rebalancer --create-home rebalancer

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

RUN mkdir -p /data && chown -R rebalancer:rebalancer /data /app
VOLUME ["/data"]
WORKDIR /data

USER rebalancer

ENTRYPOINT ["rebalancer"]
CMD ["run", "--config", "/data/portfolio.yaml", "--log-format", "json"]
