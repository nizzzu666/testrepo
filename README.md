# Aurel & Thread — WhatsApp-first storefront

A responsive catalogue for dresses and watches. Shoppers view photos and INR prices, submit a short product enquiry, and are then taken to WhatsApp with the product and customer details prefilled. There is no checkout or payment gateway.

> **Demo content:** Aurel & Thread, the six sample products, example prices and stock photos are placeholders. Replace the brand and catalogue with your real business details before launch.

## What is included

### Customer storefront
- Peaceful ivory, sage, olive and muted-clay visual design, responsive mobile layouts and subtle animations.
- Dress/watch filters, live search, product detail pages and prices.
- Enquiry form captures customer name, phone, product and optional message.
- After the form is saved, the browser opens WhatsApp with a prefilled enquiry. The customer still needs to tap **Send** in WhatsApp.

### Super Admin (business owner)
- One-time first-run setup at `/setup`; only works before the first Super Admin exists.
- Owner dashboard at `/superadmin`.
- Create staff Admin usernames and passwords.
- Reset staff passwords, disable and re-enable staff accounts.
- View store dashboard, product catalogue and recent enquiry activity.

### Staff Admin
- Staff sign-in at `/login`; no public self-registration.
- Dashboard at `/admin`.
- Add, edit, feature and delete dresses / watches.
- Change product prices and descriptions.
- Upload photos directly from a computer (JPG, PNG or WebP, up to 6 MB) or use an approved HTTPS image URL.
- View the customer enquiry inbox, contact the customer, add internal notes and update statuses (New, Contacted, Closed).
- Staff Admins cannot create, reset or disable accounts and cannot open the Super Admin dashboard.

## First-time setup (important)

The Super Admin account is **not** created with a hardcoded password. The first owner sets it up once using a private setup token.

1. Generate a strong application secret and a separate setup token:
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   Run it twice and keep the two outputs separately.
2. Configure `SECRET_KEY`, `INITIAL_SETUP_TOKEN`, `WHATSAPP_NUMBER`, and `APP_ENV` in your hosting provider's private environment settings (or in local `.env`). For India, WhatsApp number format is country code + number, digits only, e.g. `91XXXXXXXXXX`.
3. Start or deploy the application with HTTPS enabled in production.
4. Open `https://your-domain/setup`. Enter the setup token, your chosen Super Admin username and a strong password. Password must be at least 12 characters and include uppercase, lowercase, a number and a symbol.
5. After setup succeeds, **remove or clear `INITIAL_SETUP_TOKEN` from the hosting environment settings and redeploy/restart**. The database also permanently closes the setup path once the first Super Admin exists. Keep the Super Admin password private.
6. Sign in at `/login`. The Super Admin dashboard is `/superadmin`.

Do not share the initial setup token with staff. If you lose the Super Admin password, use your hosting/database administration recovery process; do not reopen first-run setup or edit the database casually.

## Create staff accounts

1. Sign in as Super Admin and open **Super Admin dashboard**.
2. In **Create an Admin**, set the staff username and a strong initial password.
3. Share those credentials privately with the staff member. Do not send passwords in a public group.
4. The staff member signs in at `/login` and works from `/admin`.
5. To change a staff password, enter a new password beside that account and select **Reset**. To stop access, select **Disable account**. Re-enable only when appropriate.

There is no public sign-up route. Staff accounts are created only by the authenticated Super Admin.

## Change product photos and prices

1. Sign in at `/login` with the Admin account supplied by the Super Admin.
2. In the dashboard, find the product and select **Edit** or select **Add a product**.
3. Change the INR price, name, category, description or featured status.
4. For the photo, choose a file from your computer, or paste an HTTPS image URL from Unsplash, Pexels or Cloudinary. When editing, leave both photo fields blank to keep the existing photo.
5. Save changes. The public storefront updates from the database automatically.

Uploaded photos are converted to WebP, stripped of their original metadata and stored in the configured persistent upload directory. Do not upload photos you do not own or have permission to use.

## How enquiries appear

A customer opens a product page, enters their name and phone number, and submits the enquiry. The site stores the details in the enquiry table, then redirects to WhatsApp with a prefilled message. Staff can see the saved enquiry at `/admin#enquiries`, contact the customer, write an internal note and move the status through New, Contacted and Closed.

