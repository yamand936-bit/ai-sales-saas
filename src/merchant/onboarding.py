from src.core.database import SessionLocal
from src.stores.models import Store
from src.chat.models import Conversation
import logging

logger = logging.getLogger(__name__)

class OnboardingEngine:
    @staticmethod
    def get_current_step(store: Store) -> int:
        current_step = store.onboarding_step or 0
        
        # Auto progression logic
        new_step = current_step
        
        # Check Step 1: AI Enabled
        if new_step == 0 and store.ai_enabled:
            new_step = 1
            
        # Check Step 2: Telegram connected
        if new_step == 1 and store.telegram_token:
            new_step = 2
            
        # Check Step 3: First message sent
        if new_step == 2:
            db = SessionLocal()
            try:
                # Store hasn't directly linked Conversation but User belongs to Store
                from src.users.models import User
                conv_count = db.query(Conversation).join(User).filter(User.store_id == store.id).count()
                if conv_count > 0:
                    new_step = 3
            except Exception as e:
                logger.error(f"Onboarding step calculation error: {e}")
            finally:
                db.close()
                
        # If progress made, update DB
        if new_step > current_step:
            db = SessionLocal()
            try:
                db_store = db.query(Store).filter_by(id=store.id).first()
                if db_store:
                    db_store.onboarding_step = new_step
                    db.commit()
            except Exception as e:
                logger.error(f"Failed to save onboarding progress: {e}")
            finally:
                db.close()
                
        return new_step

    @staticmethod
    def get_steps() -> list:
        return [
            {"step": 1, "title": "Enable AI", "action": "go_settings", "js_action": "document.getElementById('nav-settings').click();"},
            {"step": 2, "title": "Connect Telegram", "action": "connect_telegram", "js_action": "document.getElementById('nav-settings').click(); alert('Enter your Telegram Token in settings.');"},
            {"step": 3, "title": "Send Test Message", "action": "test_message", "js_action": "alert('Go to your Telegram bot and send a test message to activate the system.');"},
            {"step": 4, "title": "Go Live", "action": "done", "js_action": ""}
        ]
