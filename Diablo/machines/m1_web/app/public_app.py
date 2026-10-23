import os
import random
import re
import secrets
from datetime import datetime, timezone
from functools import wraps

import pymysql
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from auth import hash_password, verify_password
from company import (
    billing_summary,
    create_ticket,
    ensure_company_schema,
    list_docs,
    list_invoices,
    list_tickets,
    platform_status,
    site_summary,
    support_summary,
)
from db import connect
from noise import install_noise_headers
from sites import SITE_URLS, site_for_host, waf_enabled
from waf import install_cors, install_waf

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "trickshot-lab-session-key")
app.config.update(
    SESSION_COOKIE_NAME="ts_session",
    SESSION_COOKIE_DOMAIN=".trickshot.local",
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
)
install_noise_headers(app)
install_waf(app)
install_cors(app)
ensure_company_schema()

SURVEY_SERVICES = ["portal", "facturacion", "soporte", "integraciones", "otro"]

AUTH_DECOYS = [
    "/api/v1/admin",
    "/api/v1/users",
    "/api/v1/export",
    "/api/v1/config",
    "/api/v1/tokens",
    "/api/v1/audit",
    "/api/v1/sessions",
    "/api/v1/backup",
    "/api/v1/backups",
    "/api/v1/keys",
    "/api/v1/secrets",
    "/api/v1/debug",
    "/api/v1/files",
    "/api/v1/uploads",
    "/api/v1/attachments",
    "/api/v1/tickets",
    "/api/v1/reports",
    "/api/v1/internal/status",
    "/api/v1/internal/metrics",
    "/api/v1/internal/debug",
    "/api/v1/auth/login",
    "/api/v1/auth/token",
    "/api/v1/openapi.json",
    "/api/v1/swagger.json",
    "/api/swagger.json",
    "/oauth/token",
]

RESTRICTED_DECOYS = {
    "/admin": (403, "Acceso restringido a la red corporativa."),
    "/administrator": (403, "Acceso restringido a personal autorizado."),
    "/phpmyadmin": (403, "Acceso restringido a administradores de base de datos."),
    "/server-status": (403, "Estado del servidor no disponible públicamente."),
    "/actuator/env": (403, "Endpoint de gestión deshabilitado."),
    "/console": (403, "Consola administrativa deshabilitada."),
    "/manager/html": (403, "Administrador de aplicaciones deshabilitado."),
    "/wp-admin": (404, "Recurso no encontrado."),
    "/wp-login.php": (404, "Recurso no encontrado."),
    "/.env": (404, "Recurso no encontrado."),
    "/.git/config": (404, "Recurso no encontrado."),
    "/backup.zip": (404, "Recurso no encontrado."),
    "/db.sql": (404, "Recurso no encontrado."),
    "/config.php.bak": (404, "Recurso no encontrado."),
    "/openapi.json": (403, "Especificación de API no disponible."),
    "/swagger.json": (403, "Especificación de API no disponible."),
    "/api-docs": (403, "Documentación de API no disponible."),
    "/v2/api-docs": (403, "Documentación de API no disponible."),
    "/actuator": (403, "Endpoint de gestión deshabilitado."),
    "/actuator/health": (403, "Endpoint de gestión deshabilitado."),
    "/metrics": (403, "Métricas internas no disponibles."),
    "/debug": (403, "Modo de depuración deshabilitado."),
    "/env": (404, "Recurso no encontrado."),
    "/phpinfo.php": (404, "Recurso no encontrado."),
    "/info.php": (404, "Recurso no encontrado."),
    "/test.php": (404, "Recurso no encontrado."),
    "/shell.php": (404, "Recurso no encontrado."),
    "/xmlrpc.php": (404, "Recurso no encontrado."),
    "/server-info": (403, "Información del servidor no disponible."),
    "/status": (403, "Estado interno no disponible públicamente."),
}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("customer"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("customer"):
            return jsonify(error="unauthorized", code="AUTH_REQUIRED"), 401
        return view(*args, **kwargs)

    return wrapped


DEFAULT_METRICS = [
    ("logins_total", "0"),
    ("last_login_at", "-"),
    ("last_login_ip", "-"),
    ("messages_sent", "0"),
    ("messages_received", "0"),
    ("api_calls_30d", "0"),
    ("storage_used_mb", "0"),
    ("mfa_enabled", "false"),
]


def fetch_user(username):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash, display_name "
                "FROM site_users WHERE username = %s LIMIT 1",
                (username,),
            )
            return cur.fetchone()
    except Exception:
        return None
    finally:
        if conn:
            conn.close()


