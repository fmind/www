package site

import (
	"crypto/rand"
	"log/slog"
	"net/http"
	"net/url"
	"path"
	"strings"
	"time"

	"github.com/a-h/templ"
	"github.com/klauspost/compress/gzhttp"

	"github.com/fmind/www/config"
	"github.com/fmind/www/templates"
)

// canonicalHost is the production apex domain that 301-redirects to its www host,
// consolidating link equity onto a single canonical origin.
const (
	canonicalApex    = "fmind.dev"
	canonicalTarget  = "https://www.fmind.dev"
	analyticsLogName = "analytics_pageview"
)

var botUserAgentTokens = []string{
	"bot",
	"crawler",
	"spider",
	"slurp",
	"bingpreview",
	"facebookexternalhit",
	"linkedinbot",
}

// Middleware defines the standard function signature for http middleware wrappers.
type Middleware func(http.Handler) http.Handler

// Chain links multiple Middleware functions around a root http.Handler. It applies
// them in reverse so the first listed runs outermost at request time.
func Chain(h http.Handler, mws ...Middleware) http.Handler {
	for i := len(mws) - 1; i >= 0; i-- {
		h = mws[i](h)
	}
	return h
}

// responseWriter intercepts writes to capture the status code and bytes written.
type responseWriter struct {
	http.ResponseWriter
	statusCode   int
	bytesWritten int
	wroteFinal   bool
}

func (rw *responseWriter) WriteHeader(code int) {
	// net/http permits multiple informational responses, followed by one final
	// response. Preserve that behavior while recording only the status actually
	// sent as the final response.
	if code >= 100 && code < 200 {
		rw.statusCode = code
		rw.ResponseWriter.WriteHeader(code)
		return
	}
	if rw.wroteFinal {
		return
	}
	rw.statusCode = code
	rw.wroteFinal = true
	rw.ResponseWriter.WriteHeader(code)
}

func (rw *responseWriter) Write(b []byte) (int, error) {
	if !rw.wroteFinal {
		rw.statusCode = http.StatusOK
		rw.wroteFinal = true
	}
	n, err := rw.ResponseWriter.Write(b)
	rw.bytesWritten += n
	return n, err
}

// Unwrap exposes the wrapped ResponseWriter so http.ResponseController and
// optional interfaces (Flusher, Hijacker) keep working through this wrapper.
func (rw *responseWriter) Unwrap() http.ResponseWriter { return rw.ResponseWriter }

// silentPaths are high-frequency, low-signal routes we skip in the access log to
// keep production logs readable (health checks, crawlers, well-known files).
var silentPaths = map[string]bool{
	"/health":                   true,
	"/healthz":                  true,
	"/favicon.ico":              true,
	"/robots.txt":               true,
	"/sitemap.xml":              true,
	"/site.webmanifest":         true,
	"/llms.txt":                 true,
	"/humans.txt":               true,
	"/security.txt":             true,
	"/.well-known/security.txt": true,
}

var precompressedExtensions = map[string]bool{
	".avif":  true,
	".gif":   true,
	".gz":    true,
	".ico":   true,
	".jpeg":  true,
	".jpg":   true,
	".mp3":   true,
	".mp4":   true,
	".png":   true,
	".webm":  true,
	".webp":  true,
	".woff":  true,
	".woff2": true,
	".zip":   true,
}

// RequestLogger returns a Middleware that logs each request's method, path,
// status, size, and duration, skipping static assets and silentPaths.
func RequestLogger(logger *slog.Logger) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			silent := strings.HasPrefix(r.URL.Path, "/static/") || silentPaths[r.URL.Path]

			start := time.Now()
			rw := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}
			next.ServeHTTP(rw, r)

			if silent {
				return
			}
			logger.InfoContext(
				r.Context(), "http request processed",
				slog.String("method", r.Method),
				slog.String("path", r.URL.Path),
				slog.Int("status", rw.statusCode),
				slog.Int("size_bytes", rw.bytesWritten),
				slog.Duration("duration", time.Since(start)),
			)
		})
	}
}

// AnalyticsLogger emits one privacy-preserving record for each rendered HTML
// page. It deliberately retains no IP, full referrer, user agent, or visitor ID.
func AnalyticsLogger(logger *slog.Logger) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			rw := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}
			next.ServeHTTP(rw, r)

			if !strings.HasPrefix(rw.Header().Get("Content-Type"), "text/html") || rw.statusCode >= 300 && rw.statusCode < 400 {
				return
			}
			query := r.URL.Query()
			logger.InfoContext(
				r.Context(), analyticsLogName,
				slog.Time("timestamp", time.Now().UTC()),
				slog.String("path", analyticsPath(r.URL.Path, rw.statusCode)),
				slog.Int("status", rw.statusCode),
				slog.String("referer", refererHost(r.Referer())),
				slog.String("utm_source", analyticsDimension(query.Get("utm_source"))),
				slog.String("utm_medium", analyticsDimension(query.Get("utm_medium"))),
				slog.String("utm_campaign", analyticsDimension(query.Get("utm_campaign"))),
				slog.String("country", requestCountry(r.Header)),
				slog.Bool("bot", isBot(r.UserAgent())),
			)
		})
	}
}

func analyticsPath(requestPath string, status int) string {
	// Unknown URLs are attacker-controlled and can contain identifiers. Retain
	// their aggregate outcome without storing the raw 4xx/5xx request path.
	if status >= 500 {
		return "/500"
	}
	if status >= 400 {
		return "/404"
	}
	return requestPath
}

func analyticsDimension(value string) string {
	if len(value) > 128 {
		return ""
	}
	for _, char := range value {
		if char >= 'a' && char <= 'z' || char >= 'A' && char <= 'Z' || char >= '0' && char <= '9' || strings.ContainsRune("._~+-", char) {
			continue
		}
		return ""
	}
	return value
}

