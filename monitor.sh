#!/bin/bash

# ==========================================
# PRODUCTION MONITORING & ALERTING SYSTEM
# ==========================================

TELEGRAM_BOT_TOKEN="8220000360:AAEwDWXS8KB3Rzpt3AKbfZ9TJGT27pRbBes"
TELEGRAM_CHAT_ID="-1003698053410"
STATE_FILE="$HOME/monitor_state.txt"
LOG_FILE="$HOME/monitor.log"
COOLDOWN_SEC=300 # 5 minutes

# Initialize state
if [ ! -f "$STATE_FILE" ]; then
    cat <<EOF > "$STATE_FILE"
LAST_ALERT_WEB=0
LAST_ALERT_CELERY=0
LAST_ALERT_ERROR=0
LAST_ERROR_HASH=""
RESTART_COUNT_WEB=0
FIRST_RESTART_TIME_WEB=0
RESTART_COUNT_CELERY=0
FIRST_RESTART_TIME_CELERY=0
WEB_PREV_STATE="UP"
CELERY_PREV_STATE="UP"
EOF
fi

source "$STATE_FILE"

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

save_state() {
    cat <<EOF > "$STATE_FILE"
LAST_ALERT_WEB=$LAST_ALERT_WEB
LAST_ALERT_CELERY=$LAST_ALERT_CELERY
LAST_ALERT_ERROR=$LAST_ALERT_ERROR
LAST_ERROR_HASH="$LAST_ERROR_HASH"
RESTART_COUNT_WEB=$RESTART_COUNT_WEB
FIRST_RESTART_TIME_WEB=$FIRST_RESTART_TIME_WEB
RESTART_COUNT_CELERY=$RESTART_COUNT_CELERY
FIRST_RESTART_TIME_CELERY=$FIRST_RESTART_TIME_CELERY
WEB_PREV_STATE="$WEB_PREV_STATE"
CELERY_PREV_STATE="$CELERY_PREV_STATE"
EOF
}

