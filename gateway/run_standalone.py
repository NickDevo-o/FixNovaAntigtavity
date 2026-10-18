#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity Gateway / Unlocker Next (Python Standalone Engine)
Zero-dependency portable implementation of the Antigravity Gateway.
Can be executed directly on any machine with Python 3.8+.
"""

import sys
import os
import json
import time
import socket
import select
import threading
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

VERSION = "v2.5.0-open"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 10809
BUFFER_SIZE = 16384  # 16 KiB
WARN_PAYLOAD_SIZE = 100 * 1024  # 100 KiB
THROTTLE_THRESHOLD = 120 * 1024  # 120 KiB

GOOGLE_DOMAINS = [
    "googleapis.com",
    "google.com",
    "googleusercontent.com",
    "gstatic.com",
    "google.dev",
    "deepmind.com",
    "deepmind.google",
    "gemini.google",
    "youtube.com",
]

# Thread-safe in-memory DoH cache: host -> (ip, expire_time)
doh_cache = {}
doh_lock = threading.Lock()


def resolve_doh(host: str) -> str:
    """Resolves target Google hostnames using DNS over HTTPS (Cloudflare/Google)"""
    host_clean = host.lower().rstrip(".")
    # If already IP, return as-is
    try:
        socket.inet_aton(host_clean)
        return host_clean
    except socket.error:
        pass

    # Check if this domain needs DoH
    needs_doh = any(host_clean == d or host_clean.endswith("." + d) for d in GOOGLE_DOMAINS)
    if not needs_doh:
        return host

    # Check cache
    now = time.time()
    with doh_lock:
        if host_clean in doh_cache:
            ip, expires = doh_cache[host_clean]
            if now < expires:
                return ip

    # Query Cloudflare / Google DoH
    endpoints = [
        f"https://1.1.1.1/dns-query?name={urllib.parse.quote(host_clean)}&type=A",
        f"https://dns.google/resolve?name={urllib.parse.quote(host_clean)}&type=A",
    ]

    for ep in endpoints:
        try:
            req = urllib.request.Request(
                ep,
                headers={"Accept": "application/dns-json", "User-Agent": "AntigravityGateway/2.0"},
            )
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for answer in data.get("Answer", []):
                    if answer.get("type") == 1:  # A record
                        ip = answer.get("data")
                        ttl = answer.get("TTL", 3600)
                        with doh_lock:
                            doh_cache[host_clean] = (ip, now + min(ttl, 3600))
                        return ip
        except Exception:
            continue

    # Fallback to system resolver
    try:
        return socket.gethostbyname(host)
    except Exception:
        return host


def sanitize_headers(headers):
    """Strips headers revealing banned regional locations"""
    blocked = [
        "x-client-geo", "x-client-country", "cf-ipcountry",
        "x-forwarded-for", "x-real-ip", "x-user-ip", "true-client-ip"
    ]
    cleaned = []
    for k, v in headers.items():
        if k.lower() not in blocked:
            cleaned.append((k, v))
    return cleaned


def kill_orphaned_processes():
    """Terminates lingering language_server.exe and ag_dns.exe"""
    count = 0
    if sys.platform == "win32":
        for proc in ["language_server.exe", "ag_dns.exe"]:
            cmd = f'taskkill /F /IM "{proc}" >nul 2>&1'
            if os.system(cmd) == 0:
                count += 1
    else:
        for proc in ["language_server", "ag_dns"]:
            os.system(f'pkill -9 -f "{proc}" >/dev/null 2>&1')
    return count


def patch_antigravity_settings(port: int):
    """Sets http.proxy in Antigravity settings.json"""
    home = os.path.expanduser("~")
    candidates = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        for app in ["Antigravity", "Antigravity IDE", "antigravity"]:
            candidates.append(os.path.join(appdata, app, "User", "settings.json"))
    elif sys.platform == "darwin":
        for app in ["Antigravity", "Antigravity IDE"]:
            candidates.append(os.path.join(home, "Library", "Application Support", app, "User", "settings.json"))

    patched = 0
    proxy_val = f"http://127.0.0.1:{port}"
    for sf in candidates:
        if os.path.exists(os.path.dirname(sf)):
            data = {}
            if os.path.exists(sf):
                try:
                    with open(sf, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            data["http.proxy"] = proxy_val
            data["http.proxyStrictSSL"] = False
            data["http.proxySupport"] = "override"
            try:
                with open(sf, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                patched += 1
            except Exception:
                pass
    return patched


class FlowControlledProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_CONNECT(self):
        """Handles HTTPS tunneling with flow-control backpressure protection"""
        host_port = self.path
        if ":" in host_port:
            host, port_s = host_port.split(":", 1)
            port = int(port_s)
        else:
            host = host_port
            port = 443

        start_time = time.time()
        resolved_ip = resolve_doh(host)

        try:
            upstream_sock = socket.create_connection((resolved_ip, port), timeout=12.0)
        except Exception as e:
            self.send_error(502, f"Gateway connection failed: {e}")
            print(f"\033[31m❌ [CONNECT] {self.client_address[0]} -> {host_port} (ERR: {e})\033[0m")
            return

        # Send 200 Connection Established
        self.send_response(200, "Connection Established")
        self.end_headers()

        # Bidirectional flow-controlled relay
        client_sock = self.connection
        client_sock.setblocking(False)
        upstream_sock.setblocking(False)

        bytes_in = 0
        bytes_out = 0
        warned = False
        sockets = [client_sock, upstream_sock]

        try:
            while True:
                r_ready, _, x_ready = select.select(sockets, [], sockets, 60.0)
                if x_ready or not r_ready:
                    break

                for s in r_ready:
                    other = upstream_sock if s is client_sock else client_sock
                    try:
                        data = s.recv(BUFFER_SIZE)
                    except Exception:
                        data = b""

                    if not data:
                        return

                    if s is client_sock:
                        bytes_in += len(data)
                        if bytes_in > WARN_PAYLOAD_SIZE and not warned:
                            warned = True
                            print(f"\n\033[33m⚠️  [FLOW CONTROL] Large payload: {bytes_in/1024:.1f} KiB sent to {host}.\n"
                                  f"   Tip: Use /compact in Antigravity to avoid 128 KiB stream overflow!\033[0m\n")
                        if bytes_in > THROTTLE_THRESHOLD:
                            time.sleep(0.002)  # Micro-pacing backpressure
                    else:
                        bytes_out += len(data)

                    other.sendall(data)
        finally:
            try:
                upstream_sock.close()
            except Exception:
                pass
            latency = (time.time() - start_time) * 1000.0
            color = "\033[33m" if warned else "\033[32m"
            print(f"{color}✔ [TUNNEL] {host_port} | In: {bytes_in/1024:.1f} KiB | Out: {bytes_out/1024:.1f} KiB | {latency:.0f}ms\033[0m")

    def do_GET(self):
        if self.path == "/gateway-status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status = json.dumps({"status": "online", "version": VERSION, "port": self.server.server_port})
            self.wfile.write(status.encode("utf-8"))
            return
        self.send_error(404, "Endpoint not supported in transparent tunnel mode")

    def log_message(self, format, *args):
        pass  # Suppress default noisy http.server logs


def find_free_port(start_port: int, max_attempts: int = 10) -> int:
    for p in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((DEFAULT_HOST, p)) != 0:
                return p
    return start_port


def print_banner(port: int):
    print("""
