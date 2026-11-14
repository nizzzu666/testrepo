# Aurel & Thread — WhatsApp-first storefront

A responsive boutique catalogue for dresses and watches. Visitors browse photos and prices, filter the collection, open product details and tap Enquire / Buy on WhatsApp. There is no checkout or payment gateway: the button opens WhatsApp with a product-specific message for the buyer to send.

Demo content: the Aurel & Thread brand, six sample products, prices and photos are placeholders. Replace them with your own business details before launch.

## Features
- Warm ivory, sage, olive and muted-clay design with mobile layouts and subtle motion.
- Dress/watch filters, live product search, featured products and individual detail pages.
- WhatsApp links prefilled with product name and displayed INR price.
- Private admin login to add, edit, feature and remove products.
- Python Flask, SQLite, CSRF protection, password-hash verification, login rate limiting, secure session cookies, parameterized SQL and server-side validation.
- Security headers, product image host allow-list, tests, GitHub Actions, Docker and Render deployment files.

## Local setup (Windows PowerShell)
1. Install Python 3.11 or newer.
2. In the project folder run: py -m venv .venv
3. Activate it: .\\.venv\\Scripts\\Activate.ps1
4. Install packages: pip install -r requirements.txt
5. Copy .env.example to .env.
6. Generate SECRET_KEY with: python -c "import secrets; print(secrets.token_urlsafe(48))"
7. Generate ADMIN_PASSWORD_HASH with: python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('Choose-A-Long-Unique-Password!'))"
8. Edit .env. Set the random SECRET_KEY, your admin username, the generated password hash and your WhatsApp number.
9. Set COOKIE_SECURE=false for local HTTP only. Start with python app.py.
10. Open http://127.0.0.1:5000. Admin sign-in: http://127.0.0.1:5000/admin/login.

## Configuration
WHATSAPP_NUMBER must be digits in international format. For an Indian number use 91 followed by your mobile number, without plus sign, spaces or dashes. ADMIN_PASSWORD_HASH must contain the generated hash, not your plain password. Keep .env and store.db private; both are excluded from Git. The database and six demo products are created on first startup.

## Add products
Sign in at /admin/login, choose Add a product and enter the product name, category, INR price, description and HTTPS image URL. The starter accepts images from images.unsplash.com, images.pexels.com and res.cloudinary.com. Use only photos that you own or have permission to use. You can edit, feature or delete catalogue items from the admin screen.

## WhatsApp enquiry flow
Each product button opens wa.me with a prefilled message such as: Hello! I'm interested in The Solstice Dress (₹2,499). Please share availability and details. The buyer still presses Send in WhatsApp. You then confirm availability, sizing, delivery and the final amount directly. The displayed price does not charge the buyer.

## Deployment
Render: create a Blueprint from this repository and use render.yaml. Set WHATSAPP_NUMBER, ADMIN_USERNAME and ADMIN_PASSWORD_HASH in the service environment. The blueprint generates SECRET_KEY and mounts a persistent disk at /var/data for SQLite.
Docker: build the included Dockerfile, mount a persistent volume at /data and set DATABASE_PATH=/data/store.db. The included one-worker configuration keeps the default in-memory login limiter effective for this small starter. If you scale to multiple workers or instances, configure shared Redis storage with RATELIMIT_STORAGE_URI first.

## Security and launch checklist
- Use a unique, long admin password. Store its hash and SECRET_KEY only in hosting environment settings.
- Use HTTPS in production with COOKIE_SECURE=true. Do not run Flask debug mode in production.
- Keep the default single worker unless you configure shared Redis-backed rate limiting.
- Back up the SQLite database and product photos. Persistent disk is storage, not an independent backup.
- Patch dependencies, restrict GitHub and hosting account access with MFA, and review logs.
- Replace sample content, add contact details and publish shipping/return policies and legally required business disclosures.
- This starter reduces common risks but cannot guarantee a breach-proof website. Hosting, credentials, image providers, account security and maintenance remain part of the security boundary.

## Run tests
pytest -q
