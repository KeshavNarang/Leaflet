import json
import os
import sqlite3
import requests
from flask import Flask, redirect, request, url_for, render_template_string, render_template, abort, g
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from oauthlib.oauth2 import WebApplicationClient
from wtforms import Form, RadioField, StringField, BooleanField, SelectField, DateTimeField, SelectMultipleField, widgets, validators
from flask_wtf import FlaskForm
from db import init_db_command
from user import User, Opportunity
from config import ADMIN_EMAILS, OWNER_EMAILS
from datetime import datetime, timedelta
import base64
import gspread
from oauth2client.service_account import ServiceAccountCredentials

IS_PROD=os.environ.get("IS_PROD") or False

# Validate
if type(IS_PROD)!=bool:
    if IS_PROD.lower()=="true":
        IS_PROD = True
    else:
        IS_PROD = False

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
init_db_command(IS_PROD)

# OAuth 2 client setup
client = WebApplicationClient(GOOGLE_CLIENT_ID)

# Define the scope of access (read/write)
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# Path to the JSON file with credentials
# credentials_path = 'credentials.json'

# Load credentials from the JSON key file
# credentials = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)

# Get the Base64-encoded credentials from an environment variable
encoded_credentials = os.getenv("GOOGLE_CREDENTIALS_BASE_64")

# Decode and load the credentials
if encoded_credentials:
    credentials_info = json.loads(base64.b64decode(encoded_credentials))
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_info, scope)
    gc = gspread.authorize(credentials)
else:
    raise ValueError("Missing GOOGLE_CREDENTIALS_BASE64 environment variable")

# Authorize with Google Sheets API
gc = gspread.authorize(credentials)

spreadsheet_url = 'https://docs.google.com/spreadsheets/d/1boIqyXxDDv3ism27rnK9hKtqDV1JmwO8U92mTqL-2hY/'
sh = gc.open_by_url(spreadsheet_url)

# Select a worksheet
worksheet = sh.worksheet("Form Responses 2")

# Get all the values in the worksheet
data = worksheet.get_all_values()

# Initialize the list for owner emails
OWNER_EMAILS = []

# Iterate over the rows starting from the second row (index 1) since the first row is the header
for row in data[1:]:
    # Check if the fourth column is "Yes"
    if row[3].strip().lower() == "yes":
        # Add the value in the second column to the list
        OWNER_EMAILS.append(row[1].strip())

# Get all values from the worksheet
values = worksheet.get_all_values()

spreadsheet_url = 'https://docs.google.com/spreadsheets/d/1WCDdY0UU02dWUl5nxWnXz816l3sJCMRj5bE8dwooC7Y/'
sh = gc.open_by_url(spreadsheet_url)

# Select a worksheet
worksheet = sh.worksheet("Form Responses 5")

# Get all values from the worksheet
values = worksheet.get_all_values()

# Flask-Login helper to retrieve a user from our db
@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

@app.before_request
def before_request():
    g.user = current_user

@app.route("/")
def index():
    opportunities = []
    if current_user.is_authenticated:
        user_cities = [city.strip() for city in current_user.city.split(',')] if current_user.city else []
        is_admin = current_user.email in ADMIN_EMAILS
        opportunities = Opportunity.get_opportunities_for_user_cities(user_cities, is_admin)
        opportunities.sort(key=lambda x: x['due_date'])

        opportunities_with_dates = [
            (opportunity, datetime.strptime(opportunity['due_date'], '%Y-%m-%d %H:%M').strftime('%B %d, %Y'))
            for opportunity in opportunities
        ]

        current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M')
        return render_template("index.html", opportunities=opportunities, opportunities_with_dates=opportunities_with_dates, current_datetime=current_datetime, ADMIN_EMAILS=ADMIN_EMAILS, OWNER_EMAILS=OWNER_EMAILS, len=len)
    else:
        return render_template("login.html")
def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()