def start_session(user):
    session.clear()
    session["customer"] = {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
    }


def serialize_metric(row):
    updated = row.get("updated_at")
    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "key": row["metric_key"],
        "value": row["metric_value"],
        "updated_at": updated.isoformat() if updated else None,
    }


def get_metrics(account_id):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, account_id, metric_key, metric_value, updated_at "
                "FROM account_metrics WHERE account_id = %s ORDER BY id",
                (account_id,),
            )
            return [serialize_metric(row) for row in cur.fetchall()]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


def get_metric(metric_id):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, account_id, metric_key, metric_value, updated_at "
                "FROM account_metrics WHERE id = %s LIMIT 1",
                (metric_id,),
            )
            row = cur.fetchone()
            return serialize_metric(row) if row else None
    except Exception:
        return None
    finally:
        if conn:
            conn.close()


def ensure_default_metrics(account_id):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT IGNORE INTO account_metrics (account_id, metric_key, metric_value) "
                "VALUES (%s, %s, %s)",
                [(account_id, key, value) for key, value in DEFAULT_METRICS],
            )
    except Exception:
        pass
    finally:
        if conn:
            conn.close()


def bump_metric(account_id, metric_key, amount=1):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE account_metrics "
                "SET metric_value = CAST(CAST(metric_value AS UNSIGNED) + %s AS CHAR) "
                "WHERE account_id = %s AND metric_key = %s",
                (amount, account_id, metric_key),
            )
            if cur.rowcount == 0:
                try:
                    cur.execute(
                        "INSERT INTO account_metrics (account_id, metric_key, metric_value) "
                        "VALUES (%s, %s, %s)",
                        (account_id, metric_key, str(amount)),
                    )
                except pymysql.err.IntegrityError:
                    cur.execute(
                        "UPDATE account_metrics "
                        "SET metric_value = CAST(CAST(metric_value AS UNSIGNED) + %s AS CHAR) "
                        "WHERE account_id = %s AND metric_key = %s",
                        (amount, account_id, metric_key),
                    )
    except Exception:
        pass
    finally:
        if conn:
            conn.close()


def set_metric(account_id, metric_key, value):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE account_metrics SET metric_value = %s "
                "WHERE account_id = %s AND metric_key = %s",
                (value, account_id, metric_key),
            )
            if cur.rowcount == 0:
                cur.execute(
                    "SELECT id FROM account_metrics WHERE account_id = %s AND metric_key = %s",
                    (account_id, metric_key),
                )
                if cur.fetchone() is None:
                    try:
                        cur.execute(
                            "INSERT INTO account_metrics (account_id, metric_key, metric_value) "
                            "VALUES (%s, %s, %s)",
                            (account_id, metric_key, value),
                        )
                    except pymysql.err.IntegrityError:
                        cur.execute(
                            "UPDATE account_metrics SET metric_value = %s "
                            "WHERE account_id = %s AND metric_key = %s",
                            (value, account_id, metric_key),
                        )
    except Exception:
        pass
    finally:
        if conn:
            conn.close()


def record_login(account_id):
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    client_ip = (forwarded or request.remote_addr or "-")[:64]
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    bump_metric(account_id, "logins_total")
    set_metric(account_id, "last_login_at", timestamp)
    set_metric(account_id, "last_login_ip", client_ip)


def serialize_message(row):
    created = row.get("created_at")
    result = {
        "id": row["id"],
        "subject": row["subject"],
        "body": row["body"],
        "is_read": bool(row["is_read"]),
        "created_at": created.isoformat() if created else None,
    }
    if row.get("sender"):
        result["sender"] = row["sender"]
        result["sender_name"] = row.get("sender_name")
    if row.get("recipient"):
        result["recipient"] = row["recipient"]
        result["recipient_name"] = row.get("recipient_name")
    return result


def get_inbox(account_id):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT m.id, m.subject, m.body, m.is_read, m.created_at, "
                "s.username AS sender, s.display_name AS sender_name "
                "FROM messages m JOIN site_users s ON s.id = m.sender_id "
                "WHERE m.recipient_id = %s ORDER BY m.id DESC LIMIT 50",
                (account_id,),
            )
            return [serialize_message(row) for row in cur.fetchall()]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


