import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from urllib.parse import unquote

from flask import jsonify, make_response, render_template, request

from sites import SITE_URLS, site_for_host, waf_enabled

SQLI_PATTERNS = [
    re.compile(r"\bunion\b[\s\S]{0,40}\bselect\b", re.I),
    re.compile(r"'\s*(or|and)\s+'?1'?\s*=\s*'?1\b", re.I),
    re.compile(r"\b(or|and)\s+1\s*=\s*1\b", re.I),
    re.compile(r"\bsleep\s*\(\s*\d+", re.I),
    re.compile(r"\bbenchmark\s*\(", re.I),
    re.compile(r"\binformation_schema\b", re.I),
    re.compile(r"\bload_file\s*\(", re.I),
    re.compile(r"\binto\s+outfile\b", re.I),
    re.compile(r";\s*(drop|delete|update|insert|alter)\b", re.I),
    re.compile(r"\bxp_cmdshell\b", re.I),
    re.compile(r"\bwaitfor\s+delay\b", re.I),
]

XSS_PATTERNS = [
    re.compile(r"<\s*script\b", re.I),
    re.compile(r"javascript\s*:", re.I),
    re.compile(r"\bon(error|load|click|mouseover|focus)\s*=", re.I),
    re.compile(r"<\s*img[^>]+onerror", re.I),
    re.compile(r"<\s*svg[^>]*onload", re.I),
    re.compile(r"document\.cookie", re.I),
    re.compile(r"\b(alert|prompt|confirm)\s*\(", re.I),
    re.compile(r"data:text/html", re.I),
    re.compile(r"%3cscript", re.I),
]

SCANNER_PATTERNS = [
    re.compile(r"sqlmap|nikto|acunetix|nessus|nmap|masscan|dirbuster|gobuster|ffuf|wfuzz|wpscan|zaproxy", re.I),
]

RATE_LIMIT = int(os.environ.get("WAF_RATE_LIMIT", "100"))
RATE_WINDOW = int(os.environ.get("WAF_RATE_WINDOW", "60"))
RATE_BLOCK_SECONDS = int(os.environ.get("WAF_RATE_BLOCK_SECONDS", "180"))
EXPLOIT_BLOCK_SECONDS = int(os.environ.get("WAF_EXPLOIT_BLOCK_SECONDS", "300"))


class WafState:
    def __init__(self):
        self.lock = threading.Lock()
        self.blocks = {}
        self.windows = defaultdict(deque)
        self.events = deque(maxlen=250)

    def client_ip(self):
        return (
            request.headers.get("X-Real-IP")
            or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.remote_addr
            or "-"
        )

    def payloads(self):
        values = [
            request.path,
            unquote(request.query_string.decode("utf-8", "ignore")),
            request.headers.get("User-Agent", ""),
            request.headers.get("Referer", ""),
        ]

        try:
            if request.is_json:
                values.append(json.dumps(request.get_json(silent=True), ensure_ascii=False))
            elif request.form:
                values.extend(f"{key}={value}" for key, value in request.form.items())
        except Exception:
            pass

        try:
            raw = request.get_data(cache=True, as_text=True) or ""
            if len(raw) <= 65536:
                values.append(unquote(raw))
        except Exception:
            pass

        return " ".join(str(value) for value in values if value)

    def inspect(self, payload):
        for pattern in SQLI_PATTERNS:
            if pattern.search(payload):
                return "sqli", "Consulta SQL bloqueada por la política de seguridad."
        for pattern in XSS_PATTERNS:
            if pattern.search(payload):
                return "xss", "Contenido activo bloqueado por la política de seguridad."
        for pattern in SCANNER_PATTERNS:
            if pattern.search(payload):
                return "scanner", "Cliente automatizado bloqueado por la política de seguridad."
        return None, None

    def blocked(self, ip, now):
        entry = self.blocks.get(ip)
        if not entry:
            return None
        if entry["until"] <= now:
            self.blocks.pop(ip, None)
            return None
        return entry

    def add_event(self, ip, host, reason, action):
        self.events.append(
            {
                "at": time.time(),
                "ip": ip,
                "host": host,
                "reason": reason,
                "action": action,
            }
        )


STATE = WafState()


def _block_response(reason, status, seconds, site):
    retry = max(1, int(round(seconds)))
    if request.path.startswith("/api/") or "application/json" in request.headers.get("Accept", ""):
        response = jsonify(
            error="request_blocked",
            code="WAF_BLOCKED",
            reason=reason,
            retry_after=retry,
            support=SITE_URLS["support"] + "/",
        )
        response.status_code = status
    else:
        response = make_response(
            render_template(
                "public/waf_block.html",
                reason=reason,
                status=status,
                retry_after=retry,
                site=site,
            ),
            status,
        )

    response.headers["X-WAF-Status"] = "enabled"
    response.headers["X-WAF-Action"] = "blocked"
    response.headers["Retry-After"] = str(retry)
    return response


def install_waf(app):
    @app.before_request
    def enforce_waf():
        host = request.host
        site = site_for_host(host)
        if not waf_enabled(host):
            return None

        ip = STATE.client_ip()
        now = time.time()

        with STATE.lock:
            active = STATE.blocked(ip, now)
            if active:
                remaining = active["until"] - now
                return _block_response(active["reason"], active["status"], remaining, site)

            reason, message = STATE.inspect(STATE.payloads())
            if reason:
                until = now + EXPLOIT_BLOCK_SECONDS
                STATE.blocks[ip] = {
                    "until": until,
                    "reason": message,
                    "status": 403,
                }
                STATE.add_event(ip, site, reason, "blocked")
                app.logger.warning("WAF blocked %s on %s: %s", ip, site, reason)
                return _block_response(message, 403, EXPLOIT_BLOCK_SECONDS, site)

            window = STATE.windows[ip]
            while window and now - window[0] > RATE_WINDOW:
                window.popleft()
            window.append(now)

            if len(window) > RATE_LIMIT:
                until = now + RATE_BLOCK_SECONDS
                STATE.blocks[ip] = {
                    "until": until,
                    "reason": "Demasiadas solicitudes. El acceso está bloqueado temporalmente.",
                    "status": 429,
                }
                STATE.add_event(ip, site, "rate_limit", "blocked")
                app.logger.warning("WAF rate-limited %s on %s", ip, site)
                return _block_response(
                    "Demasiadas solicitudes. El acceso está bloqueado temporalmente.",
                    429,
                    RATE_BLOCK_SECONDS,
                    site,
                )

        return None

    @app.after_request
    def add_waf_header(response):
        if waf_enabled(request.host):
            response.headers.setdefault("X-WAF-Status", "enabled")
        return response


def install_cors(app):
    @app.after_request
    def add_cors(response):
        origin = request.headers.get("Origin", "")
        allowed = re.fullmatch(r"http://([a-z0-9-]+\.)*trickshot\.local(?::\d+)?", origin)
        if allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Requested-With"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            append_vary(response, "Origin")
        return response

    return app


def append_vary(response, value):
    current = response.headers.get("Vary")
    if not current:
        response.headers["Vary"] = value
    elif value.lower() not in current.lower():
        response.headers["Vary"] = current + ", " + value