func refererHost(referer string) string {
	parsed, err := url.Parse(referer)
	if err != nil {
		return ""
	}
	return strings.ToLower(parsed.Hostname())
}

func requestCountry(header http.Header) string {
	// The external load balancer must remove inbound X-Client-Geo before it
	// injects its value. That boundary is managed outside this Terraform state;
	// infra/main.tf records the externally owned domain mapping.
	country := header.Get("X-Client-Geo")
	if country == "" {
		// External Application Load Balancers can inject client geography through
		// a custom header; accepting this fallback keeps Cloud Run itself untrusted.
		country = header.Get("X-Client-Region")
	}
	country = strings.ToUpper(strings.TrimSpace(country))
	if len(country) != 2 || country[0] < 'A' || country[0] > 'Z' || country[1] < 'A' || country[1] > 'Z' {
		return ""
	}
	return country
}

func isBot(userAgent string) bool {
	userAgent = strings.ToLower(userAgent)
	for _, token := range botUserAgentTokens {
		if strings.Contains(userAgent, token) {
			return true
		}
	}
	return false
}

// CanonicalHost 301-redirects the bare apex domain to its canonical www host in
// production, so search engines index a single origin.
func CanonicalHost(env config.Environment) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			host, _, _ := strings.Cut(r.Host, ":")
			if env == config.Production && host == canonicalApex {
				target := canonicalTarget + r.URL.Path
				if r.URL.RawQuery != "" {
					target += "?" + r.URL.RawQuery
				}
				// The redirect host is a compile-time constant; only the path and
				// query are carried over, so this cannot become an open redirect.
				http.Redirect(w, r, target, http.StatusMovedPermanently) //nolint:gosec // G710: constant canonical host
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// SecurityHeaders injects robust HTTP security headers and a per-request CSP
// nonce shared with templ (templ.WithNonce → templ.GetNonce) so our own inline
// scripts are authorized without 'unsafe-inline'.
func SecurityHeaders(env config.Environment) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// rand.Text returns at least 128 bits of cryptographically random text and
			// has no recoverable error path (Go 1.24+), which is ideal for CSP nonces.
			nonce := rand.Text()

			// Our only scripts are the inline theme + menu snippets, each authorized
			// by this per-request nonce, so neither 'unsafe-inline' nor 'unsafe-eval'
			// is needed — the strongest practical script-src.
			scriptSrc := "'self' 'nonce-" + nonce + "'"
			styleSrc := "'self' 'nonce-" + nonce + "'"

			h := w.Header()
			h.Set("Content-Security-Policy", strings.Join([]string{
				"default-src 'self'",
				"base-uri 'none'",
				"object-src 'none'",
				"frame-ancestors 'none'",
				"form-action 'self'",
				"script-src " + scriptSrc,
				"style-src " + styleSrc,
				"img-src 'self' data:",
				"font-src 'self'",
				"connect-src 'self'",
			}, "; ")+";")
			h.Set("Referrer-Policy", "strict-origin-when-cross-origin")
			h.Set("X-Content-Type-Options", "nosniff")
			h.Set("X-Frame-Options", "DENY")
			h.Set("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
			h.Set("X-Permitted-Cross-Domain-Policies", "none")
			// OWASP: "0" disables the legacy, exploitable XSS auditor; CSP is the defense.
			h.Set("X-XSS-Protection", "0")
			h.Set("Permissions-Policy", "accelerometer=(), autoplay=(self), camera=(), display-capture=(), encrypted-media=(), fullscreen=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), sync-xhr=(), usb=()")

			if env == config.Production {
				h.Set("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
			}

			next.ServeHTTP(w, r.WithContext(templ.WithNonce(r.Context(), nonce)))
		})
	}
}

// MaxBody caps the request body size, turning an oversized payload into a fast
// failure instead of an unbounded in-memory read. It guards the public,
// unauthenticated /mcp endpoint, whose SDK reads the whole body with io.ReadAll.
func MaxBody(n int64) Middleware {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			r.Body = http.MaxBytesReader(w, r.Body, n)
			next.ServeHTTP(w, r)
		})
	}
}

// SkipPrecompressed marks formats that are already compressed so gzhttp passes
// them through byte-for-byte instead of spending CPU to make them slightly
// larger. gzhttp removes its internal marker before writing the response.
func SkipPrecompressed(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if precompressedExtensions[strings.ToLower(path.Ext(r.URL.Path))] {
			w.Header().Set(gzhttp.HeaderNoCompression, "1")
		}
		next.ServeHTTP(w, r)
	})
}

// StaticCache sets long-term, immutable caching for content-hashed asset URLs
// (?v=hash) and for fonts (referenced by fixed, unversioned @font-face URLs), and
// a shorter, revalidated policy for everything else under /static/.
func StaticCache(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Has("v") || strings.HasSuffix(r.URL.Path, ".woff2") {
			w.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
		} else {
			w.Header().Set("Cache-Control", "public, max-age=86400, must-revalidate")
		}
		if hash := templates.AssetHashes[r.URL.Path]; hash != "" {
			etag := `"` + hash + `"`
			w.Header().Set("ETag", etag)
			if etagMatches(r.Header.Get("If-None-Match"), etag) {
				w.WriteHeader(http.StatusNotModified)
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}

func etagMatches(header, current string) bool {
	for candidate := range strings.SplitSeq(header, ",") {
		candidate = strings.TrimSpace(candidate)
		if candidate == "*" || strings.TrimPrefix(candidate, "W/") == current {
			return true
		}
	}
	return false
}