def get_sent(account_id):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT m.id, m.subject, m.body, m.is_read, m.created_at, "
                "r.username AS recipient, r.display_name AS recipient_name "
                "FROM messages m JOIN site_users r ON r.id = m.recipient_id "
                "WHERE m.sender_id = %s ORDER BY m.id DESC LIMIT 50",
                (account_id,),
            )
            return [serialize_message(row) for row in cur.fetchall()]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


def unread_count(account_id):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS total FROM messages "
                "WHERE recipient_id = %s AND is_read = 0",
                (account_id,),
            )
            row = cur.fetchone()
            return int(row["total"]) if row else 0
    except Exception:
        return 0
    finally:
        if conn:
            conn.close()


def mark_inbox_read(account_id):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE messages SET is_read = 1 "
                "WHERE recipient_id = %s AND is_read = 0",
                (account_id,),
            )
    except Exception:
        pass
    finally:
        if conn:
            conn.close()


def create_message(sender_id, recipient_username, subject, body):
    conn = None
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username FROM site_users WHERE username = %s LIMIT 1",
                (recipient_username,),
            )
            recipient = cur.fetchone()
            if not recipient:
                return None
            cur.execute(
                "INSERT INTO messages (sender_id, recipient_id, subject, body) "
                "VALUES (%s, %s, %s, %s)",
                (sender_id, recipient["id"], subject, body),
            )
            message_id = cur.lastrowid
        bump_metric(sender_id, "messages_sent")
        bump_metric(recipient["id"], "messages_received")
        return message_id
    except Exception:
        return None
    finally:
        if conn:
            conn.close()


def fake_request_id():
    return request.headers.get("X-Request-Id") or secrets.token_hex(8)


@app.context_processor
def inject_customer():
    host = request.host
    site = site_for_host(host)
    return {
        "current_customer": session.get("customer"),
        "site": site,
        "sites": SITE_URLS,
        "waf_enabled": waf_enabled(host),
    }


@app.get("/")
def index():
    site = site_for_host(request.host)

    if site in {"portal", "app"}:
        if session.get("customer"):
            return redirect(url_for("account"))
        return redirect(url_for("login"))

    if site == "auth":
        if session.get("customer"):
            return redirect(SITE_URLS["portal"] + "/account")
        return redirect(url_for("login"))

    if site == "api":
        return render_template("public/api.html")

    if site == "docs":
        return render_template("public/docs.html")

    if site == "status":
        return render_template("public/status.html")

    if site == "support":
        return render_template("public/support.html")

    if site == "billing":
        return render_template("public/billing.html")

    return render_template("public/index.html")


