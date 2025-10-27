# 🚀 Soaring CUP Web - Docker Deployment Guide

## Quick Start for Raspberry Pi 4

Simple deployment guide for running the Soaring CUP Web application in Docker.

---

## 📋 Prerequisites

- Docker and Docker Compose installed
- Git installed
- SSH access to your Raspberry Pi
- Cloudflare Tunnel configured (optional, for external access)

---

## 📦 Deploy the Application

### 1. Clone Repository

```bash
cd ~/GitHub
git clone https://github.com/ebialobrzeski/soaring_cup_web.git
cd soaring_cup_web
```

### 2. Create Environment File

```bash
# Copy example environment file
cp .env.example .env

# Generate a secure secret key
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy the generated key, then edit the .env file:

```bash
nano .env
```

Replace `your_very_secure_random_secret_key_here_change_this_in_production` with your generated key.

Press `Ctrl+X`, then `Y`, then `Enter` to save.

### 3. Build and Start the Application

```bash
# Build the Docker image
docker-compose build

# Start the container
docker-compose up -d

# Check if it's running
docker-compose ps
```

You should see the container running.

### 4. Test the Application

```bash
# Test locally
curl -I http://127.0.0.1:5000

# Should return: HTTP/1.1 200 OK

# If you have Cloudflare Tunnel configured
curl -I https://your-domain.com

# Should return: HTTP/2 200
```

If you see `200 OK` responses, the application is running successfully! 🎉

---

## 🌐 Access Your Application

- **Local network:** `http://YOUR_PI_IP:5000`
- **Localhost (on Pi):** `http://127.0.0.1:5000`
- **External (Cloudflare Tunnel):** `https://your-domain.com`

---

## 🛠️ Common Commands

### Application Management

```bash
# View logs
docker-compose logs -f

# Restart application
docker-compose restart

# Stop application
docker-compose down

# Start application
docker-compose up -d

# Rebuild after code changes
docker-compose down
git pull
docker-compose build
docker-compose up -d
```

---

## 🔒 Backup Your Data

```bash
# Create backup
cd ~/GitHub/soaring_cup_web
tar -czf backup_$(date +%Y%m%d_%H%M%S).tar.gz data/ uploads/

# List backups
ls -lh backup_*.tar.gz

# Restore from backup
tar -xzf backup_YYYYMMDD_HHMMSS.tar.gz
```

---

## 🐛 Troubleshooting

### Application Won't Start

```bash
# Check logs
docker-compose logs

# Check if port is in use
sudo netstat -tulpn | grep 5000

# Rebuild from scratch
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Can't Access via Domain

```bash
# 1. Verify app is running locally
curl -I http://127.0.0.1:5000

# 2. Check Cloudflare Tunnel status
sudo systemctl status cloudflared

# 3. View tunnel logs
sudo journalctl -u cloudflared -f

# 4. Test domain
curl -I https://your-domain.com
```

### Permission Issues

```bash
# Fix data directory permissions
sudo chown -R $USER:$USER data/ uploads/
```

---

## 📊 Monitoring

### Check Application Health

```bash
# Check if container is running
docker-compose ps

# Check resource usage
docker stats soaring_cup_web

# Check disk space
df -h

# View application logs
docker-compose logs --tail=50
```

---

## 🔄 Updating the Application

When new features are released:

```bash
cd ~/GitHub/soaring_cup_web

# Backup current data
tar -czf backup_before_update_$(date +%Y%m%d).tar.gz data/ uploads/

# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d

# Verify it's working
curl -I http://127.0.0.1:5000
docker-compose logs -f
```

---

## 🎊 You're Done!

Your Soaring CUP Web application is now:
- ✅ Running in Docker on your Raspberry Pi
- ✅ Accessible at http://localhost:5000
- ✅ Auto-restarting on failure
- ✅ Data persisted in `./data` and `./uploads` folders

For quick reference of common commands, see [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