@app.route("/login")
def login():
    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]
    
    redirect_uri = request.base_url
    if redirect_uri.startswith("http:"):
        redirect_uri = redirect_uri.replace("http", "https", 1)

    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=redirect_uri + "/callback",
        scope=["openid", "email", "profile"],
    )

    return redirect(request_uri)

@app.route("/login/callback")
def callback():
    code = request.args.get("code")
    error = request.args.get("error")
    
    if error:
        return redirect(url_for("login"))  # Redirect back to login if there was an error
    
    if not code:
        return redirect(url_for("login"))  # Redirect back to login if code is None
        
    google_provider_cfg = get_google_provider_cfg()
    token_endpoint = google_provider_cfg["token_endpoint"]
    
    authorization_response = request.url
    if authorization_response.startswith("http:"):
        authorization_response = authorization_response.replace("http", "https", 1)

    redirect_url = request.base_url
    if redirect_url.startswith("http:"):
        redirect_url = redirect_url.replace("http", "https", 1)

    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=authorization_response,
        redirect_url=redirect_url,
        code=code
    )

    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
    )

    client.parse_request_body_response(json.dumps(token_response.json()))

    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]

    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)

    if userinfo_response.json().get("email_verified"):
        unique_id = userinfo_response.json()["sub"]
        users_email = userinfo_response.json()["email"]
        users_name = userinfo_response.json()["given_name"]
    else:
        return "User email not available or not verified by Google.", 400
    
    is_valid_user = False
    user_email = userinfo_response.json()["email"]
    emails = worksheet.col_values(2)  # Assuming emails are in the second column

    if user_email in emails:
        is_valid_user = True
    
    if not is_valid_user:
        return redirect(url_for("fill_out_form"))  # Redirect to fill out form if not

    # Get the index of the user email in the spreadsheet
    user_index = emails.index(user_email) + 1  # +1 to account for the header row

    # Read the name and county from the spreadsheet
    users_name = worksheet.cell(user_index, 3).value  # Assuming names are in the third column
    user_county = worksheet.cell(user_index, 4).value  # Assuming counties are in the fourth column

    user = User.get(unique_id)
    if not user:
        # default_city = "Santa Clara" if users_email in ADMIN_EMAILS else None
        User.create(unique_id, users_name, users_email, user_county)
        user = User(unique_id, users_name, users_email, user_county)
    
    login_user(user)

    if current_user.city is None and current_user.email not in ADMIN_EMAILS:
        return redirect(url_for("collect_city"))
    return redirect(url_for("index"))

# @app.errorhandler(404)
# def page_not_found(e):
#     return render_template('error.html', error_code=404, error_message="Page Not Found"), 404

# @app.errorhandler(500)
# def internal_server_error(e):
#     return render_template('error.html', error_code=500, error_message="Internal Server Error"), 500

# @app.errorhandler(Exception)
# def handle_exception(e):
#     return render_template('error.html', error_code=500, error_message="An unexpected error occurred"), 500

@app.route("/fill_out_form")
def fill_out_form():
    return render_template('signup.html')

@app.route("/users")
@login_required
def view_users():
    if current_user.email not in ADMIN_EMAILS:
        abort(403)  # Forbidden if not an admin

    users = User.get_all()
    return render_template("users.html", users=users)

@app.route("/edit_users", methods=["GET", "POST"])
@login_required
def edit_users():
    if current_user.email not in ADMIN_EMAILS:
        abort(403)  # Forbidden if not an owner

    users = User.get_all()  # Fetch all users from database
    return render_template("edit_users.html", users=users)

@app.route("/edit_city/<string:user_id>", methods=["GET", "POST"])
@login_required
def edit_city(user_id):
    if current_user.email not in ADMIN_EMAILS:
        abort(403)  # Forbidden if not an owner

    user = User.get(user_id)
    if not user:
        abort(404)  # User not found

    form = generate_city_form()
    if form.validate_on_submit():
        selected_cities = ', '.join(form.city.data)
        User.update_city(user_id, selected_cities)
        return redirect(url_for("edit_users"))

    return render_city_template(form)

