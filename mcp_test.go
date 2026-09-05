package site_test

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	site "github.com/fmind/www"
)

func TestMCPEndpoint(t *testing.T) {
	srv := newServer(t)

	reqBody := `{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{` +
		`"io.modelcontextprotocol/protocolVersion":"2026-07-28",` +
		`"io.modelcontextprotocol/clientInfo":{"name":"test","version":"1.0"},` +
		`"io.modelcontextprotocol/clientCapabilities":{}}}}`
	req := newMCPRequest(t, srv.URL, "server/discover", "", reqBody)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("POST /mcp: %v", err)
	}
	defer closeBody(t, resp.Body)
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read MCP response: %v", err)
	}

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200; body=%s", resp.StatusCode, body)
	}
	if !strings.Contains(string(body), `"jsonrpc"`) || !strings.Contains(string(body), site.ServiceName) {
		t.Errorf("unexpected MCP discover response: %s", body)
	}
	for _, want := range []string{
		`"supportedVersions":["2026-07-28"`,
		`"websiteUrl":"https://www.fmind.dev/"`,
		`"icons"`,
		"AI Architect (PhD) • VC Expert Advisor",
	} {
		if !strings.Contains(string(body), want) {
			t.Errorf("MCP discover response missing %s: %s", want, body)
		}
	}
	if sessionID := resp.Header.Get("Mcp-Session-Id"); sessionID != "" {
		t.Errorf("stateless MCP session ID = %q, want empty", sessionID)
	}

	publicationsBody := `{"jsonrpc":"2.0","id":2,"method":"tools/call",` +
		`"params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",` +
		`"io.modelcontextprotocol/clientInfo":{"name":"test","version":"1.0"},` +
		`"io.modelcontextprotocol/clientCapabilities":{}},` +
		`"name":"list_publications","arguments":{}}}`
	publicationsReq := newMCPRequest(t, srv.URL, "tools/call", "list_publications", publicationsBody)
	publicationsResp, err := http.DefaultClient.Do(publicationsReq)
	if err != nil {
		t.Fatalf("call list_publications: %v", err)
	}
	defer closeBody(t, publicationsResp.Body)
	publications, err := io.ReadAll(publicationsResp.Body)
	if err != nil {
		t.Fatalf("read publications response: %v", err)
	}
	if publicationsResp.StatusCode != http.StatusOK {
		t.Fatalf("list_publications status = %d; body=%s", publicationsResp.StatusCode, publications)
	}
	for _, want := range []string{
		`"articles"`,
		`MCP 2026–07–28: Stateless core, enterprise authorization, and SDK betas`,
		`https://www.fmind.dev/articles/mcp-2026-07-28-stateless-core-enterprise-authorization-and-sdk-betas/`,
	} {
		if !strings.Contains(string(publications), want) {
			t.Errorf("list_publications response missing %q: %s", want, publications)
		}
	}

	listBody := `{"jsonrpc":"2.0","id":3,"method":"prompts/list","params":{` +
		`"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",` +
		`"io.modelcontextprotocol/clientInfo":{"name":"test","version":"1.0"},` +
		`"io.modelcontextprotocol/clientCapabilities":{}}}}`
	listResp, err := http.DefaultClient.Do(newMCPRequest(t, srv.URL, "prompts/list", "", listBody))
	if err != nil {
		t.Fatalf("list prompts: %v", err)
	}
	defer closeBody(t, listResp.Body)
	prompts, err := io.ReadAll(listResp.Body)
	if err != nil {
		t.Fatalf("read prompts response: %v", err)
	}
	for _, want := range []string{`"name":"assess_fit"`, `"name":"brief_me"`, `"ttlMs":3600000`} {
		if !strings.Contains(string(prompts), want) {
			t.Errorf("prompts/list response missing %s: %s", want, prompts)
		}
	}

	promptBody := `{"jsonrpc":"2.0","id":4,"method":"prompts/get","params":{` +
		`"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",` +
		`"io.modelcontextprotocol/clientInfo":{"name":"test","version":"1.0"},` +
		`"io.modelcontextprotocol/clientCapabilities":{}},` +
		`"name":"assess_fit","arguments":{"brief":"Secure an enterprise agent platform"}}}`
	promptResp, err := http.DefaultClient.Do(newMCPRequest(t, srv.URL, "prompts/get", "assess_fit", promptBody))
	if err != nil {
		t.Fatalf("get prompt: %v", err)
	}
	defer closeBody(t, promptResp.Body)
	prompt, err := io.ReadAll(promptResp.Body)
	if err != nil {
		t.Fatalf("read prompt response: %v", err)
	}
	for _, want := range []string{"Secure an enterprise agent platform", "list_experience", "evidence-based fit assessment"} {
		if !strings.Contains(string(prompt), want) {
			t.Errorf("prompts/get response missing %q: %s", want, prompt)
		}
	}
}

