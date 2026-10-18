package doh

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/antigravity/gateway/internal/config"
)

type DNSAnswer struct {
	Name string `json:"name"`
	Type int    `json:"type"`
	TTL  int    `json:"TTL"`
	Data string `json:"data"`
}

type DNSResponse struct {
	Status int         `json:"Status"`
	Answer []DNSAnswer `json:"Answer"`
}

type cacheEntry struct {
	ips       []net.IP
	expiresAt time.Time
}

type Resolver struct {
	cfg        *config.DNSConfig
	httpClient *http.Client
	cache      map[string]cacheEntry
	mu         sync.RWMutex
}

var googleDomainSuffixes = []string{
	"googleapis.com",
	"google.com",
	"googleusercontent.com",
	"gstatic.com",
	"google.dev",
	"deepmind.com",
	"deepmind.google",
	"gemini.google",
	"youtube.com",
}

func NewResolver(cfg *config.DNSConfig) *Resolver {
	tr := &http.Transport{
		TLSClientConfig: &tls.Config{
			InsecureSkipVerify: false,
		},
		DialContext: (&net.Dialer{
			Timeout:   5 * time.Second,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		MaxIdleConns:        50,
		IdleConnTimeout:     90 * time.Second,
		TLSHandshakeTimeout: 5 * time.Second,
	}

	return &Resolver{
		cfg: cfg,
		httpClient: &http.Client{
			Transport: tr,
			Timeout:   6 * time.Second,
		},
		cache: make(map[string]cacheEntry),
	}
}

// ShouldResolveViaDoH checks if the domain is a target AI or Google endpoint
func (r *Resolver) ShouldResolveViaDoH(host string) bool {
	if !r.cfg.Enabled {
		return false
	}
	host = strings.ToLower(strings.TrimSuffix(host, "."))
	for _, suffix := range googleDomainSuffixes {
		if host == suffix || strings.HasSuffix(host, "."+suffix) {
			return true
		}
	}
	return false
}

// ResolveHost resolves a hostname to an IP address using DoH with in-memory caching
func (r *Resolver) ResolveHost(ctx context.Context, host string) ([]net.IP, error) {
	host = strings.ToLower(strings.TrimSuffix(host, "."))

	// If it's already an IP address, return directly
	if ip := net.ParseIP(host); ip != nil {
		return []net.IP{ip}, nil
	}

	// 1. Check in-memory cache
	r.mu.RLock()
	entry, found := r.cache[host]
	r.mu.RUnlock()
	if found && time.Now().Before(entry.expiresAt) {
		return entry.ips, nil
	}

	// 2. Resolve via DoH
	ips, ttl, err := r.queryDoH(ctx, host)
	if err == nil && len(ips) > 0 {
		r.mu.Lock()
		if ttl <= 0 {
			ttl = r.cfg.CacheTTLMinutes * 60
		}
		r.cache[host] = cacheEntry{
			ips:       ips,
			expiresAt: time.Now().Add(time.Duration(ttl) * time.Second),
		}
		r.mu.Unlock()
		return ips, nil
	}

	// 3. Fallback to standard system resolver if DoH fails
	sysIPs, sysErr := net.DefaultResolver.LookupIP(ctx, "ip4", host)
	if sysErr == nil && len(sysIPs) > 0 {
		return sysIPs, nil
	}

	if err != nil {
		return nil, fmt.Errorf("doh resolution failed for %s: %w", host, err)
	}
	return nil, fmt.Errorf("no IP addresses found for %s", host)
}

func (r *Resolver) queryDoH(ctx context.Context, host string) ([]net.IP, int, error) {
	// Try primary DoH endpoints
	endpoints := r.cfg.CustomDoHURLs
	if len(endpoints) == 0 {
		endpoints = []string{
			"https://1.1.1.1/dns-query",
			"https://dns.google/resolve",
			"https://9.9.9.9/dns-query",
		}
	}

	var lastErr error
	for _, ep := range endpoints {
		ips, ttl, err := r.querySingleEndpoint(ctx, ep, host)
		if err == nil && len(ips) > 0 {
			return ips, ttl, nil
		}
		lastErr = err
	}

	return nil, 0, lastErr
}

func (r *Resolver) querySingleEndpoint(ctx context.Context, ep string, host string) ([]net.IP, int, error) {
	reqURL := fmt.Sprintf("%s?name=%s&type=A", ep, url.QueryEscape(host))
	req, err := http.NewRequestWithContext(ctx, "GET", reqURL, nil)
	if err != nil {
		return nil, 0, err
	}

	req.Header.Set("Accept", "application/dns-json")
	req.Header.Set("User-Agent", "AntigravityGateway/2.0")

	resp, err := r.httpClient.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, 0, fmt.Errorf("doh server returned HTTP %d", resp.StatusCode)
	}

	var dnsResp DNSResponse
	if err := json.NewDecoder(resp.Body).Decode(&dnsResp); err != nil {
		return nil, 0, err
	}

	var ips []net.IP
	minTTL := 300
	for _, ans := range dnsResp.Answer {
		if ans.Type == 1 { // Type 1 is A (IPv4)
			if parsed := net.ParseIP(ans.Data); parsed != nil {
				ips = append(ips, parsed)
				if ans.TTL > 0 && ans.TTL < minTTL {
					minTTL = ans.TTL
				}
			}
		}
	}

	if len(ips) == 0 {
		return nil, 0, fmt.Errorf("no A records returned for %s", host)
	}

	return ips, minTTL, nil
}

// FlushCache clears in-memory resolved IPs
func (r *Resolver) FlushCache() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	count := len(r.cache)
	r.cache = make(map[string]cacheEntry)
	return count
}

// DialContext creates a net.Dialer that uses DoH for Google domains
func (r *Resolver) DialContext(ctx context.Context, network, address string) (net.Conn, error) {
	host, port, err := net.SplitHostPort(address)
	if err != nil {
		host = address
		port = "443"
	}

	dialer := &net.Dialer{
		Timeout:   10 * time.Second,
		KeepAlive: 30 * time.Second,
	}

	if r.ShouldResolveViaDoH(host) {
		ips, err := r.ResolveHost(ctx, host)
		if err == nil && len(ips) > 0 {
			// Connect to first available IP
			targetAddr := net.JoinHostPort(ips[0].String(), port)
			return dialer.DialContext(ctx, network, targetAddr)
		}
	}

	// Default dial
	return dialer.DialContext(ctx, network, address)
}
