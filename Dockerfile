# syntax=docker/dockerfile:1
FROM python:3.14.7-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS build
ARG TARGETARCH
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.10@sha256:2bb3ebca0a796a155094a27773d290c4b074572e6107f171d88d086682fd2500 /uv /uvx /bin/
ADD --chmod=0755 --checksum=sha256:1537f22912c5556438d20bbe669212b14d5c79667431f6cf01dd6b135652960f \
  https://github.com/dobicinaitis/tailwind-cli-extra/releases/download/v2.10.20/tailwindcss-extra-linux-x64 \
  /usr/local/lib/tailwindcss-extra-amd64
ADD --chmod=0755 --checksum=sha256:9e159ddee27e5a895caa41473aa1e1b3843904ec669cb9ead7b1e70f11c9d163 \
  https://github.com/dobicinaitis/tailwind-cli-extra/releases/download/v2.10.20/tailwindcss-extra-linux-arm64 \
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

FROM python:3.14.7-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS runner
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
