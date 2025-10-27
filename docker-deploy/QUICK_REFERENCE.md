# Quick Reference Commands for Soaring CUP Web

## Application Commands

### Start/Stop/Restart
```bash
docker-compose up -d          # Start application
docker-compose down           # Stop application
docker-compose restart        # Restart application
docker-compose ps             # Check status
```

### Logs
```bash
docker-compose logs -f        # Follow logs (Ctrl+C to exit)
docker-compose logs --tail=50 # Last 50 lines
```

### Update Application
```bash
cd ~/GitHub/soaring_cup_web
git pull
docker-compose down
docker-compose build
docker-compose up -d
```

## Cloudflare Tunnel Commands

### Service Management
```bash
sudo systemctl status cloudflared   # Check status
sudo systemctl restart cloudflared  # Restart tunnel
sudo systemctl stop cloudflared     # Stop tunnel
sudo systemctl start cloudflared    # Start tunnel
```

### Logs
```bash
sudo journalctl -u cloudflared -f   # Follow logs
sudo journalctl -u cloudflared -n 50 # Last 50 lines
```

### Tunnel Information
```bash
cloudflared tunnel list             # List all tunnels
cloudflared tunnel info soaring-cup # Tunnel details
```

## Backup and Restore

### Create Backup
```bash
cd ~/GitHub/soaring_cup_web
tar -czf backup_$(date +%Y%m%d_%H%M%S).tar.gz data/ uploads/
```

### Restore Backup
```bash
cd ~/GitHub/soaring_cup_web
tar -xzf backup_YYYYMMDD_HHMMSS.tar.gz
docker-compose restart
```

## Monitoring

### Resource Usage
```bash
docker stats soaring_cup_web    # Real-time stats
df -h                           # Disk space
free -h                         # Memory usage
```

### System Health
```bash
docker-compose ps               # Container status
curl http://localhost:5000      # Test local access
```

## Troubleshooting

### Container Won't Start
```bash
docker-compose logs             # Check logs
docker-compose down             # Stop everything
docker-compose build --no-cache # Rebuild
docker-compose up -d            # Start again
```

### Clear Everything and Start Fresh
```bash
docker-compose down
docker system prune -a          # Remove all unused Docker data
git pull
docker-compose build
docker-compose up -d
```

### Check Port Usage
```bash
sudo netstat -tulpn | grep 5000
```

### Fix Permissions
```bash
sudo chown -R $USER:$USER data/ uploads/
```

## Security

### Update System
```bash
sudo apt update && sudo apt upgrade -y
```

### Check Firewall
```bash
sudo ufw status
sudo ufw enable
sudo ufw allow 22/tcp
```

### Generate New Secret Key
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# Then update .env file
```

## Quick Diagnostics

Run all checks at once:
```bash
echo "=== Docker Status ===" && docker-compose ps && \
echo -e "\n=== Cloudflare Tunnel ===" && sudo systemctl status cloudflared --no-pager && \
echo -e "\n=== Disk Space ===" && df -h / && \
echo -e "\n=== Last 10 App Logs ===" && docker-compose logs --tail=10
```

## Configuration Files

- Application config: `~/GitHub/soaring_cup_web/.env`
- Docker compose: `~/GitHub/soaring_cup_web/docker-compose.yml`
- Cloudflare config: `/etc/cloudflared/config.yml`
- Tunnel credentials: `~/.cloudflared/*.json`

## URLs

- GitHub Repo: https://github.com/ebialobrzeski/soaring_cup_web
- Local Access: http://127.0.0.1:5000
- Public Access: https://your-domain.com
- Cloudflare Dashboard: https://one.dash.cloudflare.com

## Quick Health Check

Run all checks at once:
```bash
echo "=== Container Status ===" && docker-compose ps && \
echo -e "\n=== Local Access ===" && curl -I http://127.0.0.1:5000 | head -1 && \
echo -e "\n=== Tunnel Status ===" && sudo systemctl status cloudflared --no-pager | grep Active && \
echo -e "\n=== Disk Space ===" && df -h / | tail -1
```
