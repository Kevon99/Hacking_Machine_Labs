#!/bin/sh
set -eu

PASSFILE="/home/prod/.config/.secrets/.passphrase"
ROOT="/home/prod/.local/share/.cache-ts/.snapshots"
CREDFILE=$(find "$ROOT" -type f -name '.credentials.env.enc' 2>/dev/null | sort | tail -n 1)

if [ ! -r "$PASSFILE" ] || [ -z "$CREDFILE" ] || [ ! -r "$CREDFILE" ]; then
    echo "prod-db: no se pudieron leer las credenciales" >&2
    exit 1
fi

umask 077
TMPFILE=$(mktemp)
trap 'rm -f "$TMPFILE"' EXIT INT TERM

openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 \
    -pass "file:$PASSFILE" -in "$CREDFILE" > "$TMPFILE"

set -a
. "$TMPFILE"
set +a

rm -f "$TMPFILE"
trap - EXIT INT TERM

MYSQL_PWD="$DB_ROOT_PASSWORD" exec mysql \
    --skip-ssl \
    -h "$DB_HOST" \
    -P "$DB_PORT" \
    -u "$DB_ROOT_USER" \
    "$DB_NAME" "$@"
