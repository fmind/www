package config_test

import (
	"bytes"
	"log/slog"
	"testing"

	"github.com/fmind/www/config"
)

func TestLoadDefaults(t *testing.T) {
	t.Setenv("ENVIRONMENT", "")
	t.Setenv("PORT", "")

	cfg, err := config.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.Environment != config.Development {
		t.Errorf("Environment = %q, want development", cfg.Environment)
	}
	if cfg.Port != 8080 {
		t.Errorf("Port = %d, want 8080", cfg.Port)
	}
}

func TestLoadProduction(t *testing.T) {
	t.Setenv("ENVIRONMENT", "production")
	t.Setenv("PORT", "9090")

	cfg, err := config.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if cfg.Environment != config.Production {
		t.Errorf("Environment = %q, want production", cfg.Environment)
	}
	if cfg.Port != 9090 {
		t.Errorf("Port = %d, want 9090", cfg.Port)
	}
}

func TestLoadRejectsInvalidEnvironment(t *testing.T) {
	t.Setenv("ENVIRONMENT", "staging")
	if _, err := config.Load(); err == nil {
		t.Error("Load() = nil error, want failure for invalid ENVIRONMENT")
	}
}

func TestLoadRejectsInvalidPort(t *testing.T) {
	t.Setenv("ENVIRONMENT", "development")
	t.Setenv("PORT", "70000")
	if _, err := config.Load(); err == nil {
		t.Error("Load() = nil error, want failure for out-of-range PORT")
	}
}

func TestNewHandlerByEnvironment(t *testing.T) {
	var buf bytes.Buffer

	prod := config.Config{Environment: config.Production}
	if _, ok := prod.NewHandler(&buf).(*slog.JSONHandler); !ok {
		t.Error("production handler should be a JSONHandler")
	}

	dev := config.Config{Environment: config.Development}
	if _, ok := dev.NewHandler(&buf).(*slog.TextHandler); !ok {
		t.Error("development handler should be a TextHandler")
	}
}
