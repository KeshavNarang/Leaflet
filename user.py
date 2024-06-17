from flask_login import UserMixin
import sqlite3
import os

IS_PROD=os.environ.get("IS_PROD") or False

# Validate
if type(IS_PROD)!=bool:
    if IS_PROD.lower()=="true":
        IS_PROD = True
    else:
        IS_PROD = False


def get_db_connection():
    if IS_PROD:
        # Volume at /var/lib/sqlite3db/data
        conn = sqlite3.connect('/var/lib/sqlite3db/data/database.db')
    else:   
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
    def create(title, time_commitment, description, cities, due_date):
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO opportunities (title, time_commitment, description, cities, due_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (title, time_commitment, description, cities, due_date),
        )
        conn.commit()
        conn.close()
    
    @staticmethod
    def get_all():
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT title, time_commitment, description, cities, due_date FROM opportunities")
        opportunities = c.fetchall()
        conn.close()
        return opportunities
    
    @staticmethod
    def get_by_id(opportunity_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM opportunities WHERE id = ?", (opportunity_id,))
        opportunity = cursor.fetchone()
        conn.close()
        return opportunity
        
    @staticmethod
    def get_opportunities_for_user_cities(user_cities, is_admin=False):
        if not user_cities:
            return []

        query = "SELECT * FROM opportunities WHERE ("
        query += " OR ".join(["cities LIKE ?" for _ in range(len(user_cities))]) + ")"
        
        user_cities_with_wildcard = ['%{}%'.format(city) for city in user_cities]
        
        if not is_admin:
            query += " AND hidden = 0"
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, user_cities_with_wildcard)
        opportunities = cursor.fetchall()
        conn.close()

        return opportunities

    @staticmethod
    def hide(opportunity_id):
        conn = get_db_connection()
        conn.execute(
            "UPDATE opportunities SET hidden = 1 WHERE id = ?",
            (opportunity_id,)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def remove(opportunity_id):
        conn = get_db_connection()
        conn.execute(
            "DELETE FROM opportunities WHERE id = ?",
            (opportunity_id,)
        )
        conn.commit()
        conn.close()
    
    @staticmethod
    def toggle_visibility(opportunity_id, hide=True):
        conn = get_db_connection()
        if hide:
            conn.execute("UPDATE opportunities SET hidden = 1 WHERE id = ?", (opportunity_id,))
        else:
            conn.execute("UPDATE opportunities SET hidden = 0 WHERE id = ?", (opportunity_id,))
        conn.commit()
        conn.close()
    
    @staticmethod
    def update(opportunity_id, title, time_commitment, description, cities, due_date):
        conn = get_db_connection()
        conn.execute(
            "UPDATE opportunities SET title = ?, time_commitment = ?, description = ?, cities = ?, due_date = ? WHERE id = ?",
            (title, time_commitment, description, cities, due_date, opportunity_id)
        )
        conn.commit()
        conn.close()