package proxy

import (
	"net/http"
	"strings"
)

// BlockedHeaders contains headers that leak client geolocation or trigger region checks
var BlockedHeaders = []string{
	"x-client-geo",
	"x-client-country",
	"cf-ipcountry",
	"x-forwarded-for",
	"x-real-ip",
	"x-user-ip",
	"true-client-ip",
	"x-appengine-country",
	"x-appengine-region",
	"x-appengine-city",
}

// SanitizeHeaders removes headers that can leak regional location or disrupt Google AI requests
func SanitizeHeaders(header http.Header) {
	for _, h := range BlockedHeaders {
		header.Del(h)
		// Case insensitive check
		for k := range header {
			if strings.EqualFold(k, h) {
				delete(header, k)
			}
		}
	}
}

// NormalizeGoogleHeaders ensures proper User-Agent and content headers for Gemini / Cloud Code API
func NormalizeGoogleHeaders(header http.Header) {
	SanitizeHeaders(header)

	// Ensure Accept header handles SSE if requested
	if strings.Contains(strings.ToLower(header.Get("Accept")), "event-stream") {
		header.Set("Accept", "text/event-stream")
		header.Set("Cache-Control", "no-cache")
		header.Set("Connection", "keep-alive")
	}
}
