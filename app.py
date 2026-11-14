"""Role-based WhatsApp-first boutique storefront."""
import os
import re
import secrets
import sqlite3
from pathlib import Path
from functools import wraps
from urllib.parse import urlencode, urlparse

from dotenv import load_dotenv
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
SEED = [
    ("The Solstice Dress", "dresses", "A soft, flowing silhouette for slow mornings and special evenings.", 2499, "https://images.unsplash.com/photo-1595777457583-95e059d581b8?auto=format&fit=crop&w=1000&q=85", "Bestseller", 1),
    ("The Linen Edit", "dresses", "Easy tailoring and breathable texture, made for everyday elegance.", 1899, "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?auto=format&fit=crop&w=1000&q=85", "New arrival", 1),
    ("The Evening Muse", "dresses", "A graceful statement piece with a timeless, understated finish.", 3299, "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=1000&q=85", "Limited edit", 0),
    ("The Heritage Watch", "watches", "A refined everyday timepiece with a clean, classic dial.", 4199, "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=1000&q=85", "Bestseller", 1),
    ("The Minimalist", "watches", "Quiet details, versatile proportions and effortless styling.", 3599, "https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=1000&q=85", "New arrival", 1),
    ("The Modern Classic", "watches", "A considered accent for workdays, weekends and everything between.", 5299, "https://images.unsplash.com/photo-1508057198894-247b23fe5ade?auto=format&fit=crop&w=1000&q=85", "Curated pick", 0),
]
IMAGE_HOSTS = {"images.unsplash.com", "images.pexels.com", "res.cloudinary.com"}


