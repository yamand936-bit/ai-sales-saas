import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.core.database import Base
from src.core.config import settings
from unittest.mock import patch

@pytest.fixture(scope="session")
def engine():
    _engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(_engine)
    yield _engine
    _engine.dispose()

@pytest.fixture(scope="function")
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    
    # Store the original close to prevent premature close in finally: db.close() loops
    original_close = session.close
    session.close = lambda: None 
    
    with patch("src.merchant.service.SessionLocal", return_value=session):
        with patch("src.admin.service.SessionLocal", return_value=session):
            with patch("src.core.database.SessionLocal", return_value=session):
                yield session
                
    session.close = original_close
    session.close()
    transaction.rollback()
    connection.close()

# Provide a sample store and user
@pytest.fixture(scope="function")
def sample_store(db_session):
    from src.stores.models import Store
    store = Store(name="Test Store", telegram_token="test_token_123")
    db_session.add(store)
    db_session.flush() # Force ID generation
    return store
    
@pytest.fixture(scope="function")
def sample_user(db_session, sample_store):
    from src.users.models import User
    user = User(first_name="Test User", telegram_id="12345", store_id=sample_store.id)
    db_session.add(user)
    db_session.flush()
    return user
