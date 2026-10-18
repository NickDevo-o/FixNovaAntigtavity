#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NovaAntigravity Relay (AG-Relay) v1.0.0
Open-source streaming proxy & flow-control relay for Google Antigravity & Gemini.
Bypasses the 128 KiB buffer drops, 2-10 min lockout penalties, and closed-source issues.

Usage:
    python relay.py [--port 10809] [--bind 127.0.0.1] [--upstream PROXY_URL] [--doh]
"""

import sys
import os
import asyncio
import socket
import logging
import argparse
import urllib.request
import json
import ssl
from typing import Optional, Tuple

VERSION = "1.0.0"

# ANSI Colors for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
DIM = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Pacing configuration
# 32 KiB chunk size matches optimum TCP window without bursting
CHUNK_SIZE = 32 * 1024
# Micro-pause (seconds) yielded when sending large chunks to maintain smooth flow
PACING_DELAY = 0.001

class Stats:
    def __init__(self):
        self.active_tunnels = 0
        self.total_requests = 0
        self.bytes_sent = 0
        self.bytes_received = 0

stats = Stats()

class DoHResolver:
    """Optional DNS-over-HTTPS resolver using Cloudflare / Google DoH."""
    def __init__(self, endpoint: str = "https://1.1.1.1/dns-query"):
        self.endpoint = endpoint
        self.cache = {}
        self.ssl_ctx = ssl.create_default_context()

    async def resolve(self, hostname: str) -> str:
        if hostname in self.cache:
            return self.cache[hostname]
        
        # Don't resolve IP literals or localhost
        if hostname in ("127.0.0.1", "localhost") or hostname.replace(".", "").isdigit():
            return hostname

        loop = asyncio.get_running_loop()
        try:
            ip = await loop.run_in_executor(None, self._sync_resolve, hostname)
            if ip:
                self.cache[hostname] = ip
                return ip
        except Exception as e:
            logging.debug(f"[DoH] Fallback to system DNS for {hostname}: {e}")
        
        return hostname

    def _sync_resolve(self, hostname: str) -> Optional[str]:
        url = f"{self.endpoint}?name={hostname}&type=A"
        req = urllib.request.Request(url, headers={"Accept": "application/dns-json", "User-Agent": "AG-Relay/1.0"})
        with urllib.request.urlopen(req, timeout=3, context=self.ssl_ctx) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if "Answer" in data:
                for ans in data["Answer"]:
                    if ans.get("type") == 1:  # Type A
                        return ans.get("data")
        return None

# European Smart SNI Reverse Proxies (Bypasses Google Error 400 without VPN)
SMART_GEO_PROXIES = {
    "daily-cloudcode-pa.googleapis.com": ["109.120.131.200", "179.254.166.174"],
    "cloudcode-pa.googleapis.com": ["109.120.131.200", "179.254.166.174"],
    "cloudaicompanion.googleapis.com": ["109.120.131.200", "179.254.166.174"],
    "generativelanguage.googleapis.com": ["179.254.166.174", "109.120.131.200"],
    "aisandbox-pa.googleapis.com": ["179.254.166.174", "109.120.131.200"],
    "assistant-s3-pa.googleapis.com": ["179.254.166.174", "109.120.131.200"],
    "proactivebackend-pa.googleapis.com": ["179.254.166.174", "109.120.131.200"],
    "robinfrontend-pa.googleapis.com": ["179.254.166.174", "109.120.131.200"],
    "alkalimakersuite-pa.clients6.google.com": ["179.254.166.174", "109.120.131.200"],
    "webchannel-alkalimakersuite-pa.clients6.google.com": ["179.254.166.174", "109.120.131.200"],
}

async def connect_direct(host: str, port: int, resolver: Optional[DoHResolver] = None, smart_egress: bool = True) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter, str]:
    if smart_egress:
        host_clean = host.lower().rstrip(".")
        for k, ips in SMART_GEO_PROXIES.items():
            if host_clean == k or host_clean.endswith("." + k):
                for tip in ips:
                    try:
                        r, w = await asyncio.open_connection(tip, port)
                        return r, w, f"Smart-Egress ({tip}) [Анти-400]"
                    except Exception:
                        continue
    target_host = host
    if resolver:
        target_host = await resolver.resolve(host)
    r, w = await asyncio.open_connection(target_host, port)
    return r, w, f"Direct ({target_host})"

async def connect_socks5(socks_host: str, socks_port: int, target_host: str, target_port: int) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to target through an upstream SOCKS5 proxy."""
    reader, writer = await asyncio.open_connection(socks_host, socks_port)
    
    # 1. Greeting: [VER=0x05, NMETHODS=0x01, METHOD=0x00 (No Auth)]
    writer.write(b"\x05\x01\x00")
    await writer.drain()
    res = await reader.readexactly(2)
    if res != b"\x05\x00":
        writer.close()
        raise ConnectionError(f"SOCKS5 auth failed or unsupported: {res}")

    # 2. Connection request: [VER=5, CMD=1 (CONNECT), RSV=0, ATYP=3 (DOMAIN), LEN, DOMAIN, PORT]
    host_bytes = target_host.encode('utf-8')
    req = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + target_port.to_bytes(2, 'big')
    writer.write(req)
    await writer.drain()

    # 3. Response: [VER, REP, RSV, ATYP, BND.ADDR, BND.PORT]
    resp = await reader.readexactly(4)
    if resp[1] != 0:
        writer.close()
        raise ConnectionError(f"SOCKS5 upstream returned error code {resp[1]}")
    
    # Skip bound address
    atyp = resp[3]
    if atyp == 1:  # IPv4
        await reader.readexactly(6)
    elif atyp == 3:  # Domain
        dlen = (await reader.readexactly(1))[0]
        await reader.readexactly(dlen + 2)
    elif atyp == 4:  # IPv6
        await reader.readexactly(18)

    return reader, writer

