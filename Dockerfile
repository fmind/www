# syntax=docker/dockerfile:1
FROM python:3.14.8-slim@sha256:f85c5697265c178cc6887276c55fe16cf3d14ca35c3df6a5eab3b360534a55d2 AS build
ARG TARGETARCH
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 /uv /uvx /bin/
ADD --chmod=0755 --checksum=sha256:bd07f6e116dd8292983b01aea55dc355e797fca0c39c747c377209b3e2fe4f98 \
  https://github.com/dobicinaitis/tailwind-cli-extra/releases/download/v2.10.32/tailwindcss-extra-linux-x64 \
  /usr/local/lib/tailwindcss-extra-amd64
ADD --chmod=0755 --checksum=sha256:703615219d522b532ca2e95af8b1657d5db1ef6771879a1870c4c474bd194aa1 \
  https://github.com/dobicinaitis/tailwind-cli-extra/releases/download/v2.10.32/tailwindcss-extra-linux-arm64 \
  /usr/local/lib/tailwindcss-extra-arm64
RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --locked --no-install-project --no-dev
COPY . /app
# Authored media may be owner-only; normalize the immutable runtime trees so
# UID 10001 can read them without gaining write access.
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked --no-dev --no-editable \
  && /usr/local/lib/tailwindcss-extra-${TARGETARCH} \
    -i assets/css/input.css -o static/dist/styles.css --minify \
  && chmod -R u=rwX,go=rX /app/.venv /app/content /app/static

FROM python:3.14.8-slim@sha256:f85c5697265c178cc6887276c55fe16cf3d14ca35c3df6a5eab3b360534a55d2 AS runner
ENV ENVIRONMENT=production
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
# Debian security fixes can lag the pinned base image by weeks (OpenSSL and
# PCRE2 on 2026-10-05); apply them so the scanned, deployed digest carries them.
RUN apt-get update \
  && apt-get upgrade --yes --no-install-recommends \
  && rm -rf /var/lib/apt/lists/*
# Runtime images install only the locked application environment; retaining pip
# adds an unused package installer and its vendored dependency attack surface.
RUN python -m pip uninstall --yes --root-user-action=ignore pip \
  && groupadd --gid 10001 app \
  && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app \
  # The web runtime never needs privileged Debian login or mount helpers.
  && find /usr -xdev -type f -perm /6000 -exec chmod a-s {} +
USER 10001:10001
EXPOSE 8080
# Keep executable code and published content root-owned: the runtime identity
# needs read/execute access but has no reason to modify its own application.
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/content /app/content
COPY --from=build /app/static /app/static
ENTRYPOINT ["www"]
