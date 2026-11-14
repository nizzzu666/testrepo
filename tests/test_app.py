import os
import tempfile
import pytest
from werkzeug.security import generate_password_hash
from app import create_app

@pytest.fixture()
def client():
    handle,path=tempfile.mkstemp(suffix=".sqlite3"); os.close(handle)
    app=create_app({
      "TESTING":True,"SECRET_KEY":"test-secret-that-is-long-enough","DATABASE":path,
      "ADMIN_USERNAME":"owner","ADMIN_PASSWORD_HASH":generate_password_hash("Strong-Test-Password-42!"),
      "WHATSAPP_NUMBER":"919999999999","SESSION_COOKIE_SECURE":False,"WTF_CSRF_ENABLED":False,
    })
    with app.test_client() as c: yield c
    os.unlink(path)

def test_storefront_loads_products(client):
    response=client.get("/")
    assert response.status_code==200
    assert b"The Solstice Dress" in response.data
    assert b"The Heritage Watch" in response.data
    assert b"wa.me/919999999999" in response.data

def test_product_page(client):
    response=client.get("/product/1")
    assert response.status_code==200
    assert b"The Solstice Dress" in response.data

def test_unknown_product_is_404(client):
    assert client.get("/product/99999").status_code==404

def test_admin_redirects_to_login(client):
    response=client.get("/admin")
    assert response.status_code==302
    assert "/admin/login" in response.headers["Location"]

def test_login_requires_csrf_by_default():
    handle,path=tempfile.mkstemp(suffix=".sqlite3"); os.close(handle)
    app=create_app({
      "TESTING":True,"SECRET_KEY":"second-test-secret-is-long-enough","DATABASE":path,
      "ADMIN_USERNAME":"owner","ADMIN_PASSWORD_HASH":generate_password_hash("Strong-Test-Password-42!"),
      "SESSION_COOKIE_SECURE":False,
    })
    with app.test_client() as c:
      response=c.post("/admin/login",data={"username":"owner","password":"Strong-Test-Password-42!"})
      assert response.status_code==400
    os.unlink(path)
