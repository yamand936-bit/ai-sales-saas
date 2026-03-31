import datetime
import json
import logging
from sqlalchemy import func
from src.core.database import SessionLocal
from src.stores.models import Store
from src.products.models import Product
from src.orders.models import Order
from src.chat.models import Conversation, Message, AILog
from src.users.models import User

class MerchantService:
    @staticmethod
    def get_dashboard(store_id: int):
        db = SessionLocal()
        import datetime
        try:
            store = db.query(Store).filter_by(id=store_id).first()
            if not store:
                return None
    
            # Basic Stats
            total_conversations = db.query(Conversation).join(User).filter(User.store_id == store.id).count()
            paid_users = db.query(User).join(Order).filter(User.store_id == store.id, Order.status == 'paid').distinct().count()
            total_users = db.query(User).filter_by(store_id=store.id).count()
            total_orders = db.query(Order).filter_by(store_id=store.id, status='paid').count()
            revenue = db.query(func.sum(Order.total_amount)).filter(Order.store_id == store.id, Order.status == 'paid').scalar() or 0
            conversion_rate = round((paid_users / total_users * 100), 1) if total_users > 0 else 0
    
            # Tokens & AI
            from src.chat.models import AILog
            from sqlalchemy.exc import SQLAlchemyError
            
            try:
                total_tokens = db.query(func.sum(AILog.prompt_tokens + AILog.completion_tokens)).filter(AILog.store_id == store.id).scalar() or 0
                ai_interactions = db.query(AILog).filter_by(store_id=store.id).count()
            except SQLAlchemyError:
                db.rollback()
                total_tokens = 0
                ai_interactions = 0
            
            # Token Warning Calculation
            monthly_token_limit = store.monthly_token_limit or 100000
            token_warning = total_tokens >= (monthly_token_limit * 0.8)
            
            # Realtime AI Metrics (Redis)
            avg_latency = 450
            total_cost = 0.0
            total_ai_requests = 0
            try:
                import redis
                from src.core.config import settings
                r = redis.from_url(settings.REDIS_URL, decode_responses=True)
                
                # Dynamic Latency
                latencies = r.lrange(f"ai:metrics:latency:store:{store.id}", 0, 99)
                if latencies:
                    avg_latency = sum(int(l) for l in latencies) // len(latencies)
                
                # Dynamic Cost
                cost_val = r.get(f"ai:metrics:cost:store:{store.id}")
                if cost_val: total_cost = round(float(cost_val), 4)
                
                # Daily AI Requests (realtime)
                today = __import__('time').strftime("%Y-%m-%d")
                ai_reqs = r.get(f"ai:metrics:requests:store:{store.id}")
                if ai_reqs: total_ai_requests = int(ai_reqs)
                
                # Success/Failure Rates (Global node health)
                global_success = int(r.get(f"ai:openai:success") or 0) + int(r.get(f"ai:gemini:success") or 0)
                global_retry = int(r.get(f"ai:openai:retry") or 0) + int(r.get(f"ai:gemini:retry") or 0)
                global_failure = int(r.get(f"ai:openai:failure") or 0) + int(r.get(f"ai:gemini:failure") or 0)
                
                total_attempts = global_success + global_retry + global_failure
                success_rate = round((global_success / total_attempts) * 100, 1) if total_attempts > 0 else 100.0
                failure_rate = round(((global_retry + global_failure) / total_attempts) * 100, 1) if total_attempts > 0 else 0.0
                
            except Exception as e:
                success_rate = 100.0
                failure_rate = 0.0
                import logging
                logging.getLogger(__name__).warning("Redis metrics unavailable: " + str(e))
            # Lists for CRM / Inventory / Orders
            try:
                conversations = db.query(Conversation).join(User).filter(User.store_id == store.id).order_by(Conversation.created_at.desc()).all()
                import json
                for c in conversations:
                    c.lead_status = "unknown"
                    if c.context:
                        try:
                            ctx = json.loads(c.context)
                            c.lead_status = ctx.get("lead_status", "unknown")
                            c.follow_up_sent = ctx.get("follow_up_sent", False)
                            c.follow_up_replied = ctx.get("follow_up_replied", False)
                            c.converted = ctx.get("converted", False)
                            c.conversion_after_followup = ctx.get("conversion_after_followup", False)
                            c.last_product = ctx.get("last_product", "")
                            c.price_range = ctx.get("price_range", "")
                            c.intent = ctx.get("intent", "")
                        except Exception:
                            pass
                            
                human_requests = [c for c in conversations if c.requires_human]
                products = db.query(Product).filter(Product.store_id == store.id).all()
                orders = db.query(Order).filter(Order.store_id == store.id).order_by(Order.created_at.desc()).all()
            except SQLAlchemyError:
                db.rollback()
                conversations = []
                human_requests = []
                products = []
                orders = []
            users = db.query(User).filter_by(store_id=store.id).all()
    
            is_expired = False
            if store.expires_at and store.expires_at < datetime.datetime.utcnow():
                is_expired = True
    
            try:
                from sqlalchemy import cast, Date
                thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
                logs = db.query(
                    func.date(AILog.created_at).label('date'),
                    func.sum(AILog.prompt_tokens + AILog.completion_tokens).label('tokens')
                ).filter(AILog.store_id == store.id, AILog.created_at >= thirty_days_ago).group_by(func.date(AILog.created_at)).all()
                chart_dates = [log.date for log in logs if log.date]
                chart_tokens = [log.tokens for log in logs if log.date]
            except SQLAlchemyError:
                chart_dates = []
                chart_tokens = []
    
            print("API HIT: /merchant/dashboard-data")
            print("TOGGLE AI:", store.ai_enabled)
    
            # AI Smart Insights Logic
            ai_insights = []
            import logging
            logger = logging.getLogger(__name__)
    
            # Task 4: Insights Improvement
            if total_conversations > 10:
                if conversion_rate < 5.0:
                    msg = f"Your conversion rate is {conversion_rate}% (below average 5-8%). Review store policy to push for sales."
                    ai_insights.append({"icon": "⚠️", "text": msg, "color": "red"})
                    logger.info(f"Insight Generated (Store {store.id}): Low Conversion Warning")
                elif 5.0 <= conversion_rate <= 10.0:
                    msg = f"Your conversion rate is {conversion_rate}% (average). Offer a discount code to push hesitant leads."
                    ai_insights.append({"icon": "💡", "text": msg, "color": "blue"})
                    logger.info(f"Insight Generated (Store {store.id}): Average Conversion Notice")
                else:
                    msg = f"Your conversion rate is {conversion_rate}% (above average). Great job maintaining healthy engagement!"
                    ai_insights.append({"icon": "🚀", "text": msg, "color": "green"})
                    logger.info(f"Insight Generated (Store {store.id}): Good Conversion Praise")
    
            if total_tokens > (monthly_token_limit * 0.4) and conversion_rate < 5.0:
                msg = "Efficiency Warning: High token use without enough sales. Switch AI Mode to 'Sales'."
                ai_insights.append({"icon": "💸", "text": msg, "color": "yellow"})
                logger.info(f"Insight Generated (Store {store.id}): Efficiency Token Warning")
            
            if total_conversations > 0 and len(human_requests) > (total_conversations * 0.3):
                ai_insights.append({"icon": "👨‍💼", "text": "طلب تدخل بشري كبير يفوق 30%. يرجى مراجعة 'سياسة المتجر' وتزويد المساعد بمعلومات أكثر شمولية.", "color": "yellow"})
                
            if not ai_insights:
                if total_conversations == 0:
                    ai_insights.append({"icon": "✨", "text": "مرحباً! ستظهر التحليلات الذكية هنا فور بدء المحادثات.", "color": "blue"})
                else:
                    ai_insights.append({"icon": "✅", "text": "وضع المنصة مستقر ومعدل الاستجابة مثالي.", "color": "green"})
    
            # Task 1 & 4 Calculation
            followups_sent = sum(1 for c in conversations if getattr(c, "follow_up_sent", False))
            replied_count = sum(1 for c in conversations if getattr(c, "follow_up_replied", False))
            conversions_after = sum(1 for c in conversations if getattr(c, "conversion_after_followup", False))
            
            followup_rate = round((followups_sent / total_conversations) * 100, 1) if total_conversations > 0 else 0
            reply_rate = round((replied_count / followups_sent) * 100, 1) if followups_sent > 0 else 0
            conversion_after_rate = round((conversions_after / replied_count) * 100, 1) if replied_count > 0 else 0
    
            # Task 5
            if followups_sent > 0 and conversions_after > 0:
                imp_pct = round((conversions_after / total_conversations) * 100, 1) if total_conversations else 0
                if imp_pct > 0:
                    ai_insights.append({"icon": "📈", "text": f"Follow-ups improved conversion by {imp_pct}%", "color": "green"})
    
            metrics_funnel = {
                "total": total_conversations,
                "followups_sent": followups_sent,
                "replied": replied_count,
                "conversions_after": conversions_after,
                "followup_rate": followup_rate,
                "reply_rate": reply_rate,
                "conversion_after_rate": conversion_after_rate
            }
    
            return {
                "store": store,
                "lang": store.language or "ar",
                "is_expired": is_expired,
                "token_warning": token_warning,
                "monthly_token_limit": monthly_token_limit,
                "total_conversations": total_conversations,
                "total_orders": total_orders,
                "conversion_rate": conversion_rate,
                "total_tokens": total_tokens,
                "avg_latency": avg_latency,
                "total_cost": total_cost,
                "total_ai_requests": total_ai_requests,
                "ai_success_rate": success_rate,
                "ai_failure_rate": failure_rate,
                "ai_interactions": ai_interactions,
                "chart_dates": json.dumps(chart_dates),
                "chart_tokens": json.dumps(chart_tokens),
                "conversations": conversations,
                "human_requests": human_requests,
                "products": products,
                "orders": orders,
                "users": users,
                "revenue": revenue,
                "ai_insights": ai_insights,
                "metrics_funnel": metrics_funnel
            }
        finally:
            db.close()
    
    
    @staticmethod
    def get_products(store_id: int):
        db = SessionLocal()
        try:
            return db.query(Product).filter(Product.store_id == store_id).all()
        finally:
            db.close()

    @staticmethod
    def create_product(store_id: int, data: dict):
        db = SessionLocal()
        try:
            product = Product(**data, store_id=store_id)
            db.add(product)
            db.commit()
            db.refresh(product)
            return product
        finally:
            db.close()

    @staticmethod
    def update_product(product_id: int, data: dict):
        db = SessionLocal()
        try:
            product = db.query(Product).get(product_id)
            for key, value in data.items():
                setattr(product, key, value)
            db.commit()
            db.refresh(product)
            return product
        finally:
            db.close()

    @staticmethod
    def delete_product(product_id: int):
        db = SessionLocal()
        try:
            product = db.query(Product).get(product_id)
            db.delete(product)
            db.commit()
            return True
        finally:
            db.close()

    @staticmethod
    def get_orders(store_id: int):
        db = SessionLocal()
        try:
            return db.query(Order).filter(Order.store_id == store_id).all()
        finally:
            db.close()

    @staticmethod
    def get_order(order_id: int):
        db = SessionLocal()
        try:
            return db.query(Order).filter_by(id=order_id).first()
        finally:
            db.close()

    @staticmethod
    def update_order_status(order_id: int, status: str):
        db = SessionLocal()
        try:
            order = db.query(Order).filter_by(id=order_id).first()
            if not order:
                return None
            order.status = status
            db.commit()
            db.refresh(order)
            return order
        finally:
            db.close()

    @staticmethod
    def get_conversations(store_id: int):
        db = SessionLocal()
        try:
            return db.query(Conversation).join(User).filter(User.store_id == store_id).order_by(Conversation.created_at.desc()).all()
        finally:
            db.close()

    @staticmethod
    def get_messages(conversation_id: int):
        db = SessionLocal()
        try:
            return db.query(Message).filter_by(conversation_id=conversation_id).order_by(Message.timestamp).all()
        finally:
            db.close()

    @staticmethod
    def add_message(conversation_id: int, role: str, content: str):
        db = SessionLocal()
        try:
            msg = Message(conversation_id=conversation_id, role=role, content=content)
            db.add(msg)
            db.commit()
            db.refresh(msg)
            return msg
        finally:
            db.close()

    @staticmethod
    def get_store(store_id: int):
        db = SessionLocal()
        try:
            return db.query(Store).filter_by(id=store_id).first()
        finally:
            db.close()

    @staticmethod
    def get_store_by_domain(domain: str):
        db = SessionLocal()
        try:
            return db.query(Store).filter_by(domain=domain).first()
        finally:
            db.close()

    @staticmethod
    def get_store_by_email(email: str):
        db = SessionLocal()
        try:
            return db.query(Store).filter_by(owner_email=email).first()
        finally:
            db.close()

    @staticmethod
    def get_users(store_id: int):
        db = SessionLocal()
        try:
            return db.query(User).filter_by(store_id=store_id).all()
        finally:
            db.close()

    @staticmethod
    def get_user(user_id: int, store_id: int):
        db = SessionLocal()
        try:
            return db.query(User).filter_by(id=user_id, store_id=store_id).first()
        finally:
            db.close()

    @staticmethod
    def get_user_by_telegram(telegram_id: str, store_id: int):
        db = SessionLocal()
        try:
            return db.query(User).filter_by(
                telegram_id=telegram_id,
                store_id=store_id
            ).first()
        finally:
            db.close()

    @staticmethod
    def get_ai_config(store_id: int):
        db = SessionLocal()
        try:
            store = db.query(Store).filter_by(id=store_id).first()
            if not store:
                return None
            return {
                "telegram_token": store.telegram_token,
                "whatsapp_token": store.whatsapp_token,
                "instagram_token": store.instagram_token,
                "ai_mode": store.ai_mode,
                "ai_enabled": store.ai_enabled,
            }
        finally:
            db.close()

    @staticmethod
    def update_ai_config(store_id: int, data: dict):
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
    def toggle_conversation_human_mode(conv_id: int):
        db = SessionLocal()
        try:
            conv = db.query(Conversation).filter_by(id=conv_id).first()
            if not conv:
                return None
            conv.requires_human = not conv.requires_human
            db.commit()
            return conv
        finally:
            db.close()

    @staticmethod
    def resolve_conversation(conv_id: int):
        db = SessionLocal()
        try:
            conv = db.query(Conversation).filter_by(id=conv_id).first()
            if not conv:
                return None
            conv.requires_human = False
            db.commit()
            return conv
        finally:
            db.close()

    @staticmethod
    def update_conversation_context(conv_id: int, context: str):
        db = SessionLocal()
        try:
            conv = db.query(Conversation).filter_by(id=conv_id).first()
            if not conv:
                return None
            conv.context = context
            db.commit()
            return conv
        finally:
            db.close()
