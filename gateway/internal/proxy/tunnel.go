package proxy

import (
	"bufio"
	"context"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/antigravity/gateway/internal/config"
	"github.com/antigravity/gateway/internal/doh"
	"github.com/antigravity/gateway/internal/stream"
)

type TunnelManager struct {
	cfg      *config.Config
	resolver *doh.Resolver
}

func NewTunnelManager(cfg *config.Config, resolver *doh.Resolver) *TunnelManager {
	return &TunnelManager{
		cfg:      cfg,
		resolver: resolver,
	}
}

// DialTarget connects to the remote host using Direct (zapret-compatible) or Upstream Proxy with graceful fallback
func (t *TunnelManager) DialTarget(ctx context.Context, targetAddr string) (net.Conn, string, error) {
	mode := strings.ToLower(t.cfg.Upstream.Mode)

	// Mode 1: Upstream Proxy configured
	if mode == "proxy" && strings.TrimSpace(t.cfg.Upstream.ProxyURL) != "" {
		proxyURLStr := strings.TrimSpace(t.cfg.Upstream.ProxyURL)
		conn, err := t.dialViaProxy(ctx, proxyURLStr, targetAddr)
		if err == nil {
			return conn, "proxy (" + proxyURLStr + ")", nil
		}

		// Check for connection refused (os error 10061) or fallback setting
		if t.cfg.Upstream.FallbackToDirect {
			fmt.Printf("\033[33m⚠️  [FAILOVER] Upstream proxy %s failed (%v). Falling back to zapret-Direct!\033[0m\n", proxyURLStr, err)
			directConn, dErr := t.dialDirect(ctx, targetAddr)
			if dErr == nil {
				return directConn, "direct (failover)", nil
			}
			return nil, "", fmt.Errorf("both upstream proxy and direct failover failed: %v, %v", err, dErr)
		}

		return nil, "", fmt.Errorf("upstream proxy connection failed: %w", err)
	}

	// Mode 2: Direct (zapret-compatible with DoH resolution)
	conn, err := t.dialDirect(ctx, targetAddr)
	if err != nil {
		return nil, "", err
	}
	return conn, "direct (zapret)", nil
}

func (t *TunnelManager) dialDirect(ctx context.Context, targetAddr string) (net.Conn, error) {
	timeout := time.Duration(t.cfg.Upstream.TimeoutSeconds) * time.Second
	if timeout <= 0 {
		timeout = 15 * time.Second
	}

	dialCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	return t.resolver.DialContext(dialCtx, "tcp", targetAddr)
}

func (t *TunnelManager) dialViaProxy(ctx context.Context, proxyURLStr, targetAddr string) (net.Conn, error) {
	parsedURL, err := url.Parse(proxyURLStr)
	if err != nil {
		return nil, fmt.Errorf("invalid proxy URL %s: %w", proxyURLStr, err)
	}

	dialer := &net.Dialer{
		Timeout:   time.Duration(t.cfg.Upstream.TimeoutSeconds) * time.Second,
		KeepAlive: 30 * time.Second,
	}

	switch strings.ToLower(parsedURL.Scheme) {
	case "socks5":
		return t.dialSocks5(ctx, dialer, parsedURL, targetAddr)
	case "http", "https":
		return t.dialHTTPProxy(ctx, dialer, parsedURL, targetAddr)
	default:
		return nil, fmt.Errorf("unsupported proxy scheme: %s", parsedURL.Scheme)
	}
}

func (t *TunnelManager) dialHTTPProxy(ctx context.Context, dialer *net.Dialer, proxyURL *url.URL, targetAddr string) (net.Conn, error) {
	proxyConn, err := dialer.DialContext(ctx, "tcp", proxyURL.Host)
	if err != nil {
		return nil, err
	}

	// Send HTTP CONNECT to proxy
	connectReq := fmt.Sprintf("CONNECT %s HTTP/1.1\r\nHost: %s\r\nProxy-Connection: Keep-Alive\r\n\r\n", targetAddr, targetAddr)
	if _, err := proxyConn.Write([]byte(connectReq)); err != nil {
		_ = proxyConn.Close()
		return nil, err
	}

	resp, err := http.ReadResponse(bufio.NewReader(proxyConn), &http.Request{Method: "CONNECT"})
	if err != nil {
		_ = proxyConn.Close()
		return nil, err
	}
	_ = resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		_ = proxyConn.Close()
		return nil, fmt.Errorf("proxy CONNECT rejected with status %d %s", resp.StatusCode, resp.Status)
	}

	return proxyConn, nil
}

