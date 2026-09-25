# syntax=docker/dockerfile:1
FROM python:3.14.7-slim@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2 AS build
ARG TARGETARCH
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 /uv /uvx /bin/
ADD --chmod=0755 --checksum=sha256:aca04df159cc3b2c4a984c58ddb066ca892ac5fda21755207ff08ac081cb9854 \
  https://github.com/dobicinaitis/tailwind-cli-extra/releases/download/v2.10.31/tailwindcss-extra-linux-x64 \
  /usr/local/lib/tailwindcss-extra-amd64
ADD --chmod=0755 --checksum=sha256:0d3c4830e87f8e0c17c8d70190c13055f19181c8ca29cc6520ae1ff7eb2947e2 \
  https://github.com/dobicinaitis/tailwind-cli-extra/releases/download/v2.10.31/tailwindcss-extra-linux-arm64 \
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

FROM python:3.14.7-slim@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2 AS runner
ENV ENVIRONMENT=production
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
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
