// Command images generates the deterministic downscaled WebP derivatives that
// article cards and responsive body figures load.
package main

import (
	"bytes"
	"errors"
	"fmt"
	"image"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"

	webpencoder "github.com/gen2brain/webp"
	"golang.org/x/image/draw"
	_ "golang.org/x/image/webp"

	"github.com/fmind/www/templates"
)

const (
	articleImageRoot = "static/img/articles"
	// Cards render this derivative at ~378-683 CSS px and phones render body
	// figures at ~390-430, where q75 is visually indistinguishable from q80 but
	// ~16% smaller across the archive. Below q72 the curve flattens while
	// compression artifacts start showing on flat brand fills.
	derivativeQuality = 75
	derivativeMethod  = 6
	coverStem         = "cover"
)

// sourceExtensions are the formats an article ships a source image in. Videos
// and already-generated derivatives are skipped by name, not by extension.
var sourceExtensions = map[string]bool{
	".webp": true,
	".png":  true,
	".jpg":  true,
	".jpeg": true,
	".gif":  true,
}

func main() {
	if err := generateDerivatives(articleImageRoot, os.Getenv("FORCE") == "1", os.Stdout); err != nil {
		fmt.Fprintf(os.Stderr, "generate image derivatives: %v\n", err)
		os.Exit(1)
	}
}

func generateDerivatives(root string, force bool, output io.Writer) error {
	entries, err := filepath.Glob(filepath.Join(root, "*", "*"))
	if err != nil {
		return fmt.Errorf("list article images: %w", err)
	}
	sources := make([]string, 0, len(entries))
	for _, entry := range entries {
		if isSource(entry) {
			sources = append(sources, entry)
		}
	}
	if len(sources) == 0 {
		return fmt.Errorf("list article images: no source images under %q", root)
	}
	sort.Strings(sources)

	generated, skipped := 0, 0
	for _, source := range sources {
		changed, err := generateDerivative(source, force)
		if err != nil {
			return err
		}
		if changed {
			generated++
		} else {
			skipped++
		}
	}

	if _, err := fmt.Fprintf(output, "image derivatives: %d generated, %d skipped (%v px, q%d)\n", generated, skipped, templates.DerivativeWidths, derivativeQuality); err != nil {
		return fmt.Errorf("write summary: %w", err)
	}
	return nil
}

// isSource reports whether a file is an image an article body or card can load,
// as opposed to a generated derivative or an embedded video. Excluding the
// derivatives by their own naming convention is what keeps the command
// idempotent: without it, every run would downscale its previous output.
func isSource(name string) bool {
	base := filepath.Base(name)
	extension := filepath.Ext(base)
	if !sourceExtensions[strings.ToLower(extension)] {
		return false
	}
	stem := strings.TrimSuffix(base, extension)
	for _, width := range templates.DerivativeWidths {
		if strings.HasSuffix(stem, fmt.Sprintf("-%d", width)) {
			return false
		}
	}
	return true
}

// derivativeName encodes the one naming convention the generator and the
// renderer share: the renderer resolves a source's candidates by rebuilding
// these exact names, so the two must never drift.
func derivativeName(source string, width int) string {
	base := filepath.Base(source)
	stem := strings.TrimSuffix(base, filepath.Ext(base))
	return filepath.Join(filepath.Dir(source), fmt.Sprintf("%s-%d.webp", stem, width))
}

// generateDerivative writes every ladder rung a source is wide enough to earn,
// and reports whether any of them changed.
func generateDerivative(source string, force bool) (bool, error) {
	var decoded image.Image
	changed := false
	for _, width := range templates.DerivativeWidths {
		target := derivativeName(source, width)
		if !force {
			current, err := derivativeIsCurrent(source, target)
			if err != nil {
				return false, err
			}
			if current {
				continue
			}
		}
		// Decode once, lazily: most runs skip every rung on their mtime check,
		// and decoding 300 sources to discover that costs a minute of CI.
		if decoded == nil {
			data, err := os.ReadFile(source)
			if err != nil {
				return false, fmt.Errorf("read %q: %w", source, err)
			}
			// The WebP decoder does not apply EXIF orientation. Sources must be
			// pre-rotated before they enter this deterministic pipeline; all
			// current sources already satisfy that contract.
			decoded, _, err = image.Decode(bytes.NewReader(data))
			if err != nil {
				return false, fmt.Errorf("decode %q: %w", source, err)
			}
		}
		// A source narrower than a rung gains nothing from a same-size copy: the
		// renderer only names candidates it finds on disk. Cards are the one
		// exception — they load the cover derivative by name, so that rung has
		// to exist even when the source is already small.
		cardRung := width == templates.CardCoverWidth && isCover(source)
		if decoded.Bounds().Dx() <= width && !cardRung {
			continue
		}
		written, err := writeDerivative(decoded, target, width)
		if err != nil {
			return false, err
		}
		changed = changed || written
	}
	return changed, nil
}

func writeDerivative(decoded image.Image, target string, width int) (bool, error) {
	bounds := decoded.Bounds()
	outputImage := decoded
	if bounds.Dx() > width {
		height := bounds.Dy() * width / bounds.Dx()
		resized := image.NewNRGBA(image.Rect(0, 0, width, height))
		draw.CatmullRom.Scale(resized, resized.Bounds(), decoded, bounds, draw.Over, nil)
		outputImage = resized
	}

	var encoded bytes.Buffer
	if err := webpencoder.Encode(&encoded, outputImage, webpencoder.Options{Quality: derivativeQuality, Method: derivativeMethod}); err != nil {
		return false, fmt.Errorf("encode %q: %w", target, err)
	}
	if existing, err := os.ReadFile(target); err == nil && bytes.Equal(existing, encoded.Bytes()) {
		return false, nil
	} else if err != nil && !errors.Is(err, os.ErrNotExist) {
		return false, fmt.Errorf("read %q: %w", target, err)
	}
	if err := os.WriteFile(target, encoded.Bytes(), 0o644); err != nil {
		return false, fmt.Errorf("write %q: %w", target, err)
	}
	return true, nil
}

func isCover(source string) bool {
	base := filepath.Base(source)
	return strings.TrimSuffix(base, filepath.Ext(base)) == coverStem
}

func derivativeIsCurrent(source, target string) (bool, error) {
	sourceInfo, err := os.Stat(source)
	if err != nil {
		return false, fmt.Errorf("stat %q: %w", source, err)
	}
	targetInfo, err := os.Stat(target)
	if errors.Is(err, os.ErrNotExist) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("stat %q: %w", target, err)
	}
	return !targetInfo.ModTime().Before(sourceInfo.ModTime()), nil
}
