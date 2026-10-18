package proxy

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/antigravity/gateway/internal/config"
	"github.com/antigravity/gateway/internal/doh"
)

type Server struct {
	cfg           *config.Config
	resolver      *doh.Resolver
	tunnelMgr     *TunnelManager
	httpServer    *http.Server
	listener      net.Listener
	activePort    int
	forwardClient *http.Client
	mu            sync.Mutex
	isShutdown    bool
}

func NewServer(cfg *config.Config, resolver *doh.Resolver) *Server {
	tm := NewTunnelManager(cfg, resolver)

	transport := &http.Transport{
		DialContext:         resolver.DialContext,
		MaxIdleConns:        100,
		IdleConnTimeout:     90 * time.Second,
		TLSHandshakeTimeout: 10 * time.Second,
	}

	client := &http.Client{
		Transport: transport,
		Timeout:   60 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse // Don't follow redirects automatically
		},
	}

	return &Server{
		cfg:           cfg,
		resolver:      resolver,
		tunnelMgr:     tm,
		forwardClient: client,
	}
}

// Start binds to the configured port (with fallback range) and serves requests
func (s *Server) Start() (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	host := s.cfg.Server.Host
	if host == "" {
		host = "127.0.0.1"
	}
	startPort := s.cfg.Server.Port
	if startPort <= 0 {
		startPort = 10809
	}

	var listener net.Listener
	var err error
	actualPort := startPort

	// Try primary port, and if auto_port is enabled, try subsequent ports
	maxAttempts := 1
	if s.cfg.Server.AutoPort {
		maxAttempts = 12
	}

	for i := 0; i < maxAttempts; i++ {
		candidatePort := startPort + i
		addr := fmt.Sprintf("%s:%d", host, candidatePort)
		listener, err = net.Listen("tcp", addr)
		if err == nil {
			actualPort = candidatePort
			break
		}
	}

	if err != nil {
		return 0, fmt.Errorf("failed to bind to %s:%d-%d: %w", host, startPort, startPort+maxAttempts-1, err)
	}

	s.listener = listener
	s.activePort = actualPort

	mux := http.NewServeMux()
	mux.HandleFunc("/gateway-status", s.handleStatus)
	mux.HandleFunc("/", s.handleProxy)

	s.httpServer = &http.Server{
		Handler:           mux,
		ReadHeaderTimeout: 15 * time.Second,
		IdleTimeout:       120 * time.Second,
	}

	go func() {
		if serveErr := s.httpServer.Serve(listener); serveErr != nil && serveErr != http.ErrServerClosed {
			fmt.Printf("\033[31m[SERVER ERROR] %v\033[0m\n", serveErr)
		}
	}()

	return actualPort, nil
}

// ActivePort returns currently bound port
func (s *Server) ActivePort() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.activePort
}

// Stop gracefully shuts down proxy
func (s *Server) Stop(ctx context.Context) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.isShutdown = true
	if s.httpServer != nil {
		return s.httpServer.Shutdown(ctx)
	}
	return nil
}

func (s *Server) handleStatus(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(fmt.Sprintf(`{"status":"online","port":%d,"mode":"%s","doh_enabled":%t}`,
		s.activePort, s.cfg.Upstream.Mode, s.cfg.DNS.Enabled)))
}

func (s *Server) handleProxy(w http.ResponseWriter, r *http.Request) {
	// 1. If HTTP CONNECT (HTTPS tunneling)
	if r.Method == http.MethodConnect {
		s.tunnelMgr.HandleConnectTunnel(w, r)
		return
	}

	// 2. Standard Forward Proxy Request (GET, POST, etc.)
	start := time.Now()
	SanitizeHeaders(r.Header)
	NormalizeGoogleHeaders(r.Header)

	// Create forwarded request
	outURL := r.URL
	if outURL.Scheme == "" {
		outURL.Scheme = "https"
	}
	if outURL.Host == "" {
		outURL.Host = r.Host
	}

	outReq, err := http.NewRequestWithContext(r.Context(), r.Method, outURL.String(), r.Body)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Copy headers
	for k, vv := range r.Header {
		for _, v := range vv {
			outReq.Header.Add(k, v)
		}
	}
	outReq.Header.Del("Proxy-Connection")

	resp, err := s.forwardClient.Do(outReq)
	if err != nil {
		http.Error(w, fmt.Sprintf("Upstream gateway error: %v", err), http.StatusBadGateway)
		fmt.Printf("\033[31m❌ [HTTP] %s %s (ERR: %v)\033[0m\n", r.Method, r.URL.String(), err)
		return
	}
	defer resp.Body.Close()

	// Copy response headers
	for k, vv := range resp.Header {
		for _, v := range vv {
			w.Header().Add(k, v)
		}
	}
	w.WriteHeader(resp.StatusCode)

	// Stream response body with immediate flush (SSE support)
	flusher, canFlush := w.(http.Flusher)
	buf := make([]byte, 16384)
	var totalBytes int64

	for {
		n, rErr := resp.Body.Read(buf)
		if n > 0 {
			wN, wErr := w.Write(buf[:n])
			totalBytes += int64(wN)
			if canFlush {
				flusher.Flush()
			}
			if wErr != nil {
				break
			}
		}
		if rErr != nil {
			break
		}
	}

	codeColor := "\033[32m" // 2xx Green
	if resp.StatusCode >= 400 && resp.StatusCode < 500 {
		codeColor = "\033[33m" // 4xx Yellow
	} else if resp.StatusCode >= 500 {
		codeColor = "\033[31m" // 5xx Red
	}

	fmt.Printf("%s[HTTP %d] %s %s | %.1f KiB | %v\033[0m\n",
		codeColor,
		resp.StatusCode,
		r.Method,
		r.Host,
		float64(totalBytes)/1024.0,
		time.Since(start).Round(time.Millisecond),
	)
}
