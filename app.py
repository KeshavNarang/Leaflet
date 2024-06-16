import json
import os
import sqlite3
import requests
from flask import Flask, redirect, request, url_for, render_template_string, render_template
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from oauthlib.oauth2 import WebApplicationClient
from wtforms import Form, RadioField, StringField, SelectField, SelectMultipleField, widgets, validators
from flask_wtf import FlaskForm
from db import init_db_command
from user import User, Opportunity
from config import ADMIN_EMAILS

# Configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

# Flask app setup
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)

# User session management setup
login_manager = LoginManager()
login_manager.init_app(app)

# Naive database setup
try:
    init_db_command()
except sqlite3.OperationalError:
    pass

# OAuth 2 client setup
client = WebApplicationClient(GOOGLE_CLIENT_ID)

# Flask-Login helper to retrieve a user from our db
@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

@app.route("/")
def index():
    if current_user.is_authenticated:
        city = current_user.city or "Palo Alto"
        admin_buttons = '' if current_user.email not in ADMIN_EMAILS else '<a class="button" href="/create_opportunity">Create Opportunity</a>'
        return (
            f"<p>Hello, {current_user.name}! You're logged in! Email: {current_user.email}</p>"
            f"<div><p>City: {city}</p></div>"
            f'<a class="button" href="/logout">Logout</a> | '
            f'<a class="button" href="/change_city">Change City</a> | '
            f'{admin_buttons}'
        )
    else:
        return '<a class="button" href="/login">Google Login</a>'

def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()

@app.route("/login")
def login():
    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]

    # print(authorization_endpoint)
    # print(request.base_url)

    newurl=request.base_url
    newurl=newurl.replace("http", "https", 1)

    print(newurl)

    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=newurl + "/callback",
        scope=["openid", "email", "profile"],
    )
    return redirect(request_uri)

@app.route("/login/callback")
def callback():
    print("HERE")
    code = request.args.get("code")
    google_provider_cfg = get_google_provider_cfg()
    token_endpoint = google_provider_cfg["token_endpoint"]

    newurl=request.base_url
    newurl=newurl.replace("http", "https", 1)

    print(newurl)
    try:
        token_url, headers, body = client.prepare_token_request(
            token_endpoint,
            authorization_response=request.url,
            redirect_url=newurl,
            code=code
        )
        token_response = requests.post(
            token_url,
            headers=headers,
            data=body,
            auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
        )
    except Exception as e:
        return render_template_string(f"<div>{e}<div>")

    print("103")
    print(token_response)
    client.parse_request_body_response(json.dumps(token_response.json()))
    print("106")

    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]

    print("110")

    uri, headers, body = client.add_token(userinfo_endpoint)

    print("114")
    print(uri)
    print(headers)
    print(body)


    userinfo_response = requests.get(uri, headers=headers, data=body)

    print("122")
    print(userinfo_response)

    if userinfo_response.json().get("email_verified"):
        unique_id = userinfo_response.json()["sub"]
        users_email = userinfo_response.json()["email"]
        users_name = userinfo_response.json()["given_name"]
    else:
        return "User email not available or not verified by Google.", 400
    
    user = User.get(unique_id)
    if not user:
        default_city = "All" if users_email in ADMIN_EMAILS else None
        User.create(unique_id, users_name, users_email, default_city)
        user = User(unique_id, users_name, users_email, default_city)
    
    login_user(user)

    if current_user.city is None and current_user.email not in ADMIN_EMAILS:
        return redirect(url_for("collect_city"))
    return redirect(url_for("index"))

# Generate city selection form
def generate_city_form():
    class CityForm(FlaskForm):
        cities = [(city, city) for city in ['Palo Alto', 'Fremont', 'San Jose', 'Burlingame']]
        city = SelectMultipleField('City', choices=cities, option_widget=widgets.CheckboxInput(), coerce=str)
    return CityForm()

def render_city_template(form):
    return render_template("city_form.html", form=form)

@app.route("/collect_city", methods=["GET", "POST"])
@login_required
def collect_city():
    form = generate_city_form()
    if form.validate_on_submit():
        user = current_user
        selected_cities = ', '.join(form.city.data)
        User.update_city(user.id, selected_cities)
        return redirect(url_for("index"))

    return render_city_template(form)

@app.route("/change_city", methods=["GET", "POST"])
@login_required
def change_city():
    form = generate_city_form()
    if form.validate_on_submit():
        user = current_user
        selected_cities = ', '.join(form.city.data)
        User.update_city(user.id, selected_cities)
        return redirect(url_for("index"))

    return render_city_template(form)

@app.route("/create_opportunity", methods=["GET", "POST"])
@login_required
def create_opportunity():
    if current_user.email not in ADMIN_EMAILS:
        return redirect(url_for("index"))

    class OpportunityForm(FlaskForm):
        title = StringField('Title', [validators.InputRequired()])
        time_commitment = RadioField('Time Commitment', choices=[("Short", "Short"), ("Medium", "Medium"), ("Long", "Long")], validators=[validators.InputRequired()])
        description = StringField('Description', [validators.InputRequired()])
        cities = SelectMultipleField('City', choices=[("Palo Alto", "Palo Alto"), ("Fremont", "Fremont"), ("San Jose", "San Jose"), ("Burlingame", "Burlingame")], option_widget=widgets.CheckboxInput(), coerce=str)

    form = OpportunityForm()
    if form.validate_on_submit():
        title = form.title.data
        time_commitment = form.time_commitment.data
        description = form.description.data
        cities = ', '.join(form.cities.data)
        Opportunity.create(title, time_commitment, description, cities)
        return redirect(url_for("index"))

    return render_template("create_opportunity.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

if __name__ == "__main__":
    # app.run(port=os.getenv("PORT", default=5000))
    app.run(port=os.getenv("PORT", default=5000), debug=True)
    #ssl_context="adhoc"
    #port=os.getenv("PORT", default=5000)
