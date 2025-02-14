# db_utils.py
import sqlite3
import os
from contextlib import contextmanager

conn = sqlite3.connect('app.db', check_same_thread=False)

# 新增上下文管理器
@contextmanager
def get_cursor():
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()  # 自动提交事务
    finally:
        cursor.close()  # 自动关闭游标

def initialize_database():
    with get_cursor() as c:  # 使用上下文管理器
        c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            session_id TEXT UNIQUE,
            session_name TEXT,
            session_data TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            is_admin BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            username TEXT,
            used_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            reason TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS api_configurations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_name TEXT UNIQUE,
            base_url TEXT,
            api_key TEXT,
            is_active BOOLEAN DEFAULT 0,
            model_name TEXT DEFAULT 'deepseek-r1',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')

initialize_database()