@app.get("/health")
def health():
    return jsonify(status="ok", service="portal", version="4.12.3", region="eu-west-1")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("customer"):
        return redirect(url_for("account"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = fetch_user(username)

        if user and verify_password(user["password_hash"], password):
            start_session(user)
            record_login(user["id"])
            if site_for_host(request.host) == "auth":
                return redirect(SITE_URLS["portal"] + "/account")
            return redirect(url_for("account"))

        flash("Usuario o contraseña incorrectos.", "error")

    return render_template("public/login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        display_name = request.form.get("display_name", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
            flash("El usuario debe tener entre 3 y 32 caracteres válidos.", "error")
        elif not 2 <= len(display_name) <= 80:
            flash("El nombre visible debe tener entre 2 y 80 caracteres.", "error")
        elif len(password) < 8:
            flash("La contraseña debe tener al menos 8 caracteres.", "error")
        elif password != confirm:
            flash("Las contraseñas no coinciden.", "error")
        else:
            try:
                conn = connect()
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO site_users (username, password_hash, display_name) "
                        "VALUES (%s, %s, %s)",
                        (username, hash_password(password), display_name),
                    )
                    account_id = cur.lastrowid
                conn.close()
                ensure_default_metrics(account_id)
                flash("Cuenta creada correctamente. Ya puede iniciar sesión.", "success")
                return redirect(url_for("login"))
            except pymysql.err.IntegrityError:
                flash("El nombre de usuario ya está registrado.", "error")
            except Exception:
                flash("No fue posible crear la cuenta.", "error")

    return render_template("public/register.html")


@app.get("/logout")
def logout():
    session.clear()
    return redirect(SITE_URLS["main"] + "/")


@app.get("/account")
@login_required
def account():
    account_id = session["customer"]["id"]
    cases = [
        {"ref": "CASE-2041", "subject": "Solicitud de factura", "status": "En revisión"},
        {"ref": "CASE-1988", "subject": "Acceso al portal", "status": "Resuelto"},
        {"ref": "CASE-1873", "subject": "Integración de API", "status": "Pendiente"},
    ]
    quotes = [
        {"ref": "QUO-7781", "plan": "Business", "seats": 25, "status": "Vigente"},
        {"ref": "QUO-7650", "plan": "Enterprise", "seats": 80, "status": "Borrador"},
    ]
    return render_template(
        "public/account.html",
        cases=cases,
        quotes=quotes,
        metrics=get_metrics(account_id),
        inbox=get_inbox(account_id)[:3],
        sent=get_sent(account_id)[:3],
        unread=unread_count(account_id),
    )


@app.route("/messages", methods=["GET", "POST"])
@login_required
def messages():
    account_id = session["customer"]["id"]

    if request.method == "POST":
        recipient = request.form.get("recipient", "").strip()
        subject = request.form.get("subject", "").strip() or "Sin asunto"
        body = request.form.get("body", "").strip()

        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", recipient):
            flash("El nombre de usuario del destinatario no es válido.", "error")
        elif len(subject) > 160:
            flash("El asunto no puede superar los 160 caracteres.", "error")
        elif not 1 <= len(body) <= 4000:
            flash("El mensaje debe tener entre 1 y 4000 caracteres.", "error")
        else:
            message_id = create_message(account_id, recipient, subject, body)
            if message_id is None:
                flash("No existe ninguna cuenta con ese nombre de usuario.", "error")
            else:
                flash("Mensaje enviado correctamente.", "success")
                return redirect(url_for("messages"))

    mark_inbox_read(account_id)
    return render_template(
        "public/messages.html",
        inbox=get_inbox(account_id),
        sent=get_sent(account_id),
        unread=unread_count(account_id),
    )


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        flash(
            "Si la cuenta existe, se enviarán instrucciones de recuperación al correo registrado.",
            "success",
        )
        return redirect(url_for("forgot_password"))
    return render_template("public/forgot_password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        flash("El enlace de recuperación no es válido o ha expirado.", "error")
    return render_template("public/reset_password.html")


@app.route("/mfa", methods=["GET", "POST"])
def mfa():
    if request.method == "POST":
        flash("El código de verificación no es válido.", "error")
    return render_template("public/mfa.html")


@app.route("/recovery-questions", methods=["GET", "POST"])
def recovery_questions():
    questions = [
        "¿Cuál fue el nombre de su primera mascota?",
        "¿En qué ciudad nació su madre?",
        "¿Cuál fue el modelo de su primer vehículo?",
    ]
    if request.method == "POST":
        flash("Las respuestas de seguridad no coinciden.", "error")
    return render_template("public/recovery_questions.html", questions=questions)


@app.route("/comments", methods=["GET", "POST"])
def comments():
    if request.method == "POST":
        author = request.form.get("author", "").strip()
        email = request.form.get("email", "").strip()
        body = request.form.get("body", "").strip()

        if not 2 <= len(author) <= 80:
            flash("El nombre debe tener entre 2 y 80 caracteres.", "error")
        elif len(body) < 3 or len(body) > 2000:
            flash("El comentario debe tener entre 3 y 2000 caracteres.", "error")
        elif email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("El correo electrónico no es válido.", "error")
        else:
            try:
                conn = connect()
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO comments (author, email, body) VALUES (%s, %s, %s)",
                        (author, email or None, body),
                    )
                conn.close()
                flash("Comentario publicado correctamente.", "success")
                return redirect(url_for("comments"))
            except Exception:
                flash("No fue posible publicar el comentario.", "error")

    comments_list = []
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT author, body, created_at FROM comments "
                "ORDER BY id DESC LIMIT 40"
            )
            comments_list = cur.fetchall()
        conn.close()
    except Exception:
        comments_list = []

    return render_template("public/comments.html", comments=comments_list)


@app.route("/survey", methods=["GET", "POST"])
def survey():
    if request.method == "POST":
        service = request.form.get("service", "")
        feedback = request.form.get("feedback", "").strip()

        try:
            satisfaction = int(request.form.get("satisfaction", "0"))
        except ValueError:
            satisfaction = 0

        if satisfaction not in range(1, 6):
            flash("Seleccione una valoración entre 1 y 5.", "error")
        elif service not in SURVEY_SERVICES:
            flash("Seleccione un servicio válido.", "error")
        elif len(feedback) > 1500:
            flash("El comentario es demasiado largo.", "error")
        else:
            try:
                conn = connect()
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO survey_responses (satisfaction, service, feedback) "
                        "VALUES (%s, %s, %s)",
                        (satisfaction, service, feedback),
                    )
                conn.close()
                flash("Gracias por participar en la encuesta.", "success")
                return redirect(url_for("survey"))
            except Exception:
                flash("No fue posible registrar la encuesta.", "error")

    counts = {score: 0 for score in range(1, 6)}
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT satisfaction, COUNT(*) AS total FROM survey_responses "
                "GROUP BY satisfaction"
            )
            for row in cur.fetchall():
                counts[int(row["satisfaction"])] = int(row["total"])
        conn.close()
    except Exception:
        pass

    total = sum(counts.values())
    results = []
    for score in range(1, 6):
        count = counts[score]
        percent = round((count / total) * 100) if total else 0
        results.append({"score": score, "count": count, "percent": percent})

    return render_template("public/survey.html", results=results, total=total)


