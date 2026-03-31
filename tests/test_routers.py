import pytest
from src.main import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test_secret"
    with app.test_client() as client:
        yield client

# --- AUTH TESTS ---
def test_merchant_requires_auth(client):
    response = client.get("/dashboard")
    assert response.status_code in [302, 401]
    assert "/login" in response.location if response.status_code == 302 else True

def test_admin_requires_auth(client):
    response = client.get("/admin/dashboard")
    assert response.status_code in [302, 401]
    assert "/admin/login" in response.location if response.status_code == 302 else True

# --- MERCHANT ROUTES ---
def login_merchant(client, store_id):
    with client.session_transaction() as sess:
        sess['role'] = 'merchant'
        sess['store_id'] = store_id
        sess['csrf_token'] = "test_csrf_token"

def test_dashboard_route_authenticated(client, db_session, sample_store):
    login_merchant(client, sample_store.id)
    response = client.get("/dashboard")
    assert response.status_code == 200

def test_inventory_route_authenticated(client, db_session, sample_store):
    import src.merchant.router as mr
    with pytest.MonkeyPatch.context() as m:
        m.setattr(mr, "render_template", lambda *a, **k: "mocked response")
        login_merchant(client, sample_store.id)
        response = client.get("/inventory")
        assert response.status_code == 200

def test_orders_checkout_route_authenticated(client, db_session, sample_store):
    from src.orders.models import Order
    order = Order(store_id=sample_store.id, total_amount=50.0)
    db_session.add(order)
    db_session.flush()
    
    login_merchant(client, sample_store.id)
    response = client.get(f"/checkout/{order.id}")
    assert response.status_code == 200

def test_add_product_post(client, db_session, sample_store):
    login_merchant(client, sample_store.id)
    response = client.post(f"/merchant/{sample_store.id}/add_product", data={
        "name": "Test Product POST",
        "price": 50.0,
        "csrf_token": "test_csrf_token"
    })
    assert response.status_code in [200, 201, 302]

def test_toggle_system_ai(client, db_session, sample_store):
    login_merchant(client, sample_store.id)
    response = client.post(f"/merchant/{sample_store.id}/toggle_system_ai", json={"csrf_token": "test_csrf_token"})
    assert response.status_code in [200, 302]

def test_merchant_login_page(client):
    response = client.get("/login")
    assert response.status_code == 200

def test_merchant_logout_route(client):
    response = client.get("/logout")
    assert response.status_code in [200, 302]

# --- ADMIN ROUTES ---
def login_admin(client):
    with client.session_transaction() as sess:
        sess['role'] = 'admin'
        sess['is_admin'] = True
        sess['csrf_token'] = "test_csrf"

def test_admin_dashboard_authenticated(client, db_session):
    login_admin(client)
    response = client.get("/admin/dashboard")
    assert response.status_code == 200

def test_admin_stores_route(client, db_session):
    login_admin(client)
    response = client.get("/admin/stores")
    assert response.status_code == 200

def test_admin_settings_route(client, db_session):
    login_admin(client)
    response = client.get("/admin/settings")
    assert response.status_code == 200

def test_admin_store_detail_route(client, db_session, sample_store):
    login_admin(client)
    response = client.get(f"/admin/store/{sample_store.id}")
    assert response.status_code == 200
