# syntax=docker/dockerfile:1

# Build: fertige Wheels sammeln. uvloop gibt es für amd64 und arm64 als Binary – --only-binary sorgt
# dafür, dass ein fehlendes Wheel sofort auffällt statt still einen Compiler zu brauchen
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

# Gelerntes (Quellen-Statistik, Verlauf, Cache) nach /data, Ergebnisse nach /work/results –
# beides als Volume, sonst fängt jeder Container wieder bei null an
ENV PROXY_SCRAPER_HOME=/data \
    PYTHONUNBUFFERED=1
VOLUME ["/data", "/work/results"]
WORKDIR /work
USER scraper

# Ohne TTY startet der Assistent nie – "docker run image" läuft direkt mit den Standardwerten
ENTRYPOINT ["proxy-scraper"]
