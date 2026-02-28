import datetime
import os

import pymongo
from bson.objectid import ObjectId
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

# load .env file and create the app
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

# connect to MongoDB
client = pymongo.MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("MONGO_DBNAME", "sips")]

# collections 
users_col   = db["users"]
cafes_col   = db["cafes"]
saved_col   = db["saved_places"]
reviews_col = db["reviews"]

# set up flask-login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access that page."
login_manager.login_message_category = "info"


# represents the logged-in user
class User(UserMixin):
    def __init__(self, user_doc):
        self.user_doc = user_doc

    # returns the user's id from MongoDB
    def get_id(self):
        return str(self.user_doc["_id"])

    @property
    def username(self):
        return self.user_doc.get("username", "")

    @property
    def email(self):
        return self.user_doc.get("email", "")
    
    @property
    def role(self):
        return self.user_doc.get("role", "customer")


# called on every request to get the current user from the session
@login_manager.user_loader
def load_user(user_id):
    try:
        doc = users_col.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None
    return User(doc) if doc else None


# --- Splash screen ---
@app.route("/")
def index():
    """
    Route for the index page
    Returns:
        rendered template (str): The rendered HTML template.
    """
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    return render_template("index.html")


# --- Sign up ---
@app.route("/signup", methods=["GET", "POST"])
def signup():
    """
    Route for the signup page
    Returns:
        rendered template (str): The rendered HTML template.
    """
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        error = None
        if not username:
            error = "Username is required."
        elif not email:
            error = "Email is required."
        elif not password:
            error = "Password is required."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        elif users_col.find_one({"email": email}):
            error = "An account with that email already exists."
        elif users_col.find_one({"username": username}):
            error = "That username is already taken."

        if error:
            flash(error, "error")
            return render_template("signup.html", username=username, email=email)

        # save new user to database with hashed password
        new_user = {
            "username": username,
            "email": email,
            "password_hash": generate_password_hash(password),
            "created_at": datetime.datetime.utcnow(),
            "role": None
        }
        result = users_col.insert_one(new_user)
        new_user["_id"] = result.inserted_id

        # log in right after signing up
        login_user(User(new_user))
        flash(f"Welcome to Sips, {username}!", "success")
        return redirect(url_for("select_role"))
    

    return render_template("signup.html")

@app.route("/select-role", methods=["GET", "POST"])
@login_required
def select_role():
    """
    Allow new users to choose if they are a customer or a shop owner.
    """
    if request.method == "POST":
        role = request.form.get("role")

        if role in ["customer", "owner"]:
            users_col.update_one(
                {"_id": ObjectId(current_user.get_id())}, 
                {"$set": {"role": role}}
            )
            flash(f"Account set up as {role.capitalize()}!", "success")
            return redirect(url_for("home"))

    return render_template("select_role.html")

# --- Log in ---
@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Route for the login page
    Returns:
        rendered template (str): The rendered HTML template.
    """
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user_doc = users_col.find_one({"email": email})

        # one generic error 
        if not user_doc or not check_password_hash(user_doc["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html", email=email)

        login_user(User(user_doc))
        flash(f"Welcome back, {user_doc['username']}!", "success")

        # send user back to the page 
        next_page = request.args.get("next")
        return redirect(next_page or url_for("home"))

    return render_template("login.html")


# --- Log out ---
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("index"))


# --- Stub routes ---

@app.route("/home")
@login_required
def home():
    return render_template("home.html")


@app.route("/search")
@login_required
def search():
    return render_template("search.html")


@app.route("/cafe/<cafe_id>")
@login_required
def cafe_detail(cafe_id):
    return render_template("indiv_cafe.html")


@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        username = request.form.get("username")
        phone = request.form.get("phone")
        
        # update username and phone
        update_fields = {
            "username": username,
            "phone": phone
        }
        
        # if shop owner
        if current_user.role == 'owner':
            update_fields["shop_location"] = request.form.get("shop-location")
            update_fields["operation_hours"] = request.form.get("operation-hours")
            
        # update database
        users_col.update_one(
            {"_id": ObjectId(current_user.id)},
            {"$set": update_fields}
        )
        
        flash("Profile updated successfully!", "success")
        return redirect(url_for('settings')) 
    return render_template("profile.html")


@app.route("/saved")
@login_required
def saved_places():
    return render_template("saved_places.html")


# --- Run app ---
if __name__ == "__main__":
    app.run(debug=True, port=5000)