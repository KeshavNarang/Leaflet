from flask_login import UserMixin
import sqlite3

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

class User(UserMixin):
    def __init__(self, id_, name, email, city):
        self.id = id_
        self.name = name
        self.email = email
        self.city = city

    @staticmethod
    def get(user_id):
        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM user WHERE id = ?", (user_id,)
        ).fetchone()
        conn.close()
        if not user:
            return None

        return User(
            id_=user['id'], name=user['name'], email=user['email'], city=user['city']
        )

    @staticmethod
    def create(id_, name, email, city):
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO user (id, name, email, city) "
            "VALUES (?, ?, ?, ?)",
            (id_, name, email, city),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def update_city(user_id, city):
        conn = get_db_connection()
        conn.execute(
            "UPDATE user SET city = ? WHERE id = ?",
            (city, user_id)
        )
        conn.commit()
        conn.close()

class Opportunity:
    @staticmethod
    def create(title, time_commitment, description, cities):
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO opportunities (title, time_commitment, description, cities) "
            "VALUES (?, ?, ?, ?)",
            (title, time_commitment, description, cities),
        )
        conn.commit()
        conn.close()