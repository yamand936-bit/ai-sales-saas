#!/bin/bash
set -e
set -o pipefail

PROJECT_DIR="/root/ai-sales-saas"
LOG_FILE="/root/deploy.log"
BACKUP_DIR="/root/backups/$(date +%F_%T)"
BACKUP_CREATED=false

# Setup logging
exec > >(tee -a ${LOG_FILE} )
exec 2> >(tee -a ${LOG_FILE} >&2 )

echo "=================================================="
echo "🚀 STABLE DEPLOYMENT STARTED AT $(date)"
echo "=================================================="

# Rollback function
rollback() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo "❌ FATAL: Deployment failed with exit code $exit_code!"
        
        if [ "$BACKUP_CREATED" = "true" ]; then
            echo "⏪ INITIATING CIRTICAL ROLLBACK FROM $BACKUP_DIR..."
            
            # Stop services before restoring
            systemctl stop ai-sales-saas || true
            systemctl stop ai-sales-celery || true
            
            # Restore files from backup directory
            cp -r $BACKUP_DIR/* $PROJECT_DIR/
            
            echo "🔄 Restarting services post-rollback..."
            systemctl start ai-sales-saas || true
            systemctl start ai-sales-celery || true
            
            echo "✅ ROLLBACK COMPLETE. System forcibly restored to previous stable state."
        else
            echo "⚠️ No backup was created yet. Cannot rollback."
        fi
        
        echo "=================================================="
        echo "❌ DEPLOYMENT FAILED AT $(date)"
        echo "=================================================="
        exit $exit_code
    fi
}

# Trap ERR and EXIT signals to route through rollback on failure
trap rollback EXIT

# 1. Project Directory Check
cd ${PROJECT_DIR} || { echo "❌ Failed to change directory"; exit 1; }

# 2. Backup phase
echo "📦 Creating isolated snapshot backup..."
mkdir -p $BACKUP_DIR
# Using standard recursive copy as requested
cp -r $PROJECT_DIR/* $BACKUP_DIR/
BACKUP_CREATED=true
echo "✅ Backup successfully stored at $BACKUP_DIR"

# 3. Pull latest code
echo "📥 Pulling latest code..."
git pull origin main || { echo "❌ Git pull failed"; exit 1; }

# 4. Dependency Parity Check
if [ -f "requirements.txt" ]; then
    echo "📦 Checking and installing dependencies..."
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate || true
fi

# 5. Flush Python Bytecode
echo "🧹 Flushing python bytecode caches..."
find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true

# 6. Redis Infrastructure Validation
echo "🔍 Checking Redis availability..."
systemctl is-active --quiet redis-server || systemctl is-active --quiet redis || {
    echo "⚠️ Redis is NOT running! Attempting to force start..."
    systemctl start redis-server || systemctl start redis || { echo "❌ Failed to start Redis"; exit 1; }
}
echo "✅ Redis background datastore is active."

# 7. Restart Services Safely
echo "🔄 Restarting core services safely..."
systemctl restart ai-sales-saas || { echo "❌ Failed restarting ai-sales-saas web server"; exit 1; }
systemctl restart ai-sales-celery || { echo "❌ Failed restarting ai-sales-celery worker"; exit 1; }

# Optional Beat Scheduler Restart
systemctl restart ai-sales-celery-beat 2>/dev/null || echo "ℹ️ Celery Beat scheduler not detected. Skipping."

# Allow services to fully boot bindings
sleep 3

# 8. Web Health Validation
echo "🌐 Invoking application health ping..."
curl -f http://127.0.0.1:8000 || {
    echo "❌ Fatal: App HTTP server is not responding!"
    exit 1
}
echo "✅ Local health check passed!"

# Remove the trap condition since deployment successfully completed without errors
trap - EXIT

# 9. Final Output Dump
echo "=================================================="
echo "🎉 SUCCESS: DEPLOYMENT COMPLETE AT $(date)!"
echo "=================================================="
echo "📊 SERVICE UPTIME METRICS:"
echo "--- Gunicorn Web Server ---"
systemctl status ai-sales-saas --no-pager | grep -i "Active:"
echo "--- Celery Background Worker ---"
systemctl status ai-sales-celery --no-pager | grep -i "Active:"
echo "=================================================="