func TestMCPRejectsCrossOriginBrowserPost(t *testing.T) {
	srv := newServer(t)

	reqBody := `{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{` +
		`"io.modelcontextprotocol/protocolVersion":"2026-07-28",` +
		`"io.modelcontextprotocol/clientInfo":{"name":"test","version":"1.0"},` +
		`"io.modelcontextprotocol/clientCapabilities":{}}}}`
	req := newMCPRequest(t, srv.URL, "server/discover", "", reqBody)
	req.Header.Set("Origin", "https://evil.example")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("POST /mcp: %v", err)
	}
	defer closeBody(t, resp.Body)
	if resp.StatusCode != http.StatusForbidden {
		body, err := io.ReadAll(resp.Body)
		if err != nil {
			t.Fatalf("read MCP response: %v", err)
		}
		t.Fatalf("status = %d, want 403; body=%s", resp.StatusCode, body)
	}
}

func TestMCPAcceptsSameOriginBrowserPost(t *testing.T) {
	srv := newServer(t)

	reqBody := `{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{` +
		`"io.modelcontextprotocol/protocolVersion":"2026-07-28",` +
		`"io.modelcontextprotocol/clientInfo":{"name":"test","version":"1.0"},` +
		`"io.modelcontextprotocol/clientCapabilities":{}}}}`
	req := newMCPRequest(t, srv.URL, "server/discover", "", reqBody)
	req.Header.Set("Origin", srv.URL)
	req.Header.Set("Sec-Fetch-Site", "same-origin")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("POST /mcp: %v", err)
	}
	defer closeBody(t, resp.Body)
	if resp.StatusCode != http.StatusOK {
		body, err := io.ReadAll(resp.Body)
		if err != nil {
			t.Fatalf("read MCP response: %v", err)
		}
		t.Fatalf("status = %d, want 200; body=%s", resp.StatusCode, body)
	}
}

func newMCPRequest(t *testing.T, serverURL, method, name, body string) *http.Request {
	t.Helper()
	req, err := http.NewRequest(http.MethodPost, serverURL+"/mcp", strings.NewReader(body))
	if err != nil {
		t.Fatalf("new MCP request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	req.Header.Set("Mcp-Protocol-Version", "2026-07-28")
	req.Header.Set("Mcp-Method", method)
	if name != "" {
		req.Header.Set("Mcp-Name", name)
	}
	return req
}

// TestMaxBodyCapsRequestBody proves the /mcp guard: an oversized body trips the
// MaxBytesReader mid-read (so memory stays bounded and the handler errors),
// while a request within the limit passes through untouched.
func TestMaxBodyCapsRequestBody(t *testing.T) {
	const limit = 1 << 10 // 1 KiB

	handler := site.MaxBody(limit)(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if _, err := io.Copy(io.Discard, r.Body); err != nil {
			http.Error(w, "too large", http.StatusRequestEntityTooLarge)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)

	over, err := http.Post(srv.URL, "text/plain", strings.NewReader(strings.Repeat("a", 4*limit)))
	if err != nil {
		t.Fatalf("post oversized body: %v", err)
	}
	defer closeBody(t, over.Body)
	if over.StatusCode != http.StatusRequestEntityTooLarge {
		t.Errorf("oversized body status = %d, want 413", over.StatusCode)
	}

	under, err := http.Post(srv.URL, "text/plain", strings.NewReader("small body"))
	if err != nil {
		t.Fatalf("post small body: %v", err)
	}
	defer closeBody(t, under.Body)
	if under.StatusCode != http.StatusOK {
		t.Errorf("small body status = %d, want 200", under.StatusCode)
	}
}

// TestMCPSearchArticlesTool proves agents can ask what Fmind wrote about a topic
// instead of pulling the whole archive: the tool ranks, bounds, and reports the
// total so a client knows whether it saw everything.
func TestMCPSearchArticlesTool(t *testing.T) {
	srv := newServer(t)

	body := `{"jsonrpc":"2.0","id":1,"method":"tools/call",` +
		`"params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",` +
		`"io.modelcontextprotocol/clientInfo":{"name":"test","version":"1.0"},` +
		`"io.modelcontextprotocol/clientCapabilities":{}},` +
		`"name":"search_articles","arguments":{"query":"kubeflow","limit":3}}}`
	resp, err := http.DefaultClient.Do(newMCPRequest(t, srv.URL, "tools/call", "search_articles", body))
	if err != nil {
		t.Fatalf("call search_articles: %v", err)
	}
	defer closeBody(t, resp.Body)
	payload, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatalf("read search response: %v", err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("search_articles status = %d; body=%s", resp.StatusCode, payload)
	}
	for _, want := range []string{
		`"query":"kubeflow"`,
		`"total":`,
		"How to install Kubeflow Pipelines v2 on Apple Silicon",
	} {
		if !strings.Contains(string(payload), want) {
			t.Errorf("search_articles response missing %q: %s", want, payload)
		}
	}

	// An empty query is a client bug, not an invitation to dump every article.
	emptyBody := strings.Replace(body, `"query":"kubeflow"`, `"query":"  "`, 1)
	emptyResp, err := http.DefaultClient.Do(newMCPRequest(t, srv.URL, "tools/call", "search_articles", emptyBody))
	if err != nil {
		t.Fatalf("call search_articles with an empty query: %v", err)
	}
	defer closeBody(t, emptyResp.Body)
	empty, err := io.ReadAll(emptyResp.Body)
	if err != nil {
		t.Fatalf("read empty search response: %v", err)
	}
	if !strings.Contains(string(empty), "query must not be empty") {
		t.Errorf("empty query was not rejected: %s", empty)
	}
}
