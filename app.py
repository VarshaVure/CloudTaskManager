from flask import Flask, render_template, request, session, redirect
import psycopg2
import os
import cloudinary
import cloudinary.uploader
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# ============================================================
# SECRET KEY
# ============================================================

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "cloud_task_manager_secret_key"
)


# ============================================================
# CLOUDINARY CONFIGURATION
# ============================================================

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET")
)


# ============================================================
# POSTGRESQL DATABASE
# ============================================================

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

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

    # Add file_url column if it doesn't already exist
    cursor.execute("""
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS file_url TEXT
    """)

    connection.commit()

    cursor.close()
    connection.close()


# Initialize database
init_db()


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def home():

    return render_template("index.html")


# ============================================================
# REGISTER
# ============================================================

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
            """, (
                name,
                email,
                hashed_password
            ))

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


# ============================================================
# LOGIN
# ============================================================

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


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    user_name = session["user_name"]

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM tasks
        WHERE user_id = %s
        ORDER BY id DESC
    """, (user_id,))

    tasks = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "dashboard.html",
        user_name=user_name,
        tasks=tasks
    )


# ============================================================
# ADD TASK + CLOUDINARY FILE UPLOAD
# ============================================================

@app.route("/add_task", methods=["POST"])
def add_task():

    # Check login
    if "user_id" not in session:
        return redirect("/login")

    task = request.form["task"]
    user_id = session["user_id"]

    # Get uploaded file
    uploaded_file = request.files.get("file")

    file_url = None

    # ========================================================
    # CLOUDINARY UPLOAD
    # ========================================================

    if uploaded_file and uploaded_file.filename:

        try:

            print("===================================")
            print("Starting Cloudinary upload...")
            print("File name:", uploaded_file.filename)
            print("===================================")

            upload_result = cloudinary.uploader.upload(
                uploaded_file,
                resource_type="auto"
            )

            file_url = upload_result.get("secure_url")

            print("===================================")
            print("CLOUDINARY UPLOAD SUCCESS")
            print("FILE URL:", file_url)
            print("===================================")

        except Exception as e:

            print("===================================")
            print("CLOUDINARY UPLOAD ERROR")
            print(str(e))
            print("===================================")

            return """
            <h2>Cloudinary Upload Failed</h2>
            <p>Please check your Cloudinary configuration.</p>
            <p>Error:</p>
            <pre>{}</pre>
            """.format(str(e))

    else:

        print("No file was selected.")

    # ========================================================
    # SAVE TASK TO POSTGRESQL
    # ========================================================

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO tasks
        (user_id, task, status, file_url)
        VALUES (%s, %s, %s, %s)
    """, (
        user_id,
        task,
        "Pending",
        file_url
    ))

    connection.commit()

    cursor.close()
    connection.close()

    return redirect("/dashboard")


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )