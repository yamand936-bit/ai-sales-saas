from src.merchant.service import MerchantService
import pytest
from sqlalchemy.exc import SQLAlchemyError, StatementError

# --- DASHBOARD TESTS ---
def test_get_dashboard(db_session, sample_store):
    dash = MerchantService.get_dashboard(sample_store.id)
    assert dash is not None
    assert type(dash) is dict
    assert "products" in dash
    assert "conversations" in dash

def test_get_dashboard_not_found(db_session):
    dash = MerchantService.get_dashboard(99999)
    assert dash is None

# --- PRODUCT TESTS ---
def test_create_product(db_session, sample_store):
    data = {"name": "Test Product", "price": 100.0}
    product = MerchantService.create_product(sample_store.id, data)
    assert product is not None
    assert product.name == "Test Product"
    assert product.price == 100.0

def test_create_product_missing_data(db_session, sample_store):
    # Name is nullable=False, so this should raise IntegrityError
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        MerchantService.create_product(sample_store.id, {"price": 10})

def test_create_product_invalid_price(db_session, sample_store):
    with pytest.raises((StatementError, ValueError)):
        MerchantService.create_product(sample_store.id, {"name": "Invalid", "price": "not_a_number"})

def test_get_products_empty(db_session):
    prods = MerchantService.get_products(99999)
    assert prods == []

def test_get_products(db_session, sample_store):
    MerchantService.create_product(sample_store.id, {"name": "Prod 1", "price": 10})
    prods = MerchantService.get_products(sample_store.id)
    assert len(prods) == 1
    assert prods[0].name == "Prod 1"

def test_update_product(db_session, sample_store):
    product = MerchantService.create_product(sample_store.id, {"name": "Update Me", "price": 10})
    updated = MerchantService.update_product(product.id, {"name": "Updated", "price": 15})
    assert updated.name == "Updated"
    assert updated.price == 15

def test_update_product_not_found(db_session, sample_store):
    with pytest.raises(Exception):
        MerchantService.update_product(99999, {"name": "Failed"})

def test_delete_product(db_session, sample_store):
    product = MerchantService.create_product(sample_store.id, {"name": "Delete Me", "price": 10})
    res = MerchantService.delete_product(product.id)
    assert res is True
    assert MerchantService.get_products(sample_store.id) == []

def test_delete_product_not_found(db_session):
    with pytest.raises(Exception):
        MerchantService.delete_product(99999)

# --- CONVERSATION & MESSAGE TESTS ---
def test_get_conversations_empty(db_session):
    assert MerchantService.get_conversations(99999) == []

def test_get_conversations(db_session, sample_store, sample_user):
    from src.chat.models import Conversation
    conv = Conversation(user_id=sample_user.id, channel="test")
    db_session.add(conv)
    db_session.flush()

    convs = MerchantService.get_conversations(sample_store.id)
    assert isinstance(convs, list)
    assert len(convs) == 1
    assert convs[0].id == conv.id

def test_add_message(db_session, sample_user):
    from src.chat.models import Conversation
    conv = Conversation(user_id=sample_user.id, channel="test")
    db_session.add(conv)
    db_session.flush()
    
    msg = MerchantService.add_message(conv.id, "user", "Hello Test!")
    assert msg.content == "Hello Test!"
    assert msg.role == "user"
    assert msg.conversation_id == conv.id

def test_add_message_invalid_conv(db_session):
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        MerchantService.add_message(99999, "user", "Broken")

def test_get_messages(db_session, sample_user):
    from src.chat.models import Conversation
    conv = Conversation(user_id=sample_user.id, channel="test")
    db_session.add(conv)
    db_session.flush()
    MerchantService.add_message(conv.id, "user", "Message 1")
    
    msgs = MerchantService.get_messages(conv.id)
    assert len(msgs) == 1

def test_get_messages_empty(db_session):
    assert MerchantService.get_messages(99999) == []

def test_toggle_conversation_human_mode(db_session, sample_user):
    from src.chat.models import Conversation
    conv = Conversation(user_id=sample_user.id, channel="test", requires_human=False)
    db_session.add(conv)
    db_session.flush()

    res = MerchantService.toggle_conversation_human_mode(conv.id)
    assert res.requires_human is True

def test_toggle_conversation_human_mode_not_found(db_session):
    assert MerchantService.toggle_conversation_human_mode(99999) is None

def test_resolve_conversation(db_session, sample_user):
    from src.chat.models import Conversation
    conv = Conversation(user_id=sample_user.id, channel="test", requires_human=True)
    db_session.add(conv)
    db_session.flush()

    res = MerchantService.resolve_conversation(conv.id)
    assert res.requires_human is False

def test_resolve_conversation_not_found(db_session):
    assert MerchantService.resolve_conversation(99999) is None

def test_update_conversation_context(db_session, sample_user):
    from src.chat.models import Conversation
    conv = Conversation(user_id=sample_user.id, channel="test")
    db_session.add(conv)
    db_session.flush()

    res = MerchantService.update_conversation_context(conv.id, "new context")
    assert res.context == "new context"

def test_update_conversation_context_not_found(db_session):
    assert MerchantService.update_conversation_context(99999, "new context") is None

# --- ORDERS TESTS ---
def test_get_orders_empty(db_session):
    assert MerchantService.get_orders(99999) == []

def test_update_order_status_not_found(db_session):
    assert MerchantService.update_order_status(99999, "shipped") is None

def test_get_order_not_found(db_session):
    assert MerchantService.get_order(99999) is None

# --- USERS TESTS ---
def test_get_users_empty(db_session):
    assert MerchantService.get_users(99999) == []

def test_get_users(db_session, sample_store, sample_user):
    users = MerchantService.get_users(sample_store.id)
    assert len(users) == 1

def test_get_user(db_session, sample_store, sample_user):
    user = MerchantService.get_user(sample_user.id, sample_store.id)
    assert user is not None
    assert user.id == sample_user.id

def test_get_user_not_found(db_session):
    assert MerchantService.get_user(99999, 99999) is None

def test_get_user_by_telegram(db_session, sample_store, sample_user):
    user = MerchantService.get_user_by_telegram("12345", sample_store.id)
    assert user is not None

def test_get_user_by_telegram_not_found(db_session):
    assert MerchantService.get_user_by_telegram("unknown", 99999) is None

# --- STORE TESTS ---
def test_get_store_not_found(db_session):
    assert MerchantService.get_store(99999) is None

def test_get_store_by_domain_not_found(db_session):
    with pytest.raises(Exception):
        MerchantService.get_store_by_domain("unknown.com")

def test_get_store_by_email_not_found(db_session):
    assert MerchantService.get_store_by_email("unknown@test.com") is None

# --- AI CONFIG TESTS ---
def test_get_ai_config(db_session, sample_store):
    config = MerchantService.get_ai_config(sample_store.id)
    assert config is not None
    assert "ai_enabled" in config

def test_get_ai_config_not_found(db_session):
    assert MerchantService.get_ai_config(99999) is None

def test_update_ai_config(db_session, sample_store):
    res = MerchantService.update_ai_config(sample_store.id, {"ai_tone": "professional"})
    assert res is not None
    assert getattr(res, "ai_tone") == "professional"

def test_update_ai_config_not_found(db_session):
    assert MerchantService.update_ai_config(99999, {"ai_tone": "professional"}) is None