def valid_password(value):
    return (
        len(value) >= 12
        and re.search(r"[a-z]", value)
        and re.search(r"[A-Z]", value)
        and re.search(r"\d", value)
        and re.search(r"[^A-Za-z0-9]", value)
    )


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY") or ("local-only-change-this-secret" if os.getenv("APP_ENV") != "production" else ""),
        DATABASE=os.getenv("DATABASE_PATH", str(ROOT / "store.db")),
        INITIAL_SETUP_TOKEN=os.getenv("INITIAL_SETUP_TOKEN", ""),
        WHATSAPP_NUMBER=re.sub(r"\D", "", os.getenv("WHATSAPP_NUMBER", "")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "true").lower() == "true",
        PERMANENT_SESSION_LIFETIME=3600,
        SESSION_REFRESH_EACH_REQUEST=True,
        MAX_CONTENT_LENGTH=1024 * 1024,
        RATELIMIT_STORAGE_URI=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("Set SECRET_KEY before production startup.")

    CSRFProtect(app)
    limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri=app.config["RATELIMIT_STORAGE_URI"])

    def connect():
        conn = sqlite3.connect(app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def init_db():
        Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
        conn = connect()
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS products(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL CHECK(length(name) BETWEEN 2 AND 80),
                category TEXT NOT NULL CHECK(category IN ('dresses','watches')),
                description TEXT NOT NULL CHECK(length(description) BETWEEN 5 AND 240),
                price_paise INTEGER NOT NULL CHECK(price_paise BETWEEN 1 AND 100000000),
                image_url TEXT NOT NULL, tag TEXT NOT NULL DEFAULT '',
                featured INTEGER NOT NULL DEFAULT 0 CHECK(featured IN (0,1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
                conn.executemany(
                    "INSERT INTO products(name,category,description,price_paise,image_url,tag,featured) VALUES(?,?,?,?,?,?,?)",
                    [(n, c, d, p * 100, img, tag, featured) for n, c, d, p, img, tag, featured in SEED],
                )
            conn.execute("""CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('superadmin','admin')),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
                created_by INTEGER REFERENCES users(id),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS enquiries(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                product_name TEXT NOT NULL,
                product_price_paise INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                customer_message TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','contacted','closed')),
                internal_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_enquiries_created ON enquiries(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_enquiries_status ON enquiries(status)")
            conn.commit()
        finally:
            conn.close()

    def db():
        if "db" not in g:
            g.db = connect()
        return g.db

    @app.teardown_appcontext
    def close_db(_error=None):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    def current_user():
        if not getattr(g, "_user_loaded", False):
            g._user_loaded = True
            g.current_user = None
            user_id = session.get("user_id")
            if user_id:
                user = db().execute("SELECT id,username,role,is_active FROM users WHERE id=?", (user_id,)).fetchone()
                if user and user["is_active"]:
                    g.current_user = user
                else:
                    session.clear()
        return g.current_user

    def role_required(*roles):
        def decorator(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                user = current_user()
                if user is None:
                    return redirect(url_for("login_page", next=request.path))
                if user["role"] not in roles:
                    abort(403)
                return fn(*args, **kwargs)
            return wrapped
        return decorator

    def superadmin_exists():
        return db().execute("SELECT 1 FROM users WHERE role='superadmin' LIMIT 1").fetchone() is not None

    def wa_link(name, price, customer_name="", customer_phone="", customer_message=""):
        number = app.config["WHATSAPP_NUMBER"]
        if not 8 <= len(number) <= 15:
            return None
        msg = (
            f"Hello! I'm {customer_name or 'interested'} and would like to enquire about "
            f"{name} (₹{price / 100:,.2f})."
        )
        if customer_phone:
            msg += f" My contact number is {customer_phone}."
        if customer_message:
            msg += f" Message: {customer_message}"
        msg += " Please share availability and details."
        return "https://wa.me/" + number + "?" + urlencode({"text": msg})

    app.jinja_env.globals["whatsapp_link"] = wa_link
    app.jinja_env.globals["whatsapp_ready"] = lambda: 8 <= len(app.config["WHATSAPP_NUMBER"]) <= 15
    app.jinja_env.globals["current_user"] = current_user

    @app.after_request
    def security_headers(resp):
        resp.headers.update({
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Content-Security-Policy": "default-src 'self'; img-src 'self' https://images.unsplash.com https://images.pexels.com https://res.cloudinary.com data:; style-src 'self'; script-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
        })
        if request.path.startswith(("/admin", "/superadmin", "/login", "/setup")):
            resp.headers["Cache-Control"] = "no-store, private"
        if request.is_secure:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return resp

    @app.get("/")
    def home():
        products = db().execute("SELECT * FROM products ORDER BY featured DESC,id DESC").fetchall()
        return render_template("index.html", products=products)

    @app.get("/product/<int:pid>")
    def product_detail(pid):
        product = db().execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if product is None:
            abort(404)
        return render_template("product.html", product=product)

    @app.route("/setup", methods=["GET", "POST"])
    @limiter.limit("5 per hour")
    def first_run_setup():
        if superadmin_exists():
            return render_template("error.html", code=410, message="Initial setup has already been completed. Please sign in."), 410
        setup_token = app.config["INITIAL_SETUP_TOKEN"]
        if not setup_token:
            abort(503, description="Initial setup token is not configured. Set INITIAL_SETUP_TOKEN in hosting settings.")
        if request.method == "POST":
            submitted = request.form.get("setup_token", "")
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            if not secrets.compare_digest(submitted, setup_token):
                flash("The first-run setup token is not correct.", "error")
            elif not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", username):
                flash("Username must be 3–40 characters (letters, numbers, dot, underscore or hyphen).", "error")
            elif not valid_password(password):
                flash("Use at least 12 characters with uppercase, lowercase, a number and a symbol.", "error")
            elif password != confirm:
                flash("The password confirmation does not match.", "error")
            else:
                try:
                    db().execute(
                        "INSERT INTO users(username,password_hash,role) VALUES(?,?,'superadmin')",
                        (username, generate_password_hash(password)),
                    )
                    db().commit()
                except sqlite3.IntegrityError:
                    flash("That username is already in use.", "error")
                else:
                    session.clear()
                    user = db().execute("SELECT id,username,role,is_active FROM users WHERE username=?", (username,)).fetchone()
                    session["user_id"] = user["id"]
                    session.permanent = True
                    flash("Super Admin account created. Remove INITIAL_SETUP_TOKEN from hosting settings now.", "success")
                    return redirect(url_for("superadmin_dashboard"))
        return render_template("setup.html")

    @app.get("/login")
    @app.get("/admin/login")
    def login_page():
        return render_template("login.html")

    @app.post("/login")
    @app.post("/admin/login")
    @limiter.limit("5 per minute")
    def login_post():
        username = request.form.get("username", "").strip()[:80]
        password = request.form.get("password", "")[:256]
        user = db().execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
        valid = bool(user and user["is_active"] and check_password_hash(user["password_hash"], password))
        if not valid:
            flash("The sign-in details were not recognised.", "error")
            return render_template("login.html"), 401
        session.clear()
        session["user_id"] = user["id"]
        session.permanent = True
        target = url_for("superadmin_dashboard") if user["role"] == "superadmin" else url_for("admin_dashboard")
        return redirect(target)

    @app.post("/logout")
    @app.post("/admin/logout")
    def logout():
        current_user()
        if not session.get("user_id"):
            return redirect(url_for("home"))
        session.clear()
        flash("You have been signed out.", "success")
        return redirect(url_for("home"))

    @app.post("/enquire/<int:pid>")
    @limiter.limit("5 per minute")
    def create_enquiry(pid):
        product = db().execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if product is None:
            abort(404)
        # Honeypot field: real customers leave this hidden field blank.
        if request.form.get("website", "").strip():
            abort(400)
        name = request.form.get("customer_name", "").strip()[:80]
        phone_raw = request.form.get("customer_phone", "").strip()
        phone = re.sub(r"[^\d]", "", phone_raw)
        message = request.form.get("customer_message", "").strip()[:500]
        if not 2 <= len(name) <= 80:
            flash("Please enter your name.", "error")
            return redirect(url_for("product_detail", pid=pid) + "#enquiry")
        if not 10 <= len(phone) <= 15:
            flash("Please enter a valid phone number including country code.", "error")
            return redirect(url_for("product_detail", pid=pid) + "#enquiry")
        db().execute(
            """INSERT INTO enquiries(product_id,product_name,product_price_paise,customer_name,customer_phone,customer_message)
               VALUES(?,?,?,?,?,?)""",
            (pid, product["name"], product["price_paise"], name, phone, message),
        )
        db().commit()
        link = wa_link(product["name"], product["price_paise"], name, phone, message)
        if not link:
            flash("Your enquiry has been saved. The shop WhatsApp number is not configured yet.", "success")
            return redirect(url_for("product_detail", pid=pid) + "#enquiry")
        return redirect(link, code=302)

    @app.get("/admin")
    @role_required("admin", "superadmin")
    def admin_dashboard():
        products = db().execute("SELECT * FROM products ORDER BY id DESC").fetchall()
        enquiries = db().execute("SELECT * FROM enquiries ORDER BY CASE status WHEN 'new' THEN 0 WHEN 'contacted' THEN 1 ELSE 2 END, id DESC LIMIT 100").fetchall()
        counts = {
            "products": db().execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "new": db().execute("SELECT COUNT(*) FROM enquiries WHERE status='new'").fetchone()[0],
            "contacted": db().execute("SELECT COUNT(*) FROM enquiries WHERE status='contacted'").fetchone()[0],
            "closed": db().execute("SELECT COUNT(*) FROM enquiries WHERE status='closed'").fetchone()[0],
        }
        return render_template("admin.html", products=products, enquiries=enquiries, counts=counts)

    @app.get("/superadmin")
    @role_required("superadmin")
    def superadmin_dashboard():
        admins = db().execute("SELECT id,username,is_active,created_at FROM users WHERE role='admin' ORDER BY id DESC").fetchall()
        counts = {
            "products": db().execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "admins": db().execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0],
            "new": db().execute("SELECT COUNT(*) FROM enquiries WHERE status='new'").fetchone()[0],
            "all_enquiries": db().execute("SELECT COUNT(*) FROM enquiries").fetchone()[0],
        }
        recent = db().execute("SELECT * FROM enquiries ORDER BY id DESC LIMIT 8").fetchall()
        return render_template("superadmin.html", admins=admins, counts=counts, recent=recent)

    @app.post("/superadmin/admins/new")
    @role_required("superadmin")
    @limiter.limit("10 per hour")
    def create_admin():
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", username):
            flash("Username must be 3–40 characters (letters, numbers, dot, underscore or hyphen).", "error")
        elif not valid_password(password):
            flash("Use at least 12 characters with uppercase, lowercase, a number and a symbol.", "error")
        else:
            try:
                db().execute(
                    "INSERT INTO users(username,password_hash,role,created_by) VALUES(?,?,'admin',?)",
                    (username, generate_password_hash(password), current_user()["id"]),
                )
                db().commit()
                flash("Admin account created. Share the username and temporary password with the staff member securely.", "success")
            except sqlite3.IntegrityError:
                flash("That username already exists.", "error")
        return redirect(url_for("superadmin_dashboard"))

    @app.post("/superadmin/admins/<int:uid>/password")
    @role_required("superadmin")
    @limiter.limit("10 per hour")
    def reset_admin_password(uid):
        password = request.form.get("password", "")
        if not valid_password(password):
            flash("Use at least 12 characters with uppercase, lowercase, a number and a symbol.", "error")
        else:
            result = db().execute(
                "UPDATE users SET password_hash=? WHERE id=? AND role='admin'",
                (generate_password_hash(password), uid),
            )
            db().commit()
            flash("Admin password reset." if result.rowcount else "Admin account not found.", "success" if result.rowcount else "error")
        return redirect(url_for("superadmin_dashboard"))

    @app.post("/superadmin/admins/<int:uid>/toggle")
    @role_required("superadmin")
    def toggle_admin(uid):
        result = db().execute(
            "UPDATE users SET is_active=CASE WHEN is_active=1 THEN 0 ELSE 1 END WHERE id=? AND role='admin'",
            (uid,),
        )
        db().commit()
        flash("Admin account status updated." if result.rowcount else "Admin account not found.", "success" if result.rowcount else "error")
        return redirect(url_for("superadmin_dashboard"))

    def product_form_values():
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        desc = request.form.get("description", "").strip()
        tag = request.form.get("tag", "").strip()[:30]
        image = request.form.get("image_url", "").strip()
        try:
            price = round(float(request.form.get("price", "")) * 100)
        except (TypeError, ValueError):
            price = 0
        parsed = urlparse(image)
        if not 2 <= len(name) <= 80:
            raise ValueError("Product name must be 2–80 characters.")
        if category not in {"dresses", "watches"}:
            raise ValueError("Choose Dresses or Watches.")
        if not 5 <= len(desc) <= 240:
            raise ValueError("Description must be 5–240 characters.")
        if not 1 <= price <= 100000000:
            raise ValueError("Enter a valid INR price.")
        if parsed.scheme != "https" or parsed.hostname not in IMAGE_HOSTS or parsed.username or parsed.password:
            raise ValueError("Use an HTTPS image from Unsplash, Pexels or Cloudinary.")
        return (name, category, desc, price, image, tag, 1 if request.form.get("featured") == "on" else 0)

    @app.route("/admin/products/new", methods=["GET", "POST"])
    @role_required("admin", "superadmin")
    def product_new():
        if request.method == "POST":
            try:
                db().execute("INSERT INTO products(name,category,description,price_paise,image_url,tag,featured) VALUES(?,?,?,?,?,?,?)", product_form_values())
                db().commit()
                flash("Product added to your shop.", "success")
                return redirect(url_for("admin_dashboard"))
            except ValueError as exc:
                flash(str(exc), "error")
        return render_template("product_form.html", product=None)

    @app.route("/admin/products/<int:pid>/edit", methods=["GET", "POST"])
    @role_required("admin", "superadmin")
    def product_edit(pid):
        product = db().execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        if product is None:
            abort(404)
        if request.method == "POST":
            try:
                db().execute(
                    "UPDATE products SET name=?,category=?,description=?,price_paise=?,image_url=?,tag=?,featured=? WHERE id=?",
                    product_form_values() + (pid,),
                )
                db().commit()
                flash("Product updated.", "success")
                return redirect(url_for("admin_dashboard"))
            except ValueError as exc:
                flash(str(exc), "error")
        return render_template("product_form.html", product=product)

    @app.post("/admin/products/<int:pid>/delete")
    @role_required("admin", "superadmin")
    def product_delete(pid):
        db().execute("DELETE FROM products WHERE id=?", (pid,))
        db().commit()
        flash("Product removed.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/enquiries/<int:eid>/update")
    @role_required("admin", "superadmin")
    def update_enquiry(eid):
        status = request.form.get("status", "")
        note = request.form.get("internal_note", "").strip()[:500]
        if status not in {"new", "contacted", "closed"}:
            abort(400)
        result = db().execute("UPDATE enquiries SET status=?,internal_note=? WHERE id=?", (status, note, eid))
        db().commit()
        flash("Enquiry updated." if result.rowcount else "Enquiry not found.", "success" if result.rowcount else "error")
        return redirect(url_for("admin_dashboard") + "#enquiries")

    @app.errorhandler(400)
    def bad_request(_error):
        return render_template("error.html", code=400, message="That request could not be processed."), 400

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("error.html", code=403, message="You do not have permission to view this area."), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, message="We couldn't find that page."), 404

    @app.errorhandler(429)
    def rate_limited(_error):
        return render_template("error.html", code=429, message="Too many attempts. Please try again shortly."), 429

    with app.app_context():
        init_db()
    return app


app = create_app()
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=os.getenv("APP_ENV") != "production")
