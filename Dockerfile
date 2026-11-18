FROM docker.io/library/python:3.12-slim-trixie AS base

FROM base AS build
WORKDIR /build
COPY pyproject.toml README.md LICENSE.txt ./
COPY src/ ./src/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir . \
    && /opt/venv/bin/python -m pip check

FROM base
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=build /opt/venv /opt/venv
WORKDIR /etc/gmc-geiger-mqtt
USER 10001:10001
ENTRYPOINT ["gmc-geiger-mqtt"]
CMD ["/etc/gmc-geiger-mqtt/config.yaml"]