**Important:** The website can record submission of its enquiry form. It cannot independently verify that a customer subsequently pressed Send in WhatsApp or that a WhatsApp message was delivered. Directly opening a WhatsApp link without submitting the form will not create a website enquiry record.

## Local setup (Windows PowerShell)

1. Install Python 3.11 or newer.
2. In the project folder:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   ```
3. Generate two distinct values:
   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
4. Edit `.env`: paste one value into `SECRET_KEY` and the other into `INITIAL_SETUP_TOKEN`; set `WHATSAPP_NUMBER` to your business number.
5. Keep `COOKIE_SECURE=false` for local HTTP testing only. Start the site:
   ```powershell
   python app.py
   ```
6. Open `http://127.0.0.1:5000/setup` and complete the first-time Super Admin setup. Remove the setup token from your local `.env` after setup.
7. Staff and Super Admin sign in at `http://127.0.0.1:5000/login`.

The SQLite database is created automatically with six demonstration products. Do not commit `.env`, the database or customer enquiry information.

## Environment configuration

- `SECRET_KEY`: long random application secret; required in production.
- `INITIAL_SETUP_TOKEN`: private one-time owner setup secret; remove after first-run setup.
- `WHATSAPP_NUMBER`: business WhatsApp number in international format, digits only.
- `APP_ENV`: set to `production` on hosting.
- `COOKIE_SECURE`: `true` for HTTPS production; `false` only for local HTTP.
- `DATABASE_PATH`: SQLite database path; must be persistent in production.
- `UPLOAD_FOLDER`: persistent directory for uploaded WebP product photographs.
- `RATELIMIT_STORAGE_URI`: defaults to `memory://`. The current Render / Docker configuration uses a single Gunicorn worker. Use shared Redis storage before scaling to multiple workers or instances.

## Deployment

### Render
1. Push this repository to GitHub and create a Render Blueprint from `render.yaml`.
2. Add private environment values for `INITIAL_SETUP_TOKEN` and `WHATSAPP_NUMBER`. The blueprint generates `SECRET_KEY`.
3. Deploy, open the generated HTTPS URL plus `/setup`, and create the Super Admin.
4. Remove / clear `INITIAL_SETUP_TOKEN` in the Render environment and redeploy.
5. The blueprint mounts a persistent disk at `/var/data`, with SQLite at `/var/data/store.db` and uploaded photos at `/var/data/uploads`.

### Docker
Build the included Dockerfile, mount a persistent volume at `/data`, and set `SECRET_KEY`, `INITIAL_SETUP_TOKEN`, `WHATSAPP_NUMBER`, `APP_ENV=production` and `COOKIE_SECURE=true`. The container uses `/data/store.db` and `/data/uploads`. Remove the setup token after creating the Super Admin.

## Security and operational notes

- CSRF protection on forms, strong password policy and password hashing, login / setup rate limits, role checks on every private dashboard action and secure session cookies.
- SQL queries are parameterized, photo uploads are decoded / resized and re-encoded as WebP, and only generated safe filenames are served from the upload route.
- Security headers, no-store headers on private pages, size limits and an upload image-host allow-list are included.
- Keep the app on HTTPS, use MFA for GitHub and hosting accounts, restrict database access, rotate secrets if exposed and back up both the database and uploaded photo directory.
- Current limiter storage defaults to process memory and the deployment files use one worker. Configure shared Redis before scaling.
- No application can guarantee complete protection from breaches. Hosting access, weak credentials, account recovery, dependencies, backups and maintenance remain part of the security boundary.
- Before opening to customers, replace demo products and photos, confirm WhatsApp number and prices, test the complete customer enquiry flow, and publish your shipping, returns, privacy and business policies as applicable.

## Run tests

```powershell
pytest -q
```

## Project structure

- `app.py` — Flask routes, role checks, SQLite schema, enquiry capture and image validation.
- `templates/` — storefront, first-run setup, Super Admin, Admin and product pages.
- `static/styles.css`, `static/app.js` — responsive design, filtering and animations.
- `tests/test_app.py` — application and security smoke tests.
- `.github/workflows/ci.yml` — GitHub Actions test workflow.
- `render.yaml`, `Dockerfile`, `Procfile` — deployment entry points.
- `.env.example` — local environment template.
