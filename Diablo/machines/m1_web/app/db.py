import os

import pymysql


def connect():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "m1_db"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "db_admin"),
        password=os.environ.get("DB_PASSWORD", "SuperSecretDBPass123!"),
        database=os.environ.get("DB_NAME", "corp_db"),
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=90,
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
