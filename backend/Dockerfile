# syntax=docker/dockerfile:1.7
# Multi-stage Dockerfile — supports linux/amd64 and linux/arm64

# ── Base ───────────────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS base

LABEL org.opencontainers.image.source="https://github.com/your-org/codeatlas-ai"
LABEL org.opencontainers.image.description="CodeAtlas AI Backend"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies (git + openssh-client for cloning, libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /home/codeatlas/.ssh \
    && ssh-keyscan -t rsa,ecdsa,ed25519 github.com gitlab.com bitbucket.org >> /home/codeatlas/.ssh/known_hosts 2>/dev/null \
    && printf 'Host *\n  StrictHostKeyChecking accept-new\n  UserKnownHostsFile /home/codeatlas/.ssh/known_hosts\n  IdentityFile /home/codeatlas/.ssh/id_rsa\n  IdentityFile /home/codeatlas/.ssh/id_ed25519\n' > /etc/ssh/ssh_config.d/codeatlas.conf \
    && chmod 700 /home/codeatlas/.ssh \
    && chmod 600 /home/codeatlas/.ssh/known_hosts

WORKDIR /app

# ── Dependencies ───────────────────────────────────────────────────────────────
FROM base AS deps

COPY pyproject.toml .
COPY app/ ./app/
RUN pip install --upgrade pip \
 && pip install -e ".[dev]" \
    --extra-index-url https://download.pytorch.org/whl/cpu

# ── Production ─────────────────────────────────────────────────────────────────
FROM base AS production

# Copy sources first so pip editable install can find the package
COPY pyproject.toml .
COPY app/ ./app/
RUN pip install --upgrade pip \
 && pip install -e "." \
    --extra-index-url https://download.pytorch.org/whl/cpu

COPY . .

# Create non-root user with a real home dir for SSH key resolution
RUN addgroup --system codeatlas \
    && adduser --system --ingroup codeatlas --home /home/codeatlas --shell /bin/sh codeatlas \
    && chown -R codeatlas:codeatlas /app /home/codeatlas/.ssh

ENV HOME=/home/codeatlas
USER codeatlas

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# ── Development (with hot-reload) ──────────────────────────────────────────────
FROM deps AS development

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
