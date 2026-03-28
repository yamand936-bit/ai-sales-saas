import os
import sys
import time

# Ensure src module is discoverable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.database import Base, engine
from src.stores.models import Store
from src.users.models import User
from src.products.models import Product
from src.orders.models import Order, OrderItem
from src.chat.models import Conversation, Message, AILog

def init():
    for _ in range(15):
        try:
            Base.metadata.create_all(bind=engine)
            from sqlalchemy import inspect
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            print("TABLES_CREATED:" + ",".join(tables))
            return
        except Exception as e:
            time.sleep(2)
    print("DB_ERROR: Could not connect to Postgres after 15 attempts")

if __name__ == "__main__":
    init()
