#!/bin/bash
# AI Sales SaaS - Celery Worker & Beat SystemD Installation Script
# This script configures the background daemon allowing the AI agents to reply to webhooks 24/7 without stalling the Flask server.

echo "Installing Celery Systemd Services..."

# 1. Create the Celery Worker Service
cat << 'EOF' > /etc/systemd/system/ai-sales-celery.service
[Unit]
Description=AI Sales SaaS - Celery Worker
After=network.target redis-server.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/root/ai-sales-saas
Environment="PATH=/root/ai-sales-saas/venv/bin:$PATH"
Environment="PYTHONPATH=/root/ai-sales-saas"
ExecStart=/root/ai-sales-saas/venv/bin/celery -A src.core.celery_app.celery worker --loglevel=info --concurrency=2

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 2. Create the Celery Beat Service (Cron Scheduler for Expirations)
cat << 'EOF' > /etc/systemd/system/ai-sales-celery-beat.service
[Unit]
Description=AI Sales SaaS - Celery Beat Scheduler
After=network.target redis-server.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/root/ai-sales-saas
Environment="PATH=/root/ai-sales-saas/venv/bin:$PATH"
Environment="PYTHONPATH=/root/ai-sales-saas"
ExecStart=/root/ai-sales-saas/venv/bin/celery -A src.core.celery_app.celery beat --loglevel=info

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd deamons..."
systemctl daemon-reload

echo "Enabling and Starting Celery Worker..."
systemctl enable ai-sales-celery
systemctl start ai-sales-celery

echo "Enabling and Starting Celery Beat..."
systemctl enable ai-sales-celery-beat
systemctl start ai-sales-celery-beat

echo "✅ Celery successfully installed and initiated!"
systemctl status ai-sales-celery --no-pager
systemctl status ai-sales-celery-beat --no-pager
