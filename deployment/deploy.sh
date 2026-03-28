#!/bin/bash
# Production Deployment Script for AI Sales SaaS
# Note: Must be run as root or with sudo on a Debian/Ubuntu Linux server.

set -e

echo "Starting Deployment..."

# 1. Server Setup
echo "Updating packages..."
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y python3 python3-pip python3-venv nginx git curl docker.io docker-compose certbot python3-certbot-nginx

# 2. Project Setup
PROJECT_DIR="/opt/ai-sales-saas"
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Cloning repository..."
    # Replace with actual repository URL
    sudo git clone https://github.com/your-repo/ai-sales-saas.git $PROJECT_DIR
else
    echo "Pulling latest changes..."
    cd $PROJECT_DIR && sudo git pull
fi

cd $PROJECT_DIR

echo "Creating virtual environment..."
sudo python3 -m venv venv
source venv/bin/activate

echo "Installing requirements..."
pip install -r requirements.txt
pip install gunicorn psycopg2-binary
# Ensure Celery and Redis are installed
pip install celery redis fastapi-limiter

# 3. Environment Configuration
echo "Configuring environment..."
if [ ! -f ".env" ]; then
    sudo cp .env.example .env
    echo "Please update the .env file with actual production secrets."
fi

# 4. Infrastructure (Docker)
echo "Starting PostgreSQL and Redis..."
sudo docker start ai_sales_postgres || sudo docker run -d --name ai_sales_postgres --restart always -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=saas -p 5432:5432 postgres
sudo docker start ai_sales_redis || sudo docker run -d --name ai_sales_redis --restart always -p 6379:6379 redis

# Wait for DB to be ready
sleep 5

# 5. Database Initialization
echo "Initializing Database..."
export PYTHONPATH=.
python -c "from src.core.database import Base, engine; Base.metadata.create_all(bind=engine)"

# 6 & 9. Process Management (Systemd)
echo "Configuring Systemd Services..."
sudo cp deployment/ai-sales-saas.service /etc/systemd/system/
sudo cp deployment/ai-sales-saas-celery.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ai-sales-saas
sudo systemctl enable ai-sales-saas-celery
sudo systemctl restart ai-sales-saas
sudo systemctl restart ai-sales-saas-celery

# 7. Nginx Setup
echo "Configuring Nginx..."
sudo cp deployment/nginx.conf /etc/nginx/sites-available/ai-sales-saas
sudo ln -sf /etc/nginx/sites-available/ai-sales-saas /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo systemctl restart nginx

# 8. SSL (Certbot)
# Uncomment the following line to automatically issue SSL once domain is pointed.
# sudo certbot --nginx -d yourdomain.com --non-interactive --agree-tos -m admin@yourdomain.com

echo "Deployment completed successfully!"
echo "API should be reachable at http://localhost (or your domain)."
