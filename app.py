from flask import Flask, render_template, request, session, redirect
import psycopg2
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Secret key from Render environment variable
app.secret_key = os.environ.get(
    "SECRET_KEY",
    "cloud_task_manager_secret_key"
)

# PostgreSQL database URL
DATABASE_URL = os.environ.get("DATABASE_URL")


# Connect to PostgreSQL
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


# Create database tables
def init_db():

    connection = get_db_connection()
    cursor = connection.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Tasks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            task TEXT NOT NULL,
            status TEXT DEFAULT 'Pending'
        )
    """)

    connection.commit()
    cursor.close()
    connection.close()


# Initialize database
init_db()


# Home page
@app.route("/")
def home():
    return render_template("index.html")


# Register
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        connection = get_db_connection()
        cursor = connection.cursor()

        try:

            cursor.execute("""
                INSERT INTO users (name, email, password)
                VALUES (%s, %s, %s)
            """, (name, email, hashed_password))

            connection.commit()

        except psycopg2.IntegrityError:

            connection.rollback()
            cursor.close()
            connection.close()

            return "Email already registered!"

        cursor.close()
        connection.close()

        return "Registration successful!"

    return render_template("register.html")


# Login
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE email = %s",
            (email,)
        )

        user = cursor.fetchone()

        cursor.close()
        connection.close()

        if user and check_password_hash(user[3], password):

            session["user_id"] = user[0]
            session["user_name"] = user[1]

            return redirect("/dashboard")

        return "Invalid email or password!"

    return render_template("login.html")


# Dashboard
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    user_name = session["user_name"]

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM tasks WHERE user_id = %s",
        (user_id,)
    )

    tasks = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "dashboard.html",
        user_name=user_name,
        tasks=tasks
    )


# Add task
@app.route("/add_task", methods=["POST"])
def add_task():

    if "user_id" not in session:
        return redirect("/login")

    task = request.form["task"]
    user_id = session["user_id"]

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO tasks (user_id, task)
        VALUES (%s, %s)
    """, (user_id, task))

    connection.commit()

    cursor.close()
    connection.close()

    return redirect("/dashboard")


# Logout
@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# Run application locally
if __name__ == "__main__":
    app.run(debug=True)