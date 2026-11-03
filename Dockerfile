FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/pstviewer

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-pypff \
    libpff1 \
    pff-tools \
    poppler-utils \
    antiword \
    catdoc \
    tesseract-ocr \
    tesseract-ocr-por \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/pstviewer

COPY requirements.txt /opt/pstviewer/requirements.txt
RUN python3 -m venv --system-site-packages /opt/pstviewer/venv \
    && /opt/pstviewer/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/pstviewer/venv/bin/pip install --no-cache-dir -r /opt/pstviewer/requirements.txt

COPY app /opt/pstviewer/app
COPY database /opt/pstviewer/database
COPY scripts /opt/pstviewer/scripts
COPY config /opt/pstviewer/config

RUN mkdir -p /srv/pstviewer/sessions /srv/pstviewer/quarantine /var/lib/pstviewer/jobs /var/log/pstviewer/application /var/log/pstviewer/audit

EXPOSE 8085