def get_split_point(data: bytes, host: str) -> int:
    """Finds the optimal TCP fragment split point to bypass DPI (SNI Split)"""
    if len(data) > 5 and data[0] == 0x16:  # TLS Handshake (ClientHello)
        host_b = host.encode('utf-8')
        idx = data.find(host_b)
        if idx != -1 and idx + 2 < len(data):
            return idx + 2  # Split right inside the SNI domain name
        return 3  # Fallback: split TLS record header
    return 0

async def pipe_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str, host: str = "", enable_dpi_bypass: bool = True) -> int:
    """
    Pipes bytes with built-in User-Space DPI Bypass (SNI Splitter) and flow control.
    Bypasses ISP ТСПУ/DPI without zapret, drivers, or VPNs.
    """
    transferred = 0
    warned = False
    is_first_chunk = True

    # Ensure TCP_NODELAY is active for immediate segment transmission
    sock = writer.get_extra_info('socket')
    if sock:
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass

    try:
        while not reader.at_eof():
            chunk = await reader.read(CHUNK_SIZE)
            if not chunk:
                break

            # --- USER-SPACE DPI BYPASS (SNI Splitter) ---
            if is_first_chunk and direction == "client->remote" and enable_dpi_bypass:
                is_first_chunk = False
                split_pos = get_split_point(chunk, host)
                if split_pos > 0 and split_pos < len(chunk):
                    part1 = chunk[:split_pos]
                    part2 = chunk[split_pos:]
                    
                    writer.write(part1)
                    await writer.drain()
                    await asyncio.sleep(0.002)  # 2ms delay forces OS TCP stack to send separate TCP segment
                    
                    writer.write(part2)
                    await writer.drain()

                    transferred += len(chunk)
                    logging.info(f"[{GREEN}DPI BYPASS{RESET}] TLS ClientHello for {BOLD}{host}{RESET} split at byte {split_pos} (zapret/VPN not required!)")
                    continue

            is_first_chunk = False
            writer.write(chunk)
            await writer.drain()
            
            chunk_len = len(chunk)
            transferred += chunk_len

            # Large payload alert for prompt history (>100 KiB)
            if direction == "client->remote" and transferred > 100 * 1024 and not warned:
                warned = True
                print(f"\n{YELLOW}⚠️  [FLOW CONTROL] Large request payload: {transferred/1024:.1f} KiB sent to {host}.{RESET}")
                print(f"{DIM}   Tip: Use /compact in Antigravity or split giant files to prevent 128 KiB HTTP/2 window overflow!{RESET}\n")
            
            # Flow-control pacing: yield micro-sleep on large chunks
            if chunk_len >= 16384:
                await asyncio.sleep(PACING_DELAY)
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        pass
    except Exception as e:
        logging.debug(f"Pipe {direction} error: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
    return transferred

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, 
                        upstream_socks: Optional[Tuple[str, int]] = None,
                        resolver: Optional[DoHResolver] = None,
                        smart_egress: bool = True):
    client_ip, client_port = writer.get_extra_info('peername')[:2]
    stats.total_requests += 1

    try:
        # Read the HTTP request line
        line = await reader.readline()
        if not line:
            writer.close()
            return

        req_str = line.decode('utf-8', errors='ignore').strip()
        parts = req_str.split()
        if len(parts) < 2:
            writer.close()
            return

        method, target = parts[0], parts[1]

        # Antigravity and Language Server communicate via HTTPS tunnels (CONNECT)
        if method.upper() == "CONNECT":
            host, port_str = target.split(":") if ":" in target else (target, "443")
            port = int(port_str)

            # Consume headers until empty line
            while True:
                h = await reader.readline()
                if not h or h == b'\r\n' or h == b'\n':
                    break

            # Connect upstream (direct or via SOCKS5)
            try:
                if upstream_socks:
                    remote_reader, remote_writer = await connect_socks5(upstream_socks[0], upstream_socks[1], host, port)
                    route_info = f"SOCKS5 -> {upstream_socks[0]}:{upstream_socks[1]}"
                else:
                    remote_reader, remote_writer, route_info = await connect_direct(host, port, resolver, smart_egress)
            except Exception as e:
                logging.warning(f"[{YELLOW}UPSTREAM FAIL{RESET}] {host}:{port} -> {e}")
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await writer.drain()
                writer.close()
                return

            # Acknowledge tunnel establishment
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()

            stats.active_tunnels += 1
            logging.info(f"[{GREEN}TUNNEL OK{RESET}] {client_ip}:{client_port} <-> {BOLD}{host}:{port}{RESET} [{route_info}] (Active: {stats.active_tunnels})")

            # Dual-way streaming with pacing
            t1 = asyncio.create_task(pipe_stream(reader, remote_writer, "client->remote", host))
            t2 = asyncio.create_task(pipe_stream(remote_reader, writer, "remote->client", host))

            sent, recv = await asyncio.gather(t1, t2, return_exceptions=True)
            stats.active_tunnels -= 1

            up_kb = round((sent if isinstance(sent, int) else 0) / 1024, 1)
            down_kb = round((recv if isinstance(recv, int) else 0) / 1024, 1)
            logging.info(f"[{CYAN}CLOSED{RESET}] {host}:{port} | Up: {up_kb} KB, Down: {down_kb} KB")
        else:
            # Simple HTTP forward proxy fallback
            writer.write(b"HTTP/1.1 405 Method Not Allowed\r\nContent-Type: text/plain\r\n\r\nOnly CONNECT method supported.")
            await writer.drain()
            writer.close()
    except Exception as e:
        logging.debug(f"Client handler exception: {e}")
        try:
            writer.close()
        except Exception:
            pass