@app.get("/api/v1/status")
def api_status():
    return jsonify(
        status="ok",
        service="trickshot-portal",
        version="4.12.3",
        region="eu-west-1",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/v1/version")
def api_version():
    return jsonify(
        application="trickshot-portal",
        build="2026.10.17-rc2",
        runtime="edge-runtime",
        api="v1",
    )


@app.get("/api/v1/products")
def api_products():
    return jsonify(
        products=[
            {"id": "starter", "name": "Starter", "price": 29, "seats": 5},
            {"id": "business", "name": "Business", "price": 99, "seats": 25},
            {"id": "enterprise", "name": "Enterprise", "price": 349, "seats": 100},
        ]
    )


@app.get("/api/v1/faq")
def api_faq():
    return jsonify(
        faq=[
            {"question": "¿Cómo restablezco mi contraseña?", "category": "cuenta"},
            {"question": "¿Dónde consulto mis facturas?", "category": "facturacion"},
            {"question": "¿Cómo integro la API?", "category": "integraciones"},
            {"question": "¿Cuál es el horario de soporte?", "category": "soporte"},
        ]
    )


@app.get("/api/v1/metrics")
def api_metrics():
    return jsonify(
        uptime_seconds=random.randint(80000, 900000),
        requests_per_minute=random.randint(80, 600),
        cache_hit_ratio=round(random.uniform(0.72, 0.98), 2),
        active_workers=random.randint(2, 8),
        queue_depth=random.randint(0, 20),
    )


@app.get("/api/v1/search")
def api_search():
    query = request.args.get("q", "").strip()[:100]

    if not query:
        return jsonify(query="", results=[], status="ok")

    try:
        conn = connect()
        with conn.cursor() as cur:
            pattern = f"%{query}%"
            cur.execute(
                "SELECT title, category, SUBSTRING(body, 1, 180) AS excerpt "
                "FROM kb_articles WHERE title LIKE %s OR body LIKE %s "
                "ORDER BY id LIMIT 10",
                (pattern, pattern),
            )
            results = cur.fetchall()
        conn.close()
        return jsonify(query=query, results=results, status="ok")
    except Exception:
        return jsonify(query=query, results=[], status="degraded")


@app.get("/api/v1/verify")
def api_verify_decoy():
    return jsonify(status="not_found", source="public-api")


@app.get("/api/v1/tickets/status")
def api_ticket_status_decoy():
    return jsonify(status="unknown", queue="public")


@app.post("/api/v1/newsletter")
def api_newsletter():
    data = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 160:
        return jsonify(status="invalid_email"), 400

    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO newsletter_subscribers (email) VALUES (%s)",
                (email,),
            )
        conn.close()
    except Exception:
        return jsonify(status="degraded"), 503

    return jsonify(status="subscribed")


