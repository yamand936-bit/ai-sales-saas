import src.core.models_aggregator
from src.core.database import SessionLocal
from src.chat.models import Message

db = SessionLocal()
msgs = db.query(Message).order_by(Message.id.desc()).limit(10).all()
with open("db_logs.txt", "w", encoding="utf-8") as f:
    for m in reversed(msgs):
        f.write(f"{m.role}: {m.content}\n")
print("Logs saved to db_logs.txt")
