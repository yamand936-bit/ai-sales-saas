from src.merchant.service import MerchantService

def test_get_dashboard(db_session, sample_store):
    dash = MerchantService.get_dashboard(sample_store.id)
    assert dash is not None
    assert type(dash) is dict
    assert "products" in dash
    assert "conversations" in dash

def test_create_product(db_session, sample_store):
    data = {"name": "Test Product", "price": 100.0}
    product = MerchantService.create_product(sample_store.id, data)
    assert product is not None
    assert product.name == "Test Product"
    assert product.price == 100.0

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
