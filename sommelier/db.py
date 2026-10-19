"""Хранение истории запросов и подборок в SQLite."""
import json
import sqlite3
from datetime import datetime

import config


def _connect():
    connection = sqlite3.connect(config.DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _init():
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                query TEXT NOT NULL,
                favorite_books TEXT,
                taste TEXT NOT NULL,
                result TEXT NOT NULL
            )
            """
        )


def save_request(query, favorite_books, taste, picks):
    """Сохраняет подборку и возвращает её id."""
    with _connect() as connection:
        cursor = connection.execute(
            "INSERT INTO requests (created_at, query, favorite_books, taste, result)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                datetime.now().replace(microsecond=0).isoformat(sep=" "),
                query,
                favorite_books,
                json.dumps(taste, ensure_ascii=False),
                json.dumps(picks, ensure_ascii=False),
            ),
        )
        return cursor.lastrowid


def get_request(request_id):
    """Подборка по id или None, если запись не найдена."""
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM requests WHERE id = ?", (request_id,)
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "query": row["query"],
        "favorite_books": row["favorite_books"],
        "taste": json.loads(row["taste"]),
        "picks": json.loads(row["result"]),
    }


def recent(limit=None):
    """Список последних запросов для главной страницы (without full result)."""
    limit = limit or config.HISTORY_LIMIT
    with _connect() as connection:
        rows = connection.execute(
            "SELECT id, created_at, query FROM requests"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


_init()