import sqlite3

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            city TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            time_commitment TEXT NOT NULL,
            description TEXT NOT NULL,
            cities TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def init_db_command():
    init_db()
