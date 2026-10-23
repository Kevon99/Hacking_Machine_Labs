#!/bin/sh
set -e

DB_HOST="${DB_HOST:-m1_db}"
DB_PORT="${DB_PORT:-3306}"
DB_ROOT_USER="${DB_ROOT_USER:-root}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-rootpassword}"
DB_NAME="${DB_NAME:-corp_db}"

until python -c "import os, socket; s = socket.create_connection((os.environ.get('DB_HOST', 'm1_db'), int(os.environ.get('DB_PORT', '3306'))), 2); s.close()" 2>/dev/null; do
  echo "[m1_web] waiting for database at ${DB_HOST}:${DB_PORT}..."
  sleep 2
done

prepare_prod_assets() {
  PASSFILE="/home/prod/.config/.secrets/.passphrase"
  SNAPSHOT_ROOT="/home/prod/.local/share/.cache-ts/.snapshots"

  install -d -o prod -g prod -m 700 \
    /home/prod/.config/.secrets \
    /home/prod/.local/state \
    /home/prod/.local/share/.cache-ts \
    "$SNAPSHOT_ROOT"

  if [ ! -s "$PASSFILE" ]; then
    umask 077
    openssl rand -base64 32 > "$PASSFILE"
  fi

  chown prod:prod "$PASSFILE"
  chmod 600 "$PASSFILE"

  SNAPSHOT_DIR="$SNAPSHOT_ROOT/$(date -u +%Y%m%dT%H%M%SZ)"
  install -d -o prod -g prod -m 700 "$SNAPSHOT_DIR"

  WORKDIR=$(mktemp -d)
  trap 'rm -rf "$WORKDIR" "$SNAPSHOT_DIR"' EXIT INT TERM

  cleanup_failed_backup() {
    rm -rf "$WORKDIR" "$SNAPSHOT_DIR"
    trap - EXIT INT TERM
  }

  if ! mysqldump \
    -h "$DB_HOST" \
    -P "$DB_PORT" \
    -u "$DB_ROOT_USER" \
    -p"$DB_ROOT_PASSWORD" \
    --skip-ssl \
    --single-transaction \
    --routines \
    --triggers \
    --default-character-set=utf8mb4 \
    "$DB_NAME" > "$WORKDIR/corp_db.sql"; then
    echo "[m1_web] database dump failed" >&2
    cleanup_failed_backup
    return 1
  fi

  if ! gzip -c "$WORKDIR/corp_db.sql" > "$WORKDIR/corp_db.sql.gz"; then
    echo "[m1_web] database compression failed" >&2
    cleanup_failed_backup
    return 1
  fi

  if ! ROOT_PASSWORD="$DB_ROOT_PASSWORD" \
    ADMIN_PASSWORD="${DB_PASSWORD:-SuperSecretDBPass123!}" \
    python3 /usr/local/bin/build_vault.py "$WORKDIR/vault.db" "$PASSFILE"; then
    echo "[m1_web] credential vault build failed" >&2
    cleanup_failed_backup
    return 1
  fi

  cat > "$WORKDIR/credentials.env" <<EOF
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
DB_NAME=$DB_NAME
DB_ROOT_USER=$DB_ROOT_USER
DB_ROOT_PASSWORD=$DB_ROOT_PASSWORD
DB_ADMIN_USER=db_admin
DB_ADMIN_PASSWORD=${DB_PASSWORD:-SuperSecretDBPass123!}
EOF

  cat > "$WORKDIR/manifest.json" <<EOF
{"created_at":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","database":"$DB_NAME","format":"mysql-dump-gzip","vault":"sqlite3","hash_algorithm":"pbkdf2_sha256","iterations":200000,"pepper_source":".passphrase"}
EOF

  if ! tar -czf "$WORKDIR/snapshot.tar.gz" -C "$WORKDIR" \
    corp_db.sql.gz vault.db credentials.env manifest.json; then
    echo "[m1_web] snapshot archive failed" >&2
    cleanup_failed_backup
    return 1
  fi

  if ! openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 -salt \
    -pass "file:$PASSFILE" \
    -in "$WORKDIR/snapshot.tar.gz" \
    -out "$SNAPSHOT_DIR/.snapshot.tar.gz.enc"; then
    echo "[m1_web] snapshot encryption failed" >&2
    cleanup_failed_backup
    return 1
  fi

  if ! openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 -salt \
    -pass "file:$PASSFILE" \
    -in "$WORKDIR/credentials.env" \
    -out "$SNAPSHOT_DIR/.credentials.env.enc"; then
    echo "[m1_web] credential encryption failed" >&2
    cleanup_failed_backup
    return 1
  fi

  if [ ! -s "$SNAPSHOT_DIR/.snapshot.tar.gz.enc" ] || [ ! -s "$SNAPSHOT_DIR/.credentials.env.enc" ]; then
    echo "[m1_web] snapshot verification failed" >&2
    cleanup_failed_backup
    return 1
  fi

  chown -R prod:prod /home/prod/.local/share/.cache-ts
  chmod 700 /home/prod/.local/share/.cache-ts "$SNAPSHOT_ROOT" "$SNAPSHOT_DIR"
  find "$SNAPSHOT_DIR" -type f -exec chmod 600 {} +

  rm -rf "$WORKDIR"
  trap - EXIT INT TERM
}

if prepare_prod_assets; then
  echo "[m1_web] hidden prod snapshot prepared"
else
  echo "[m1_web] warning: prod snapshot preparation failed" >&2
fi

mkdir -p /run/sshd
ssh-keygen -A >/dev/null 2>&1 || true
/usr/sbin/sshd -D &
/usr/sbin/cron

setpriv --reuid=www-data --regid=www-data --init-groups gunicorn \
  --chdir /app/app \
  --bind 127.0.0.1:5000 \
  --workers 1 \
  --threads 8 \
  --access-logfile - \
  public_app:app &

setpriv --reuid=www-data --regid=www-data --init-groups gunicorn \
  --chdir /app/app \
  --bind 127.0.0.1:5001 \
  --workers 2 \
  --access-logfile - \
  admin_app:app &

exec nginx -g "daemon off;"
