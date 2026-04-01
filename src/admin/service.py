import datetime
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from src.core.database import SessionLocal
from src.core.models import SystemSetting
from src.stores.models import Store, Plan
from src.users.models import User
from src.orders.models import Order
from src.chat.models import Conversation, Message, AILog

class AdminService:

    @staticmethod
    def get_all_stores():
        db = SessionLocal()
        try:
            return db.query(Store).all()
        finally:
            db.close()

    @staticmethod
    def get_store_detail(store_id: int):
        db = SessionLocal()
        try:
            store = db.query(Store).filter_by(id=store_id).first()
            if not store:
                return None
                
            conv_count = db.query(Conversation).join(User).filter(User.store_id == store_id).count()
            order_count = db.query(Order).filter_by(store_id=store_id, status='paid').count()
            thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
            tokens_used = db.query(func.sum(AILog.prompt_tokens + AILog.completion_tokens)).filter(AILog.store_id == store_id, AILog.created_at >= thirty_days_ago).scalar() or 0
            
            return {
                "store": store,
                "conv_count": conv_count,
                "order_count": order_count,
                "tokens_used": tokens_used
            }
        except SQLAlchemyError:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def update_store(store_id: int, data: dict):
        db = SessionLocal()
        try:
            store = db.query(Store).filter_by(id=store_id).first()
            if not store:
                return None
                
            for key, value in data.items():
                if hasattr(store, key):
                    setattr(store, key, value)
                    
            db.commit()
            db.refresh(store)
            return store
        finally:
            db.close()

    @staticmethod
    def create_store(data: dict):
        db = SessionLocal()
        try:
            free_plan = db.query(Plan).filter(Plan.name == "Free").first()
            if not free_plan:
                free_plan = Plan(name="Free", price_usd=0.0, monthly_token_limit=100000, features='{"advanced": false}')
                db.add(free_plan)
                db.commit()
                db.refresh(free_plan)

            data["plan_id"] = free_plan.id
            data["monthly_token_limit"] = free_plan.monthly_token_limit
            
            new_store = Store(**data)
            db.add(new_store)
            db.commit()
            db.refresh(new_store)
            return new_store
        finally:
            db.close()
            
    @staticmethod
    def delete_store(store_id: int):
        db = SessionLocal()
        try:
            store = db.query(Store).filter_by(id=store_id).first()
            if store:
                db.delete(store)
                db.commit()
                return True
            return False
        finally:
            db.close()

    @staticmethod
    def get_system_settings():
        db = SessionLocal()
        try:
            return db.query(SystemSetting).all()
        finally:
            db.close()

    @staticmethod
    def update_system_settings(data: dict):
        db = SessionLocal()
        try:
            for key, value in data.items():
                setting = db.query(SystemSetting).filter_by(key=key).first()
                if setting:
                    setting.value = value
                else:
                    db.add(SystemSetting(key=key, value=value))
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def get_global_stats():
        db = SessionLocal()
        try:
            active_stores = db.query(Store).filter_by(status='active').count()
            total_revenue = db.query(func.sum(Store.plan_price)).scalar() or 0
            total_stores = db.query(func.count(Store.id)).scalar() or 0
            overdue_stores = db.query(Store).filter_by(payment_status='overdue').count()
            total_orders = db.query(func.count(Order.id)).scalar() or 0
            thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
            global_tokens = db.query(func.sum(AILog.prompt_tokens + AILog.completion_tokens)).filter(AILog.created_at >= thirty_days_ago).scalar() or 0
            
            return {
                "active_stores": active_stores,
                "total_revenue": total_revenue,
                "total_stores": total_stores,
                "overdue_stores": overdue_stores,
                "total_orders": total_orders,
                "global_tokens": global_tokens,
                "messages_today": 0,
                "admin_logs": [],
                "chart_dates": [],
                "chart_tokens": []
            }
        except SQLAlchemyError:
            db.rollback()
            return None
        finally:
            db.close()

    @staticmethod
    def get_ai_usage():
        db = SessionLocal()
        try:
            logs = db.query(AILog).order_by(AILog.created_at.desc()).limit(10).all()
            return [{"store_id": l.store_id, "prompt_tokens": l.prompt_tokens} for l in logs]
        finally:
            db.close()

    @staticmethod
    def get_subscription_days(store_id: int):
        db = SessionLocal()
        try:
            store = db.query(Store).filter_by(id=store_id).first()
            if store and getattr(store, 'next_billing_date', None):
                return max((store.next_billing_date - datetime.datetime.utcnow()).days, 0)
            return 0
        finally:
            db.close()

    @staticmethod
    def get_latest_messages():
        db = SessionLocal()
        try:
            msgs = db.query(Message).order_by(Message.timestamp.desc()).limit(10).all()
            return [{"id": m.id, "role": m.role, "content": m.content} for m in msgs]
        finally:
            db.close()
            
    @staticmethod
    def get_latest_conversations():
        db = SessionLocal()
        try:
            convs = db.query(Conversation).order_by(Conversation.created_at.desc()).limit(10).all()
            return [{"id": c.id, "user_id": c.user_id, "requires_human": c.requires_human} for c in convs]
        finally:
            db.close()

    @staticmethod
    def update_store_plan(store_id: int, plan_id: int):
        db = SessionLocal()
        try:
            store = db.query(Store).filter_by(id=store_id).first()
            plan = db.query(Plan).filter_by(id=plan_id).first()
            if store and plan:
                store.plan_id = plan.id
                store.monthly_token_limit = plan.monthly_token_limit
                db.commit()
                return True
            return False
        finally:
            db.close()

    @staticmethod
    def update_subscription_status(store_id: int, status: str):
        db = SessionLocal()
        try:
            store = db.query(Store).filter_by(id=store_id).first()
            if store:
                store.subscription_status = status
                db.commit()
                return True
            return False
        finally:
            db.close()

    @staticmethod
    def get_all_features():
        from src.core.models import FeatureFlag
        db = SessionLocal()
        try:
            return db.query(FeatureFlag).all()
        finally:
            db.close()

    @staticmethod
    def toggle_feature(key: str):
        from src.core.feature_service import FeatureService
        return FeatureService.toggle_feature(key)
