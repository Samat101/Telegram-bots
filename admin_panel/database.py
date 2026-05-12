import sqlite3
from datetime import datetime
from contextlib import contextmanager


@contextmanager
def get_db():
    conn = sqlite3.connect('users.db')
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined TEXT
            )
        ''')
        conn.commit()


def add_user(user_id: int, username: str, first_name: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name, joined)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()


def get_all_users():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, first_name, joined FROM users')
        users = cursor.fetchall()
    return [{'user_id': u[0], 'username': u[1], 'first_name': u[2], 'joined': u[3]} for u in users]


def get_users_count():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
    return count