async def main():
    # Setup terminal colors on Windows
    if os.name == 'nt':
        os.system('')

    parser = argparse.ArgumentParser(description=f"NovaAntigravity Relay v{VERSION}")
    parser.add_argument("--bind", default="127.0.0.1", help="Binding interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=10809, help="Listening port (default: 10809)")
    parser.add_argument("--socks5", default=None, help="Upstream SOCKS5 proxy host:port (e.g. 127.0.0.1:1080)")
    parser.add_argument("--no-doh", action="store_true", help="Disable DoH resolution (use system DNS)")
    parser.add_argument("--no-smart", action="store_true", help="Disable Smart EU reverse proxy (use direct connection)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format=f"{DIM}%(asctime)s{RESET} %(message)s", datefmt="%H:%M:%S")

    upstream_socks = None
    if args.socks5:
        shost, sport = args.socks5.split(":") if ":" in args.socks5 else (args.socks5, 1080)
        upstream_socks = (shost, int(sport))

    resolver = None if args.no_doh else DoHResolver()
    smart_active = not args.no_smart and not upstream_socks

    print(f"""
{CYAN}{BOLD}=============================================================
   NovaAntigravity Relay (AG-Relay) v{VERSION}
   Open-Source Proxy & Stream Flow Controller for Antigravity
============================================================={RESET}
{BOLD}Listen Address:{RESET}   http://{args.bind}:{args.port}
{BOLD}Smart Egress:{RESET}     {"Smart EU Relay (Bypasses Error 400 without VPN) [Active]" if smart_active else ("SOCKS5 -> " + args.socks5 if upstream_socks else "Direct")}
{BOLD}DNS Resolver:{RESET}     {"Cloudflare DoH (1.1.1.1) [Active]" if resolver else "System DNS"}
{BOLD}Buffer Pacing:{RESET}    Active (32 KiB chunks, no 128 KiB burst drops)
{BOLD}Lockout Policy:{RESET}   No penalties (0s lockout, zero artificial delays)
-------------------------------------------------------------
{YELLOW}Set environment variable:{RESET}
    AG_LS_PROXY=http://{args.bind}:{args.port}
-------------------------------------------------------------
{GREEN}Press Ctrl+C to stop the relay.{RESET}
""")

    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, upstream_socks, resolver, smart_egress=not args.no_smart),
        args.bind, args.port
    )

    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Relay stopped by user.{RESET}")
        sys.exit(0)