@app.route("/delete_user/<string:user_id>", methods=["GET", "POST"])
@login_required
def delete_user(user_id):
    if current_user.email not in ADMIN_EMAILS:
        abort(403)  # Forbidden if not an owner

    User.remove(user_id)
    return redirect(url_for("edit_users"))

@app.route('/resources')
@login_required
def resources():
    opportunities = Opportunity.get_all()  # Fetch opportunities from your data source
    return render_template('resources.html', opportunities=opportunities, ADMIN_EMAILS=ADMIN_EMAILS)

@app.route('/calendar')
@login_required
def calendar():
    opportunities = Opportunity.get_all()  # Fetch opportunities from your data source
    return render_template('calendar.html', opportunities=opportunities)

# Generate city selection form
def generate_city_form():
    class CityForm(FlaskForm):
        cities = [(city, city) for city in ['Santa Clara', 'San Mateo']]
        city = SelectMultipleField('City', choices=cities, option_widget=widgets.CheckboxInput(), coerce=str)
    return CityForm()

def render_city_template(form):
    return render_template("city_form.html", form=form)

@app.route("/status",methods=["GET"])
def show_status():
    if IS_PROD:
        return render_template_string("<div>Status: Production</div>")
    else:
        return render_template_string("<div>Status: Local</div>")

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

@app.route("/opportunity/<int:opportunity_id>")
def view_opportunity(opportunity_id):
    opportunity = Opportunity.get_by_id(opportunity_id)
    if not opportunity:
        abort(404)

    formatted_date = datetime.strptime(opportunity['due_date'], '%Y-%m-%d %H:%M').strftime('%B %d, %Y')
    return render_template("view_opportunity.html", opportunity=opportunity, formatted_date=formatted_date, ADMIN_EMAILS=ADMIN_EMAILS)

@app.route("/editor", methods=['GET', 'POST'])
def editor():
    if current_user.email not in ADMIN_EMAILS:
        return redirect(url_for("index"))
    
    if request.method == 'POST':
        new_content = request.form['description']
        # Save the new content to the database or file
        with open('templates/resources_content.html', 'w') as file:
            file.write(new_content)
        return redirect(url_for('resources'))
    
    # Load current content
    with open('templates/resources_content.html', 'r') as file:
        current_content = file.read()
    
    class WYSIWYG(FlaskForm):
        description = StringField('Description', [validators.InputRequired()])

    form = WYSIWYG()
    if form.validate_on_submit():
        description = form.description.data

    return render_template('edit_resources.html', content=current_content, form=form)

@app.route("/edit_resources")
def edit_resources():
    if current_user.email not in ADMIN_EMAILS:
        return redirect(url_for("index"))
    return render_template('edit_resources.html')

@app.route("/opportunity/<int:opportunity_id>/edit", methods=["GET", "POST"])
@login_required
def edit_opportunity(opportunity_id):
    # if current_user.email not in ADMIN_EMAILS:
    #     return redirect(url_for("index"))

    opportunity = Opportunity.get_by_id(opportunity_id)
    if not opportunity:
        abort(404)

    class EditOpportunityForm(FlaskForm):
        title = StringField('Title', [validators.InputRequired()], default=opportunity['title'])
        time_commitment = RadioField('Time Commitment', choices=[("Short", "Short"), ("Medium", "Medium"), ("Long", "Long")], validators=[validators.InputRequired()], default=opportunity['time_commitment'])
        description = StringField('Description', [validators.InputRequired()], default=opportunity['description'])
        cities = SelectMultipleField('City', choices=[("Santa Clara", "Santa Clara"), ("San Mateo", "San Mateo")], option_widget=widgets.CheckboxInput(), coerce=str, default=opportunity['cities'].split(', '))
        due_date = StringField('Due Date', [validators.InputRequired()], default=opportunity['due_date'])
    
    form = EditOpportunityForm()
    if form.validate_on_submit():
        title = form.title.data
        time_commitment = form.time_commitment.data
        description = form.description.data
        cities = ', '.join(form.cities.data)
        due_date = form.due_date.data
        # Update the opportunity
        Opportunity.update(opportunity_id, title, time_commitment, description, cities, due_date)
        return redirect(url_for("index"))

    return render_template("edit_opportunity.html", form=form)

