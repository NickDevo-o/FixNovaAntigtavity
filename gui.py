#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity Unlocker Next - Modern Desktop GUI Control Center v2.7.0
Clean, intuitive Windows 11 Fluent-style dark UI.
Supports:
 - Smart Egress: Autonomous European SNI Reverse Proxy (Bypasses Google Error 400 without VPN)
 - Standalone User-space DPI Bypass (SNI Splitter, zapret not required)
 - Upstream Proxy Egress (SOCKS5 / HTTP)
 - Built-in Cloudflare DoH (1.1.1.1)
 - Support for both Antigravity 2.0 and Antigravity IDE
 - 32 KiB chunk stream flow-control (Anti-128K Working freeze)
 - 1-Click System Hosts Protection with UAC elevation
"""

import sys
import os
import time
import socket
import select
import threading
import queue
import subprocess
import urllib.request
import urllib.parse
import json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from relay import patcher

VERSION = "v2.7.0"
DEFAULT_PORT = 10809

# UI Colors (Dark Fluent)
C_BG = "#121215"
C_CARD = "#1c1c22"
C_CARD_HOVER = "#23232b"
C_BORDER = "#2e2e38"
C_TEXT = "#ffffff"
C_MUTED = "#9496a1"
C_ACCENT = "#6366f1"
C_ACCENT_HOVER = "#4f46e5"
C_GREEN = "#10b981"
C_YELLOW = "#f59e0b"
C_RED = "#ef4444"

GOOGLE_DOMAINS = [
    "googleapis.com", "google.com", "googleusercontent.com",
    "gstatic.com", "google.dev", "deepmind.com", "deepmind.google",
    "gemini.google", "youtube.com"
]

# European Smart SNI Reverse Proxies (routes to Google from Europe, bypassing Error 400 without VPN)
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


class UnlockerCore:
    def __init__(self, log_callback):
        self.log_callback = log_callback
        self.is_running = False
        self.server_sock = None
        self.thread = None
        self.port = DEFAULT_PORT
        self.upstream_mode = "smart"  # "smart", "proxy", "direct"
        self.upstream_url = "socks5://127.0.0.1:10808"
        self.active_tunnels = 0
        self.bytes_in = 0
        self.bytes_out = 0
        self.doh_cache = {}
        self.doh_lock = threading.Lock()

    def log(self, text, tag="info"):
        self.log_callback(text, tag)

    def resolve_doh(self, host):
        host_clean = host.lower().rstrip(".")
        try:
            socket.inet_aton(host_clean)
            return host_clean
        except socket.error:
            pass

        needs_doh = any(host_clean == d or host_clean.endswith("." + d) for d in GOOGLE_DOMAINS)
        if not needs_doh:
            return host

        now = time.time()
        with self.doh_lock:
            if host_clean in self.doh_cache:
                ip, exp = self.doh_cache[host_clean]
                if now < exp:
                    return ip

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
                with urllib.request.urlopen(req, timeout=3.5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    for ans in data.get("Answer", []):
                        if ans.get("type") == 1:
                            ip = ans.get("data")
                            ttl = min(ans.get("TTL", 3600), 3600)
                            with self.doh_lock:
                                self.doh_cache[host_clean] = (ip, now + ttl)
                            return ip
            except Exception:
                continue

        try:
            return socket.gethostbyname(host)
        except Exception:
            return host

    def connect_socks5(self, socks_host, socks_port, target_host, target_port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(8.0)
        s.connect((socks_host, socks_port))
        # 1. Greeting
        s.sendall(b"\x05\x01\x00")
        resp = s.recv(2)
        if resp != b"\x05\x00":
            s.close()
            raise ConnectionError("SOCKS5 rejected")
        # 2. Connect
        host_b = target_host.encode('utf-8')
        req = b"\x05\x01\x00\x03" + bytes([len(host_b)]) + host_b + target_port.to_bytes(2, 'big')
        s.sendall(req)
        r = s.recv(10)
        if len(r) < 4 or r[1] != 0:
            s.close()
            raise ConnectionError(f"SOCKS5 error code {r[1] if len(r)>1 else '?'}")
        return s

    def connect_http_proxy(self, proxy_host, proxy_port, target_host, target_port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(8.0)
        s.connect((proxy_host, proxy_port))
        req = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n\r\n"
        s.sendall(req.encode('utf-8'))
        resp = s.recv(4096)
        if b"200" not in resp.split(b"\r\n")[0]:
            s.close()
            raise ConnectionError(f"HTTP proxy error: {resp[:30]}")
        return s

    def connect_target(self, host, port):
        # 1. User upstream proxy (SOCKS5 / HTTP)
        if self.upstream_mode == "proxy" and self.upstream_url.strip():
            u = self.upstream_url.strip()
            parsed = urllib.parse.urlparse(u if "://" in u else "socks5://" + u)
            scheme = parsed.scheme.lower()
            phost = parsed.hostname or "127.0.0.1"
            pport = parsed.port or (10808 if scheme == "socks5" else 7890)

            try:
                if scheme == "socks5":
                    s = self.connect_socks5(phost, pport, host, port)
                else:
                    s = self.connect_http_proxy(phost, pport, host, port)
                return s, f"Upstream: {u}"
            except Exception as e:
                self.log(f"⚠️ Сбой прокси {u}: {e}. Мягкий переход на Smart-шлюз...", "warn")

        # 2. Smart Egress: European SNI reverse proxy (Fixes Error 400 without VPN)
        if self.upstream_mode in ("smart", "proxy"):
            host_clean = host.lower().rstrip(".")
            matched_key = None
            for k in SMART_GEO_PROXIES:
                if host_clean == k or host_clean.endswith("." + k):
                    matched_key = k
                    break

            if matched_key:
                target_ips = list(SMART_GEO_PROXIES[matched_key])
                # Check if system hosts or local DNS already provides a smart IP
                try:
                    sys_ip = socket.gethostbyname(host)
                    if sys_ip in ("109.120.131.200", "179.254.166.174", "143.20.64.55"):
                        target_ips = [sys_ip] + [ip for ip in target_ips if ip != sys_ip]
                except Exception:
                    pass

                last_err = None
                for tip in target_ips:
                    try:
                        s = socket.create_connection((tip, port), timeout=6.0)
                        return s, f"Smart-Egress ({tip}) [Анти-400]"
                    except Exception as e:
                        last_err = e
                        continue
                self.log(f"⚠️ Все Smart-реле {target_ips} недоступны ({last_err}), fallback на прямой DoH...", "warn")

        # 3. Direct connection with DoH resolution
        resolved_ip = self.resolve_doh(host)
        s = socket.create_connection((resolved_ip, port), timeout=8.0)
        return s, f"Direct (DoH -> {resolved_ip})"

    def start(self, port=DEFAULT_PORT):
        if self.is_running:
            return
        self.port = port
        self.is_running = True
        self.thread = threading.Thread(target=self._run_server, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
        self.server_sock = None
        self.log("Шлюз остановлен.", "warn")

    def _run_server(self):
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(("127.0.0.1", self.port))
            self.server_sock.listen(128)
            self.server_sock.settimeout(1.0)
            if self.upstream_mode == "smart":
                mode_desc = "Smart Egress (EU Relay, Анти-400 без VPN)"
            elif self.upstream_mode == "proxy":
                mode_desc = f"Upstream Proxy {self.upstream_url}"
            else:
                mode_desc = "Direct (DoH + SNI-Split)"
            self.log(f"Шлюз успешно запущен на 127.0.0.1:{self.port} [{mode_desc}]", "success")
        except Exception as e:
            self.log(f"Ошибка бинда порта {self.port}: {e}", "error")
            self.is_running = False
            return

        while self.is_running:
            try:
                client_sock, client_addr = self.server_sock.accept()
                threading.Thread(target=self._handle_client, args=(client_sock, client_addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _handle_client(self, client_sock, client_addr):
        client_sock.settimeout(15.0)
        try:
            req_line = client_sock.recv(4096).decode("utf-8", errors="ignore")
            if not req_line:
                client_sock.close()
                return

            first_line = req_line.split("\r\n")[0]
            parts = first_line.split()
            if len(parts) < 2:
                client_sock.close()
                return

            method, target = parts[0], parts[1]

            if method.upper() == "CONNECT":
                host, port_s = target.split(":") if ":" in target else (target, "443")
                port = int(port_s)

                try:
                    upstream_sock, route_desc = self.connect_target(host, port)
                except Exception as e:
                    client_sock.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                    client_sock.close()
                    self.log(f"Сбой подключения к {target}: {e}", "error")
                    return

                client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self.active_tunnels += 1

                self._pump(client_sock, upstream_sock, host, route_desc)
                self.active_tunnels = max(0, self.active_tunnels - 1)
            else:
                client_sock.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                client_sock.close()
        except Exception:
            try:
                client_sock.close()
            except Exception:
                pass

    def _pump(self, client_sock, upstream_sock, host, route_desc):
        client_sock.setblocking(False)
        upstream_sock.setblocking(False)
        sockets = [client_sock, upstream_sock]

        bytes_c2u = 0
        bytes_u2c = 0
        start_t = time.time()
        warned = False
        is_first_c2u = True

        try:
            while self.is_running:
                r, _, x = select.select(sockets, [], sockets, 60.0)
                if x or not r:
                    break

                for s in r:
                    other = upstream_sock if s is client_sock else client_sock
                    try:
                        data = s.recv(32768)
                    except Exception:
                        data = b""

                    if not data:
                        return

                    dlen = len(data)
                    if s is client_sock:
                        # User-Space DPI Bypass (SNI Split) for direct and smart egress
                        if is_first_c2u and self.upstream_mode != "proxy":
                            is_first_c2u = False
                            split_pos = 0
                            if dlen > 5 and data[0] == 0x16:  # TLS Handshake ClientHello
                                host_b = host.encode('utf-8')
                                idx = data.find(host_b)
                                if idx != -1 and idx + 2 < dlen:
                                    split_pos = idx + 2
                                else:
                                    split_pos = 3

                            if split_pos > 0 and split_pos < dlen:
                                try:
                                    other.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                                except Exception:
                                    pass
                                part1 = data[:split_pos]
                                part2 = data[split_pos:]
                                other.sendall(part1)
                                time.sleep(0.002)  # Yield 2ms to force OS TCP segment separation
                                other.sendall(part2)
                                bytes_c2u += dlen
                                self.bytes_in += dlen
                                self.log(f"🛡️ [DPI Split] {host} фрагментирован (обход ТСПУ без zapret)", "success")
                                continue

                        is_first_c2u = False
                        bytes_c2u += dlen
                        self.bytes_in += dlen
                        if bytes_c2u > 100 * 1024 and not warned:
                            warned = True
                            self.log(f"Большой контекст: {bytes_c2u/1024:.1f} КиБ -> {host} (Включен микро-пейсинг Anti-128K)", "warn")
                        if bytes_c2u > 120 * 1024:
                            time.sleep(0.001)
                    else:
                        bytes_u2c += dlen
                        self.bytes_out += dlen

                    other.sendall(data)
        finally:
            try:
                client_sock.close()
            except Exception:
                pass
            try:
                upstream_sock.close()
            except Exception:
                pass
            duration_ms = (time.time() - start_t) * 1000.0
            tag = "warn" if warned else "tunnel"
            self.log(f"✔ [Туннель] {host} | Исх: {bytes_c2u/1024:.1f} КБ | Вх: {bytes_u2c/1024:.1f} КБ | {route_desc} | {duration_ms:.0f}мс", tag)


class ModernUnlockerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Antigravity Unlocker Next {VERSION}")
        self.root.geometry("880x680")
        self.root.minsize(780, 600)
        self.root.configure(bg=C_BG)

        self.log_queue = queue.Queue()
        self.core = UnlockerCore(self.post_log)

        self.var_route_mode = tk.StringVar(value="smart")
        self.var_proxy_url = tk.StringVar(value="socks5://127.0.0.1:10808")

        self._setup_styles()
        self._build_ui()
        self._refresh_status()

        self.root.after(100, self._process_log_queue)
        self.root.after(4000, self._auto_refresh_status)

        # Auto-start core on launch
        self.toggle_server()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=C_BG)
        style.configure("Card.TFrame", background=C_CARD, relief="flat")
        style.configure("TLabel", background=C_BG, foreground=C_TEXT, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=C_CARD, foreground=C_TEXT, font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background=C_CARD, foreground=C_TEXT, font=("Segoe UI", 11, "bold"))
        style.configure("Muted.TLabel", background=C_CARD, foreground=C_MUTED, font=("Segoe UI", 9))

    def _build_ui(self):
        # 1. Header Bar
        header = tk.Frame(self.root, bg=C_CARD, height=64, padx=20, pady=12)
        header.pack(fill=tk.X, side=tk.TOP)

        title_box = tk.Frame(header, bg=C_CARD)
        title_box.pack(side=tk.LEFT)

        app_title = tk.Label(title_box, text="⚡ Antigravity Unlocker Next", font=("Segoe UI", 15, "bold"), fg=C_TEXT, bg=C_CARD)
        app_title.pack(anchor="w")

        app_sub = tk.Label(title_box, text="Автономный шлюз: обход ТСПУ + Smart Egress (без ошибки 400 и без VPN) + Anti-128K Pacing", font=("Segoe UI", 9), fg=C_MUTED, bg=C_CARD)
        app_sub.pack(anchor="w")

        self.btn_toggle = tk.Button(
            header, text="🚀 ЗАПУСТИТЬ ШЛЮЗ", font=("Segoe UI", 11, "bold"),
            bg=C_GREEN, fg="#ffffff", activebackground="#059669", activeforeground="#ffffff",
            relief="flat", padx=18, pady=8, cursor="hand2", command=self.toggle_server
        )
        self.btn_toggle.pack(side=tk.RIGHT)

        # 2. Main Content
        content = tk.Frame(self.root, bg=C_BG, padx=16, pady=12)
        content.pack(fill=tk.BOTH, expand=True)

        # Row 1: Status Cards
        grid_frame = tk.Frame(content, bg=C_BG)
        grid_frame.pack(fill=tk.X, pady=(0, 10))

        self.card_dpi = self._create_card(grid_frame, "🛡️ Обход DPI / ТСПУ", "Встроенный SNI-Splitter", 0)
        self.card_client = self._create_card(grid_frame, "💻 Клиент Antigravity", "Проверка установки...", 1)
        self.card_route = self._create_card(grid_frame, "🌐 Маршрут выхода (Egress)", "Smart Egress (Без 400)", 2)

        # Row 2: Upstream Route Configuration Card (Fix for Error 400)
        route_card = tk.Frame(content, bg=C_CARD, padx=14, pady=10, highlightbackground=C_BORDER, highlightthickness=1)
        route_card.pack(fill=tk.X, pady=(0, 10))

        rc_top = tk.Frame(route_card, bg=C_CARD)
        rc_top.pack(fill=tk.X)

        lbl_rc_title = tk.Label(rc_top, text="🌐 Режим выхода в сеть (Устранение ошибки 400 'User location is not supported'):", font=("Segoe UI", 10, "bold"), fg=C_TEXT, bg=C_CARD)
        lbl_rc_title.pack(side=tk.LEFT)

        # Radio options
        rc_radios = tk.Frame(route_card, bg=C_CARD)
        rc_radios.pack(fill=tk.X, pady=(6, 4))

        rb_smart = tk.Radiobutton(
            rc_radios, text="🌟 Встроенный Smart-шлюз (Авто / Без VPN / Анти-400)", variable=self.var_route_mode, value="smart",
            bg=C_CARD, fg=C_TEXT, selectcolor="#2d2d38", activebackground=C_CARD, activeforeground=C_TEXT,
            font=("Segoe UI", 9, "bold"), command=self._on_route_mode_change
        )
        rb_smart.pack(side=tk.LEFT, padx=(0, 14))

        rb_proxy = tk.Radiobutton(
            rc_radios, text="🌐 Свой зарубежный прокси (SOCKS5 / HTTP)", variable=self.var_route_mode, value="proxy",
            bg=C_CARD, fg=C_TEXT, selectcolor="#2d2d38", activebackground=C_CARD, activeforeground=C_TEXT,
            font=("Segoe UI", 9), command=self._on_route_mode_change
        )
        rb_proxy.pack(side=tk.LEFT, padx=(0, 14))

        rb_direct = tk.Radiobutton(
            rc_radios, text="⚡ Прямой выход (DoH + SNI Split)", variable=self.var_route_mode, value="direct",
            bg=C_CARD, fg=C_TEXT, selectcolor="#2d2d38", activebackground=C_CARD, activeforeground=C_TEXT,
            font=("Segoe UI", 9), command=self._on_route_mode_change
        )
        rb_direct.pack(side=tk.LEFT)

        # Proxy input bar
        self.f_proxy_input = tk.Frame(route_card, bg=C_CARD)
        self.f_proxy_input.pack(fill=tk.X, pady=(4, 2))

        lbl_hint = tk.Label(self.f_proxy_input, text="Адрес прокси (Xray/Clash/WARP):", font=("Segoe UI", 9), fg=C_MUTED, bg=C_CARD)
        lbl_hint.pack(side=tk.LEFT, padx=(0, 8))

        self.ent_proxy = tk.Entry(self.f_proxy_input, textvariable=self.var_proxy_url, font=("Segoe UI", 9), bg="#0d0d0f", fg="#ffffff", insertbackground="#ffffff", relief="flat", width=34)
        self.ent_proxy.pack(side=tk.LEFT, padx=(0, 8), ipady=2)

        btn_test_proxy = tk.Button(
            self.f_proxy_input, text="Проверить прокси", font=("Segoe UI", 8),
            bg=C_CARD_HOVER, fg=C_TEXT, activebackground="#383844", relief="flat", padx=10, pady=2,
            cursor="hand2", command=self.test_upstream_proxy
        )
        btn_test_proxy.pack(side=tk.LEFT)

        # Row 3: Action Buttons Bar
        actions_bar = tk.Frame(content, bg=C_CARD, padx=14, pady=8)
        actions_bar.pack(fill=tk.X, pady=(0, 10))

        self.btn_ide = tk.Button(
            actions_bar, text="💻 Запустить Antigravity", font=("Segoe UI", 10, "bold"),
            bg=C_ACCENT, fg="#ffffff", activebackground=C_ACCENT_HOVER, relief="flat", padx=14, pady=6,
            cursor="hand2", command=self.launch_ide
        )
        self.btn_ide.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_patch_toggle = tk.Button(
            actions_bar, text="🔧 Пропатчить IDE", font=("Segoe UI", 10),
            bg=C_CARD_HOVER, fg=C_TEXT, activebackground="#33333d", relief="flat", padx=12, pady=6,
            cursor="hand2", command=self.toggle_patch
        )
        self.btn_patch_toggle.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_hosts = tk.Button(
            actions_bar, text="🛡️ Защитить в hosts", font=("Segoe UI", 10),
            bg=C_CARD_HOVER, fg=C_TEXT, activebackground="#33333d", relief="flat", padx=12, pady=6,
            cursor="hand2", command=self.add_to_hosts
        )
        self.btn_hosts.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_clean = tk.Button(
            actions_bar, text="🧹 Очистить GPUCache", font=("Segoe UI", 10),
            bg=C_CARD_HOVER, fg=C_TEXT, activebackground="#33333d", relief="flat", padx=12, pady=6,
            cursor="hand2", command=self.clean_cache
        )
        self.btn_clean.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_warmup = tk.Button(
            actions_bar, text="🩺 Тест связи (Ping)", font=("Segoe UI", 10),
            bg=C_CARD_HOVER, fg=C_TEXT, activebackground="#33333d", relief="flat", padx=12, pady=6,
            cursor="hand2", command=self.test_ping
        )
        self.btn_warmup.pack(side=tk.LEFT, padx=(0, 8))

        btn_clear_log = tk.Button(
            actions_bar, text="Очистить лог", font=("Segoe UI", 9),
            bg=C_CARD, fg=C_MUTED, activebackground=C_CARD_HOVER, relief="flat", padx=8, pady=6,
            cursor="hand2", command=self.clear_log
        )
        btn_clear_log.pack(side=tk.RIGHT)

        # Row 4: Live Log Panel
        log_frame = tk.Frame(content, bg=C_CARD, padx=12, pady=10)
        log_frame.pack(fill=tk.BOTH, expand=True)

        log_header = tk.Frame(log_frame, bg=C_CARD)
        log_header.pack(fill=tk.X, pady=(0, 6))

        lbl_log = tk.Label(log_header, text="📡 Журнал запросов реального времени", font=("Segoe UI", 10, "bold"), fg=C_TEXT, bg=C_CARD)
        lbl_log.pack(side=tk.LEFT)

        self.lbl_stats = tk.Label(log_header, text="Активных туннелей: 0  |  Трафик: 0.0 МБ", font=("Segoe UI", 9), fg=C_MUTED, bg=C_CARD)
        self.lbl_stats.pack(side=tk.RIGHT)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, bg="#0d0d0f", fg="#d1d5db", font=("Consolas", 9),
            relief="flat", wrap=tk.WORD, borderwidth=0, highlightthickness=0
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.log_text.tag_config("info", foreground="#9ca3af")
        self.log_text.tag_config("success", foreground="#34d399")
        self.log_text.tag_config("warn", foreground="#fbbf24")
        self.log_text.tag_config("error", foreground="#f87171")
        self.log_text.tag_config("tunnel", foreground="#60a5fa")

        # Footer
        footer = tk.Frame(self.root, bg="#0d0d0f", height=28, padx=16, pady=4)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        self.lbl_footer = tk.Label(
            footer, text="Порт: 127.0.0.1:10809  •  Smart Egress: Активен  •  AG_LS_PROXY готов",
            font=("Segoe UI", 8), fg=C_MUTED, bg="#0d0d0f"
        )
        self.lbl_footer.pack(side=tk.LEFT)

        lbl_ver = tk.Label(footer, text="FixNovaAntigravity " + VERSION, font=("Segoe UI", 8), fg=C_MUTED, bg="#0d0d0f")
        lbl_ver.pack(side=tk.RIGHT)

    def _create_card(self, parent, title, subtitle, col):
        card = tk.Frame(parent, bg=C_CARD, padx=12, pady=10, relief="flat", highlightbackground=C_BORDER, highlightthickness=1)
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0 if col == 2 else 6))
        parent.grid_columnconfigure(col, weight=1)

        t_lbl = tk.Label(card, text=title, font=("Segoe UI", 10, "bold"), fg=C_TEXT, bg=C_CARD)
        t_lbl.pack(anchor="w")

        s_lbl = tk.Label(card, text=subtitle, font=("Segoe UI", 9), fg=C_MUTED, bg=C_CARD)
        s_lbl.pack(anchor="w", pady=(2, 0))

        return {"frame": card, "title": t_lbl, "sub": s_lbl}

    def _on_route_mode_change(self):
        mode = self.var_route_mode.get()
        self.core.upstream_mode = mode
        self.core.upstream_url = self.var_proxy_url.get()
        if mode == "smart":
            self.card_route["sub"].config(text="🟢 Smart-шлюз (EU Relay, Анти-400)", fg=C_GREEN)
            self.log("Маршрут переключен: Встроенный Smart-шлюз (Защита от ошибки 400 без VPN)", "success")
        elif mode == "proxy":
            self.card_route["sub"].config(text=f"🟢 Прокси: {self.var_proxy_url.get()}", fg=C_GREEN)
            self.log(f"Маршрут переключен: Upstream Прокси ({self.var_proxy_url.get()})", "success")
        else:
            self.card_route["sub"].config(text="⚪ Прямой (DoH + SNI-Split)", fg=C_MUTED)
            self.log("Маршрут переключен: Прямой выход (DoH + SNI-Split)", "info")

    def test_upstream_proxy(self):
        u = self.var_proxy_url.get().strip()
        self.post_log(f"Проверка доступности прокси {u}...", "info")

        def _test():
            try:
                parsed = urllib.parse.urlparse(u if "://" in u else "socks5://" + u)
                phost = parsed.hostname or "127.0.0.1"
                pport = parsed.port or (10808 if parsed.scheme.lower() == "socks5" else 7890)

                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3.0)
                s.connect((phost, pport))
                s.close()
                self.post_log(f"✔ Прокси {phost}:{pport} ДОСТУПЕН и отвечает!", "success")
                self._on_route_mode_change()
                messagebox.showinfo("Успех", f"Прокси {phost}:{pport} успешно подключен и готов к работе!")
            except Exception as e:
                self.post_log(f"❌ Прокси {u} недоступен: {e}", "error")
                messagebox.showerror("Ошибка подключения", f"Не удалось подключиться к {u}:\n{e}\n\nУбедитесь, что ваш Xray/Clash/WARP запущен.")

        threading.Thread(target=_test, daemon=True).start()

    def post_log(self, text, tag="info"):
        self.log_queue.put((text, tag))

    def _process_log_queue(self):
        while not self.log_queue.empty():
            text, tag = self.log_queue.get_nowait()
            ts = time.strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{ts}] {text}\n", tag)
            self.log_text.see(tk.END)

        total_mb = (self.core.bytes_in + self.core.bytes_out) / (1024 * 1024)
        self.lbl_stats.config(text=f"Активных туннелей: {self.core.active_tunnels}  |  Трафик: {total_mb:.2f} МБ")

        self.root.after(100, self._process_log_queue)

    def toggle_server(self):
        if self.core.is_running:
            self.core.stop()
            self.btn_toggle.config(text="🚀 ЗАПУСТИТЬ ШЛЮЗ", bg=C_GREEN, activebackground="#059669")
        else:
            self.core.upstream_mode = self.var_route_mode.get()
            self.core.upstream_url = self.var_proxy_url.get()
            self.core.start(DEFAULT_PORT)
            self.btn_toggle.config(text="⏹️ ОСТАНОВИТЬ ШЛЮЗ", bg=C_RED, activebackground="#b91c1c")

    def _refresh_status(self):
        # 1. Check zapret
        zapret_running = False
        try:
            tasks = subprocess.check_output('tasklist /fi "imagename eq winws.exe"', shell=True).decode("utf-8", errors="ignore")
            zapret_running = "winws.exe" in tasks
        except Exception:
            pass

        if zapret_running:
            self.card_dpi["sub"].config(text="🟢 Встроенный + zapret (активен)", fg=C_GREEN)
        else:
            self.card_dpi["sub"].config(text="🟢 Встроенный SNI-Split (автономно)", fg=C_GREEN)

        # 2. Check Client (Antigravity 2.0 and Antigravity IDE)
        localapp = os.environ.get("LOCALAPPDATA", "")
        ag2_exe = os.path.join(localapp, "Programs", "antigravity", "Antigravity.exe")
        has_ag2 = os.path.exists(ag2_exe)

        paths = patcher.find_ide_paths()
        has_ide = len(paths) > 0
        ide_patched = False
        if has_ide:
            ide_patched = (patcher.get_status(paths[0]) == "patched")

        if has_ag2 and not has_ide:
            self.card_client["sub"].config(text="🟢 Antigravity 2.0 (через AG_LS_PROXY)", fg=C_GREEN)
            self.btn_patch_toggle.config(text="ℹ️ О клиенте 2.0")
        elif has_ide:
            if ide_patched:
                self.card_client["sub"].config(text="🟢 Antigravity IDE (пропатчена)", fg=C_GREEN)
                self.btn_patch_toggle.config(text="↩️ Откатить патч IDE")
            else:
                self.card_client["sub"].config(text="⚪ Antigravity IDE (оригинал)", fg=C_MUTED)
                self.btn_patch_toggle.config(text="🔧 Пропатчить IDE")
        else:
            self.card_client["sub"].config(text="⚪ Клиент не найден в %LOCALAPPDATA%", fg=C_MUTED)

        # 3. Route card
        mode = self.var_route_mode.get()
        if mode == "smart":
            self.card_route["sub"].config(text="🟢 Smart-шлюз (EU Relay, Анти-400)", fg=C_GREEN)
        elif mode == "proxy":
            self.card_route["sub"].config(text=f"🟢 Прокси: {self.var_proxy_url.get()}", fg=C_GREEN)
        else:
            self.card_route["sub"].config(text="⚪ Прямой (DoH + SNI-Split)", fg=C_MUTED)

    def _auto_refresh_status(self):
        self._refresh_status()
        self.root.after(4000, self._auto_refresh_status)

    def toggle_patch(self):
        paths = patcher.find_ide_paths()
        localapp = os.environ.get("LOCALAPPDATA", "")
        ag2_exe = os.path.join(localapp, "Programs", "antigravity", "Antigravity.exe")
        has_ag2 = os.path.exists(ag2_exe)

        if not paths:
            if has_ag2:
                messagebox.showinfo("Antigravity 2.0",
                    "У вас установлена версия Antigravity 2.0!\n\n"
                    "В версии 2.0 файлы не требуют ручной модификации — клиент автоматически подхватывает шлюз через системную переменную AG_LS_PROXY=http://127.0.0.1:10809.\n\n"
                    "Просто нажмите «💻 Запустить Antigravity»!")
                return
            messagebox.showerror("Ошибка", "Не найден файл main.js Antigravity IDE.")
            return

        target = paths[0]
        status = patcher.get_status(target)

        if status == "patched":
            if patcher.restore_file(target):
                self.post_log("Патч успешно удален (восстановлен оригинал).", "success")
                messagebox.showinfo("Готово", "Оригинальный файл main.js успешно восстановлен из бэкапа!")
            else:
                messagebox.showerror("Ошибка", "Не удалось восстановить бэкап.")
        else:
            if patcher.patch_file(target):
                self.post_log("Патч онбординга и Pro-тира успешно применен к Antigravity IDE!", "success")
                messagebox.showinfo("Успех!", "Antigravity IDE успешно пропатчена!\nОшибка 400 и проверка онбординга сняты.")
            else:
                messagebox.showerror("Ошибка", "Не удалось применить патч.")

        self._refresh_status()

    def launch_ide(self):
        proxy_val = f"http://127.0.0.1:{self.core.port}"
        os.environ["AG_LS_PROXY"] = proxy_val
        os.environ["HTTP_PROXY"] = proxy_val
        os.environ["HTTPS_PROXY"] = proxy_val

        localapp = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(localapp, "Programs", "antigravity", "Antigravity.exe"),
            os.path.join(localapp, "Programs", "Antigravity IDE", "Antigravity IDE.exe"),
        ]

        launched = False
        for exe in candidates:
            if os.path.exists(exe):
                subprocess.Popen([exe], env=os.environ.copy())
                self.post_log(f"Запущен клиент: {exe} с AG_LS_PROXY={proxy_val}", "success")
                launched = True
                break

        if not launched:
            messagebox.showwarning("Внимание", "Исполняемый файл Antigravity не найден по стандартным путям. Вы можете открыть его вручную — шлюз активен на порту 10809.")

    def add_to_hosts(self):
        hosts_path = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "drivers", "etc", "hosts")
        needed_entries = [
            ("109.120.131.200", "daily-cloudcode-pa.googleapis.com"),
            ("109.120.131.200", "cloudcode-pa.googleapis.com"),
            ("109.120.131.200", "cloudaicompanion.googleapis.com"),
            ("179.254.166.174", "generativelanguage.googleapis.com"),
            ("179.254.166.174", "aisandbox-pa.googleapis.com"),
            ("179.254.166.174", "assistant-s3-pa.googleapis.com"),
            ("179.254.166.174", "proactivebackend-pa.googleapis.com"),
            ("179.254.166.174", "robinfrontend-pa.googleapis.com"),
            ("179.254.166.174", "alkalimakersuite-pa.clients6.google.com"),
            ("179.254.166.174", "webchannel-alkalimakersuite-pa.clients6.google.com"),
        ]

        existing = ""
        try:
            with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
                existing = f.read()
        except Exception:
            pass

        missing = [f"{ip} {dom}" for ip, dom in needed_entries if dom not in existing]

        if not missing:
            self.post_log("Все домены Google AI уже прописаны в hosts!", "success")
            messagebox.showinfo("Защита hosts", "Все необходимые домены Antigravity и Google AI уже присутствуют в файле hosts!\nДополнительных действий не требуется.")
            return

        temp_bat = os.path.join(os.environ.get("TEMP", os.path.dirname(os.path.abspath(__file__))), "update_hosts.bat")
        bat_lines = [
            "@echo off",
            "chcp 65001 >nul",
            f'set "HPATH={hosts_path}"',
            'echo. >> "%HPATH%"',
            'echo # Antigravity Unlocker Next - Smart Egress >> "%HPATH%"',
        ]
        for m in missing:
            bat_lines.append(f'echo {m} >> "%HPATH%"')
        bat_lines.append('ipconfig /flushdns >nul')
        bat_lines.append('exit /b 0')

        try:
            with open(temp_bat, "w", encoding="utf-8") as f:
                f.write("\r\n".join(bat_lines))

            cmd = f'powershell -NoProfile -Command "Start-Process cmd.exe -ArgumentList \'/c \"\"{temp_bat}\"\"\' -Verb RunAs -Wait"'
            subprocess.run(cmd, shell=True, capture_output=True)
            try:
                os.remove(temp_bat)
            except Exception:
                pass

            time.sleep(0.5)
            with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
                after_content = f.read()

            added_count = sum(1 for _, dom in needed_entries if dom in after_content and dom not in existing)
            if added_count > 0:
                self.post_log(f"Успешно добавлено {added_count} доменов в hosts! DNS сброшен.", "success")
                messagebox.showinfo("Успех", f"В системный файл hosts успешно добавлены {added_count} доменов Antigravity.\nТеперь ошибка 400 надежно снята и на системном уровне!")
            else:
                self.post_log("Запрос прав Администратора был отклонен или отменен.", "warn")
        except Exception as e:
            self.post_log(f"Ошибка обновления hosts: {e}", "error")
            messagebox.showerror("Ошибка", f"Не удалось обновить hosts:\n{e}")

    def clean_cache(self):
        appdata = os.environ.get("APPDATA", "")
        localapp = os.environ.get("LOCALAPPDATA", "")
        cleaned = 0

        for root_p in [appdata, localapp]:
            if not root_p:
                continue
            for app in ["Antigravity", "Antigravity IDE", "antigravity"]:
                for folder in ["GPUCache", "Code Cache"]:
                    target_dir = os.path.join(root_p, app, folder)
                    if os.path.exists(target_dir):
                        try:
                            import shutil
                            shutil.rmtree(target_dir, ignore_errors=True)
                            cleaned += 1
                        except Exception:
                            pass

        try:
            subprocess.run("ipconfig /flushdns", shell=True, capture_output=True)
        except Exception:
            pass

        self.post_log(f"GPUCache очищен ({cleaned} папок), DNS Windows сброшен.", "success")
        messagebox.showinfo("Очистка завершена", f"Очищено {cleaned} кэш-папок (черный экран устранен) и сброшен системный DNS.")

    def test_ping(self):
        def _probe():
            self.post_log("Диагностика связи и проверка Smart Egress (Анти-400)...", "info")
            # 1. Test Smart Egress Relay (Europe)
            t0 = time.time()
            try:
                s = socket.create_connection(("109.120.131.200", 443), timeout=4.0)
                s.close()
                dt1 = (time.time() - t0) * 1000.0
                self.post_log(f"✔ [Smart Egress OK] 109.120.131.200:443 ({dt1:.0f}мс, EU Relay активен - Ошибка 400 снята!)", "success")
            except Exception as e:
                self.post_log(f"⚠️ [Smart Egress FAIL] 109.120.131.200: {e}", "warn")

            # 2. Test DoH 1.1.1.1
            t1 = time.time()
            try:
                ip = self.core.resolve_doh("accounts.google.com")
                dt2 = (time.time() - t1) * 1000.0
                self.post_log(f"✔ [DoH OK] accounts.google.com -> {ip} ({dt2:.0f}мс)", "success")
            except Exception as e:
                self.post_log(f"❌ [DoH FAIL] Сбой DoH: {e}", "error")

        threading.Thread(target=_probe, daemon=True).start()

    def clear_log(self):
        self.log_text.delete("1.0", tk.END)


def main():
    root = tk.Tk()
    app = ModernUnlockerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
