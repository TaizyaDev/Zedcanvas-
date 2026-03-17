from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
import json, os, re, uuid, smtplib, random, hashlib, hmac, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


import psycopg2
import psycopg2.extras
from contextlib import contextmanager

# ════════════════════════════════════════
# DATABASE
# ════════════════════════════════════════
DATABASE_URL = os.environ.get("DATABASE_URL", "")

@contextmanager
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Create all tables if they don't exist."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS stories (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS challenges (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS listings (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS bookmarks (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS profile_views (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS resets (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS collabs (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS blocks (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS groups (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS group_messages (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
    print("[DB] Tables initialized successfully")

# ── Generic DB helpers ──
def db_load(table):
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(f"SELECT data FROM {table} ORDER BY created_at ASC")
            return [row["data"] for row in cur.fetchall()]
    except Exception as e:
        print(f"[DB ERROR] load {table}: {e}")
        return []

def db_save_all(table, items):
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(f"DELETE FROM {table}")
            for item in items:
                cur.execute(
                    f"INSERT INTO {table} (id, data) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                    (item.get("id", str(uuid.uuid4())), json.dumps(item))
                )
    except Exception as e:
        print(f"[DB ERROR] save_all {table}: {e}")

def db_upsert(table, item):
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                f"INSERT INTO {table} (id, data) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
                (item.get("id", str(uuid.uuid4())), json.dumps(item))
            )
    except Exception as e:
        print(f"[DB ERROR] upsert {table}: {e}")

def db_delete(table, item_id):
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(f"DELETE FROM {table} WHERE id = %s", (item_id,))
    except Exception as e:
        print(f"[DB ERROR] delete {table}: {e}")

# Initialize DB on startup
if DATABASE_URL:
    try:
        init_db()
    except Exception as e:
        print(f"[DB INIT ERROR] {e}")


import urllib.request
import urllib.parse
import base64
import hashlib

# ════════════════════════════════════════
# CLOUDINARY IMAGE HOSTING
# ════════════════════════════════════════
CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "dbo7y3jo5")
CLOUDINARY_API_KEY    = os.environ.get("CLOUDINARY_API_KEY", "191442868351399")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "D76kBZ0SJ9KxJQsn1QVWJ1LNLOg")

def upload_to_cloudinary(file_obj, folder="zedcanvas"):
    """Upload image to Cloudinary and return URL."""
    try:
        import hmac as _hmac
        timestamp = str(int(time.time()))
        # Create signature
        params = f"folder={folder}&timestamp={timestamp}"
        sig_str = params + CLOUDINARY_API_SECRET
        signature = hashlib.sha1(sig_str.encode()).hexdigest()

        # Read file data
        file_obj.seek(0)
        file_data = file_obj.read()
        file_obj.seek(0)

        # Build multipart form data
        boundary = uuid.uuid4().hex
        body = []
        # Add file
        body.append(f"--{boundary}".encode())
        body.append(b'Content-Disposition: form-data; name="file"; filename="upload"')
        body.append(b"Content-Type: application/octet-stream")
        body.append(b"")
        body.append(file_data)
        # Add fields
        for key, val in [
            ("api_key", CLOUDINARY_API_KEY),
            ("timestamp", timestamp),
            ("folder", folder),
            ("signature", signature),
        ]:
            body.append(f"--{boundary}".encode())
            body.append(f'Content-Disposition: form-data; name="{key}"'.encode())
            body.append(b"")
            body.append(val.encode())
        body.append(f"--{boundary}--".encode())
        body_bytes = b"\r\n".join(body)

        url = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload"
        req = urllib.request.Request(url, data=body_bytes)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("Content-Length", str(len(body_bytes)))

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return result.get("secure_url", "")
    except Exception as e:
        print(f"[CLOUDINARY ERROR] {e}")
        return ""

# ── Load .env file if it exists ──
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"')
load_env()

import os as _os
_basedir = _os.path.abspath(_os.path.dirname(__file__))
app = Flask(__name__, template_folder=_basedir, static_folder=_os.path.join(_basedir, "static"))
app.secret_key = os.environ.get("SECRET_KEY", "zedcanvas_secret_change_this_in_production")

# ── Secure session cookies ──
app.config.update(
    SESSION_COOKIE_HTTPONLY  = True,
    SESSION_COOKIE_SAMESITE  = "Lax",
    SESSION_COOKIE_SECURE    = os.environ.get("RENDER", False),  # Auto True on Render
    MAX_CONTENT_LENGTH       = 5 * 1024 * 1024,  # 5MB max upload
)

# ════════════════════════════════════════
# ✏️  YOUR EMAIL DETAILS — EDIT THESE
# ════════════════════════════════════════
EMAIL_ADDRESS  = "zedcanvas4all@gmail.com"
EMAIL_PASSWORD = "jodehbhwzrozyfuc"
# ════════════════════════════════════════

AVATAR_FOLDER = "static/uploads/avatars"
POST_FOLDER   = "static/uploads/posts"
ALLOWED_EXT   = {"png", "jpg", "jpeg", "gif", "webp"}

for folder in [AVATAR_FOLDER, POST_FOLDER]:
    os.makedirs(folder, exist_ok=True)

ART_STYLES = [
    "Oil Painting", "Acrylic", "Watercolour", "Digital Art",
    "Pencil / Charcoal", "Sculpture", "Photography",
    "Mixed Media", "Ink", "Street Art", "Textile", "Other"
]

ART_CATEGORIES = [
    "🖌️ Painting", "✏️ Drawing", "📸 Photography", "💻 Digital Art",
    "🗿 Sculpture", "🎭 Mixed Media", "🖼️ Illustration", "🏙️ Street Art",
    "🧵 Textile", "🎨 Abstract", "🌍 Landscape", "👤 Portrait", "Other"
]

# ════════════════════════════════════════
# DATA HELPERS (PostgreSQL)
# ════════════════════════════════════════
def load_users():    return db_load("users")
def save_users(d):   db_save_all("users", d)
def load_posts():    return db_load("posts")
def save_posts(d):   db_save_all("posts", d)
def load_messages(): return db_load("messages")
def save_messages(d): db_save_all("messages", d)
def load_notifs():   return db_load("notifications")
def save_notifs(d):  db_save_all("notifications", d)
def load_pending():  return db_load("resets")
def save_pending(d): db_save_all("resets", d)

def get_user_by_id(uid):
    return next((u for u in load_users() if u["id"] == uid), None)

def get_user_by_username(username):
    return next((u for u in load_users() if u["username"].lower() == username.lower()), None)

def get_user_by_email(email):
    return next((u for u in load_users() if u["email"].lower() == email.lower()), None)

def current_user():
    uid = session.get("user_id")
    if not uid: return None
    return get_user_by_id(uid)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def time_ago(dt_str):
    try:
        dt   = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        diff = datetime.now() - dt
        s    = int(diff.total_seconds())
        if s < 60:    return "just now"
        if s < 3600:  return f"{s//60}m ago"
        if s < 86400: return f"{s//3600}h ago"
        return f"{s//86400}d ago"
    except: return ""

