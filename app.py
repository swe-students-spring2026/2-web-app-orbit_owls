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
    cafes = list(cafes_col.find())

    selected_cafe = None
    selected_id = request.args.get("selected")

    if selected_id:
        try:
            selected_cafe = cafes_col.find_one({"_id": ObjectId(selected_id)})
        except Exception:
            selected_cafe = None
    return render_template("home.html", cafes=cafes, selected_cafe=selected_cafe)


@app.route("/search", methods=["GET"])
@login_required
def search():
    query = request.args.get("q")
    cafes = []

    if query:
        cafes = list(db.cafes.find({
            "name": {"$regex": query, "$options": "i"}
        }))

    return render_template("search.html", cafes=cafes)

# Cafe Indiv Pages
@app.route("/cafe/<cafe_id>")
@login_required
def cafe_detail(cafe_id):
    try: 
        cafe= cafes_col.find_one({"_id": ObjectId(cafe_id)})
    except Exception:
        flash("Invalid cafe link.", "error")
        return redirect(url_for("home"))

    if not cafe:
        flash("Cafe not found.", "error")
        return redirect(url_for("home"))
    reviews= list(reviews_col.find({"cafe_id": cafe["_id"]}))

    for r in reviews:
        r["user_id_str"]= str(r.get("user_id"))

    current_user_id = str(current_user.get_id())
    return render_template(
        "indiv-cafe-screen.html",
        cafe=cafe, 
        reviews=reviews,
        current_user_id=current_user_id
    )

#Posting reviews
@app.route("/cafe/<cafe_id>/review", methods=["POST"])
@login_required
def add_review(cafe_id):
    try:
        cafe_obj_id= ObjectId(cafe_id)
    except Exception:
        flash("Invalid cafe link.","error")
        return redirect(url_for("home"))

    cafe= cafes_col.find_one({"_id": cafe_obj_id})
    if not cafe:
        flash("Cafe not found.", "error")
        return redirect(url_for("home"))

    rating_str= request.form.get("rating", "").strip()
    text= request.form.get("text", "").strip()

    if not rating_str.isdigit():
        flash("Rating must be a number from 1 to 5.", "error")
        return redirect(url_for("cafe_detail", cafe_id=cafe_id))

    rating = int(rating_str)
    if rating < 1 or rating > 5:
        flash("Rating must be between 1 and 5.", "error")
        return redirect(url_for("cafe_detail", cafe_id=cafe_id))

    if not text:
        flash("Review text cannot be empty.", "error")
        return redirect(url_for("cafe_detail", cafe_id=cafe_id))

    reviews_col.insert_one({
        "cafe_id": cafe_obj_id,
        "user_id": ObjectId(current_user.get_id()),
        "username": current_user.username,
        "rating": rating,
        "text": text,
        "created_at": datetime.datetime.utcnow()
    })

    flash("Review posted!", "success")
    return redirect(url_for("cafe_detail", cafe_id=cafe_id))

#Deleting reviews 
@app.route("/review/<review_id>/delete", methods=["POST"])
@login_required
def delete_review(review_id):
    try:
        rid= ObjectId(review_id)
    except Exception:
        flash("Invalid review.", "error")
        return redirect(url_for("home"))

    review= reviews_col.find_one({"_id":rid})
    if not review:
        flash("Review not found.", "error")
        return redirect(url_for("home"))

    # Only author can delete
    if str(review.get("user_id")) != str(current_user.get_id()):
        flash("You can only delete your own review.", "error")
        return redirect(url_for("cafe_detail", cafe_id=str(review["cafe_id"])))

    reviews_col.delete_one({"_id":rid})
    flash("Review deleted.", "success")
    return redirect(url_for("cafe_detail", cafe_id=str(review["cafe_id"])))

#Edit reviews 
@app.route("/review/<review_id>/edit", methods=["POST"])
@login_required
def edit_review(review_id):
    try:
        rid= ObjectId(review_id)
    except Exception:
        flash("Invalid review.", "error")
        return redirect(url_for("home"))

    review = reviews_col.find_one({"_id":rid})
    if not review:
        flash("Review not found.", "error")
        return redirect(url_for("home"))

    #Only author can make edits
    if str(review.get("user_id"))!= str(current_user.get_id()):
        flash("You can only edit your own review.", "error")
        return redirect(url_for("cafe_detail", cafe_id=str(review["cafe_id"])))

    #Get new values 
    rating_str= request.form.get("rating", "").strip()
    text= request.form.get("text", "").strip()

    # Validate rating
    if not rating_str.isdigit():
        flash("Rating must be a number 1–5.", "error")
        return redirect(url_for("cafe_detail", cafe_id=str(review["cafe_id"])))
    rating = int(rating_str)
    if rating < 1 or rating > 5:
        flash("Rating must be between 1 and 5.", "error")
        return redirect(url_for("cafe_detail", cafe_id=str(review["cafe_id"])))
    if not text:
        flash("Review text cannot be empty.", "error")
        return redirect(url_for("cafe_detail", cafe_id=str(review["cafe_id"])))

    # Update 
    reviews_col.update_one(
        {"_id": rid},
        {"$set": {"rating": rating, "text": text}}
    )

    flash("Review updated.", "success")
    return redirect(url_for("cafe_detail", cafe_id=str(review["cafe_id"])))


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
            {"_id": ObjectId(current_user.get_id())},
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