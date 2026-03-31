from src.admin.service import AdminService
from src.stores.models import Store

def test_get_all_stores(db_session, sample_store):
    stores = AdminService.get_all_stores()
    assert isinstance(stores, list)
    assert len(stores) >= 1
    # Check if our sample store is in there
    assert any(s.id == sample_store.id for s in stores)

def test_update_store(db_session, sample_store):
    updated = AdminService.update_store(sample_store.id, {"name": "Updated Mock Name", "status": "suspended"})
    assert updated is not None
    assert updated.name == "Updated Mock Name"
    assert updated.status == "suspended"
    
    # Verify persistence check
    store_check = db_session.query(Store).filter_by(id=sample_store.id).first()
    assert store_check.name == "Updated Mock Name"

def test_get_global_stats(db_session, sample_store):
    stats = AdminService.get_global_stats()
    assert stats is not None
    assert "active_stores" in stats
    assert "total_revenue" in stats
    assert "total_orders" in stats
    assert "global_tokens" in stats
    assert isinstance(stats["active_stores"], int)