func (t *TunnelManager) dialSocks5(ctx context.Context, dialer *net.Dialer, proxyURL *url.URL, targetAddr string) (net.Conn, error) {
	conn, err := dialer.DialContext(ctx, "tcp", proxyURL.Host)
	if err != nil {
		return nil, err
	}

	// Simple SOCKS5 handshake (no auth)
	// 1. Client greeting: VER=5, NMETHODS=1, METHOD=0 (no auth)
	if _, err := conn.Write([]byte{0x05, 0x01, 0x00}); err != nil {
		_ = conn.Close()
		return nil, err
	}

	resp := make([]byte, 2)
	if _, err := conn.Read(resp); err != nil || resp[0] != 0x05 || resp[1] != 0x00 {
		_ = conn.Close()
		return nil, fmt.Errorf("socks5 greeting rejected or requires auth")
	}

	// 2. Client connection request
	host, portStr, err := net.SplitHostPort(targetAddr)
	if err != nil {
		_ = conn.Close()
		return nil, err
	}
	var port uint16
	fmt.Sscanf(portStr, "%d", &port)

	req := []byte{0x05, 0x01, 0x00, 0x03, byte(len(host))}
	req = append(req, []byte(host)...)
	req = append(req, byte(port>>8), byte(port&0xff))

	if _, err := conn.Write(req); err != nil {
		_ = conn.Close()
		return nil, err
	}

	// Read reply
	reply := make([]byte, 10)
	if _, err := conn.Read(reply); err != nil || reply[1] != 0x00 {
		_ = conn.Close()
		return nil, fmt.Errorf("socks5 connect failed with code 0x%02x", reply[1])
	}

	return conn, nil
}

// HandleConnectTunnel bridges client CONNECT request with destination
func (t *TunnelManager) HandleConnectTunnel(w http.ResponseWriter, r *http.Request) {
	targetAddr := r.Host
	if !strings.Contains(targetAddr, ":") {
		targetAddr = net.JoinHostPort(targetAddr, "443")
	}

	start := time.Now()

	// Connect to destination
	destConn, routeDesc, err := t.DialTarget(r.Context(), targetAddr)
	if err != nil {
		http.Error(w, fmt.Sprintf("Gateway tunnel failure: %v", err), http.StatusBadGateway)
		fmt.Printf("\033[31m❌ [CONNECT] %s -> %s (ERR: %v)\033[0m\n", r.RemoteAddr, targetAddr, err)
		return
	}
	defer destConn.Close()

	// Hijack client connection
	hijacker, ok := w.(http.Hijacker)
	if !ok {
		http.Error(w, "HTTP Hijacking not supported", http.StatusInternalServerError)
		return
	}

	clientConn, _, err := hijacker.Hijack()
	if err != nil {
		http.Error(w, err.Error(), http.StatusServiceUnavailable)
		return
	}
	defer clientConn.Close()

	// Send 200 Connection Established to client
	_, _ = clientConn.Write([]byte("HTTP/1.1 200 Connection Established\r\n\r\n"))

	// Stream with flow control pump
	pump := stream.NewFlowControlledPump(&t.cfg.Stream)
	stats, _ := pump.RelayBidirectional(r.Context(), clientConn, destConn, targetAddr)

	latency := time.Since(start)
	statusColor := "\033[32m" // Green
	if stats.LargePayloadWarning {
		statusColor = "\033[33m" // Yellow
	}

	fmt.Printf("%s✔ [TUNNEL] %s -> %s | In: %.1f KiB | Out: %.1f KiB | %s | %v\033[0m\n",
		statusColor,
		r.RemoteAddr,
		targetAddr,
		float64(stats.BytesClientToUpstream)/1024.0,
		float64(stats.BytesUpstreamToClient)/1024.0,
		routeDesc,
		latency.Round(time.Millisecond),
	)
}
