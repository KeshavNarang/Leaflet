import sqlite3

def init_db(IS_PROD):
    if IS_PROD:
        # Volume at /var/lib/sqlite3db/data
        conn = sqlite3.connect('/var/lib/sqlite3db/data/database.db')
        print("starting")
    else:   
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
            cities TEXT NOT NULL,
            hidden INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def init_db_command(IS_PROD):
    init_db(IS_PROD)
