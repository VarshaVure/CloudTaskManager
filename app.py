from flask import Flask, render_template, request, session, redirect
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Secret key for sessions
app.secret_key = "cloud_task_manager_secret_key"


# Database initialization
def init_db():

    connection = sqlite3.connect("database.db")
    cursor = connection.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # Tasks table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task TEXT NOT NULL,
            status TEXT DEFAULT 'Pending'
        )
    """)

    connection.commit()
    connection.close()


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

        connection = sqlite3.connect("database.db")
        cursor = connection.cursor()

        try:

            cursor.execute("""
                INSERT INTO users (name, email, password)
                VALUES (?, ?, ?)
            """, (name, email, hashed_password))

            connection.commit()

        except sqlite3.IntegrityError:

            connection.close()
            return "Email already registered!"

        connection.close()

        return "Registration successful!"

    return render_template("register.html")


# Login
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        connection = sqlite3.connect("database.db")
        cursor = connection.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        )

        user = cursor.fetchone()

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

    connection = sqlite3.connect("database.db")
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM tasks WHERE user_id = ?",
        (user_id,)
    )

    tasks = cursor.fetchall()

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

    connection = sqlite3.connect("database.db")
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO tasks (user_id, task)
        VALUES (?, ?)
    """, (user_id, task))

    connection.commit()
    connection.close()

    return redirect("/dashboard")


# Logout
@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# Start application
if __name__ == "__main__":

    init_db()

    app.run(debug=True)