def api_login_impl():
    data = request.get_json(silent=True) or request.form
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    user = fetch_user(username)

    if not user or not verify_password(user["password_hash"], password):
        return jsonify(error="unauthorized", code="INVALID_CREDENTIALS"), 401

    start_session(user)
    record_login(user["id"])
    account_id = user["id"]
    return jsonify(
        status="authenticated",
        account={
            "id": account_id,
            "username": user["username"],
            "display_name": user["display_name"],
        },
        metrics=get_metrics(account_id),
        unread=unread_count(account_id),
        links={
            "account": url_for("api_account"),
            "metrics": url_for("api_account_metrics", account_id=account_id),
            "messages": url_for("api_messages"),
        },
    )


@app.post("/api/v1/login")
def api_login():
    return api_login_impl()


@app.post("/api/v1/session")
def api_session_login():
    return api_login_impl()


@app.get("/api/v1/session")
@api_login_required
def api_session():
    customer = session["customer"]
    return jsonify(
        status="authenticated",
        account=customer,
        metrics=get_metrics(customer["id"]),
        unread=unread_count(customer["id"]),
    )


@app.delete("/api/v1/session")
def api_session_logout():
    session.clear()
    return jsonify(status="logged_out")


@app.get("/api/v1/account")
@api_login_required
def api_account():
    customer = session["customer"]
    return jsonify(
        account=customer,
        metrics=get_metrics(customer["id"]),
        unread=unread_count(customer["id"]),
    )


@app.get("/api/v1/account/metrics")
@api_login_required
def api_account_metrics_path():
    customer = session["customer"]
    return jsonify(
        account_id=customer["id"],
        scope="account",
        metrics=get_metrics(customer["id"]),
    )


@app.get("/api/v1/accounts/<int:account_id>/metrics")
@api_login_required
def api_account_metrics(account_id):
    current_id = session["customer"]["id"]
    if account_id != current_id:
        return jsonify(
            error="forbidden",
            code="ACCOUNT_SCOPE_MISMATCH",
            requested_account_id=account_id,
            scope="account",
        ), 403
    return jsonify(
        account_id=current_id,
        scope="account",
        metrics=get_metrics(current_id),
    )


@app.get("/api/v1/metrics/<int:metric_id>")
@api_login_required
def api_metric(metric_id):
    current_id = session["customer"]["id"]
    metric = get_metric(metric_id)
    if metric is None:
        return jsonify(error="not_found", code="METRIC_NOT_FOUND"), 404
    if metric["account_id"] != current_id:
        return jsonify(
            error="forbidden",
            code="METRIC_SCOPE_MISMATCH",
            metric_id=metric_id,
            scope="account",
        ), 403
    return jsonify(metric=metric)


@app.get("/api/v1/messages")
@api_login_required
def api_messages():
    account_id = session["customer"]["id"]
    return jsonify(
        inbox=get_inbox(account_id),
        sent=get_sent(account_id),
        unread=unread_count(account_id),
    )


@app.post("/api/v1/messages")
@api_login_required
def api_send_message():
    data = request.get_json(silent=True) or request.form
    recipient = str(data.get("recipient", "")).strip()
    subject = str(data.get("subject", "")).strip() or "Sin asunto"
    body = str(data.get("body", "")).strip()

    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", recipient):
        return jsonify(error="invalid_recipient"), 400
    if len(subject) > 160:
        return jsonify(error="invalid_subject"), 400
    if not 1 <= len(body) <= 4000:
        return jsonify(error="invalid_body"), 400

    message_id = create_message(session["customer"]["id"], recipient, subject, body)
    if message_id is None:
        return jsonify(error="recipient_not_found"), 404
    return jsonify(
        status="sent",
        message_id=message_id,
        recipient=recipient,
        subject=subject,
    ), 201


@app.post("/api/v1/auth/forgot-password")
def fake_forgot_password():
    return jsonify(
        status="accepted",
        delivery="email",
        expires_in=900,
        request_id=fake_request_id(),
    ), 202


@app.post("/api/v1/auth/reset-password")
def fake_reset_password():
    return jsonify(
        status="accepted",
        message="Reset request queued for processing.",
        request_id=fake_request_id(),
    ), 202


@app.post("/api/v1/auth/mfa/verify")
def fake_mfa_verify():
    return jsonify(
        status="invalid_code",
        remaining_attempts=2,
        request_id=fake_request_id(),
    ), 400


