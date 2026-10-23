SITE_URLS = {
    "main": "http://trickshot.local",
    "portal": "http://portal.trickshot.local",
    "app": "http://app.trickshot.local",
    "auth": "http://auth.trickshot.local",
    "api": "http://api.trickshot.local",
    "docs": "http://docs.trickshot.local",
    "status": "http://status.trickshot.local",
    "support": "http://support.trickshot.local",
    "billing": "http://billing.trickshot.local",
    "cdn": "http://cdn.trickshot.local",
}

HOST_SITES = {
    "trickshot.local": "main",
    "www.trickshot.local": "main",
    "portal.trickshot.local": "portal",
    "app.trickshot.local": "app",
    "auth.trickshot.local": "auth",
    "api.trickshot.local": "api",
    "docs.trickshot.local": "docs",
    "status.trickshot.local": "status",
    "support.trickshot.local": "support",
    "billing.trickshot.local": "billing",
    "cdn.trickshot.local": "cdn",
}

WAF_SITES = {"main", "portal", "app", "auth", "api", "support", "billing"}


def site_for_host(host):
    hostname = (host or "").split(":", 1)[0].lower()
    return HOST_SITES.get(hostname, "main")


def waf_enabled(host):
    return site_for_host(host) in WAF_SITES
