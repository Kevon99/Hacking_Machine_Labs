import os
import subprocess
from functools import wraps

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from db import connect
from noise import install_noise_headers

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "trickshot-lab-session-key")
install_noise_headers(app)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


@app.get("/")
def index():
    if session.get("user"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        try:
            conn = connect()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, username, role FROM users WHERE username = %s AND password = %s",
                    (username, password),
                )
                user = cur.fetchone()
            conn.close()
        except Exception:
            user = None

        if user:
            session["user"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))

        flash("Credenciales inválidas", "error")

    return render_template("admin/login.html")


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/dashboard")
@login_required
def dashboard():
    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ticket_id, subject, status, priority, created_at "
                "FROM tickets ORDER BY id DESC"
            )
            tickets = cur.fetchall()
        conn.close()
    except Exception:
        tickets = []

    return render_template("admin/dashboard.html", tickets=tickets)


@app.get("/api/v1/verify")
def verify_ticket():
    ticket_id = request.args.get("ticket_id", "")

    if not ticket_id:
        return jsonify(status="not_found")

    query = "SELECT id FROM tickets WHERE ticket_id = '%s'" % ticket_id

    try:
        conn = connect()
        with conn.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()
        conn.close()
    except Exception:
        row = None

    return jsonify(status="found" if row else "not_found")


@app.route("/admin/reports", methods=["GET", "POST"])
@login_required
def reports():
    output = None

    if request.method == "POST":
        report_name = request.form.get("report_name", "monthly")
        report_format = request.form.get("report_format", "csv")
        command = (
            f"/usr/local/bin/generate_report.sh "
            f"--name {report_name} --format {report_format}"
        )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            output = f"{result.stdout}{result.stderr}".strip()
        except subprocess.TimeoutExpired:
            output = "La generación del reporte excedió el tiempo límite."

        flash("Reporte procesado", "success")

    return render_template("admin/reports.html", output=output)


@app.route("/admin/backup", methods=["GET", "POST"])
@login_required
def backup():
    output = None

    if request.method == "POST":
        filename = request.form.get("filename", "corp_backup.tar.gz")
        ftp_host = request.form.get("ftp_host", "backup.trickshot.local")
        command = (
            f"tar czf /tmp/backups/{filename} /var/www/app/data "
            f"&& echo 'Backup preparado para {ftp_host}'"
        )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            output = f"{result.stdout}{result.stderr}".strip()
        except subprocess.TimeoutExpired:
            output = "El respaldo excedió el tiempo límite."

        flash("Respaldo procesado", "success")

    return render_template("admin/backup.html", output=output)
