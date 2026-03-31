import os

filepath = "C:/Users/yaman/.gemini/antigravity/playground/ai-sales-saas/src/main.py"
with open(filepath, 'r', encoding='utf-8') as f:
    code = f.read()

# Make sure not to duplicate
if "/admin/ai-health" not in code:
    health_endpoint = """
@app.route("/admin/ai-health")
@admin_required
def admin_ai_health():
    import redis
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        # Parse metrics
        success = int(r.get("ai:success") or 0)
        retry = int(r.get("ai:retry") or 0)
        fallback = int(r.get("ai:fallback") or 0)
        failure = int(r.get("ai:failure") or 0)
        
        total = success + fallback + failure
        if total == 0:
            success_rate = 100.0
            failure_rate = 0.0
            fallback_rate = 0.0
        else:
            success_rate = round(success / total * 100, 2)
            failure_rate = round(failure / total * 100, 2)
            fallback_rate = round(fallback / total * 100, 2)
            
        # Parse providers
        from src.ai_engine.service import ai_engine
        providers = ai_engine.router.providers
        
        active_providers = []
        degraded_providers = []
        best_provider = None
        min_failures = float('inf')
        
        for name, provider in providers.items():
            if provider.is_configured():
                if ai_engine.router._is_degraded(name):
                    degraded_providers.append(name)
                else:
                    active_providers.append(name)
                    # Simple heuristic: provider with least failures in the current window is "best"
                    fails = r.llen(f"failure_streak:{name}")
                    if fails < min_failures:
                        min_failures = fails
                        best_provider = name

        return jsonify({
            "status": "online" if active_providers else "degraded",
            "global_metrics": {
                "success_rate_percent": success_rate,
                "failure_rate_percent": failure_rate,
                "fallback_percent": fallback_rate,
                "raw_counts": {
                    "success": success,
                    "retry": retry,
                    "fallback": fallback,
                    "failure": failure
                }
            },
            "providers": {
                "active": active_providers,
                "degraded": degraded_providers,
                "best_recommended": best_provider or "none"
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
"""
    # Append to the end of the file
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write("\n" + health_endpoint)
    print("Health Endpoint Added")
else:
    print("Health Endpoint Already Exists")