\033[36m   ___         __   _                      _ __         
  / _ | ___   / /_ (_)__ _  _______ __  __(_) /___ __  
 / __ |/ _ \\ / __// // _` |/ __/ _` \\ \\/ / / __/ // /  
/_/ |_/_//_/ \\__//_/ \\__, /_/  \\__,_/\\_/_/_/\\__/\\_, /   
                     /___/   \033[1;32mG A T E W A Y\033[0m\033[36m     /___/    \033[0m
\033[90m========================================================\033[0m
\033[1;37m Antigravity Gateway / Unlocker Next  •  {version}\033[0m
\033[90m Direct zapret-Bypass • Built-in DoH • Anti-Overflow 128K\033[0m
\033[90m========================================================\033[0m
⚡ Слушатель прокси: \033[1;32mhttp://{host}:{port}\033[0m
🌐 Маршрутизация:   \033[32mПрямое соединение (zapret WinDivert DPI Bypass)\033[0m
🛡️  DNS-резолвер:     \033[32mВстроенный DoH (1.1.1.1 / dns.google)\033[0m
🌊 Защита буфера:   \033[32mВКЛЮЧЕНА (Anti-RST 128 KiB Throttling)\033[0m
\033[90m--------------------------------------------------------\033[0m
Горячие клавиши: [R] Сброс DNS  •  [C] Чистка кэша  •  [Q] Выход
\033[90m--------------------------------------------------------\033[0m
""".format(version=VERSION, host=DEFAULT_HOST, port=port))


def hotkey_loop():
    while True:
        try:
            line = sys.stdin.readline().strip().upper()
            if line == "R":
                with doh_lock:
                    count = len(doh_cache)
                    doh_cache.clear()
                if sys.platform == "win32":
                    os.system("ipconfig /flushdns >nul 2>&1")
                print(f"\n\033[32m✔ DoH кэш ({count} записей) и системный DNS сброшены.\033[0m\n")
            elif line == "C":
                k = kill_orphaned_processes()
                print(f"\n\033[32m✔ Завершено процессов: {k}.\033[0m\n")
            elif line == "Q":
                print("\nЗавершение работы...")
                os._exit(0)
        except Exception:
            break


def main():
    port = find_free_port(DEFAULT_PORT)
    patched = patch_antigravity_settings(port)

    print_banner(port)
    if patched > 0:
        print(f"🔧 Настройки Antigravity успешно обновлены ({patched} файлов)\n")

    # Start hotkey thread
    t = threading.Thread(target=hotkey_loop, daemon=True)
    t.start()

    server = HTTPServer((DEFAULT_HOST, port), FlowControlledProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nШлюз остановлен.")
        server.server_close()


if __name__ == "__main__":
    main()
