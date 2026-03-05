# Web Application Exercise

A little exercise to build a web application following an agile development process. See the [instructions](instructions.md) for more detail.

## Product Vision Statement

Sips is a New York City based app that allows users to discover, rate, and share honest reviews of nearby cafes, making it easy to find the perfect place to grab a drink nearby.

## User stories

Our project was developed with simulated users in mind. We categorized them into:

- Users: Anyone who is looking to discover a new cafe, rate resturants, and leave reviews.
- Shop owners: Business owners who want a page to advertise their cafe and share the latest info.

View our user stories below:

[User Stories](https://github.com/swe-students-spring2026/2-web-app-orbit_owls/issues)

## Steps to Run the Application

### 1. Prerequisites

- Python 3.9+ installed
- A configured `.env` file (see below)

---

### 2. Environment Variables

Create a `.env` file in the root directory of the project with the following content:

```
MONGO_URI=your_mongo_uri
MONGO_DBNAME=sips
SECRET_KEY=your_secret_key
```

Replace the placeholder values with your actual configuration values.

---

### 3. Run

Install Pipenv (if not already installed):

```bash
pip install pipenv

# Install dependencies:

pipenv install

# Activate the virtual environment:

pipenv shell

# Start the application:

python app.py
```

---

### 4. Open in Browser

Once the server is running, access the application at:

http://127.0.0.1:5000

## Agile Methodology

We split our project into two development phases using the Agile Methodology.

View the taskboards for our two sprints below:

[Sprint 1 Task Board](https://github.com/orgs/swe-students-spring2026/projects/13)

[Sprint 2 Task Board](https://github.com/orgs/swe-students-spring2026/projects/63)