@app.route("/create_opportunity", methods=["GET", "POST"])
@login_required
def create_opportunity():
    # if current_user.email not in ADMIN_EMAILS:
    #     return redirect(url_for("index"))

    class OpportunityForm(FlaskForm):
        title = StringField('Title', [validators.InputRequired()])
        time_commitment = RadioField('Time Commitment', choices=[("Short", "Short"), ("Medium", "Medium"), ("Long", "Long")], validators=[validators.InputRequired()])
        description = StringField('Description', [validators.InputRequired()])
        cities = SelectMultipleField('City', choices=[("Santa Clara", "Santa Clara"), ("San Mateo", "San Mateo")], option_widget=widgets.CheckboxInput(), coerce=str)
        due_date = StringField('Due Date', [validators.InputRequired()]) 
        recurring = BooleanField('Recurring Weekly')
        end_date = StringField('End Date', validators=[validators.Optional()])

    form = OpportunityForm()
    if form.validate_on_submit():
        title = form.title.data
        time_commitment = form.time_commitment.data
        description = form.description.data
        cities = ', '.join(form.cities.data)
        due_date = form.due_date.data
        recurring = form.recurring.data
        end_date = form.end_date.data
        
        # Convert string dates to datetime objects
        due_date_dt = datetime.strptime(due_date, '%Y-%m-%d %H:%M')
        end_date_dt = datetime.strptime(end_date, '%Y-%m-%d %H:%M') if end_date else None

        # If recurrence is enabled, create multiple opportunities
        if recurring and end_date_dt:
            while due_date_dt <= end_date_dt:
                Opportunity.create(title, time_commitment, description, cities, due_date_dt.strftime('%Y-%m-%d %H:%M'))
                due_date_dt += timedelta(weeks=1)  # Move to the next week
        else:
            Opportunity.create(title, time_commitment, description, cities, due_date)

        return redirect(url_for("index"))

    return render_template("create_opportunity.html", form=form)


@app.route("/hide_opportunity/<int:opportunity_id>")
@login_required
def hide_opportunity(opportunity_id):
    if current_user.email not in ADMIN_EMAILS:
        return redirect(url_for("index"))
    Opportunity.hide(opportunity_id)
    return redirect(url_for("index"))

@app.route("/remove_opportunity/<int:opportunity_id>")
@login_required
def remove_opportunity(opportunity_id):
    if current_user.email not in ADMIN_EMAILS:
        return redirect(url_for("index"))
    Opportunity.remove(opportunity_id)
    return redirect(url_for("index"))

@app.route("/toggle_opportunity/<int:opportunity_id>")
@login_required
def toggle_opportunity(opportunity_id):
    if current_user.email not in ADMIN_EMAILS:
        return redirect(url_for("index"))
    
    # Determine current hidden status
    opportunity = Opportunity.get_by_id(opportunity_id)
    if opportunity is None:
        return redirect(url_for("index"))

    hidden = opportunity['hidden'] if opportunity else None
    Opportunity.toggle_visibility(opportunity_id, hide=not hidden)
    return redirect(url_for("index"))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

if __name__ == "__main__":
    if IS_PROD:
        app.run(port=os.getenv("PORT", default=5000), debug=True)
    else:
        # For Local:
        app.run(ssl_context="adhoc", port=os.getenv("PORT", default=5000), debug=True)
