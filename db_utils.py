# db_utils.py
import sqlite3
import os

conn = sqlite3.connect('app.db', check_same_thread=False)
c = conn.cursor()

def initialize_database():
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

    conn.commit()

initialize_database()
