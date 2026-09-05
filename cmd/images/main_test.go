package main

import (
	"bytes"
	"fmt"
	"image"
	"image/png"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/fmind/www/templates"
)

func TestGenerateDerivativesResizesAndIsIdempotent(t *testing.T) {
	root := t.TempDir()
	directory := filepath.Join(root, "example")
	if err := os.Mkdir(directory, 0o755); err != nil {
		t.Fatalf("create article directory: %v", err)
	}
	source := filepath.Join(directory, "cover.png")
	// Keep the fixture shallow: method 6 exercises the same resize/encode path
	// without making the race-enabled repository gate spend a minute on pixels.
	writePNG(t, source, 1_000, 10)

	var summary bytes.Buffer
	if err := generateDerivatives(root, true, &summary); err != nil {
		t.Fatalf("generate derivatives: %v", err)
	}
	if !strings.Contains(summary.String(), "1 generated, 0 skipped") {
		t.Errorf("summary = %q", summary.String())
	}

	target := filepath.Join(directory, "cover-800.webp")
	data, err := os.ReadFile(target)
	if err != nil {
		t.Fatalf("read generated derivative: %v", err)
	}
	config, _, err := image.DecodeConfig(bytes.NewReader(data))
	if err != nil {
		t.Fatalf("decode generated derivative: %v", err)
	}
	if config.Width != templates.CardCoverWidth || config.Height != 8 {
		t.Errorf("generated dimensions = %dx%d, want 800x8", config.Width, config.Height)
	}

	summary.Reset()
	if regenerateErr := generateDerivatives(root, true, &summary); regenerateErr != nil {
		t.Fatalf("regenerate derivatives: %v", regenerateErr)
	}
	after, err := os.ReadFile(target)
	if err != nil {
		t.Fatalf("read regenerated derivative: %v", err)
	}
	if !bytes.Equal(data, after) || !strings.Contains(summary.String(), "0 generated, 1 skipped") {
		t.Errorf("forced regeneration was not byte-idempotent: %q", summary.String())
	}
}

func TestGenerateDerivativesKeepsSmallCoverDimensions(t *testing.T) {
	root := t.TempDir()
	directory := filepath.Join(root, "small")
	if err := os.Mkdir(directory, 0o755); err != nil {
		t.Fatalf("create article directory: %v", err)
	}
	writePNG(t, filepath.Join(directory, "cover.png"), templates.CardCoverWidth, 8)

	if err := generateDerivatives(root, true, ioDiscard{}); err != nil {
		t.Fatalf("generate derivatives: %v", err)
	}
	target, err := os.ReadFile(filepath.Join(directory, "cover-800.webp"))
	if err != nil {
		t.Fatalf("read small source derivative: %v", err)
	}
	config, _, err := image.DecodeConfig(bytes.NewReader(target))
	if err != nil {
		t.Fatalf("decode small source derivative: %v", err)
	}
	if config.Width != templates.CardCoverWidth || config.Height != 8 {
		t.Errorf("small derivative dimensions = %dx%d, want 800x8", config.Width, config.Height)
	}
}

// Body figures earn a derivative on the same terms as covers, which is what
// gives a phone a candidate other than the full-resolution diagram.
func TestGenerateDerivativesCoversEveryBodyFigure(t *testing.T) {
	root := t.TempDir()
	directory := filepath.Join(root, "example")
	if err := os.Mkdir(directory, 0o755); err != nil {
		t.Fatalf("create article directory: %v", err)
	}
	writePNG(t, filepath.Join(directory, "cover.png"), 1_000, 10)
	writePNG(t, filepath.Join(directory, "03.webp"), 1_000, 10)

	var summary bytes.Buffer
	if err := generateDerivatives(root, true, &summary); err != nil {
		t.Fatalf("generate derivatives: %v", err)
	}
	if !strings.Contains(summary.String(), "2 generated, 0 skipped") {
		t.Errorf("summary = %q", summary.String())
	}
	if _, err := os.Stat(filepath.Join(directory, "03-800.webp")); err != nil {
		t.Errorf("body figure derivative missing: %v", err)
	}
}

// A non-cover source already narrower than the derivative width gets no
// same-size copy: the renderer omits its srcset and loads the source directly,
// so a second file would be bytes in the binary that nothing ever requests.
func TestGenerateDerivativesSkipsPhoneSizedFigures(t *testing.T) {
	root := t.TempDir()
	directory := filepath.Join(root, "example")
	if err := os.Mkdir(directory, 0o755); err != nil {
		t.Fatalf("create article directory: %v", err)
	}
	writePNG(t, filepath.Join(directory, "cover.png"), 1_000, 10)
	writePNG(t, filepath.Join(directory, "02.webp"), 500, 300)

	if err := generateDerivatives(root, true, ioDiscard{}); err != nil {
		t.Fatalf("generate derivatives: %v", err)
	}
	if _, err := os.Stat(filepath.Join(directory, "02-800.webp")); !os.IsNotExist(err) {
		t.Errorf("phone-sized figure should not gain a derivative, stat error = %v", err)
	}
}

// A source wide enough for the whole ladder gets every rung, and a rung is
// never upscaled past the source it came from.
func TestGenerateDerivativesWritesEveryLadderRung(t *testing.T) {
	root := t.TempDir()
	directory := filepath.Join(root, "example")
	if err := os.Mkdir(directory, 0o755); err != nil {
		t.Fatalf("create article directory: %v", err)
	}
	writePNG(t, filepath.Join(directory, "cover.png"), 2_048, 16)

	if err := generateDerivatives(root, true, ioDiscard{}); err != nil {
		t.Fatalf("generate derivatives: %v", err)
	}
	for _, width := range templates.DerivativeWidths {
		target := filepath.Join(directory, fmt.Sprintf("cover-%d.webp", width))
		data, err := os.ReadFile(target)
		if err != nil {
			t.Fatalf("read %dpx rung: %v", width, err)
		}
		config, _, err := image.DecodeConfig(bytes.NewReader(data))
		if err != nil {
			t.Fatalf("decode %dpx rung: %v", width, err)
		}
		if config.Width != width {
			t.Errorf("%dpx rung is %dpx wide", width, config.Width)
		}
	}
}

// The command must never treat its own output as a source, or every run would
// downscale the previous run's derivative and the committed tree would churn.
func TestIsSourceExcludesDerivativesAndVideos(t *testing.T) {
	for name, want := range map[string]bool{
		"static/img/articles/example/cover.png":      true,
		"static/img/articles/example/03.webp":        true,
		"static/img/articles/example/Diagram.JPEG":   true,
		"static/img/articles/example/cover-800.webp": false,
		"static/img/articles/example/Cover-800.WEBP": false,
		"static/img/articles/example/03-800.webp":    false,
		"static/img/articles/example/03-1280.webp":   false,
		"static/img/articles/example/demo.mp4":       false,
		"static/img/articles/example/notes.txt":      false,
	} {
		if got := isSource(name); got != want {
			t.Errorf("isSource(%q) = %t, want %t", name, got, want)
		}
	}
}

type ioDiscard struct{}

func (ioDiscard) Write(data []byte) (int, error) { return len(data), nil }

func writePNG(t *testing.T, name string, width, height int) {
	t.Helper()
	var encoded bytes.Buffer
	if err := png.Encode(&encoded, image.NewNRGBA(image.Rect(0, 0, width, height))); err != nil {
		t.Fatalf("encode source image: %v", err)
	}
	if err := os.WriteFile(name, encoded.Bytes(), 0o644); err != nil {
		t.Fatalf("write source image: %v", err)
	}
}
