from src.admin.service import AdminService
from src.stores.models import Store
import pytest
from sqlalchemy.exc import SQLAlchemyError, StatementError

def test_get_all_stores(db_session, sample_store):
    stores = AdminService.get_all_stores()
    assert isinstance(stores, list)
    assert len(stores) >= 1
    # Check if our sample store is in there
    assert any(s.id == sample_store.id for s in stores)

def test_get_store_detail(db_session, sample_store):
    detail = AdminService.get_store_detail(sample_store.id)
    assert detail is not None
    assert "store" in detail
    assert detail["store"].id == sample_store.id
    assert "conv_count" in detail

def test_get_store_detail_not_found(db_session):
    detail = AdminService.get_store_detail(99999)
    assert detail is None

def test_update_store(db_session, sample_store):
    updated = AdminService.update_store(sample_store.id, {"name": "Updated Mock Name", "status": "suspended"})
    assert updated is not None
    assert updated.name == "Updated Mock Name"
    assert updated.status == "suspended"
    
    # Verify persistence check
    store_check = db_session.query(Store).filter_by(id=sample_store.id).first()
    assert store_check.name == "Updated Mock Name"

def test_update_store_not_found(db_session):
    res = AdminService.update_store(99999, {"name": "Fail"})
    assert res is None

def test_create_store(db_session):
    data = {
        "name": "New Admin Store",
        "owner_name": "Admin",
        "owner_email": "admin@localhost",
        "password_hash": "mockhash",
        "plan_price": 99.0,
        "monthly_token_limit": 50000
    }
    store = AdminService.create_store(data)
    assert store is not None
    assert store.name == "New Admin Store"
    assert store.owner_email == "admin@localhost"
    assert store.id is not None

def test_create_store_missing_data(db_session):
    from sqlalchemy.exc import IntegrityError
    # Missing nullable=False name field
    with pytest.raises(IntegrityError):
        AdminService.create_store({"owner_name": "Fail"})

def test_delete_store(db_session):
    store = AdminService.create_store({"name": "Delete Target"})
    res = AdminService.delete_store(store.id)
    assert res is True
    
    check = AdminService.get_store_detail(store.id)
    assert check is None

def test_delete_store_not_found(db_session):
    res = AdminService.delete_store(99999)
    assert res is False

def test_get_global_stats(db_session, sample_store):
    stats = AdminService.get_global_stats()
    assert stats is not None
    assert "active_stores" in stats
    assert "total_revenue" in stats
    assert "total_orders" in stats
    assert "global_tokens" in stats
    assert isinstance(stats["active_stores"], int)

def test_get_system_settings_empty(db_session):
    # Depending on baseline, may be empty or populated
    settings = AdminService.get_system_settings()
    assert isinstance(settings, list)

def test_update_system_settings(db_session):
    res = AdminService.update_system_settings({"max_users": "100"})
    assert res is True
    
    settings = AdminService.get_system_settings()
    has_max = any(s.key == "max_users" for s in settings)
    assert has_max is True

def test_get_ai_usage(db_session):
    usage = AdminService.get_ai_usage()
    assert isinstance(usage, list)

def test_get_subscription_days(db_session, sample_store):
    days = AdminService.get_subscription_days(sample_store.id)
    assert isinstance(days, int)
    assert days == 0 # None set

def test_get_subscription_days_not_found(db_session):
    days = AdminService.get_subscription_days(99999)
    assert days == 0

def test_get_latest_messages(db_session):
    msgs = AdminService.get_latest_messages()
    assert isinstance(msgs, list)

def test_get_latest_conversations(db_session):
    convs = AdminService.get_latest_conversations()
    assert isinstance(convs, list)
