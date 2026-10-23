#!/bin/sh
set -eu

ROOT="/home/prod/.local/share/.cache-ts/.snapshots"
PASSFILE="/home/prod/.config/.secrets/.passphrase"

LATEST=$(find "$ROOT" -type f -name '.snapshot.tar.gz.enc' 2>/dev/null | sort | tail -n 1)

if [ -z "$LATEST" ]; then
    echo "prod-backup: no hay snapshots disponibles" >&2
    exit 1
fi

echo "Snapshot: $LATEST"
echo "Contenido:"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 \
    -pass "file:$PASSFILE" -in "$LATEST" | tar tzf -
