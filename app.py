from flask import Flask, render_template, request, session, redirect
import psycopg2
import os
import cloudinary
import cloudinary.uploader
import logging
import time
from collections import deque
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)


# ==========================================
# SECRET KEY
# ==========================================

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "cloud_task_manager_secret_key"
)


# ==========================================
# LOGGING CONFIGURATION
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ==========================================
# MONITORING CONFIGURATION
# ==========================================

# Time when application started
APP_START_TIME = time.time()

# Store latest 20 requests
request_logs = deque(maxlen=20)

# Store active users with their latest activity time
active_users = {}


# ==========================================
# REQUEST MONITORING
# ==========================================

@app.before_request
def monitor_request():

    # Ignore monitoring page from request log
    if request.path != "/monitor":

        request_logs.append({
            "method": request.method,
            "path": request.path,
            "time": time.strftime("%H:%M:%S")
        })

    # Track logged-in user's activity
    if "user_id" in session:

        active_users[session["user_id"]] = {
            "name": session.get("user_name", "User"),
            "last_active": time.time()
        }


# ==========================================
# CLOUDINARY CONFIGURATION
# ==========================================

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET")
)


# ==========================================
# DATABASE CONFIGURATION
# ==========================================

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

def init_db():

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            task TEXT NOT NULL,
            status TEXT DEFAULT 'Pending'
        )
    """)

    cursor.execute("""
        ALTER TABLE tasks
        ADD COLUMN IF NOT EXISTS file_url TEXT
    """)

    connection.commit()

    cursor.close()
    connection.close()

    logger.info("Database initialized successfully")


init_db()


# ==========================================
# HOME PAGE
# ==========================================

@app.route("/")
def home():

    logger.info("Home page accessed")

    return render_template("index.html")


# ==========================================
# REGISTER
# ==========================================

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

            logger.info(
                "New user registered: %s",
                email
            )

        except psycopg2.IntegrityError:

            connection.rollback()

            logger.warning(
                "Registration failed - email already exists: %s",
                email
            )

            cursor.close()
            connection.close()

            return "Email already registered!"

        cursor.close()
        connection.close()

        return "Registration successful!"

    return render_template("register.html")


# ==========================================
# LOGIN
# ==========================================

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

            active_users[user[0]] = {
                "name": user[1],
                "last_active": time.time()
            }

            logger.info(
                "Successful login: %s",
                email
            )

            return redirect("/dashboard")

        logger.warning(
            "Failed login attempt: %s",
            email
        )

        return "Invalid email or password!"

    return render_template("login.html")


# ==========================================
# DASHBOARD
# ==========================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:

        logger.warning(
            "Unauthorized dashboard access attempt"
        )

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

    logger.info(
        "Dashboard accessed by user: %s",
        user_name
    )

    return render_template(
        "dashboard.html",
        user_name=user_name,
        tasks=tasks
    )


# ==========================================
# ADD TASK + CLOUDINARY UPLOAD
# ==========================================

@app.route("/add_task", methods=["POST"])
def add_task():

    if "user_id" not in session:

        logger.warning(
            "Unauthorized task creation attempt"
        )

        return redirect("/login")

    task = request.form["task"]
    user_id = session["user_id"]

    uploaded_file = request.files.get("file")

    file_url = None


    # --------------------------------------
    # CLOUDINARY FILE UPLOAD
    # --------------------------------------

    if uploaded_file and uploaded_file.filename:

        try:

            logger.info(
                "Starting Cloudinary upload: %s",
                uploaded_file.filename
            )

            upload_result = cloudinary.uploader.upload(
                uploaded_file,
                resource_type="auto"
            )

            file_url = upload_result.get("secure_url")

            logger.info(
                "Cloudinary upload successful: %s",
                uploaded_file.filename
            )

        except Exception as e:

            logger.error(
                "Cloudinary upload failed: %s",
                str(e)
            )

            return """
            <h2>Cloudinary Upload Failed</h2>
            <p>Please check your Cloudinary configuration.</p>
            """

    else:

        logger.info(
            "No file selected for task"
        )


    # --------------------------------------
    # SAVE TASK TO DATABASE
    # --------------------------------------

    try:

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

        logger.info(
            "Task added successfully for user ID: %s",
            user_id
        )

    except Exception as e:

        logger.error(
            "Task database insertion failed: %s",
            str(e)
        )

        return """
        <h2>Task Creation Failed</h2>
        <p>An error occurred while saving the task.</p>
        """

    return redirect("/dashboard")


# ==========================================
# LOGOUT
# ==========================================

@app.route("/logout")
def logout():

    user_id = session.get("user_id")
    user_name = session.get("user_name")

    # Remove user from active users
    if user_id in active_users:
        del active_users[user_id]

    session.clear()

    logger.info(
        "User logged out: %s",
        user_name
    )

    return redirect("/login")


# ==========================================
# MONITORING DASHBOARD
# ==========================================

@app.route("/monitor")
def monitor():

    # Remove users inactive for more than 5 minutes
    current_time = time.time()

    inactive_users = []

    for user_id, user_data in active_users.items():

        if current_time - user_data["last_active"] > 300:
            inactive_users.append(user_id)

    for user_id in inactive_users:
        del active_users[user_id]


    # Calculate application uptime
    uptime_seconds = int(
        current_time - APP_START_TIME
    )

    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60

    uptime = (
        f"{days}d {hours}h {minutes}m {seconds}s"
    )


    # Server status
    server_status = "Online"


    # Number of active users
    active_user_count = len(active_users)


    logger.info("Monitoring dashboard accessed")


    return render_template(
        "monitor.html",
        active_users=active_user_count,
        uptime=uptime,
        server_status=server_status,
        request_logs=list(request_logs)
    )


# ==========================================
# ERROR HANDLERS
# ==========================================

@app.errorhandler(404)
def page_not_found(error):

    logger.warning(
        "404 error - page not found: %s",
        request.path
    )

    return """
    <h2>404 - Page Not Found</h2>
    <p>The requested page does not exist.</p>
    """, 404


@app.errorhandler(500)
def internal_server_error(error):

    logger.error(
        "500 internal server error: %s",
        str(error)
    )

    return """
    <h2>500 - Internal Server Error</h2>
    <p>An unexpected error occurred.</p>
    """, 500


# ==========================================
# APPLICATION START
# ==========================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )