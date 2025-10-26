#!/bin/bash

# Soaring CUP Web - Deployment Script
# This script automates the deployment process

set -e  # Exit on error

echo "🚀 Soaring CUP Web - Deployment Script"
echo "======================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo -e "${YELLOW}Warning: This doesn't appear to be a Raspberry Pi${NC}"
    echo "Continue anyway? (y/n)"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo -e "${GREEN}✅ Docker installed${NC}"
    echo "Please log out and log back in, then run this script again"
    exit 0
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose..."
    sudo apt-get install -y docker-compose
    echo -e "${GREEN}✅ Docker Compose installed${NC}"
fi

# Clone repository if not exists
if [ ! -d "soaring_cup_web" ]; then
    echo "Cloning repository..."
    git clone https://github.com/ebialobrzeski/soaring_cup_web.git
    cd soaring_cup_web
else
    echo "Repository already exists, pulling latest changes..."
    cd soaring_cup_web
    git pull
fi

# Create .env file if not exists
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    cp .env.example .env
    
    # Generate secret key
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/your_very_secure_random_secret_key_here_change_this_in_production/$SECRET_KEY/" .env
    echo -e "${GREEN}✅ .env file created with secure key${NC}"
else
    echo -e "${YELLOW}⚠️  .env file already exists, skipping${NC}"
fi

# Build and start containers
echo "Building Docker image..."
docker-compose build

echo "Starting application..."
docker-compose up -d

# Wait for application to start
echo "Waiting for application to start..."
sleep 5

# Check if container is running
if docker-compose ps | grep -q "Up"; then
    echo -e "${GREEN}✅ Application is running!${NC}"
    echo ""
    echo "Test it locally: curl http://localhost:5000"
    echo ""
    echo "Next steps:"
    echo "1. Install Cloudflare Tunnel: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/"
    echo "2. Configure your tunnel to point to http://localhost:5000"
    echo "3. Access your application via your domain"
else
    echo -e "${RED}❌ Application failed to start${NC}"
    echo "Check logs with: docker-compose logs"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 Deployment complete!${NC}"
