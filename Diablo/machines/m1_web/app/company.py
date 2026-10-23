import random
from datetime import datetime, timezone

from db import connect

_SCHEMA_READY = False

INVOICES = [
    ("INV-2026-0912", "demo", "Cliente Demo", "1240.00", "EUR", "paid", "2026-09-01", "2026-09-30", "Plan Business · septiembre 2026"),
    ("INV-2026-1018", "demo", "Cliente Demo", "1240.00", "EUR", "pending", "2026-10-01", "2026-10-31", "Plan Business · octubre 2026"),
    ("INV-2026-0871", "ana.torres", "Ana Torres", "3480.00", "EUR", "paid", "2026-08-01", "2026-08-31", "Plan Enterprise · agosto 2026"),
    ("INV-2026-0944", "ana.torres", "Ana Torres", "3480.00", "EUR", "paid", "2026-09-01", "2026-09-30", "Plan Enterprise · septiembre 2026"),
    ("INV-2026-1051", "ana.torres", "Ana Torres", "3480.00", "EUR", "pending", "2026-10-01", "2026-10-31", "Plan Enterprise · octubre 2026"),
    ("INV-2026-0778", "bruno.diaz", "Bruno Díaz", "890.00", "EUR", "paid", "2026-07-01", "2026-07-31", "Plan Business · julio 2026"),
    ("INV-2026-0962", "carla.mendez", "Carla Méndez", "1240.00", "EUR", "overdue", "2026-09-01", "2026-09-30", "Plan Business · septiembre 2026"),
    ("INV-2026-1044", "elena.vidal", "Elena Vidal", "3480.00", "EUR", "paid", "2026-10-01", "2026-10-31", "Plan Enterprise · octubre 2026"),
]

COMPONENTS = [
    {"name": "Edge / WAF", "status": "operational", "latency_ms": 18, "detail": "mad1 · fra1"},
    {"name": "API Gateway", "status": "operational", "latency_ms": 42, "detail": "v1 · 99.98%"},
    {"name": "Portal de clientes", "status": "operational", "latency_ms": 51, "detail": "eu-west-1"},
    {"name": "Autenticación SSO", "status": "operational", "latency_ms": 37, "detail": "auth.trickshot.local"},
    {"name": "Mesa de soporte", "status": "degraded", "latency_ms": 188, "detail": "cola alta"},
    {"name": "Facturación", "status": "operational", "latency_ms": 64, "detail": "Stripe Connect"},
    {"name": "Base de datos", "status": "operational", "latency_ms": 9, "detail": "shard-a"},
    {"name": "CDN de assets", "status": "operational", "latency_ms": 12, "detail": "cache hit 94%"},
]

INCIDENTS = [
    {"id": "INC-2026-014", "title": "Latencia elevada en la cola de soporte", "status": "monitoring", "started_at": "2026-10-21T04:12:00Z"},
    {"id": "INC-2026-011", "title": "Rotación programada de certificados", "status": "resolved", "started_at": "2026-10-17T22:00:00Z"},
]


def ensure_company_schema():
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return True

    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS invoices (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    invoice_number VARCHAR(32) NOT NULL UNIQUE,
                    customer_username VARCHAR(64) NOT NULL,
                    customer_name VARCHAR(80) NOT NULL,
                    amount DECIMAL(10, 2) NOT NULL,
                    currency CHAR(3) NOT NULL DEFAULT 'EUR',
                    status VARCHAR(24) NOT NULL,
                    issued_at DATE NOT NULL,
                    due_at DATE NOT NULL,
                    description VARCHAR(180) NOT NULL,
                    KEY idx_invoices_customer (customer_username),
                    KEY idx_invoices_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cur.execute("SELECT COUNT(*) AS total FROM invoices")
            if int(cur.fetchone()["total"]) == 0:
                cur.executemany(
                    "INSERT INTO invoices "
                    "(invoice_number, customer_username, customer_name, amount, currency, status, issued_at, due_at, description) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    INVOICES,
                )
        _SCHEMA_READY = True
        return True
    except Exception:
        return False
    finally:
        if conn:
            conn.close()


def _iso(value):
    return value.isoformat() if value else None


def list_invoices(customer_username=None, limit=50):
    ensure_company_schema()
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            if customer_username:
                cur.execute(
                    "SELECT invoice_number, customer_username, customer_name, amount, currency, "
                    "status, issued_at, due_at, description FROM invoices "
                    "WHERE customer_username = %s ORDER BY issued_at DESC LIMIT %s",
                    (customer_username, int(limit)),
                )
            else:
                cur.execute(
                    "SELECT invoice_number, customer_username, customer_name, amount, currency, "
                    "status, issued_at, due_at, description FROM invoices "
                    "ORDER BY issued_at DESC LIMIT %s",
                    (int(limit),),
                )
            rows = cur.fetchall()
        return [
            {
                "invoice_number": row["invoice_number"],
                "customer_username": row["customer_username"],
                "customer_name": row["customer_name"],
                "amount": float(row["amount"]),
                "currency": row["currency"],
                "status": row["status"],
                "issued_at": _iso(row["issued_at"]),
                "due_at": _iso(row["due_at"]),
                "description": row["description"],
            }
            for row in rows
        ]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


def billing_summary(customer_username=None):
    invoices = list_invoices(customer_username=customer_username, limit=200)
    outstanding = sum(item["amount"] for item in invoices if item["status"] in {"pending", "overdue"})
    paid = sum(item["amount"] for item in invoices if item["status"] == "paid")
    return {
        "invoices": len(invoices),
        "outstanding": round(outstanding, 2),
        "paid": round(paid, 2),
        "currency": "EUR",
    }


def serialize_ticket(row):
    return {
        "ticket_id": row["ticket_id"],
        "subject": row["subject"],
        "status": row["status"],
        "priority": row["priority"],
        "opened_by": row["opened_by"],
        "created_at": _iso(row.get("created_at")),
    }


def list_tickets(limit=30):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ticket_id, subject, status, priority, opened_by, created_at "
                "FROM tickets ORDER BY id DESC LIMIT %s",
                (int(limit),),
            )
            rows = cur.fetchall()
        return [serialize_ticket(row) for row in rows]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


