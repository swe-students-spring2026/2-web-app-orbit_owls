import datetime
import os
import re

import pymongo
from bson.objectid import ObjectId
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash
from pymongo import ASCENDING,DESCENDING
from zoneinfo import ZoneInfo
from datetime import timedelta

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
checkins_col= db["checkins"]

#Helper to update ratings
def update_cafe_rating(cafe_id):
    reviews=list(reviews_col.find({"cafe_id": cafe_id}))

    if not reviews:
        cafes_col.update_one(
            {"_id": cafe_id},
            {"$set": {"rating": 0}}
        )
        return
    total= sum(r["rating"] for r in reviews)
    average= round(total / len(reviews), 1)
    cafes_col.update_one(
        {"_id": cafe_id},
        {"$set": {"rating": average}}
    )
#Helper function to extract times 
def hours_list_from_range(hours_value):
    if isinstance(hours_value, dict):
        ny_tz= ZoneInfo("America/New_York")
        today_key= datetime.datetime.now(ny_tz).strftime("%a").lower() 
        hours_str= (hours_value.get(today_key) or "").strip()
    else:
        hours_str=(hours_value or "").strip()

    if not hours_str or "closed" in hours_str.lower():
        return []
    parts= re.split(r"\s*[–—-]\s*", hours_str)
    
    def parse_time(t):
        m= re.search(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)", t, re.I)
        if not m:
            return None
        h= int(m.group(1))
        ampm= m.group(3).upper()
        if ampm== "PM" and h!= 12:
            h+= 12
        if ampm== "AM" and h== 12:
            h= 0
        return h
    start= parse_time(parts[0])
    end= parse_time(parts[1])
    return list(range(start, end + 1))

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
            if role == "owner":
            
                existing_cafe = cafes_col.find_one({"owner_id": ObjectId(current_user.get_id())})
                if not existing_cafe:
                    new_cafe = {
                        "owner_id": ObjectId(current_user.get_id()), 
                        "name": "My New Cafe", 
                        "address": "Please update your address",
                        "price_range": "$$",
                        "operation_hours": {day: "Closed" for day in ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']},
                        "amenities": [],
                        "popular": [],
                        "photos": [],
                        "created_at": datetime.datetime.utcnow()
                    }
                    cafes_col.insert_one(new_cafe)
            flash(f"Account set up as {role.capitalize()}!", "success")

            if role == "owner":
                return redirect(url_for("profile"))
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

    grouped = {}
    for cafe in cafes:
        address = cafe.get("address", "")
        parts = address.split()
        zip_code = parts[-1] if parts else "Other"
        if zip_code not in grouped:
            grouped[zip_code] = []
        grouped[zip_code].append(cafe)

    return render_template("home.html", grouped=grouped, selected_cafe=selected_cafe)


@app.route("/search", methods=["GET"])
@login_required
def search():
    query = request.args.get("q")
    min_rating = request.args.get("min_rating")
    price = request.args.get("price_range")
    sort_by = request.args.get("sort_by")

    filters = {}

    #normal search 
    if query:
        filters["name"] = {"$regex": query, "$options": "i"}

    # rating filter 
    if min_rating:
        filters["rating"] = {"$gte": float(min_rating)}

    # price filter
    if price:
        filters["price_range"] = price

    cafes_query = db.cafes.find(filters)

    # sort
    if sort_by == "rating_desc":
        cafes_query = cafes_query.sort("rating", DESCENDING)
    elif sort_by == "rating_asc":
        cafes_query = cafes_query.sort("rating", ASCENDING)
    elif sort_by == "name_asc":
        cafes_query = cafes_query.sort("name", ASCENDING)
    elif sort_by == "name_desc":
        cafes_query = cafes_query.sort("name", DESCENDING)
    elif sort_by == "price_asc":
        cafes_query = cafes_query.sort("price_range", ASCENDING)
    elif sort_by == "price_desc":
        cafes_query = cafes_query.sort("price_range", DESCENDING)

    cafes = list(cafes_query)

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
    
    since= datetime.datetime.utcnow() - timedelta(days=30)
    checkins= list(checkins_col.find({
        "cafe_id": cafe["_id"],
        "created_at": {"$gte": since}
    }))
    ny_tz= ZoneInfo("America/New_York")
    utc_tz= ZoneInfo("UTC")
    today_key = datetime.datetime.now(ny_tz).strftime("%a").lower()  # mon/tue/...
    #Formatting
    hours_val= cafe.get("hours", "")
    if isinstance(hours_val, dict):
        today_hours= (hours_val.get(today_key) or "").strip()
    else:
        today_hours= (hours_val or "").strip()
    if not today_hours:
        today_hours= "Not listed"
    hour_counts= {}
    #Convert to NY
    for c in checkins:
        utc_time= c["created_at"].replace(tzinfo=utc_tz)
        ny_time= utc_time.astimezone(ny_tz)
        hr= ny_time.hour
        hour_counts[hr]= hour_counts.get(hr, 0) + 1

    hours= hours_list_from_range(cafe.get("hours", ""))
    hours= hours[::2] #List every two hours 
    peak_times= [{"hour": hr, "count": hour_counts.get(hr, 0)} for hr in hours]
    max_count= max((p["count"] for p in peak_times), default=0)

    reviews= list(reviews_col.find({"cafe_id": cafe["_id"]}))
    for r in reviews:
        r["user_id_str"]= str(r.get("user_id"))
    current_user_id= str(current_user.get_id())

    return render_template(
        "indiv-cafe-screen.html",
        cafe=cafe,
        reviews=reviews,
        current_user_id=current_user_id,
        peak_times=peak_times,
        max_count=max_count,
        hours=hours,
        today_hours=today_hours
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
    update_cafe_rating(cafe_obj_id)
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
    update_cafe_rating(review["cafe_id"])
    flash("Review deleted successfully.", "success")
    # takes user back to their previous screen(my reviews) or the cafe screen
    next_url = request.referrer or url_for("cafe_detail", cafe_id=str(review["cafe_id"]))
    return redirect(next_url)

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
    update_cafe_rating(review["cafe_id"])
    flash("Review updated successfully.", "success")
    # takes user back to their previous screen(my reviews) or the cafe screen
    next_url = request.referrer or url_for("cafe_detail", cafe_id=str(review["cafe_id"]))
    return redirect(next_url)

#Add photos
@app.route("/cafe/<cafe_id>/photo_url", methods=["POST"])
@login_required
def add_photo_url(cafe_id):
    try:
        cafe_obj_id= ObjectId(cafe_id)
    except Exception:
        flash("Invalid cafe link.", "error")
        return redirect(url_for("home"))
    # read & validate input
    photo_url= (request.form.get("photo_url") or "").strip()
    if not photo_url:
        flash("Please paste a photo_url URL.", "error")
        return redirect(url_for("cafe_detail", cafe_id=cafe_id))

    if not (photo_url.startswith("http://") or photo_url.startswith("https://")):
        flash("photo_url URL must start with http:// or https://", "error")
        return redirect(url_for("cafe_detail", cafe_id=cafe_id))

    photo_doc= {
        "_id": ObjectId(),
        "url": photo_url,
        "user_id": ObjectId(current_user.get_id()),
        "created_at": datetime.datetime.utcnow()
    }
    cafes_col.update_one(
        {"_id": cafe_obj_id},
        {"$push": {"photos": photo_doc}}
    )

    return redirect(url_for("cafe_detail", cafe_id=cafe_id))

#Delete photos
@app.route("/cafe/<cafe_id>/photo/<photo_id>/delete", methods=["POST"])
@login_required
def delete_photo(cafe_id, photo_id):
    try:
        cafe_obj_id = ObjectId(cafe_id)
        photo_obj_id = ObjectId(photo_id)
    except Exception:
        flash("Invalid link.", "error")
        return redirect(url_for("home"))

    cafe= cafes_col.find_one({"_id": cafe_obj_id})
    # find the photo inside the array
    photo = None
    for p in cafe.get("photos", []):
    # object style photo
        if isinstance(p, dict) and str(p.get("_id")) == str(photo_obj_id):
            photo= p
            break
    # permission check
    if str(photo.get("user_id")) != str(current_user.get_id()):
        flash("You can only delete photos you uploaded.", "error")
        return redirect(url_for("cafe_detail", cafe_id=cafe_id))
    # remove it
    cafes_col.update_one(
        {"_id": cafe_obj_id},
        {"$pull": {"photos": {"_id": photo_obj_id}}}
    )
    return redirect(url_for("cafe_detail", cafe_id=cafe_id))

#Cafe check in 
@app.route("/cafe/<cafe_id>/checkin", methods=["POST"])
@login_required
def add_checkin(cafe_id):
    try:
        cafe_obj_id = ObjectId(cafe_id)
    except Exception:
        flash("Invalid cafe link.", "error")
        return redirect(url_for("home"))
    
    hour_str = (request.form.get("hour") or "").strip()
    hour= int(hour_str)
    ny_tz= ZoneInfo("America/New_York")
    utc_tz= ZoneInfo("UTC")

    now_ny= datetime.datetime.now(ny_tz)
    ny_time= now_ny.replace(hour=hour, minute=0, second=0, microsecond=0)
    utc_time= ny_time.astimezone(utc_tz).replace(tzinfo=None)  

    checkins_col.insert_one({
        "cafe_id": cafe_obj_id,
        "user_id": ObjectId(current_user.get_id()),
        "created_at": utc_time
    })
    flash(f"Checked in!", "success")
    return redirect(url_for("cafe_detail", cafe_id=cafe_id))

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")


@app.route("/my_reviews")
@login_required
def my_reviews():
    user_id = ObjectId(current_user.get_id())

    # Fetch all reviews by this user, sorted newest first
    reviews = list(reviews_col.find({"user_id": user_id}).sort("created_at", -1))

    # Add extra info for the template
    for r in reviews:
        # Convert ObjectIds to strings for template
        r["_id_str"] = str(r["_id"])
        r["user_id_str"] = str(r["user_id"])

        # Add cafe name for display
        cafe = cafes_col.find_one({"_id": r["cafe_id"]})
        r["cafe_name"] = cafe.get("name") if cafe else "Unknown Cafe"

        # Ensure created_at is datetime
        if "created_at" not in r or not isinstance(r["created_at"], datetime.datetime):
            r["created_at"] = None

    return render_template(
        "my-reviews.html",
        reviews=reviews,
        current_user_id=str(user_id)
    )

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    # get the user doc
    user_data = users_col.find_one({"_id": ObjectId(current_user.get_id())})
    op_hours = user_data.get('operation_hours')
    if not isinstance(op_hours, dict):
        op_hours = {} # make operation hours dict if it was str before

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
            days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

            op_hours = {day: request.form.get(f'hours_{day}') for day in days}
            amenities_raw = request.form.get("amenities", "")
            popular_raw = request.form.get("popular", "")

            amenities_list = [item.strip() for item in amenities_raw.split(",") if item.strip()]
            popular_list = [item.strip() for item in popular_raw.split(",") if item.strip()]

            cafe_update = {
                "name": request.form.get("cafe_name"),
                "address": request.form.get("shop_location"),
                "map_src": request.form.get("map_src"),
                "hours": op_hours,
                "amenities": amenities_list,
                "popular": popular_list
            }

            user_update = {
                "cafe_name": request.form.get("cafe_name"),
                "shop_location": request.form.get("shop_location"),
                "map_src": request.form.get("map_src"),
                "operation_hours": op_hours,
                "amenities": amenities_list,
                "popular": popular_list
            }
            # update database
            users_col.update_one(
                {"_id": ObjectId(current_user.get_id())},
                {"$set": user_update}
            )

            cafes_col.update_one(
                {"owner_id": ObjectId(current_user.get_id())},
                {"$set": cafe_update}
            )
        users_col.update_one(
            {"_id": ObjectId(current_user.get_id())},
            {"$set": update_fields}
        )
        
        flash("Profile updated successfully!", "success")
        return redirect(url_for('settings')) 
    return render_template("profile.html", op_hours=op_hours)


@app.route("/saved")
@login_required
def saved_places():
    return render_template("saved_places.html")


# --- Run app ---
if __name__ == "__main__":
    app.run(debug=True, port=5000)