@app.post("/api/v1/auth/mfa/disable")
def fake_mfa_disable():
    return jsonify(
        status="pending_approval",
        challenge_id="mfa_" + secrets.token_hex(8),
        delivery="email",
        request_id=fake_request_id(),
    ), 202


@app.get("/api/v1/auth/legacy-token")
def fake_legacy_token():
    return jsonify(
        status="deprecated",
        token="ts_legacy_" + secrets.token_hex(24),
        token_type="Bearer",
        scope="account:recover",
        expires_in=300,
        request_id=fake_request_id(),
    )


@app.get("/api/v1/account/recovery/questions")
def fake_recovery_questions():
    return jsonify(
        status="ok",
        questions=[
            "¿Cuál fue el nombre de su primera mascota?",
            "¿En qué ciudad nació su madre?",
            "¿Cuál fue el modelo de su primer vehículo?",
        ],
        request_id=fake_request_id(),
    )


@app.post("/api/v1/account/recovery/answers")
def fake_recovery_answers():
    return jsonify(
        status="verification_failed",
        remaining_attempts=2,
        request_id=fake_request_id(),
    )


@app.post("/api/v1/account/email")
def fake_account_email():
    return jsonify(
        status="verification_sent",
        delivery="email",
        request_id=fake_request_id(),
    ), 202


@app.post("/api/v1/account/verify-email")
def fake_verify_email():
    return jsonify(
        status="invalid_token",
        request_id=fake_request_id(),
    ), 400


@app.post("/api/v1/auth/support-unlock")
def fake_support_unlock():
    return jsonify(
        status="case_created",
        case_id="CASE-" + str(random.randint(2050, 9999)),
        request_id=fake_request_id(),
    ), 202


@app.post("/api/v1/oauth/impersonate")
def fake_impersonate():
    return jsonify(
        status="queued",
        approval="required",
        request_id=fake_request_id(),
    ), 202


def decoy_auth():
    response = jsonify(
        error="unauthorized",
        code="AUTH_REQUIRED",
        request_id=request.headers.get("X-Request-Id", ""),
    )
    response.headers["WWW-Authenticate"] = 'Bearer realm="trickshot-api"'
    return response, 401


for decoy_path in AUTH_DECOYS:
    app.add_url_rule(
        decoy_path,
        endpoint="decoy_" + decoy_path.strip("/").replace("/", "_"),
        view_func=decoy_auth,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )


def decoy_graphql():
    response = jsonify(errors=[{"message": "Introspection is disabled."}])
    response.headers["WWW-Authenticate"] = 'Bearer realm="trickshot-api"'
    return response, 401


for graphql_path in ["/graphql", "/api/v1/graphql"]:
    app.add_url_rule(
        graphql_path,
        endpoint="decoy_" + graphql_path.strip("/").replace("/", "_"),
        view_func=decoy_graphql,
        methods=["GET", "POST"],
    )


def make_restricted_decoy(status, message):
    def view():
        if request.path.startswith("/api/"):
            return jsonify(error="not_found"), status
        return render_template("public/decoy.html", code=status, message=message), status

    return view


for decoy_path, (status, message) in RESTRICTED_DECOYS.items():
    app.add_url_rule(
        decoy_path,
        endpoint="restricted_" + decoy_path.strip("/").replace("/", "_").replace(".", "_"),
        view_func=make_restricted_decoy(status, message),
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )


@app.route("/api/v1/users/<int:user_id>", methods=["GET", "PUT", "PATCH", "DELETE"])
def decoy_user(user_id):
    return decoy_auth()


@app.route("/api/v1/files/<path:filename>", methods=["GET", "POST", "DELETE"])
def decoy_file(filename):
    return decoy_auth()


