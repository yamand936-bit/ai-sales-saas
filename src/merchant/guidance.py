import datetime
from sqlalchemy import func
from src.core.database import SessionLocal
from src.chat.models import Conversation, AILog
from src.stores.models import Store

class GuidanceEngine:

    @staticmethod
    def get_insights(store: Store, total_tokens: int, pending_human: int) -> list:
        insights = []

        # 1. Critical priorities (danger)
        if not store.ai_enabled:
            insights.append({
                "type": "danger",
                "message": "AI is OFF — you are losing customers",
                "action": "Enable AI",
                "js_action": "document.getElementById('nav-settings').click();",
                "priority": 1
            })

        # 2. Token Usage Warning (warning)
        limit = store.monthly_token_limit if store.monthly_token_limit else 100000
        if limit > 0:
            usage_perc = (total_tokens / limit) * 100
            if usage_perc >= 80:
                insights.append({
                    "type": "warning",
                    "message": f"You used {int(usage_perc)}% of your plan limit",
                    "action": "Upgrade plan",
                    "js_action": "alert('Contact an admin to upgrade your plan limit.');",
                    "priority": 2
                })

        # 3. Operations Info (info)
        if pending_human > 5:
            insights.append({
                "type": "info",
                "message": f"You have {pending_human} customers waiting for human response",
                "action": "Reply now",
                "js_action": "document.getElementById('nav-chat').click();",
                "priority": 3
            })

        # Sort by priority
        return sorted(insights, key=lambda x: x["priority"])
