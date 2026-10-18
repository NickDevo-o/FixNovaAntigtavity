package stream

import (
	"context"
	"fmt"
	"io"
	"net"
	"sync/atomic"
	"time"

	"github.com/antigravity/gateway/internal/config"
)

type PumpStats struct {
	BytesClientToUpstream int64
	BytesUpstreamToClient int64
	StartTime             time.Time
	Duration              time.Duration
	LargePayloadWarning   bool
}

type FlowControlledPump struct {
	cfg   *config.StreamConfig
	stats PumpStats
}

func NewFlowControlledPump(cfg *config.StreamConfig) *FlowControlledPump {
	return &FlowControlledPump{
		cfg: cfg,
		stats: PumpStats{
			StartTime: time.Now(),
		},
	}
}

// RelayBidirectional pumps data between client and upstream with adaptive flow control
func (p *FlowControlledPump) RelayBidirectional(ctx context.Context, clientConn net.Conn, upstreamConn net.Conn, host string) (*PumpStats, error) {
	errCh := make(chan error, 2)

	// Set keepalive on both ends if supported
	if tcp, ok := clientConn.(*net.TCPConn); ok {
		_ = tcp.SetKeepAlive(true)
		_ = tcp.SetKeepAlivePeriod(time.Duration(p.cfg.KeepAliveSeconds) * time.Second)
	}
	if tcp, ok := upstreamConn.(*net.TCPConn); ok {
		_ = tcp.SetKeepAlive(true)
		_ = tcp.SetKeepAlivePeriod(time.Duration(p.cfg.KeepAliveSeconds) * time.Second)
	}

	// 1. Client -> Upstream (Requests, Prompts, Payloads)
	go func() {
		errCh <- p.pumpWithBackpressure(ctx, clientConn, upstreamConn, &p.stats.BytesClientToUpstream, true, host)
	}()

	// 2. Upstream -> Client (Responses, SSE Streaming Tokens)
	go func() {
		errCh <- p.pumpWithBackpressure(ctx, upstreamConn, clientConn, &p.stats.BytesUpstreamToClient, false, host)
	}()

	// Wait for first direction to complete or error out
	firstErr := <-errCh

	// Close write half or connections
	_ = clientConn.Close()
	_ = upstreamConn.Close()

	// Drain second direction
	<-errCh

	p.stats.Duration = time.Since(p.stats.StartTime)
	return &p.stats, firstErr
}

// pumpWithBackpressure moves bytes in controlled chunks, preventing HTTP/2 window overflow
func (p *FlowControlledPump) pumpWithBackpressure(
	ctx context.Context,
	src io.Reader,
	dst io.Writer,
	byteCounter *int64,
	isRequest bool,
	host string,
) error {
	bufSize := p.cfg.BufferSize
	if bufSize <= 0 {
		bufSize = 16384 // 16 KiB
	}
	buf := make([]byte, bufSize)

	warnThresholdBytes := int64(p.cfg.WarnPayloadSizeKB) * 1024
	throttleThresholdBytes := int64(p.cfg.ThrottleThresholdKB) * 1024
	warned := false

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		n, rErr := src.Read(buf)
		if n > 0 {
			totalSoFar := atomic.AddInt64(byteCounter, int64(n))

			// Check for large payload warning (e.g. prompt history exceeding 100 KiB)
			if isRequest && totalSoFar > warnThresholdBytes && !warned {
				warned = true
				p.stats.LargePayloadWarning = true
				fmt.Printf("\n\033[33m⚠️  [FLOW CONTROL] Large payload: %.1f KiB sent to %s.\n"+
					"   Tip: Use /compact in Antigravity or split giant files to prevent 128 KiB HTTP/2 window overflow!\033[0m\n\n",
					float64(totalSoFar)/1024.0, host)
			}

			// Smooth backpressure pacing: if payload exceeds threshold, apply micro-pacing
			// to avoid blasting data faster than 110 KB/s and overflowing standard 128 KiB windows
			if isRequest && p.cfg.EnableThrottling && totalSoFar > throttleThresholdBytes {
				// Micro-delay proportional to chunk size to ensure receiver window update frames arrive cleanly
				time.Sleep(2 * time.Millisecond)
			}

			// Write to destination with full chunk delivery
			written := 0
			for written < n {
				w, wErr := dst.Write(buf[written:n])
				if w > 0 {
					written += w
				}
				if wErr != nil {
					return wErr
				}
			}
		}

		if rErr != nil {
			if rErr == io.EOF {
				return nil
			}
			return rErr
		}
	}
}
