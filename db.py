"""Viestien tallennus MariaDB:hen tai testeissä muistiin."""

import os
import threading

import pymysql

DatabaseError = pymysql.MySQLError

_memory = {}
_lock = threading.Lock()


def _use_mysql():
    return bool(os.environ.get("DB_NAME"))


def _connect():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )


def save_message(session_id, role, content):
    if not _use_mysql():
        with _lock:
            _memory.setdefault(session_id, []).append(
                {"role": role, "content": content}
            )
        return

    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)",
            (session_id, role, content),
        )


def get_history(session_id, limit=10):
    if not _use_mysql():
        with _lock:
            return list(_memory.get(session_id, []))[-limit:]

    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT role, content FROM (
                SELECT id, role, content FROM messages
                WHERE session_id = %s ORDER BY id DESC LIMIT %s
            ) AS recent ORDER BY id ASC
            """,
            (session_id, limit),
        )
        return list(cursor.fetchall())


def delete_history(session_id):
    if not _use_mysql():
        with _lock:
            _memory.pop(session_id, None)
        return

    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM messages WHERE session_id = %s",
            (session_id,),
        )


def check_connection():
    if _use_mysql():
        with _connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
