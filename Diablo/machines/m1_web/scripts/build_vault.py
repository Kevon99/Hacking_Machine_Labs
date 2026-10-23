#!/usr/local/bin/python3
import hashlib
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

db_path = Path(sys.argv[1])
passphrase_path = Path(sys.argv[2])

passphrase = passphrase_path.read_text(encoding="utf-8").strip()
root_password = os.environ["ROOT_PASSWORD"]
admin_password = os.environ["ADMIN_PASSWORD"]
iterations = 200000

conn = sqlite3.connect(db_path)
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS credentials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL,
        algorithm TEXT NOT NULL,
        iterations INTEGER NOT NULL,
        salt TEXT NOT NULL,
        hash TEXT NOT NULL,
        pepper_source TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """
)
conn.execute(
    """
    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """
)

created_at = datetime.now(timezone.utc).isoformat()
entries = [
    ("root", "database-root", root_password),
    ("db_admin", "database-admin", admin_password),
]

for username, role, password in entries:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        (salt + passphrase).encode("utf-8"),
        iterations,
    ).hex()
    conn.execute(
        """
        INSERT INTO credentials
            (username, role, algorithm, iterations, salt, hash, pepper_source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            role = excluded.role,
            algorithm = excluded.algorithm,
            iterations = excluded.iterations,
            salt = excluded.salt,
            hash = excluded.hash,
            pepper_source = excluded.pepper_source,
            created_at = excluded.created_at
        """,
        (
            username,
            role,
            "pbkdf2_sha256",
            iterations,
            salt,
            digest,
            ".passphrase",
            created_at,
        ),
    )

conn.execute(
    "INSERT INTO metadata (key, value) VALUES (?, ?) "
    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
    ("created_at", created_at),
)
conn.execute(
    "INSERT INTO metadata (key, value) VALUES (?, ?) "
    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
    ("source", "corp_db"),
)
conn.commit()
conn.close()
