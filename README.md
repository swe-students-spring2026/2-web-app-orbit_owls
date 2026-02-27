# Web Application Exercise

A little exercise to build a web application following an agile development process. See the [instructions](instructions.md) for more detail.

## Product vision statement

Sips is a New York City based app that allows users to discover, rate, and share honest reviews of nearby cafes, making it easy to find the perfect place to grab a drink nearby.

## User stories

See instructions. Delete this line and place a link to the user stories here.

## Steps necessary to run the software

Set up the .env file
Get the `.env` file from the team Discord channel and place it in the root of the project folder:
```
MONGO_URI=your_mongo_uri
MONGO_DBNAME=sips
SECRET_KEY=your_secret_key
```

### 3a. Run without Docker

```bash
pip install pipenv
pipenv install
pipenv shell
python app.py
```

### 4. Open in browser

Go to `http://127.0.0.1:5000`

## Task boards

See instructions. Delete this line and place a link to the task boards here.

