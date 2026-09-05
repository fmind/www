// Command www serves the portfolio website of Médéric Hurier (Fmind).
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	site "github.com/fmind/www"
	"github.com/fmind/www/config"
)

func main() {
	// Load configuration and initialize structured logging (fail fast on error).
	cfg, err := config.Load()
	if err != nil {
		slog.Error("load configuration", "error", err)
		os.Exit(1)
	}

	// Wrap the environment-appropriate handler for OTel trace correlation.
	logger := slog.New(&site.OtelHandler{Handler: cfg.NewHandler(os.Stderr)})
	slog.SetDefault(logger)

	// Graceful shutdown lifecycle.
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// Install OpenTelemetry tracing (no-op unless an OTLP endpoint is configured).
	shutdownOTel, err := site.SetupOTel(ctx, site.ServiceName)
	if err != nil {
		logger.Error("setup opentelemetry", "error", err)
		os.Exit(1)
	}
	defer func() {
		flushCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if shutdownErr := shutdownOTel(flushCtx); shutdownErr != nil {
			logger.Error("shutdown opentelemetry", "error", shutdownErr)
		}
	}()

	handler, err := site.NewAppHandler(logger, cfg)
	if err != nil {
		logger.Error("build application handler", "error", err)
		os.Exit(1)
	}

	server := &http.Server{
		Addr:              ":" + strconv.Itoa(cfg.Port),
		Handler:           handler,
		ReadHeaderTimeout: 3 * time.Second,
		ReadTimeout:       5 * time.Second,
		WriteTimeout:      10 * time.Second,
		IdleTimeout:       120 * time.Second,
	}

	// Closed once the shutdown goroutine has finished draining, so the main
	// goroutine can block on it before exiting.
	idleClosed := make(chan struct{})
	go func() {
		<-ctx.Done()
		logger.Info("shutdown signal received")

		shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()

		if err := server.Shutdown(shutdownCtx); err != nil {
			logger.Error("graceful shutdown failed", "error", err)
			if closeErr := server.Close(); closeErr != nil {
				logger.Error("force close failed", "error", closeErr)
			}
		}
		close(idleClosed)
	}()

	logger.Info("server listening", "addr", server.Addr, "env", cfg.Environment)
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		logger.Error("server error", "error", err)
		os.Exit(1)
	}
	// ListenAndServe returns the instant Shutdown closes the listener, but the
	// drain runs on in the goroutine; wait for it so in-flight requests finish
	// (and the deferred OTel flush runs) before the process exits.
	<-idleClosed
	logger.Info("graceful shutdown complete")
}