def support_summary():
    tickets = list_tickets(limit=500)
    counts = {"open": 0, "pending": 0, "closed": 0}
    for ticket in tickets:
        counts[ticket["status"]] = counts.get(ticket["status"], 0) + 1
    return {
        "total": len(tickets),
        "open": counts.get("open", 0),
        "pending": counts.get("pending", 0),
        "closed": counts.get("closed", 0),
        "first_response_minutes": 11,
    }


def create_ticket(subject, priority="medium", opened_by="guest"):
    if priority not in {"low", "medium", "high", "critical"}:
        priority = "medium"

    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(id), 1000) AS max_id FROM tickets")
            ticket_id = "TCK-" + str(int(cur.fetchone()["max_id"]) + 1001)
            cur.execute(
                "INSERT INTO tickets (ticket_id, subject, status, priority, opened_by) "
                "VALUES (%s, %s, 'open', %s, %s)",
                (ticket_id, subject, priority, opened_by),
            )
        return {
            "ticket_id": ticket_id,
            "subject": subject,
            "status": "open",
            "priority": priority,
            "opened_by": opened_by,
        }
    except Exception:
        return None
    finally:
        if conn:
            conn.close()


def list_docs(query=None, limit=20):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            if query:
                pattern = f"%{query}%"
                cur.execute(
                    "SELECT id, title, category, body FROM kb_articles "
                    "WHERE title LIKE %s OR body LIKE %s OR category LIKE %s "
                    "ORDER BY id LIMIT %s",
                    (pattern, pattern, pattern, int(limit)),
                )
            else:
                cur.execute(
                    "SELECT id, title, category, body FROM kb_articles ORDER BY id LIMIT %s",
                    (int(limit),),
                )
            rows = cur.fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"],
                "category": row["category"],
                "excerpt": row["body"][:220],
            }
            for row in rows
        ]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


def docs_summary():
    docs = list_docs(limit=200)
    categories = sorted({doc["category"] for doc in docs})
    return {"articles": len(docs), "categories": categories, "search": "full-text"}


def platform_status():
    return {
        "status": "degraded" if any(item["status"] != "operational" for item in COMPONENTS) else "operational",
        "components": COMPONENTS,
        "incidents": INCIDENTS,
        "region": "eu-west-1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def site_summary(site):
    ensure_company_schema()

    if site == "support":
        data = support_summary()
        status = "degraded" if data["open"] > 3 else "operational"
    elif site == "billing":
        data = billing_summary()
        status = "operational"
    elif site == "docs":
        data = docs_summary()
        status = "operational"
    elif site == "status":
        data = platform_status()
        status = data["status"]
    elif site == "auth":
        data = {
            "accounts": _scalar("SELECT COUNT(*) AS total FROM site_users", "total"),
            "mfa_enabled": _scalar("SELECT COUNT(*) AS total FROM account_metrics WHERE metric_key = 'mfa_enabled' AND metric_value = 'true'", "total"),
            "active_sessions": random.randint(38, 96),
        }
        status = "operational"
    elif site in {"portal", "app"}:
        data = {
            "messages": _scalar("SELECT COUNT(*) AS total FROM messages", "total"),
            "comments": _scalar("SELECT COUNT(*) AS total FROM comments", "total"),
            "accounts": _scalar("SELECT COUNT(*) AS total FROM site_users", "total"),
        }
        status = "operational"
    elif site == "cdn":
        data = {"assets": 12, "cache_hit_ratio": 0.94, "edge_nodes": 5}
        status = "operational"
    else:
        data = {
            "requests_per_minute": random.randint(180, 420),
            "p95_ms": random.randint(35, 90),
            "error_rate": round(random.uniform(0.001, 0.009), 4),
        }
        status = "operational"

    return {
        "site": site,
        "status": status,
        "metrics": data,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _scalar(sql, key):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            return int(row[key]) if row else 0
    except Exception:
        return 0
    finally:
        if conn:
            conn.close()
