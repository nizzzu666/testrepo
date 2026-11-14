import os
import re
import tempfile
from io import BytesIO

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

from app import create_app


@pytest.fixture()
def client():
    handle, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(handle)
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-that-is-long-enough",
        "DATABASE": path,
        "UPLOAD_FOLDER": path + ".uploads",
        "INITIAL_SETUP_TOKEN": "this-is-a-test-only-long-setup-token",
        "WHATSAPP_NUMBER": "919999999999",
        "SESSION_COOKIE_SECURE": False,
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_STORAGE_URI": "memory://",
    })
    with app.test_client() as test_client:
        yield test_client
    os.unlink(path)
    import shutil
    shutil.rmtree(path + ".uploads", ignore_errors=True)


def setup_superadmin(client):
    response = client.post("/setup", data={
        "setup_token": "this-is-a-test-only-long-setup-token",
        "username": "owner",
        "password": "Strong-Owner-Password-42!",
        "confirm_password": "Strong-Owner-Password-42!",
    })
    assert response.status_code == 302
    assert "/superadmin" in response.headers["Location"]


def create_staff(client):
    setup_superadmin(client)
    response = client.post("/superadmin/admins/new", data={
        "username": "staff-one",
        "password": "Strong-Staff-Password-42!",
    })
    assert response.status_code == 302
    client.post("/logout")


def login_staff(client):
    return client.post("/login", data={
        "username": "staff-one",
        "password": "Strong-Staff-Password-42!",
    })


def test_storefront_loads_products_and_enquiry_cta(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"The Solstice Dress" in response.data
    assert b"The Heritage Watch" in response.data
    assert b"#enquiry" in response.data


def test_product_page_has_customer_enquiry_form(client):
    response = client.get("/product/1")
    assert response.status_code == 200
    assert b"The Solstice Dress" in response.data
    assert b"customer_name" in response.data
    assert b"customer_phone" in response.data


def test_unknown_product_is_404(client):
    assert client.get("/product/99999").status_code == 404


def test_first_run_setup_is_one_time_and_creates_superadmin(client):
    setup_superadmin(client)
    assert client.get("/superadmin").status_code == 200
    second = client.post("/setup", data={
        "setup_token": "this-is-a-test-only-long-setup-token",
        "username": "owner2",
        "password": "Another-Owner-Password-42!",
        "confirm_password": "Another-Owner-Password-42!",
    })
    assert second.status_code == 410


def test_first_run_setup_rejects_weak_password(client):
    response = client.post("/setup", data={
        "setup_token": "this-is-a-test-only-long-setup-token",
        "username": "owner",
        "password": "short",
        "confirm_password": "short",
    })
    assert response.status_code == 200
    assert b"At least 12 characters" in response.data
    assert client.get("/superadmin").status_code == 302


def test_admin_creation_and_role_restrictions(client):
    create_staff(client)
    login = login_staff(client)
    assert login.status_code == 302
    assert "/admin" in login.headers["Location"]
    assert client.get("/admin").status_code == 200
    assert client.get("/superadmin").status_code == 403


def test_product_enquiry_is_saved_and_visible_in_dashboard(client):
    create_staff(client)
    response = client.post("/enquire/1", data={
        "customer_name": "Asha",
        "customer_phone": "919876543210",
        "customer_message": "Do you have size M?",
        "website": "",
    }, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].startswith("https://wa.me/919999999999?")
    login_staff(client)
    dashboard = client.get("/admin")
    assert dashboard.status_code == 200
    assert b"Asha" in dashboard.data
    assert b"Do you have size M?" in dashboard.data
    update = client.post("/admin/enquiries/1/update", data={
        "status": "contacted",
        "internal_note": "Called customer",
    })
    assert update.status_code == 302
    dashboard = client.get("/admin")
    assert b"Contacted" in dashboard.data
    assert b"Called customer" in dashboard.data


def test_admin_can_upload_product_photo_and_set_price(client):
    create_staff(client)
    login_staff(client)
    img = Image.new("RGB", (80, 80), color=(120, 150, 110))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    response = client.post("/admin/products/new", data={
        "name": "Uploaded Sample",
        "category": "dresses",
        "price": "2499.00",
        "description": "A test item with a locally uploaded photo.",
        "image_url": "",
        "tag": "Test",
        "featured": "on",
        "image_file": (buffer, "sample.png"),
    }, content_type="multipart/form-data")
    assert response.status_code == 302
    page = client.get("/")
    assert b"Uploaded Sample" in page.data
    match = re.search(rb'src="(/uploads/[a-f0-9]{32}\.webp)"', page.data)
    assert match
    uploaded = client.get(match.group(1).decode())
    assert uploaded.status_code == 200
    assert uploaded.mimetype == "image/webp"


def test_login_requires_csrf_by_default():
    handle, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(handle)
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "second-test-secret-is-long-enough",
        "DATABASE": path,
        "UPLOAD_FOLDER": path + ".uploads",
        "INITIAL_SETUP_TOKEN": "test-token",
        "SESSION_COOKIE_SECURE": False,
    })
    with app.test_client() as test_client:
        response = test_client.post("/login", data={"username": "owner", "password": "something"})
        assert response.status_code == 400
    os.unlink(path)
    import shutil
    shutil.rmtree(path + ".uploads", ignore_errors=True)