@app.route("/api/v2/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def decoy_api_v2(subpath):
    return jsonify(error="not_found", api_version="v2-beta"), 404


@app.get("/.well-known/openid-configuration")
def openid_configuration():
    return jsonify(
        issuer="https://auth.trickshot.local",
        authorization_endpoint="https://auth.trickshot.local/oauth/authorize",
        token_endpoint="https://auth.trickshot.local/oauth/token",
        userinfo_endpoint="https://auth.trickshot.local/oauth/userinfo",
        jwks_uri="https://auth.trickshot.local/.well-known/jwks.json",
        scopes_supported=["openid", "profile", "email"],
        response_types_supported=["code"],
        subject_types_supported=["public"],
        id_token_signing_alg_values_supported=["RS256"],
    )


@app.get("/.well-known/jwks.json")
def jwks():
    return jsonify(keys=[])


@app.get("/robots.txt")
def robots():
    content = (
        "User-agent: *\n"
        "Disallow: /admin\n"
        "Disallow: /administrator\n"
        "Disallow: /api/v1/admin\n"
        "Disallow: /api/v1/internal\n"
        "Disallow: /api/v1/account\n"
        "Disallow: /messages\n"
        "Disallow: /forgot-password\n"
        "Disallow: /reset-password\n"
        "Disallow: /backup\n"
        "Disallow: /server-status\n"
        "Disallow: /phpmyadmin\n"
        "Disallow: /console\n"
        "Sitemap: http://trickshot.local/sitemap.xml\n"
    )
    return Response(content, mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap():
    paths = [
        "/",
        "/comments",
        "/survey",
        "/login",
        "/register",
        "/api/v1/status",
        "/api/v1/products",
        "/api/v1/faq",
    ]
    entries = "".join(
        f"<url><loc>http://trickshot.local{path}</loc></url>" for path in paths
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</urlset>"
    )
    return Response(content, mimetype="application/xml")


@app.get("/security.txt")
@app.get("/.well-known/security.txt")
def security_txt():
    content = (
        "Contact: mailto:security@trickshot.local\n"
        "Expires: 2027-12-31T23:59:00.000Z\n"
        "Preferred-Languages: es, en\n"
        "Canonical: http://trickshot.local/.well-known/security.txt\n"
    )
    return Response(content, mimetype="text/plain")


@app.get("/api/v1/summary")
def api_site_summary():
    return jsonify(site_summary(site_for_host(request.host)))


@app.get("/api/v1/platform/status")
def api_platform_status():
    return jsonify(platform_status())


@app.get("/api/v1/support/tickets")
def api_support_tickets():
    return jsonify(tickets=list_tickets(limit=40))


@app.post("/api/v1/support/tickets")
def api_create_ticket():
    data = request.get_json(silent=True) or request.form
    subject = str(data.get("subject", "")).strip()
    priority = str(data.get("priority", "medium")).strip().lower()
    opened_by = str(data.get("opened_by", "")).strip()

    if not session.get("customer") and not opened_by:
        opened_by = "guest"

    if session.get("customer"):
        opened_by = session["customer"]["username"]

    if not 4 <= len(subject) <= 180:
        return jsonify(error="invalid_subject", code="TICKET_SUBJECT_INVALID"), 400
    if priority not in {"low", "medium", "high", "critical"}:
        return jsonify(error="invalid_priority", code="TICKET_PRIORITY_INVALID"), 400

    ticket = create_ticket(subject, priority, opened_by or "guest")
    if not ticket:
        return jsonify(error="ticket_unavailable", code="TICKET_STORE_UNAVAILABLE"), 503

    return jsonify(status="created", ticket=ticket), 201


@app.get("/api/v1/support/summary")
def api_support_summary():
    return jsonify(support_summary())


@app.get("/api/v1/billing/invoices")
def api_billing_invoices():
    account = request.args.get("account", "").strip()
    if not account and session.get("customer"):
        account = session["customer"]["username"]
    return jsonify(
        account=account or "all",
        invoices=list_invoices(customer_username=account or None, limit=50),
        summary=billing_summary(customer_username=account or None),
    )


@app.get("/api/v1/billing/summary")
def api_billing_summary():
    account = request.args.get("account", "").strip()
    if not account and session.get("customer"):
        account = session["customer"]["username"]
    return jsonify(account=account or "all", summary=billing_summary(customer_username=account or None))


@app.get("/api/v1/docs/articles")
def api_docs_articles():
    query = request.args.get("q", "").strip()[:120]
    try:
        limit = min(max(int(request.args.get("limit", "20")), 1), 50)
    except ValueError:
        limit = 20
    return jsonify(query=query, articles=list_docs(query=query or None, limit=limit))


@app.get("/api/v1/docs/summary")
def api_docs_summary():
    return jsonify(site_summary("docs"))


@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/api/"):
        return jsonify(error="not_found"), 404
    return render_template("public/404.html"), 404
