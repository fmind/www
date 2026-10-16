# syntax=docker/dockerfile:1
FROM python:3.14.8-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS build
ARG TARGETARCH
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 /uv /uvx /bin/
ADD --chmod=0755 --checksum=sha256:eca9e42452e39d19c68b74dc527c67fd7a890197d7cce329722e9a54e9fd339c \
  https://github.com/dobicinaitis/tailwind-cli-extra/releases/download/v2.10.34/tailwindcss-extra-linux-x64 \
  /usr/local/lib/tailwindcss-extra-amd64
ADD --chmod=0755 --checksum=sha256:5798c5c79a734e4600de4491184fb8d55386c86790ef2fe91d59d58514b9657e \
  https://github.com/dobicinaitis/tailwind-cli-extra/releases/download/v2.10.34/tailwindcss-extra-linux-arm64 \
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

FROM python:3.14.8-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS runner
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
