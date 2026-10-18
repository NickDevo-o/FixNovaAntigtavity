package cleaner

import (
	"context"
	"crypto/tls"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"time"
)

type WarmupResult struct {
	Endpoint string
	Success  bool
	Latency  time.Duration
	Status   int
	Error    error
}

// WarmupGoogleSocket sends a probe request to verify connectivity and warm up TLS sockets
func WarmupGoogleSocket(proxyPort int) WarmupResult {
	proxyURL, _ := url.Parse(fmt.Sprintf("http://127.0.0.1:%d", proxyPort))

	transport := &http.Transport{
		Proxy: http.ProxyURL(proxyURL),
		TLSClientConfig: &tls.Config{
			InsecureSkipVerify: true,
		},
		DialContext: (&net.Dialer{
			Timeout: 5 * time.Second,
		}).DialContext,
		TLSHandshakeTimeout: 5 * time.Second,
	}

	client := &http.Client{
		Transport: transport,
		Timeout:   8 * time.Second,
	}

	testURL := "https://accounts.google.com/generate_204"
	start := time.Now()

	req, err := http.NewRequestWithContext(context.Background(), "GET", testURL, nil)
	if err != nil {
		return WarmupResult{Endpoint: testURL, Success: false, Error: err}
	}
	req.Header.Set("User-Agent", "AntigravityGateway-Probe/2.0")

	resp, err := client.Do(req)
	latency := time.Since(start)

	if err != nil {
		return WarmupResult{
			Endpoint: testURL,
			Success:  false,
			Latency:  latency,
			Error:    err,
		}
	}
	defer resp.Body.Close()

	return WarmupResult{
		Endpoint: testURL,
		Success:  resp.StatusCode == 204 || resp.StatusCode == 200,
		Latency:  latency,
		Status:   resp.StatusCode,
	}
}
