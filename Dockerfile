# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM golang:1.27.0 AS css
ARG BUILDARCH
ADD --chmod=0755 --checksum=sha256:29bd5364e7796d4b43a6d429801fc2d92223bd32a5385883674872fa855c0471 \
  https://github.com/dobicinaitis/tailwind-cli-extra/releases/download/v2.10.10/tailwindcss-extra-linux-x64 \
  /usr/local/lib/tailwindcss-extra-amd64
ADD --chmod=0755 --checksum=sha256:65f19e7c334783b08bb58cccbd07f809a6d6e44d63219c6952147f221a86c6f0 \
  https://github.com/dobicinaitis/tailwind-cli-extra/releases/download/v2.10.10/tailwindcss-extra-linux-arm64 \
  /usr/local/lib/tailwindcss-extra-arm64
WORKDIR /app
COPY assets/css/input.css assets/css/input.css
COPY templates templates
RUN /usr/local/lib/tailwindcss-extra-${BUILDARCH} -i assets/css/input.css -o static/dist/styles.css --minify

FROM --platform=$BUILDPLATFORM golang:1.27.0 AS builder
ARG TARGETARCH
ARG TARGETOS
WORKDIR /app
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY . .
COPY --from=css /app/static/dist/styles.css static/dist/styles.css
RUN --mount=type=cache,target=/go/pkg/mod \
  --mount=type=cache,target=/root/.cache/go-build \
  go tool templ generate && \
  CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
  go build -trimpath -ldflags="-s -w" -o www-fmind-dev ./cmd/www-fmind-dev

FROM gcr.io/distroless/static-debian13:nonroot AS runner
ENV ENVIRONMENT=production
# Distroless defines nonroot as numeric 65532; numeric ownership remains
# resolvable even when a container runtime does not load /etc/passwd.
USER 65532:65532
WORKDIR /app
EXPOSE 8080
COPY --from=builder /app/www-fmind-dev ./www-fmind-dev
ENTRYPOINT ["./www-fmind-dev"]
