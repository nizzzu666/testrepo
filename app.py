"""Secure WhatsApp-first boutique catalogue."""
import os, re, secrets, sqlite3
from pathlib import Path
from functools import wraps
from urllib.parse import urlencode, urlparse
from dotenv import load_dotenv
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
SEED = [
 ("The Solstice Dress","dresses","A soft, flowing silhouette for slow mornings and special evenings.",2499,"https://images.unsplash.com/photo-1595777457583-95e059d581b8?auto=format&fit=crop&w=1000&q=85","Bestseller",1),
 ("The Linen Edit","dresses","Easy tailoring and breathable texture, made for everyday elegance.",1899,"https://images.unsplash.com/photo-1490481651871-ab68de25d43d?auto=format&fit=crop&w=1000&q=85","New arrival",1),
 ("The Evening Muse","dresses","A graceful statement piece with a timeless, understated finish.",3299,"https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=1000&q=85","Limited edit",0),
 ("The Heritage Watch","watches","A refined everyday timepiece with a clean, classic dial.",4199,"https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=1000&q=85","Bestseller",1),
 ("The Minimalist","watches","Quiet details, versatile proportions and effortless styling.",3599,"https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=1000&q=85","New arrival",1),
 ("The Modern Classic","watches","A considered accent for workdays, weekends and everything between.",5299,"https://images.unsplash.com/photo-1508057198894-247b23fe5ade?auto=format&fit=crop&w=1000&q=85","Curated pick",0),
]
IMAGE_HOSTS = {"images.unsplash.com","images.pexels.com","res.cloudinary.com"}

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY") or ("local-only-change-this-secret" if os.getenv("APP_ENV") != "production" else ""),
        DATABASE=os.getenv("DATABASE_PATH", str(ROOT / "store.db")),
        ADMIN_USERNAME=os.getenv("ADMIN_USERNAME","storeadmin"),
        ADMIN_PASSWORD_HASH=os.getenv("ADMIN_PASSWORD_HASH",""),
        WHATSAPP_NUMBER=re.sub(r"\D","",os.getenv("WHATSAPP_NUMBER","")),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE","true").lower()=="true",
        PERMANENT_SESSION_LIFETIME=3600, MAX_CONTENT_LENGTH=1024*1024,
        RATELIMIT_STORAGE_URI=os.getenv("RATELIMIT_STORAGE_URI","memory://"),
    )
    if test_config: app.config.update(test_config)
    if not app.config["SECRET_KEY"]: raise RuntimeError("Set SECRET_KEY before production startup.")
    CSRFProtect(app)
    limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri=app.config["RATELIMIT_STORAGE_URI"])

    def connect():
        db=sqlite3.connect(app.config["DATABASE"]); db.row_factory=sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON"); return db

    def init_db():
        Path(app.config["DATABASE"]).parent.mkdir(parents=True,exist_ok=True)
        db=connect()
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS products(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL CHECK(length(name) BETWEEN 2 AND 80),
              category TEXT NOT NULL CHECK(category IN ('dresses','watches')),
              description TEXT NOT NULL CHECK(length(description) BETWEEN 5 AND 240),
              price_paise INTEGER NOT NULL CHECK(price_paise BETWEEN 1 AND 100000000),
              image_url TEXT NOT NULL, tag TEXT NOT NULL DEFAULT '',
              featured INTEGER NOT NULL DEFAULT 0 CHECK(featured IN (0,1)),
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            if db.execute("SELECT COUNT(*) FROM products").fetchone()[0]==0:
                db.executemany("INSERT INTO products(name,category,description,price_paise,image_url,tag,featured) VALUES(?,?,?,?,?,?,?)",
                    [(n,c,d,p*100,img,t,f) for n,c,d,p,img,t,f in SEED])
            db.commit()
        finally: db.close()

    def db():
        if "db" not in g: g.db=connect()
        return g.db

    @app.teardown_appcontext
    def close_db(_error=None):
        conn=g.pop("db",None)
        if conn is not None: conn.close()

    def wa_link(name, price):
        number=app.config["WHATSAPP_NUMBER"]
        if not 8 <= len(number) <= 15: return None
        msg=f"Hello! I'm interested in {name} (₹{price/100:,.0f}). Please share availability and details."
        return "https://wa.me/"+number+"?"+urlencode({"text":msg})

    app.jinja_env.globals["whatsapp_link"]=wa_link
    app.jinja_env.globals["whatsapp_ready"]=lambda: 8 <= len(app.config["WHATSAPP_NUMBER"]) <= 15

    @app.after_request
    def headers(resp):
        resp.headers.update({
          "X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY",
          "Referrer-Policy":"strict-origin-when-cross-origin",
          "Permissions-Policy":"camera=(), microphone=(), geolocation=()",
          "Content-Security-Policy":"default-src 'self'; img-src 'self' https://images.unsplash.com https://images.pexels.com https://res.cloudinary.com data:; style-src 'self'; script-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
        })
        if request.path.startswith("/admin"): resp.headers["Cache-Control"]="no-store, private"
        if request.is_secure: resp.headers["Strict-Transport-Security"]="max-age=31536000; includeSubDomains"
        return resp

    def admin_required(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            if not app.config["ADMIN_PASSWORD_HASH"]: abort(503,description="Admin credentials are not configured; see README.")
            if not session.get("is_admin"): return redirect(url_for("admin_login"))
            return fn(*args,**kwargs)
        return wrapped

    @app.get("/")
    def home():
        products=db().execute("SELECT * FROM products ORDER BY featured DESC,id DESC").fetchall()
        return render_template("index.html",products=products)

    @app.get("/product/<int:pid>")
    def product_detail(pid):
        product=db().execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
        if product is None: abort(404)
        return render_template("product.html",product=product)

    @app.get("/admin/login")
    def admin_login():
        if not app.config["ADMIN_PASSWORD_HASH"]: abort(503,description="Configure ADMIN_PASSWORD_HASH; see README.")
        return render_template("login.html")

    @app.post("/admin/login")
    @limiter.limit("5 per minute")
    def admin_login_post():
        username=request.form.get("username","")[:80]
        password=request.form.get("password","")[:256]
        valid_user=secrets.compare_digest(username,app.config["ADMIN_USERNAME"])
        valid_pass=check_password_hash(app.config["ADMIN_PASSWORD_HASH"],password) if app.config["ADMIN_PASSWORD_HASH"] else False
        if not (valid_user and valid_pass):
            flash("The sign-in details were not recognised.","error")
            return render_template("login.html"),401
        session.clear(); session["is_admin"]=True; session.permanent=True
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/logout")
    @admin_required
    def admin_logout():
        session.clear(); return redirect(url_for("home"))

    @app.get("/admin")
    @admin_required
    def admin_dashboard():
        products=db().execute("SELECT * FROM products ORDER BY id DESC").fetchall()
        return render_template("admin.html",products=products)

    def form_values():
        name=request.form.get("name","").strip()
        category=request.form.get("category","").strip()
        desc=request.form.get("description","").strip()
        tag=request.form.get("tag","").strip()[:30]
        image=request.form.get("image_url","").strip()
        try: price=round(float(request.form.get("price",""))*100)
        except (TypeError,ValueError): price=0
        parsed=urlparse(image)
        if not 2<=len(name)<=80: raise ValueError("Product name must be 2–80 characters.")
        if category not in {"dresses","watches"}: raise ValueError("Choose Dresses or Watches.")
        if not 5<=len(desc)<=240: raise ValueError("Description must be 5–240 characters.")
        if not 1<=price<=100000000: raise ValueError("Enter a valid INR price.")
        if parsed.scheme!="https" or parsed.hostname not in IMAGE_HOSTS or parsed.username or parsed.password:
            raise ValueError("Use an HTTPS image from Unsplash, Pexels or Cloudinary.")
        return (name,category,desc,price,image,tag,1 if request.form.get("featured")=="on" else 0)

    @app.route("/admin/products/new",methods=["GET","POST"])
    @admin_required
    def product_new():
        if request.method=="POST":
            try:
                db().execute("INSERT INTO products(name,category,description,price_paise,image_url,tag,featured) VALUES(?,?,?,?,?,?,?)",form_values())
                db().commit(); flash("Product added to your shop.","success"); return redirect(url_for("admin_dashboard"))
            except ValueError as e: flash(str(e),"error")
        return render_template("product_form.html",product=None)

    @app.route("/admin/products/<int:pid>/edit",methods=["GET","POST"])
    @admin_required
    def product_edit(pid):
        product=db().execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
        if product is None: abort(404)
        if request.method=="POST":
            try:
                db().execute("UPDATE products SET name=?,category=?,description=?,price_paise=?,image_url=?,tag=?,featured=? WHERE id=?",form_values()+(pid,))
                db().commit(); flash("Product updated.","success"); return redirect(url_for("admin_dashboard"))
            except ValueError as e: flash(str(e),"error")
        return render_template("product_form.html",product=product)

    @app.post("/admin/products/<int:pid>/delete")
    @admin_required
    def product_delete(pid):
        db().execute("DELETE FROM products WHERE id=?",(pid,)); db().commit()
        flash("Product removed.","success"); return redirect(url_for("admin_dashboard"))

    @app.errorhandler(404)
    def not_found(_e): return render_template("error.html",code=404,message="We couldn't find that page."),404

    @app.errorhandler(429)
    def rate_limited(_e): return render_template("error.html",code=429,message="Too many attempts. Please try again shortly."),429

    with app.app_context(): init_db()
    return app

app=create_app()
if __name__=="__main__":
    app.run(host="127.0.0.1",port=int(os.getenv("PORT","5000")),debug=os.getenv("APP_ENV")!="production")
