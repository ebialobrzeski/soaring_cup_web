# GlidePlan

**AI-Powered Gliding Task Planner & Waypoint Manager**

A comprehensive web application for glider pilots featuring AI-driven task planning, waypoint management, airspace validation, and weather integration. Built with Flask, PostgreSQL, and modern web technologies.

---

##  Features

###  AI Task Planner

- **Intelligent Route Generation**: AI analyzes weather, airspace, and terrain to suggest optimal task routes
- **Multi-criteria Optimization**: Considers thermal strength, wind conditions, airspace restrictions, and safety margins
- **Weather Integration**: Open-Meteo (free), Windy API (CAPE, cloud cover, wind gusts, RH), IMGW-PIB (Polish data)
- **Airspace Safety**: OpenAIP integration, per-route conflict detection, Poland border geofence with toggle, configurable class filtering
- **Safety Profiles**: Conservative/Standard/Aggressive with triangle preferences and distance constraints
- **Custom AI Instructions**: Personalize via `ai_planner_instructions.md`
- **Export Formats**: CUP, LKT, TSK, XCTSK with QR codes

###  Waypoint & Task Management

- Import/export CUP, CSV, LKT, TSK, XCTSK formats
- Interactive Leaflet maps with click-to-add
- Public/private libraries with share links
- 22 XCSoar/SeeYou waypoint styles
- QR code generation for mobile

###  User Management & Safety

- Secure authentication with bcrypt
- Free/Premium/Admin tiers with usage tracking
- Real-time airspace validation
- Border geofencing (26-point Poland polygon)
- Max distance constraints (60-75% of target)

---

##  Quick Start

### Docker Deployment (Recommended)

```bash
git clone <repository-url>
cd soaring_cup_web
cp .env.example .env  # Edit with API keys and passwords
docker-compose up -d
```

Access at: **http://localhost:5000**

Includes: Flask + Gunicorn, PostgreSQL 16, automatic migrations, persistent volumes

### Local Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
createdb gliding_forecast
cp .env.example .env  # Edit DATABASE_URL
python app.py
```

---

##  Configuration

### Required API Keys (for full functionality)

| Service | Purpose | Free Tier | Get Key |
|---------|---------|-----------|---------|
| **OpenRouter** | AI planning (GeminiLlamaDeepSeek) | Yes | [openrouter.ai/keys](https://openrouter.ai/keys) |
| **Windy** | Enhanced weather & thermals | 1,000/mo | [api.windy.com/keys](https://api.windy.com/keys) |
| **OpenAIP** | European airspace | Yes | [openaip.net](https://www.openaip.net/) |

See `.env.example` for all configuration options.

---

##  Usage

### AI Task Planner

1. Navigate to **AI Planner** tab
2. Select takeoff airport, target distance, optional destination
3. Choose safety profile (Conservative/Standard/Aggressive)
4. Configure airspace constraints and border crossing toggle
5. Click **Generate Routes**
6. Export in CUP/LKT/TSK/XCTSK format

### Customizing AI Behavior

Edit `ai_planner_instructions.md`:

```markdown
# Custom AI Planner Instructions
## Safety Priorities
- Always prioritize routes within glide range
## Route Preferences
- Prefer 3-leg routes for conservative profile
```

---

##  Architecture

**Stack**: Flask 3.1, SQLAlchemy 2.0, PostgreSQL 16, Vanilla JS, Shoelace, Leaflet

**AI**: OpenRouter (Gemini 2.0 Flash  Llama 3.3 70B  DeepSeek Chat)

**Weather**: Open-Meteo + Windy API + IMGW-PIB

**Airspace**: OpenAIP European database

**Key Features**:
- Modular architecture (routes/services/models separation)
- Per-candidate airspace validation via callback pattern
- 26-point Poland geofence with ray-casting
- Session persistence for AI planner inputs
- Usage tracking with tier-based quotas

---

##  Production Deployment

### Deployment Checklist

- [ ] Generate secure `SECRET_KEY` (64 hex chars)
- [ ] Set strong `DB_PASSWORD`
- [ ] Add API keys (OpenRouter, Windy, OpenAIP)
- [ ] Configure SSL/TLS (Caddy/Nginx reverse proxy)
- [ ] Set up PostgreSQL backups
- [ ] Configure firewall (allow 80/443 only)

### Logs

`logs/glideplan.log` with rotation (10MB max, 10 backups)

---

##  Recent Updates

-  OpenRouter integration with automatic fallback
-  Enhanced Windy API (CAPE, cloud cover, wind gusts, RH)  
-  Poland border geofence with override toggle
-  Per-route airspace validation
-  Docker Compose with PostgreSQL 16
-  Cleaned up requirements.txt (removed obsolete google-generativeai, groq SDKs)
-  Route type scoring (triangle preference for conservative/standard)
-  Max distance from home constraints

---

##  Acknowledgments

Open-Meteo  OpenAIP  Windy  OpenRouter  Leaflet  Shoelace

---

**Happy Flying! **
