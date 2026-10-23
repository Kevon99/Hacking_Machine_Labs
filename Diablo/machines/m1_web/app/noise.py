import random
import uuid

from flask import request

EDGE_POPS = ["mad1", "mad2", "fra1", "ams3", "lhr2"]
APP_NODES = ["app-01", "app-02", "app-03", "app-04", "app-07"]
CACHE_STATES = ["HIT", "MISS", "BYPASS", "STALE", "EXPIRED"]
DB_SHARDS = ["shard-a", "shard-b", "shard-c", "legacy-01"]
RATE_LIMITS = [60, 120, 300, 600]


def install_noise_headers(app):
    @app.after_request
    def add_noise_headers(response):
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex

        response.headers.setdefault("X-Request-Id", request_id)
        response.headers.setdefault("X-Correlation-Id", request_id)
        response.headers.setdefault("X-Edge-POP", random.choice(EDGE_POPS))
        response.headers.setdefault("X-Backend-Server", random.choice(APP_NODES))
        response.headers.setdefault("X-Cache-Status", random.choice(CACHE_STATES))
        response.headers.setdefault("X-Cache-TTL", str(random.randint(30, 900)))
        response.headers.setdefault("X-Cache-Key", f"{request.host}{request.path}")
        response.headers.setdefault("X-DB-Shard", random.choice(DB_SHARDS))
        response.headers.setdefault("X-Env", "production")
        response.headers.setdefault("X-Deploy", "2026.10.17-rc2")
        response.headers.setdefault("X-Feature-Flags", "portal_beta,legacy_api,new_checkout")
        response.headers.setdefault("X-RateLimit-Limit", str(random.choice(RATE_LIMITS)))
        response.headers.setdefault("X-RateLimit-Remaining", str(random.randint(1, 59)))
        response.headers.setdefault("X-RateLimit-Reset", str(random.randint(15, 60)))
        response.headers.setdefault("X-Powered-By", "Trickshot Portal/4.12.3")
        response.headers.setdefault("X-AspNet-Version", "4.0.30319")
        response.headers.setdefault("X-Generator", "WordPress 6.4.2")
        response.headers.setdefault("X-Drupal-Cache", "HIT")
        response.headers.setdefault("X-Session-Source", "edge-cookie-v2")
        response.headers.setdefault("X-Origin-Server", request.host)
        response.headers.setdefault("X-Debug-Trace", uuid.uuid4().hex[:16])
        response.headers.setdefault("X-Proxy-Id", uuid.uuid4().hex[:12])
        response.headers.setdefault("X-Runtime", f"{random.uniform(0.01, 0.4):.3f}")
        response.headers.setdefault("X-Render-Time", f"{random.uniform(0.005, 0.25):.3f}")
        response.headers.setdefault("X-DB-Query-Count", str(random.randint(0, 9)))
        response.headers.setdefault("X-Cache-Hits", str(random.randint(0, 12)))
        response.headers.setdefault("X-Backend-Pool", random.choice(["blue", "green", "canary"]))
        response.headers.setdefault("X-Edge-Request-Class", random.choice(["public", "asset", "api"]))
        response.headers.setdefault("X-CDN-Provider", random.choice(["fastly", "akamai", "cloudfront"]))
        response.headers.setdefault("X-Trace-Sampled", random.choice(["true", "false"]))
        response.headers.setdefault("X-Varnish", str(random.randint(100000, 999999)))
        response.headers.setdefault("Via", "1.1 trickshot-edge")

        return response