def add_notification(to_uid, from_uid, ntype, ref_id=""):
    if to_uid == from_uid: return
    notifs = load_notifs()
    notifs.append({
        "id": str(uuid.uuid4()), "to_uid": to_uid,
        "from_uid": from_uid, "type": ntype,
        "ref_id": ref_id, "read": False,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    save_notifs(notifs)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        # Update last seen on every request
        try:
            update_last_seen(session["user_id"])
        except: pass
        return f(*args, **kwargs)
    return decorated


# ════════════════════════════════════════
# SECURITY
# ════════════════════════════════════════

# ── Rate Limiting (no extra packages needed) ──
_rate_store = {}

def rate_limit(key, max_calls, window_seconds):
    """Returns True if allowed, False if rate limited."""
    now   = time.time()
    store = _rate_store.setdefault(key, [])
    # Remove old entries outside window
    _rate_store[key] = [t for t in store if now - t < window_seconds]
    if len(_rate_store[key]) >= max_calls:
        return False
    _rate_store[key].append(now)
    return True

def get_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()

# ── CSRF Protection ──
def generate_csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = uuid.uuid4().hex
    return session["csrf_token"]

def validate_csrf():
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not token or token != session.get("csrf_token"):
        abort(403)

app.jinja_env.globals["csrf_token"] = generate_csrf
app.jinja_env.globals["enumerate"]   = enumerate

# ── Input Sanitizer ──
def sanitize(text, max_length=500):
    if not text: return ""
    # Strip dangerous characters
    text = re.sub(r"[<>]", "", text)
    return text.strip()[:max_length]

def sanitize_username(username):
    return re.sub(r"[^a-z0-9_]", "", username.lower())[:20]

# ── Secure file upload ──
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_MIME  = {"image/jpeg", "image/png", "image/gif", "image/webp"}

def secure_save(file_obj, folder, prefix):
    """Validates and saves uploaded file. Returns filename or empty string."""
    if not file_obj or not file_obj.filename:
        return ""
    ext = file_obj.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        return ""
    # Check file size by reading header bytes
    file_obj.seek(0, 2)
    size = file_obj.tell()
    file_obj.seek(0)
    if size > MAX_FILE_SIZE:
        flash("File too large. Max 5MB.", "error")
        return ""
    fname = f"{prefix}_{uuid.uuid4().hex}.{ext}"
    file_obj.save(os.path.join(folder, secure_filename(fname)))
    return fname

# ════════════════════════════════════════
# EMAIL VERIFICATION
# ════════════════════════════════════════
def generate_code():
    return str(random.randint(100000, 999999))

def send_verification_email(email, username, code):
    try:
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = f"Your ZedCanvas verification code: {code}"
        msg["From"]    = EMAIL_ADDRESS
        msg["To"]      = email
        html = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#f8f8f8;
                    border-radius:12px;overflow:hidden;border:1px solid #e2e2e2;">
          <div style="background:#0a0a0a;padding:2rem;text-align:center;">
            <h1 style="color:#f8f8f8;font-size:1.8rem;margin:0;letter-spacing:0.05em;">ZedCanvas</h1>
            <p style="color:#888;margin:0.4rem 0 0;font-size:0.85rem;">Zambia's Art Network 🇿🇲</p>
          </div>
          <div style="padding:2rem;text-align:center;">
            <h2 style="color:#0a0a0a;font-size:1.2rem;margin-bottom:0.5rem;">
              Hey @{username}, verify your email 👋
            </h2>
            <p style="color:#666;font-size:0.9rem;margin-bottom:1.5rem;">
              Enter this code to activate your ZedCanvas account:
            </p>
            <div style="background:#0a0a0a;color:#f8f8f8;font-size:2.5rem;font-weight:700;
                        letter-spacing:0.3em;padding:1rem 1.5rem;border-radius:10px;
                        display:inline-block;margin-bottom:1.5rem;">
              {code}
            </div>
            <p style="color:#aaa;font-size:0.78rem;">
              This code expires in <strong>10 minutes</strong>.<br/>
              If you didn't sign up for ZedCanvas, ignore this email.
            </p>
          </div>
        </div>"""
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, email, msg.as_string())
        print(f"[EMAIL SENT] Verification code to {email}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR - Skipping] {e}")
        return False

def send_reset_email_safe(email, username, token):
    try:
        return send_reset_email(email, username, token)
    except:
        return False



# ════════════════════════════════════════
# TAGGING & POLLS
# ════════════════════════════════════════
def parse_mentions(text, post_id, author_id):
    """Find @username mentions, notify them, return linked text."""
    if not text: return text
    users   = load_users()
    um      = {u["username"].lower(): u for u in users}
    words   = text.split()
    for word in words:
        if word.startswith("@"):
            username = re.sub(r"[^a-z0-9_]", "", word[1:].lower())
            if username in um:
                mentioned = um[username]
                if mentioned["id"] != author_id:
                    add_notification(mentioned["id"], author_id, "mention", post_id)
    return text

# ════════════════════════════════════════
# ACTIVE STATUS
# ════════════════════════════════════════
def update_last_seen(user_id):
    """Update user last seen timestamp."""
    try:
        users  = load_users()
        user   = next((u for u in users if u["id"] == user_id), None)
        if user:
            user["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_users(users)
    except: pass

def get_online_status(user, viewer=None):
    """Returns online status based on privacy settings."""
    if not user: return None
    privacy = user.get("active_status_privacy", "everyone")
    # Check if viewer can see status
    if privacy == "nobody":
        return None
    if privacy == "followers" and viewer:
        if viewer["id"] not in user.get("followers", []) and viewer["id"] != user["id"]:
            return None
    last_seen = user.get("last_seen")
    if not last_seen: return None
    try:
        dt   = datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
        diff = (datetime.now() - dt).total_seconds()
        if diff < 300:   return "online"     # 5 minutes
        if diff < 3600:  return f"{int(diff//60)}m ago"
        if diff < 86400: return f"{int(diff//3600)}h ago"
        return f"{int(diff//86400)}d ago"
    except: return None

# ════════════════════════════════════════
# AUTH
# ════════════════════════════════════════
@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")

@app.route("/static/sw.js")
def service_worker():
    return app.send_static_file("sw.js")

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("feed"))
    return render_template("landing.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("user_id"):
        return redirect(url_for("feed"))
    if request.method == "POST":
        full_name = sanitize(request.form.get("full_name", ""), 60)
        username  = sanitize_username(request.form.get("username", ""))
        email     = sanitize(request.form.get("email", ""), 120).lower()
        password  = request.form.get("password", "").strip()
        bio       = sanitize(request.form.get("bio", ""), 300)
        art_style = sanitize(request.form.get("art_style", ""), 50)
        users     = load_users()
        errors    = []

        if not full_name: errors.append("Full name is required.")
        if not username:  errors.append("Username is required.")
        if not re.match(r"^[a-z0-9_]{3,20}$", username):
            errors.append("Username: 3-20 chars, letters/numbers/underscores only.")
        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$", email):
            errors.append("Please enter a valid email.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if any(u["username"].lower() == username for u in users):
            errors.append("Username already taken.")
        if any(u["email"].lower() == email for u in users):
            errors.append("Email already registered.")

        if errors:
            for e in errors: flash(e, "error")
            return render_template("signup.html", art_styles=ART_STYLES, form=request.form)

        # Handle avatar upload (secure)
        photo  = request.files.get("photo")
        avatar = secure_save(photo, AVATAR_FOLDER, "avatar") if photo else ""

        # Generate verification code
        code    = generate_code()
        expires = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

        # Save to pending
        pending = [p for p in load_pending() if p["email"] != email]
        pending.append({
            "id":        str(uuid.uuid4()),
            "full_name": full_name,
            "username":  username,
            "email":     email,
            "password":  generate_password_hash(password),
            "bio":       bio,
            "art_style": art_style,
            "avatar":    avatar,
            "code":      code,
            "expires":   expires,
        })
        save_pending(pending)

        # Try to send verification email
        try:
            sent = send_verification_email(email, username, code)
        except:
            sent = False
        if sent:
            flash(f"A 6-digit code was sent to {email} — check your inbox! 📧", "success")
            session["pending_email"] = email
            return redirect(url_for("verify"))
        else:
            # Email failed — create account directly without verification
            print(f"[EMAIL FAILED] Creating account without verification for {email}")
            users = load_users()
            new_user = {
                "id":         str(uuid.uuid4()),
                "full_name":  full_name,
                "username":   username,
                "email":      email,
                "password":   generate_password_hash(password),
                "bio":        bio,
                "art_style":  art_style,
                "avatar":     avatar,
                "followers":  [],
                "following":  [],
                "verified":   False,
                "joined":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            users.append(new_user)
            save_users(users)
            # Clean pending
            pending = [p for p in load_pending() if p["email"] != email]
            save_pending(pending)
            session["user_id"] = new_user["id"]
            flash(f"Welcome to ZedCanvas, @{username}! 🎨🇿🇲", "success")
            return redirect(url_for("feed"))

    return render_template("signup.html", art_styles=ART_STYLES, form={})


@app.route("/verify", methods=["GET", "POST"])
def verify():
    email = session.get("pending_email")
    if not email:
        return redirect(url_for("signup"))

    if request.method == "POST":
        code    = request.form.get("code", "").strip()
        pending = load_pending()
        entry   = next((p for p in pending if p["email"] == email), None)

        if not entry:
            flash("Session expired. Please sign up again.", "error")
            return redirect(url_for("signup"))

        if datetime.strptime(entry["expires"], "%Y-%m-%d %H:%M:%S") < datetime.now():
            flash("Code expired. Please sign up again.", "error")
            pending = [p for p in pending if p["email"] != email]
            save_pending(pending)
            session.pop("pending_email", None)
            return redirect(url_for("signup"))

        if entry["code"] != code:
            flash("Incorrect code. Try again.", "error")
            return render_template("verify.html", email=email)

        # ✅ Verified! Create account
        users = load_users()
        new_user = {
            "id":         entry["id"],
            "full_name":  entry["full_name"],
            "username":   entry["username"],
            "email":      entry["email"],
            "password":   entry["password"],
            "bio":        entry["bio"],
            "art_style":  entry["art_style"],
            "avatar":     entry["avatar"],
            "followers":  [],
            "following":  [],
            "verified":   True,
            "joined":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        users.append(new_user)
        save_users(users)

        # Remove from pending
        pending = [p for p in pending if p["email"] != email]
        save_pending(pending)
        session.pop("pending_email", None)

        session["user_id"] = new_user["id"]
        flash(f"Welcome to ZedCanvas, @{new_user['username']}! 🎨🇿🇲", "success")
        return redirect(url_for("feed"))

    return render_template("verify.html", email=email)


@app.route("/verify/resend", methods=["POST"])
def resend_code():
    email   = session.get("pending_email")
    pending = load_pending()
    entry   = next((p for p in pending if p["email"] == email), None)
    if entry:
        code    = generate_code()
        expires = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        entry["code"]    = code
        entry["expires"] = expires
        save_pending(pending)
        send_verification_email(email, entry["username"], code)
        flash("A new code has been sent! 📧", "success")
    return redirect(url_for("verify"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("feed"))
    if request.method == "POST":
        # Rate limit: 10 attempts per minute per IP
        if not rate_limit(f"login:{get_ip()}", 10, 60):
            flash("Too many login attempts. Please wait a minute.", "error")
            return render_template("login.html")
        login_id = sanitize(request.form.get("login_id", "")).lower()
        password = request.form.get("password", "").strip()
        user = get_user_by_email(login_id) or get_user_by_username(login_id)
        if user and check_password_hash(user["password"], password):
            if user.get("banned"):
                flash("Your account has been suspended.", "error")
                return render_template("login.html")
            session["user_id"] = user["id"]
            session.permanent = True
            flash(f"Welcome back, @{user['username']}! 🎨", "success")
            return redirect(url_for("feed"))
        # Small delay to slow brute force
        time.sleep(0.5)
        flash("Invalid email/username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ════════════════════════════════════════
# FEED & DISCOVER
# ════════════════════════════════════════
@app.route("/feed")
@login_required
def feed():
    me      = current_user()
    posts   = load_posts()
    users   = load_users()
    um      = {u["id"]: u for u in users}
    visible = [p for p in posts if p["user_id"] in me["following"] or p["user_id"] == me["id"]]
    visible = sorted(visible, key=lambda p: p["created"], reverse=True)
    # ── Stories ──
    active_stories = get_active_stories()
    # Group by user, keep latest per user
    seen_users = set()
    stories_bar = []
    for s in sorted(active_stories, key=lambda s: s["created"], reverse=True):
        if s["user_id"] not in seen_users:
            seen_users.add(s["user_id"])
            s["author"]   = um.get(s["user_id"], {})
            s["seen"]     = me["id"] in s.get("views", [])
            stories_bar.append(s)
    # Put my story first if exists
    my_story = next((s for s in stories_bar if s["user_id"] == me["id"]), None)
    if my_story:
        stories_bar.remove(my_story)
        stories_bar.insert(0, my_story)
    all_posts = load_posts()
    posts_map = {p["id"]: p for p in all_posts}
    listings  = load_listings()
    listed_ids = {l["post_id"] for l in listings if l["status"] == "available"}
    listing_map = {l["post_id"]: l["id"] for l in listings if l["status"] == "available"}
    for p in visible:
        p["time_ago"]  = time_ago(p["created"])
        p["author"]    = um.get(p["user_id"], {})
        p["liked"]     = me["id"] in p.get("likes", [])
        p["reposted"]  = any(r for r in all_posts if r.get("repost_of") == p["id"] and r["user_id"] == me["id"])
        p["repost_count"] = sum(1 for r in all_posts if r.get("repost_of") == p["id"])
        p["for_sale"]  = p["id"] in listed_ids
        p["listing_id"] = listing_map.get(p["id"], "")
        if p.get("repost_of"):
            orig = posts_map.get(p["repost_of"])
            p["orig_post"]   = orig
            p["orig_author"] = um.get(orig["user_id"], {}) if orig else {}
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return render_template("feed.html", posts=visible, me=me,
                           notif_count=len(notifs), stories=stories_bar, now=now)


@app.route("/discover")
@login_required
def discover():
    me          = current_user()
    users       = load_users()
    posts       = load_posts()
    category    = request.args.get("cat", "").strip()
    suggestions = [u for u in users if u["id"] != me["id"] and u["id"] not in me["following"]]
    if category:
        recent = [p for p in posts if (p.get("category") or "").lower() == category.lower()]
    else:
        recent = posts
    recent = sorted(recent, key=lambda p: p["created"], reverse=True)[:30]
    um = {u["id"]: u for u in users}
    for p in recent:
        p["time_ago"] = time_ago(p["created"])
        p["author"]   = um.get(p["user_id"], {})
        p["liked"]    = me["id"] in p.get("likes", [])
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    return render_template("discover.html", suggestions=suggestions,
                           posts=recent, me=me, notif_count=len(notifs),
                           categories=ART_CATEGORIES, active_cat=category)

# ════════════════════════════════════════
# POSTS
# ════════════════════════════════════════
@app.route("/post/create", methods=["GET", "POST"])
@login_required
def create_post():
    me = current_user()
    if request.method == "POST":
        caption = sanitize(request.form.get("caption", ""), 2200)
        image   = request.files.get("image")
        if not caption and (not image or not image.filename):
            flash("Please add a caption or image.", "error")
            notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
            return render_template("create_post.html", me=me, notif_count=len(notifs), categories=ART_CATEGORIES)
        img_fname = ""
        if image and image.filename and allowed_file(image.filename):
            img_fname = upload_to_cloudinary(image, folder="zedcanvas/posts")
        posts = load_posts()
        category = request.form.get("category", "").strip()
        tags_raw = request.form.get("tags", "").strip()
        tags     = [t.strip().lstrip("#").lower() for t in tags_raw.replace(",", " ").split() if t.strip()][:10]
        posts = load_posts()
        posts.append({
            "id":       str(uuid.uuid4()),
            "user_id":  me["id"],
            "caption":  caption,
            "image":    img_fname,
            "category": category,
            "tags":     tags,
            "likes":    [],
            "comments": [],
            "pinned":   False,
            "created":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        save_posts(posts)
        if caption:
            parse_mentions(caption, posts[-1]["id"], me["id"])
        check_achievements(me["id"])
        flash("Post shared! 🎨", "success")
        return redirect(url_for("feed"))
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    return render_template("create_post.html", me=me, notif_count=len(notifs), categories=ART_CATEGORIES)


@app.route("/post/<post_id>/like", methods=["POST"])
@login_required
def like_post(post_id):
    me = current_user()
    if not rate_limit(f"like:{me['id']}", 60, 60):
        return jsonify({"error": "Slow down!"}), 429
    posts = load_posts()
    post  = next((p for p in posts if p["id"] == post_id), None)
    if post:
        if me["id"] in post["likes"]:
            post["likes"].remove(me["id"]); liked = False
        else:
            post["likes"].append(me["id"]); liked = True
            add_notification(post["user_id"], me["id"], "like", post_id)
        save_posts(posts)
        check_achievements(post["user_id"])
        return jsonify({"liked": liked, "count": len(post["likes"])})
    return jsonify({"error": "Not found"}), 404


@app.route("/post/<post_id>/comment", methods=["POST"])
@login_required
def comment_post(post_id):
    me        = current_user()
    text      = sanitize(request.form.get("comment", ""), 500)
    reply_to  = request.form.get("reply_to", "").strip()  # comment id being replied to
    if not text:
        return redirect(request.referrer or url_for("feed"))
    if not rate_limit(f"comment:{me['id']}", 20, 60):
        flash("Slow down on the comments!", "error")
        return redirect(request.referrer or url_for("feed"))
    posts = load_posts()
    post  = next((p for p in posts if p["id"] == post_id), None)
    if post:
        comment = {
            "id":       str(uuid.uuid4()),
            "user_id":  me["id"],
            "username": me["username"],
            "avatar":   me["avatar"],
            "text":     text,
            "reply_to": reply_to,
            "replies":  [],
            "created":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if reply_to:
            # Find parent comment and add reply there
            parent = next((c for c in post["comments"] if c["id"] == reply_to), None)
            if parent:
                parent.setdefault("replies", []).append(comment)
                # Notify the person being replied to
                add_notification(parent["user_id"], me["id"], "reply", post_id)
            else:
                post["comments"].append(comment)
        else:
            post["comments"].append(comment)
            add_notification(post["user_id"], me["id"], "comment", post_id)
        save_posts(posts)
    return redirect(request.referrer or url_for("feed"))


@app.route("/post/<post_id>/comment/<comment_id>/delete", methods=["POST"])
@login_required
def delete_comment(post_id, comment_id):
    me    = current_user()
    posts = load_posts()
    post  = next((p for p in posts if p["id"] == post_id), None)
    if post:
        # Check top-level comments
        post["comments"] = [
            c for c in post["comments"] if not (c["id"] == comment_id and c["user_id"] == me["id"])
        ]
        # Check replies inside comments
        for c in post["comments"]:
            c["replies"] = [
                r for r in c.get("replies", [])
                if not (r["id"] == comment_id and r["user_id"] == me["id"])
            ]
        save_posts(posts)
    return redirect(request.referrer or url_for("feed"))


@app.route("/post/<post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    me    = current_user()
    posts = load_posts()
    post  = next((p for p in posts if p["id"] == post_id), None)
    if post and post["user_id"] == me["id"]:
        save_posts([p for p in posts if p["id"] != post_id])
        flash("Post deleted.", "success")
    return redirect(request.referrer or url_for("feed"))

# ════════════════════════════════════════
# PROFILES
# ════════════════════════════════════════
@app.route("/u/<username>")
@login_required
def profile(username):
    me   = current_user()
    user = get_user_by_username(username)
    if not user: return "User not found", 404
    # Track profile view
    track_profile_view(user["id"], me["id"])
    posts = sorted([p for p in load_posts() if p["user_id"] == user["id"]],
                   key=lambda p: p["created"], reverse=True)
    for p in posts:
        p["time_ago"] = time_ago(p["created"])
        p["liked"]    = me["id"] in p.get("likes", [])
    is_following = user["id"] in me["following"]
    notifs  = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    all_users = load_users()
    is_owner  = all_users and all_users[0]["id"] == me["id"]
    status    = get_online_status(user, me)
    return render_template("profile.html", user=user, posts=posts,
                           me=me, is_following=is_following,
                           notif_count=len(notifs), is_owner=is_owner,
                           online_status=status)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    me    = current_user()
    users = load_users()
    user  = next((u for u in users if u["id"] == me["id"]), None)
    if not user:
        flash("Session error. Please log in again.", "error")
        return redirect(url_for("logout"))
    if request.method == "POST":
        try:
            user["full_name"] = sanitize(request.form.get("full_name", ""), 60)
            user["bio"]       = sanitize(request.form.get("bio", ""), 300)
            user["art_style"] = sanitize(request.form.get("art_style", ""), 50)
            photo = request.files.get("photo")
            if photo and photo.filename and allowed_file(photo.filename):
                try:
                    avatar_url = upload_to_cloudinary(photo, folder="zedcanvas/avatars")
                    if avatar_url:
                        user["avatar"] = avatar_url
                except Exception as e:
                    print(f"[AVATAR ERROR] {e}")
            save_users(users)
            flash("Profile updated! ✅", "success")
            return redirect(url_for("profile", username=user["username"]))
        except Exception as e:
            print(f"[SETTINGS ERROR] {e}")
            flash("Something went wrong. Please try again.", "error")
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    return render_template("settings.html", me=me, art_styles=ART_STYLES, notif_count=len(notifs))

# ════════════════════════════════════════
# FOLLOW
# ════════════════════════════════════════
@app.route("/follow/<uid>", methods=["POST"])
@login_required
def follow(uid):
    me = current_user()
    if not rate_limit(f"follow:{me['id']}", 30, 60):
        return jsonify({"error": "Too fast! Slow down."}), 429
    users = load_users()
    me_u  = next((u for u in users if u["id"] == me["id"]), None)
    them  = next((u for u in users if u["id"] == uid), None)
    if not them or uid == me["id"]:
        return jsonify({"error": "Invalid"}), 400
    if uid in me_u["following"]:
        me_u["following"].remove(uid)
        them["followers"].remove(me["id"])
        following = False
    else:
        me_u["following"].append(uid)
        them["followers"].append(me["id"])
        following = True
        add_notification(uid, me["id"], "follow")

        # ── Auto-verify at 1k followers ──
        if len(them["followers"]) >= 1000 and not them.get("verified"):
            them["verified"] = True
            add_notification(uid, uid, "verified")
            print(f"[VERIFIED] @{them['username']} reached 1k followers!")

    save_users(users)
    return jsonify({"following": following, "follower_count": len(them["followers"])})

# ════════════════════════════════════════
# MESSAGES
# ════════════════════════════════════════
@app.route("/messages")
@login_required
def messages():
    me       = current_user()
    all_msgs = load_messages()
    users    = load_users()
    um       = {u["id"]: u for u in users}
    convos   = {}
    for msg in all_msgs:
        if me["id"] in [msg["from_id"], msg["to_id"]]:
            other_id = msg["to_id"] if msg["from_id"] == me["id"] else msg["from_id"]
            if other_id not in convos or msg["created"] > convos[other_id]["created"]:
                convos[other_id] = msg
    convo_list = sorted(convos.values(), key=lambda m: m["created"], reverse=True)
    for c in convo_list:
        other_id      = c["to_id"] if c["from_id"] == me["id"] else c["from_id"]
        c["other"]    = um.get(other_id, {})
        c["time_ago"] = time_ago(c["created"])
        c["unread"]   = not c["read"] and c["to_id"] == me["id"]
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    # Add online status to each convo
    for c in convo_list:
        c["online_status"] = get_online_status(c.get("other"), me)
    return render_template("messages.html", convos=convo_list, me=me, notif_count=len(notifs))


@app.route("/messages/<uid>", methods=["GET", "POST"])
@login_required
def conversation(uid):
    me   = current_user()
    them = get_user_by_id(uid)
    if not them: return "User not found", 404
    msgs = load_messages()
    if request.method == "POST":
        text = sanitize(request.form.get("message", ""), 1000)
        if text:
            msgs.append({
                "id":      str(uuid.uuid4()),
                "from_id": me["id"], "to_id": uid,
                "text":    text, "read": False,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            save_messages(msgs)
            add_notification(uid, me["id"], "message")
        return redirect(url_for("conversation", uid=uid))
    for m in msgs:
        if m["to_id"] == me["id"] and m["from_id"] == uid:
            m["read"] = True
    save_messages(msgs)
    thread = sorted([m for m in msgs if set([m["from_id"], m["to_id"]]) == set([me["id"], uid])],
                    key=lambda m: m["created"])
    for m in thread:
        m["time_ago"] = time_ago(m["created"])
    notifs  = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    status  = get_online_status(them, me)
    return render_template("conversation.html", them=them, thread=thread,
                           me=me, notif_count=len(notifs), online_status=status)

# ════════════════════════════════════════
# NOTIFICATIONS
# ════════════════════════════════════════
@app.route("/notifications")
@login_required
def notifications():
    me     = current_user()
    notifs = load_notifs()
    mine   = sorted([n for n in notifs if n["to_uid"] == me["id"]],
                    key=lambda n: n["created"], reverse=True)
    um     = {u["id"]: u for u in load_users()}
    for n in mine:
        n["from_user"] = um.get(n["from_uid"], {})
        n["time_ago"]  = time_ago(n["created"])
    for n in notifs:
        if n["to_uid"] == me["id"]: n["read"] = True
    save_notifs(notifs)
    return render_template("notifications.html", notifs=mine, me=me, notif_count=0)

# ════════════════════════════════════════
# ════════════════════════════════════════
# SEARCH
# ════════════════════════════════════════
@app.route("/search")
@login_required
def search():
    me      = current_user()
    query   = request.args.get("q", "").strip().lower()
    users   = load_users()
    posts   = load_posts()
    notifs  = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    results_users = []
    results_posts = []
    if query:
        results_users = [u for u in users if
                         query in u["username"].lower() or
                         query in u["full_name"].lower() or
                         query in (u.get("art_style") or "").lower()]
        um = {u["id"]: u for u in users}
        results_posts = [p for p in posts if query in (p.get("caption") or "").lower()]
        for p in results_posts:
            p["time_ago"] = time_ago(p["created"])
            p["author"]   = um.get(p["user_id"], {})
            p["liked"]    = me["id"] in p.get("likes", [])
        results_posts = sorted(results_posts, key=lambda p: p["created"], reverse=True)
    return render_template("search.html", query=query, users=results_users,
                           posts=results_posts, me=me, notif_count=len(notifs))


# ════════════════════════════════════════
# TAGS & CATEGORIES
# ════════════════════════════════════════
@app.route("/tag/<tag>")
@login_required
def tag_posts(tag):
    me    = current_user()
    posts = load_posts()
    users = load_users()
    um    = {u["id"]: u for u in users}
    tagged = [p for p in posts if tag.lower() in [t.lower() for t in p.get("tags", [])]]
    tagged = sorted(tagged, key=lambda p: p["created"], reverse=True)
    for p in tagged:
        p["time_ago"] = time_ago(p["created"])
        p["author"]   = um.get(p["user_id"], {})
        p["liked"]    = me["id"] in p.get("likes", [])
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    return render_template("tag_posts.html", tag=tag, posts=tagged, me=me, notif_count=len(notifs))


@app.route("/category/<path:category>")
@login_required
def category_posts(category):
    me    = current_user()
    posts = load_posts()
    users = load_users()
    um    = {u["id"]: u for u in users}
    filtered = [p for p in posts if (p.get("category") or "").lower() == category.lower()]
    filtered = sorted(filtered, key=lambda p: p["created"], reverse=True)
    for p in filtered:
        p["time_ago"] = time_ago(p["created"])
        p["author"]   = um.get(p["user_id"], {})
        p["liked"]    = me["id"] in p.get("likes", [])
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    return render_template("tag_posts.html", tag=category, posts=filtered, me=me, notif_count=len(notifs))


# ════════════════════════════════════════
# PIN POST
# ════════════════════════════════════════
@app.route("/post/<post_id>/pin", methods=["POST"])
@login_required
def pin_post(post_id):
    me    = current_user()
    posts = load_posts()
    # Unpin all my posts first
    for p in posts:
        if p["user_id"] == me["id"]:
            p["pinned"] = False
    # Pin the selected one
    post = next((p for p in posts if p["id"] == post_id and p["user_id"] == me["id"]), None)
    if post:
        post["pinned"] = True
        flash("Post pinned to your profile! 📌", "success")
    save_posts(posts)
    return redirect(request.referrer or url_for("profile", username=me["username"]))


@app.route("/post/<post_id>/unpin", methods=["POST"])
@login_required
def unpin_post(post_id):
    me    = current_user()
    posts = load_posts()
    post  = next((p for p in posts if p["id"] == post_id and p["user_id"] == me["id"]), None)
    if post:
        post["pinned"] = False
        flash("Post unpinned.", "success")
    save_posts(posts)
    return redirect(request.referrer or url_for("profile", username=me["username"]))

# ════════════════════════════════════════
# BOOKMARKS
# ════════════════════════════════════════
def load_bookmarks(): return db_load("bookmarks")
def save_bookmarks(d): db_save_all("bookmarks", d)

@app.route("/post/<post_id>/bookmark", methods=["POST"])
@login_required
def bookmark_post(post_id):
    me        = current_user()
    bookmarks = load_bookmarks()
    existing  = next((b for b in bookmarks if b["user_id"] == me["id"] and b["post_id"] == post_id), None)
    if existing:
        bookmarks = [b for b in bookmarks if not (b["user_id"] == me["id"] and b["post_id"] == post_id)]
        saved = False
    else:
        bookmarks.append({
            "user_id": me["id"], "post_id": post_id,
            "saved_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        saved = True
    save_bookmarks(bookmarks)
    return jsonify({"saved": saved})

@app.route("/bookmarks")
@login_required
def bookmarks():
    me        = current_user()
    all_b     = load_bookmarks()
    my_b      = [b["post_id"] for b in all_b if b["user_id"] == me["id"]]
    posts     = load_posts()
    users     = load_users()
    um        = {u["id"]: u for u in users}
    saved     = [p for p in posts if p["id"] in my_b]
    saved     = sorted(saved, key=lambda p: p["created"], reverse=True)
    for p in saved:
        p["time_ago"] = time_ago(p["created"])
        p["author"]   = um.get(p["user_id"], {})
        p["liked"]    = me["id"] in p.get("likes", [])
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    return render_template("bookmarks.html", posts=saved, me=me, notif_count=len(notifs))

# ════════════════════════════════════════
# FORGOT PASSWORD
# ════════════════════════════════════════
def load_resets():  return db_load("resets")
def save_resets(d): db_save_all("resets", d)

def send_reset_email(email, username, token):
    try:
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = "Reset your ZedCanvas password"
        msg["From"]    = EMAIL_ADDRESS
        msg["To"]      = email
        reset_link = f"http://127.0.0.1:8080/reset-password/{token}"
        html = f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;background:#f8f8f8;
                    border-radius:12px;overflow:hidden;border:1px solid #e2e2e2;">
          <div style="background:#0a0a0a;padding:2rem;text-align:center;">
            <h1 style="color:#f8f8f8;font-size:1.8rem;margin:0;letter-spacing:0.05em;">ZedCanvas</h1>
            <p style="color:#888;margin:0.4rem 0 0;font-size:0.85rem;">Password Reset 🔐</p>
          </div>
          <div style="padding:2rem;text-align:center;">
            <h2 style="color:#0a0a0a;font-size:1.1rem;margin-bottom:0.5rem;">
              Hey @{username}, reset your password
            </h2>
            <p style="color:#666;font-size:0.9rem;margin-bottom:1.5rem;line-height:1.6;">
              We received a request to reset your password.<br/>
              Click the button below to set a new one.
            </p>
            <a href="{reset_link}"
               style="display:inline-block;background:#0a0a0a;color:#f8f8f8;
                      padding:0.85rem 2rem;border-radius:10px;text-decoration:none;
                      font-weight:700;font-size:0.95rem;margin-bottom:1.5rem;">
              Reset Password
            </a>
            <p style="color:#aaa;font-size:0.78rem;line-height:1.6;">
              This link expires in <strong>30 minutes</strong>.<br/>
              If you didn't request this, ignore this email — your account is safe.
            </p>
          </div>
        </div>"""
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, email, msg.as_string())
        print(f"[EMAIL SENT] Password reset to {email}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR - Skipping] {e}")
        return False


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user  = get_user_by_email(email)
        # Always show success msg (don't reveal if email exists)
        if user:
            try:
                token   = uuid.uuid4().hex
                expires = (datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
                resets  = [r for r in load_resets() if r["email"] != email]
                resets.append({"email": email, "token": token, "expires": expires, "used": False})
                save_resets(resets)
                send_reset_email(email, user["username"], token)
            except Exception as e:
                print(f"[RESET EMAIL ERROR] {e}")
        flash("If that email is registered, a reset link has been sent! 📧", "success")
        return redirect(url_for("forgot_password"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    resets = load_resets()
    entry  = next((r for r in resets if r["token"] == token and not r["used"]), None)
    if not entry:
        flash("This reset link is invalid or has already been used.", "error")
        return redirect(url_for("login"))
    if datetime.strptime(entry["expires"], "%Y-%m-%d %H:%M:%S") < datetime.now():
        flash("This reset link has expired. Please request a new one.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "").strip()
        confirm  = request.form.get("confirm", "").strip()
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("reset_password.html", token=token)
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html", token=token)
        # Update password
        users = load_users()
        user  = next((u for u in users if u["email"] == entry["email"]), None)
        if user:
            user["password"] = generate_password_hash(password)
            save_users(users)
        # Mark token as used
        entry["used"] = True
        save_resets(resets)
        flash("Password updated successfully! Please log in. 🎨", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)


# ════════════════════════════════════════
# ANALYTICS & VERIFIED BADGE
# ════════════════════════════════════════
def load_views():  return db_load("profile_views")
def save_views(d): db_save_all("profile_views", d)

def track_profile_view(profile_uid, viewer_uid):
    if profile_uid == viewer_uid: return
    views = load_views()
    views.append({
        "profile_uid": profile_uid,
        "viewer_uid":  viewer_uid,
        "viewed_on":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    # Keep only last 1000 views
    if len(views) > 1000: views = views[-1000:]
    save_views(views)

@app.route("/analytics")
@login_required
def analytics():
    me       = current_user()
    posts    = [p for p in load_posts() if p["user_id"] == me["id"]]
    views    = load_views()
    notifs   = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    users    = load_users()
    um       = {u["id"]: u for u in users}

    # Stats
    total_likes    = sum(len(p.get("likes", [])) for p in posts)
    total_comments = sum(len(p.get("comments", [])) for p in posts)
    total_posts    = len(posts)
    followers      = len(me.get("followers", []))
    following      = len(me.get("following", []))

    # Profile views — last 30 days
    from datetime import timedelta
    cutoff     = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    my_views   = [v for v in views if v["profile_uid"] == me["id"] and v["viewed_on"] >= cutoff]
    total_views = len(my_views)

    # Views per day (last 7 days)
    days_data = []
    for i in range(6, -1, -1):
        day     = datetime.now() - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        count   = sum(1 for v in my_views if v["viewed_on"].startswith(day_str))
        days_data.append({"day": day.strftime("%a"), "count": count})

    # Recent viewers
    seen = set()
    recent_viewers = []
    for v in reversed(my_views):
        if v["viewer_uid"] not in seen:
            seen.add(v["viewer_uid"])
            viewer = um.get(v["viewer_uid"])
            if viewer:
                recent_viewers.append(viewer)
        if len(recent_viewers) >= 6: break

    # Top posts by likes
    top_posts = sorted(posts, key=lambda p: len(p.get("likes", [])), reverse=True)[:3]

    return render_template("analytics.html",
        me=me, notif_count=len(notifs),
        total_likes=total_likes, total_comments=total_comments,
        total_posts=total_posts, followers=followers,
        following=following, total_views=total_views,
        days_data=days_data, recent_viewers=recent_viewers,
        top_posts=top_posts)


# Admin — grant/revoke verified badge
@app.route("/admin/verify/<uid>", methods=["POST"])
@login_required
def toggle_verified(uid):
    me = current_user()
    # Only allow the first registered user (owner) to verify others
    users    = load_users()
    if not users or users[0]["id"] != me["id"]:
        flash("Only the platform owner can verify artists.", "error")
        return redirect(request.referrer or url_for("feed"))
    user = next((u for u in users if u["id"] == uid), None)
    if user:
        user["verified"] = not user.get("verified", False)
        save_users(users)
        status = "verified ✅" if user["verified"] else "unverified"
        flash(f"@{user['username']} is now {status}!", "success")
    return redirect(request.referrer or url_for("profile", username=user["username"]))


# ════════════════════════════════════════
# REPOSTS
# ════════════════════════════════════════
@app.route("/post/<post_id>/repost", methods=["POST"])
@login_required
def repost(post_id):
    me    = current_user()
    if not rate_limit(f"repost:{me['id']}", 20, 60):
        return jsonify({"error": "Slow down!"}), 429
    posts = load_posts()
    orig  = next((p for p in posts if p["id"] == post_id), None)
    if not orig:
        return jsonify({"error": "Post not found"}), 404
    if orig["user_id"] == me["id"]:
        return jsonify({"error": "Cannot repost your own post"}), 400

    # Check if already reposted
    existing = next((p for p in posts if
                     p.get("repost_of") == post_id and
                     p["user_id"] == me["id"]), None)
    if existing:
        # Undo repost
        posts = [p for p in posts if not (p.get("repost_of") == post_id and p["user_id"] == me["id"])]
        save_posts(posts)
        return jsonify({"reposted": False})
    else:
        # Create repost
        posts.append({
            "id":        str(uuid.uuid4()),
            "user_id":   me["id"],
            "repost_of": post_id,
            "caption":   "",
            "image":     orig.get("image", ""),
            "category":  orig.get("category", ""),
            "tags":      orig.get("tags", []),
            "likes":     [],
            "comments":  [],
            "pinned":    False,
            "created":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        save_posts(posts)
        add_notification(orig["user_id"], me["id"], "repost", post_id)
        return jsonify({"reposted": True})


# ════════════════════════════════════════
# STORIES
# ════════════════════════════════════════
def load_stories():  return db_load("stories")
def save_stories(d): db_save_all("stories", d)

def get_active_stories():
    """Return only stories less than 24 hours old."""
    stories = load_stories()
    cutoff  = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    active  = [s for s in stories if s["created"] >= cutoff]
    if len(active) != len(stories):
        save_stories(active)
    return active


@app.route("/stories/create", methods=["GET", "POST"])
@login_required
def create_story():
    me = current_user()
    if request.method == "POST":
        if not rate_limit(f"story:{me['id']}", 10, 3600):
            flash("Max 10 stories per hour.", "error")
            return redirect(url_for("feed"))
        image   = request.files.get("image")
        caption = sanitize(request.form.get("caption", ""), 200)
        if not image or not image.filename:
            flash("Please upload an image for your story.", "error")
            return redirect(url_for("feed"))
        img_fname = upload_to_cloudinary(image, folder="zedcanvas/stories")
        if not img_fname:
            flash("Invalid image file.", "error")
            return redirect(url_for("feed"))
        stories = load_stories()
        stories.append({
            "id":       str(uuid.uuid4()),
            "user_id":  me["id"],
            "username": me["username"],
            "avatar":   me["avatar"],
            "image":    img_fname,
            "caption":  caption,
            "views":    [],
            "created":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        save_stories(stories)
        flash("Story posted! It disappears in 24 hours 📷", "success")
        return redirect(url_for("feed"))
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    return render_template("create_story.html", me=me, notif_count=len(notifs))


@app.route("/stories/<story_id>")
@login_required
def view_story(story_id):
    me      = current_user()
    stories = get_active_stories()
    story   = next((s for s in stories if s["id"] == story_id), None)
    if not story:
        flash("Story has expired or not found.", "error")
        return redirect(url_for("feed"))
    # Track view
    if me["id"] not in story["views"]:
        story["views"].append(me["id"])
        save_stories(stories)
    # Get prev/next story for swiping
    users   = load_users()
    um      = {u["id"]: u for u in users}
    story["author"] = um.get(story["user_id"], {})
    # Group stories by user, get adjacent
    all_ids = [s["id"] for s in stories]
    idx     = all_ids.index(story_id) if story_id in all_ids else 0
    prev_id = all_ids[idx - 1] if idx > 0 else None
    next_id = all_ids[idx + 1] if idx < len(all_ids) - 1 else None
    # Viewers (only shown to story owner)
    viewers = []
    if story["user_id"] == me["id"]:
        viewers = [um.get(uid, {}) for uid in story["views"] if uid != me["id"]]
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    return render_template("view_story.html", story=story, me=me,
                           prev_id=prev_id, next_id=next_id,
                           viewers=viewers, notif_count=len(notifs))


@app.route("/stories/<story_id>/delete", methods=["POST"])
@login_required
def delete_story(story_id):
    me      = current_user()
    stories = load_stories()
    stories = [s for s in stories if not (s["id"] == story_id and s["user_id"] == me["id"])]
    save_stories(stories)
    flash("Story deleted.", "success")
    return redirect(url_for("feed"))


# ════════════════════════════════════════
# ART MARKETPLACE
# ════════════════════════════════════════
def load_listings():  return db_load("listings")
def save_listings(d): db_save_all("listings", d)


@app.route("/marketplace")
@login_required
def marketplace():
    me       = current_user()
    listings = load_listings()
    users    = load_users()
    posts    = load_posts()
    um       = {u["id"]: u for u in users}
    pm       = {p["id"]: p for p in posts}
    category = request.args.get("cat", "").strip()
    sort     = request.args.get("sort", "newest")
    # Filter
    active = [l for l in listings if l["status"] == "available"]
    if category:
        active = [l for l in active if l.get("category", "").lower() == category.lower()]
    # Sort
    if sort == "price_low":
        active = sorted(active, key=lambda l: float(l.get("price", 0)))
    elif sort == "price_high":
        active = sorted(active, key=lambda l: float(l.get("price", 0)), reverse=True)
    else:
        active = sorted(active, key=lambda l: l["created"], reverse=True)
    for l in active:
        l["seller"]   = um.get(l["user_id"], {})
        l["post"]     = pm.get(l.get("post_id", ""), {})
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    return render_template("marketplace.html", listings=active, me=me,
                           notif_count=len(notifs), categories=ART_CATEGORIES,
                           active_cat=category, sort=sort)


@app.route("/marketplace/sell", methods=["GET", "POST"])
@login_required
def sell_artwork():
    me    = current_user()
    posts = load_posts()
    # Only show user's own posts that aren't already listed
    listings    = load_listings()
    listed_ids  = {l["post_id"] for l in listings if l["user_id"] == me["id"] and l["status"] == "available"}
    my_posts    = [p for p in posts if p["user_id"] == me["id"] and p.get("image") and p["id"] not in listed_ids]
    if request.method == "POST":
        post_id     = request.form.get("post_id", "").strip()
        price       = request.form.get("price", "").strip()
        currency    = request.form.get("currency", "ZMW").strip()
        description = sanitize(request.form.get("description", ""), 500)
        category    = sanitize(request.form.get("category", ""), 50)
        if not post_id or not price:
            flash("Please select a post and set a price.", "error")
            notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
            return render_template("sell_artwork.html", me=me, my_posts=my_posts,
                                   notif_count=len(notifs), categories=ART_CATEGORIES)
        try:
            price = float(price)
            if price <= 0: raise ValueError
        except:
            flash("Please enter a valid price.", "error")
            return redirect(request.url)
        # Find the post
        post = next((p for p in posts if p["id"] == post_id), None)
        if not post or post["user_id"] != me["id"]:
            flash("Invalid post.", "error")
            return redirect(request.url)
        listings = load_listings()
        listings.append({
            "id":          str(uuid.uuid4()),
            "user_id":     me["id"],
            "post_id":     post_id,
            "title":       sanitize(request.form.get("title", post.get("caption", "Artwork")[:50]), 80),
            "description": description,
            "price":       price,
            "currency":    currency,
            "category":    category,
            "status":      "available",
            "created":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        save_listings(listings)
        flash("Your artwork is now listed for sale! 🛒", "success")
        return redirect(url_for("marketplace"))
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    return render_template("sell_artwork.html", me=me, my_posts=my_posts,
                           notif_count=len(notifs), categories=ART_CATEGORIES)


@app.route("/marketplace/listing/<lid>")
@login_required
def listing_detail(lid):
    me       = current_user()
    listings = load_listings()
    listing  = next((l for l in listings if l["id"] == lid), None)
    if not listing: return "Listing not found", 404
    users    = load_users()
    posts    = load_posts()
    um       = {u["id"]: u for u in users}
    pm       = {p["id"]: p for p in posts}
    listing["seller"] = um.get(listing["user_id"], {})
    listing["post"]   = pm.get(listing.get("post_id", ""), {})
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    return render_template("listing_detail.html", listing=listing,
                           me=me, notif_count=len(notifs))


@app.route("/marketplace/listing/<lid>/sold", methods=["POST"])
@login_required
def mark_sold(lid):
    me       = current_user()
    listings = load_listings()
    listing  = next((l for l in listings if l["id"] == lid and l["user_id"] == me["id"]), None)
    if listing:
        listing["status"] = "sold"
        save_listings(listings)
        flash("Marked as sold! Congratulations! 🎉", "success")
    return redirect(url_for("marketplace"))


@app.route("/marketplace/listing/<lid>/delete", methods=["POST"])
@login_required
def delete_listing(lid):
    me       = current_user()
    listings = load_listings()
    listings = [l for l in listings if not (l["id"] == lid and l["user_id"] == me["id"])]
    save_listings(listings)
    flash("Listing removed.", "success")
    return redirect(url_for("marketplace"))


# ════════════════════════════════════════
# POLLS
# ════════════════════════════════════════
@app.route("/polls/create", methods=["GET", "POST"])
@login_required
def create_poll():
    me = current_user()
    if request.method == "POST":
        question = sanitize(request.form.get("question", ""), 200)
        options  = []
        for i in range(1, 5):
            opt = sanitize(request.form.get(f"option{i}", ""), 100)
            if opt: options.append(opt)
        if not question or len(options) < 2:
            flash("Please add a question and at least 2 options.", "error")
            notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
            return render_template("create_poll.html", me=me, notif_count=len(notifs))
        duration = int(request.form.get("duration", 24))
        expires  = (datetime.now() + timedelta(hours=duration)).strftime("%Y-%m-%d %H:%M:%S")
        posts    = load_posts()
        poll_id  = str(uuid.uuid4())
        posts.append({
            "id":       poll_id,
            "user_id":  me["id"],
            "caption":  question,
            "image":    "",
            "category": "",
            "tags":     [],
            "likes":    [],
            "comments": [],
            "pinned":   False,
            "is_poll":  True,
            "poll": {
                "question": question,
                "options":  [{"text": o, "votes": []} for o in options],
                "expires":  expires,
            },
            "created":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        save_posts(posts)
        parse_mentions(question, poll_id, me["id"])
        flash("Poll posted! 🗳️", "success")
        return redirect(url_for("feed"))
    notifs = [n for n in load_notifs() if n["to_uid"] == me["id"] and not n["read"]]
    return render_template("create_poll.html", me=me, notif_count=len(notifs))


@app.route("/polls/<post_id>/vote", methods=["POST"])
@login_required
def vote_poll(post_id):
    me       = current_user()
    option_i = int(request.form.get("option", 0))
    posts    = load_posts()
    post     = next((p for p in posts if p["id"] == post_id and p.get("is_poll")), None)
    if not post:
        return jsonify({"error": "Poll not found"}), 404
    # Check if expired
    expires = post["poll"].get("expires", "")
    if expires and datetime.strptime(expires, "%Y-%m-%d %H:%M:%S") < datetime.now():
        return jsonify({"error": "Poll has ended"}), 400
    # Remove existing vote from all options
    for opt in post["poll"]["options"]:
        if me["id"] in opt["votes"]:
            opt["votes"].remove(me["id"])
    # Add new vote
    if 0 <= option_i < len(post["poll"]["options"]):
        post["poll"]["options"][option_i]["votes"].append(me["id"])
    save_posts(posts)
    # Return updated results
    total  = sum(len(o["votes"]) for o in post["poll"]["options"])
    results = []
    for i, o in enumerate(post["poll"]["options"]):
        pct = round(len(o["votes"]) / total * 100) if total > 0 else 0
        results.append({"text": o["text"], "votes": len(o["votes"]), "pct": pct,
                         "voted": me["id"] in o["votes"]})
    return jsonify({"results": results, "total": total})



if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8080)
