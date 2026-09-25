# syntax=docker/dockerfile:1

# build: collect ready-made wheels. uvloop exists as a binary for amd64 and arm64 – --only-binary makes
# a missing wheel show up right away instead of quietly needing a compiler
FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY proxyscraper ./proxyscraper
RUN pip wheel --no-cache-dir --only-binary uvloop --wheel-dir /wheels ".[fast]"

FROM python:3.12-slim
LABEL org.opencontainers.image.title="proxy-scraper" \
      org.opencontainers.image.description="Free proxies that actually work – scraped, verified, learned." \
      org.opencontainers.image.source="https://github.com/maximilianfeix/proxy-scraper" \
      org.opencontainers.image.licenses="MIT"

COPY --from=build /wheels /tmp/wheels
RUN pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels \
 && useradd --create-home --uid 1000 scraper \
 && mkdir -p /data /work/results && chown -R scraper /data /work

# learned state (source statistics, history, cache) goes to /data, results to /work/results –
# both as volumes, otherwise every container starts from zero again
ENV PROXY_SCRAPER_HOME=/data \
    PYTHONUNBUFFERED=1
VOLUME ["/data", "/work/results"]
WORKDIR /work
USER scraper

# without a TTY the wizard never starts – "docker run image" runs straight away with the defaults
ENTRYPOINT ["proxy-scraper"]