send_telegram_alert() {
    local issue_type="$1"   # web | celery | error
    local service_name="$2" # ai-sales-saas | ai-sales-celery | System
    local status="$3"       # DOWN | ERROR | RECOVERED | FLAPPING
    local error_text="$4"   # Details / Traceback
    
    local now=$(date +%s)
    
    # Evaluate Cooldown per issue (except RECOVERED which sends immediately)
    if [ "$status" != "RECOVERED" ] && [ "$status" != "FLAPPING" ]; then
        local time_since=9999
        if [ "$issue_type" == "web" ]; then time_since=$((now - LAST_ALERT_WEB)); fi
        if [ "$issue_type" == "celery" ]; then time_since=$((now - LAST_ALERT_CELERY)); fi
        if [ "$issue_type" == "error" ]; then time_since=$((now - LAST_ALERT_ERROR)); fi

        if [ $time_since -lt $COOLDOWN_SEC ]; then
            log "Skipping [$issue_type] alert ($status) - active cooldown"
            return
        fi
    fi

    # Escape HTML specifically to prevent Telegram parser crashes
    local safe_err=$(echo -e "$error_text" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')
    
    local formatted_msg="🚨 <b>AI Sales Server Alert</b> 🚨%0A%0A"
    formatted_msg+="<b>Service:</b> ${service_name}%0A"
    formatted_msg+="<b>Status:</b> ${status}%0A"
    formatted_msg+="<b>Time:</b> $(date +'%Y-%m-%d %H:%M:%S')%0A%0A"
    
    if [ "$status" == "RECOVERED" ]; then
        formatted_msg+="<b>Details:</b>%0A<pre>${safe_err}</pre>"
    else
        formatted_msg+="<b>Error:</b>%0A<pre>${safe_err}</pre>"
    fi
    
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d parse_mode="HTML" \
        -d text="$formatted_msg" > /dev/null
        
    if [ "$status" != "RECOVERED" ] && [ "$status" != "FLAPPING" ]; then
        if [ "$issue_type" == "web" ]; then LAST_ALERT_WEB=$now; fi
        if [ "$issue_type" == "celery" ]; then LAST_ALERT_CELERY=$now; fi
        if [ "$issue_type" == "error" ]; then LAST_ALERT_ERROR=$now; fi
        save_state
    fi
}

check_flapping() {
    local service="$1"
    local now=$(date +%s)
    local count=0
    local first_time=0
    
    if [ "$service" == "ai-sales-saas" ]; then
        count=$RESTART_COUNT_WEB
        first_time=$FIRST_RESTART_TIME_WEB
    else
        count=$RESTART_COUNT_CELERY
        first_time=$FIRST_RESTART_TIME_CELERY
    fi
    
    # Reset threshold window outside of 5 mins (300 sec)
    if [ $((now - first_time)) -gt 300 ]; then
        count=0
        first_time=$now
    fi
    
    count=$((count + 1))
    
    if [ "$service" == "ai-sales-saas" ]; then
        RESTART_COUNT_WEB=$count
        FIRST_RESTART_TIME_WEB=$first_time
    else
        RESTART_COUNT_CELERY=$count
        FIRST_RESTART_TIME_CELERY=$first_time
    fi
    save_state
    
    if [ $count -ge 3 ]; then
        log "⚠️ FATAL: Service $service is FLAPPING (restarted $count times in 5 mins)."
        send_telegram_alert "system" "$service" "FLAPPING" "Service restarted too many times. Manual intervention required."
        return 1 # FLAPPING: do not restart
    fi
    return 0 # SAFE: proceed with restart
}

log "🛡️ Advanced Production Monitoring Online."

while true; do
    
    WEB_DOWN=0
    CELERY_DOWN=0
    
    # 1. Healthcheck Gunicorn URL + Service Unit
    curl -s -f http://127.0.0.1:8000/ > /dev/null
    if [ $? -ne 0 ]; then
        WEB_DOWN=1
    fi
    
    systemctl is-active --quiet ai-sales-saas
    if [ $? -ne 0 ]; then
        WEB_DOWN=1
    fi
    
    if [ $WEB_DOWN -eq 1 ]; then
        if [ "$WEB_PREV_STATE" == "UP" ]; then
            log "❌ Web server (ai-sales-saas) detected OFFLINE"
            WEB_PREV_STATE="DOWN"
            save_state
            send_telegram_alert "web" "ai-sales-saas" "DOWN" "Service not responding to health check"
        fi
        
        check_flapping "ai-sales-saas"
        if [ $? -eq 0 ]; then
            systemctl restart ai-sales-saas
        fi
    else
        if [ "$WEB_PREV_STATE" == "DOWN" ]; then
            log "✅ Web server (ai-sales-saas) RECOVERED"
            WEB_PREV_STATE="UP"
            save_state
            send_telegram_alert "web" "ai-sales-saas" "RECOVERED" "Service restored successfully"
        fi
    fi

    # 2. Healthcheck Celery Worker
    systemctl is-active --quiet ai-sales-celery
    if [ $? -ne 0 ]; then
        if [ "$CELERY_PREV_STATE" == "UP" ]; then
            log "❌ Background Worker (ai-sales-celery) detected OFFLINE"
            CELERY_PREV_STATE="DOWN"
            save_state
            send_telegram_alert "celery" "ai-sales-celery" "DOWN" "Service not responding to health check"
        fi
        
        check_flapping "ai-sales-celery"
        if [ $? -eq 0 ]; then
            systemctl restart ai-sales-celery
        fi
    else
        if [ "$CELERY_PREV_STATE" == "DOWN" ]; then
            log "✅ Background Worker (ai-sales-celery) RECOVERED"
            CELERY_PREV_STATE="UP"
            save_state
            send_telegram_alert "celery" "ai-sales-celery" "RECOVERED" "Service restored successfully"
        fi
    fi
    
    # 3. Log Hashing & Trace Diagnostics
    ERRORS=$(journalctl -u ai-sales-celery -n 30 --no-pager | grep -i "error\|traceback" -A 2 | grep -v -i "Idempotency")
    
    if [ ! -z "$ERRORS" ]; then
        # Create a unique 32-char footprint of the error cluster
        CURRENT_ERROR_HASH=$(echo "$ERRORS" | md5sum | awk '{print $1}')
        
        if [ "$CURRENT_ERROR_HASH" != "$LAST_ERROR_HASH" ]; then
            log "⚠️ Unique Trace Exception caught (Hash: $CURRENT_ERROR_HASH)"
            
            # Grab just the bottom 4 trace lines (or context)
            LAST_ERR=$(echo "$ERRORS" | tail -n 4)
            send_telegram_alert "error" "ai-sales-celery" "ERROR" "$LAST_ERR"
            
            LAST_ERROR_HASH="$CURRENT_ERROR_HASH"
            save_state
        fi
    fi

    sleep 30
done
