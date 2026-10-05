# EcoTravel Advisor: Conversational Agent for Sustainable Tourism Planning

An AI-powered conversational travel advisor built with **Rasa 3.6.21** and **Python 3.10.11**. The system provides personalized eco-friendly travel itineraries, carbon footprint estimations, green hotel recommendations, and sustainable transport choices, featuring robust two-stage fallback and human advisor escalation.

---

## Key Features

- **Automated Trip Planning**: Multi-turn slots tracking (`destination`, `travel_dates`, `budget`, `sustainability_level`).
- **Carbon Footprint Calculation**: Transport emissions calculations (rail, car, air) with comparative sustainability labels.
- **Eco-Accommodation Search**: Weighted multi-attribute ranking prioritizing certified environmental features.
- **Verified Carbon Offset Guidance**: Educational guidance emphasizing the mitigation hierarchy (Avoid → Reduce → Residual Offset).
- **Two-Stage Fallback**: Stage 1 provides interactive clarification buttons; Stage 2 prepares a full context handover package for human advisors.
- **High-Performance Architecture**: Verified local response latency under 65 milliseconds (well within the <3.0s requirement).

---

## Baseline Verification Summary

- **Rasa Version**: 3.6.21
- **Python Version**: 3.10.11
- **Core Stories Evaluation**: 18/18 stories passed (Precision = 1.000, Recall = 1.000, F1 = 1.000)
- **Action Predictions**: 65/65 actions correct (Accuracy = 1.000)
- **Local Response Latency**: Mean response time = 0.035s – 0.060s (<3.0s requirement PASS)
- **Docker Compose Runtime**: VERIFIED PASS (Rasa, Action Server, and Nginx containers communicating on Docker network)
- **Hugging Face Architecture**: LOCAL SINGLE-CONTAINER ARCHITECTURE VERIFIED PASS (Nginx reverse proxy on port 7860)

---

## Project Structure

```text
EcoTravelAdvisor/
├── actions/
│   └── actions.py              # Custom actions (Climatiq, Amadeus, offset recommendations)
├── data/
│   ├── nlu.yml                 # Intent training data & entity annotations
│   ├── rules.yml               # Policy rules (form activation, fallbacks)
│   ├── stories.yml             # Conversation flows & training stories
│   └── external/               # Local fallback datasets (hotels, flights, activities, offsets)
├── frontend/
│   ├── index.html              # Modern glassmorphism web chat interface
│   ├── styles.css              # Responsive custom styling & animations
│   └── app.js                 # Dynamic REST client supporting direct & reverse-proxy routing
├── models/
│   └── 20261002-230550-drab-union.tar.gz  # Final verified trained Rasa model
├── results/                    # Empirical evaluation reports, confusion matrices, and latency CSVs
├── tests/
│   ├── test_nlu.yml            # NLU test suite
│   └── test_stories.yml        # Core conversation test stories (18 stories)
├── config.yml                  # Rasa NLU pipeline & Core policy configuration
├── credentials.yml             # Rasa REST channel settings
├── domain.yml                  # Intents, entities, slots, actions & response templates
├── endpoints.yml               # Local native action endpoint configuration (127.0.0.1:5055)
├── endpoints.docker.yml        # Docker Compose action endpoint configuration (actions:5055)
├── endpoints.hf.yml            # Single-container loopback action endpoint (127.0.0.1:5055)
├── Dockerfile                  # Action server container definition
├── Dockerfile.hf               # Hugging Face single-container definition (Port 7860)
├── docker-compose.yml          # Multi-container orchestration (Rasa, Action Server, Frontend)
├── nginx.hf.conf               # Nginx reverse proxy configuration for port 7860
├── start-hf.sh                 # Unix process supervisor script for single-container runtime
├── main.py                     # Unified local orchestrator & one-click launcher
├── .env.example                # Environment template for external API keys
└── README.md                   # System documentation & deployment manual
```

---

## Installation & Setup

### 1. Environment Requirements
- **Python**: 3.10.11 (64-bit)
- **OS**: Windows, macOS, or Linux
- **Git**: Installed

### 2. Create Virtual Environment & Install Dependencies
```bash
# Clone the repository
git clone https://github.com/<your-username>/EcoTravelAdvisor.git
cd EcoTravelAdvisor

# Create Python 3.10 virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install required dependencies
pip install -r requirements.txt
```

### 3. API Key Configuration
Copy `.env.example` to `.env` and insert your credentials if available:
```bash
cp .env.example .env
```
*Note: External APIs automatically fall back to verified local datasets if API keys are omitted or restricted.*

---

## Running the System

### Option A: One-Click Unified Launcher (Recommended)
Runs all servers automatically (Action Server, Rasa Server, Frontend) and opens the web app in your default browser:
```bash
python main.py
```

### Option B: Manual Multi-Terminal Execution

**Terminal 1 — Rasa Action Server:**
```bash
rasa run actions
```
*Listens on `http://127.0.0.1:5055/webhook`.*

**Terminal 2 — Rasa API Server:**
```bash
rasa run --enable-api --cors "*"
```
*Listens on `http://127.0.0.1:5005`.*

**Terminal 3 — Web Frontend:**
```bash
python -m http.server 8080 --directory frontend
```
*Open `http://localhost:8080` in your web browser.*

---

## Docker Compose Deployment

The project includes verified multi-container orchestration.

```bash
# Build custom action image
docker compose build

# Start full stack (Rasa, Action Server, Frontend)
docker compose up -d

# Inspect status and logs
docker compose ps
docker compose logs

# Stop container stack cleanly
docker compose down
```

**Exposed Docker Endpoints:**
- Web Frontend: `http://localhost:8080`
- Rasa Server: `http://localhost:5005`
- Action Server: `http://localhost:5055`

---

## Hugging Face Spaces Deployment

The project supports single-container deployment on Hugging Face Docker Spaces using Nginx as a reverse proxy on port `7860`.

### Local HF Image Test
```bash
# Build HF single-container image
docker build -f Dockerfile.hf -t ecotraveladvisor-hf .

# Test locally on port 7860
docker run -d --name hf_test -p 7860:7860 --env-file .env ecotraveladvisor-hf
```
*Frontend available at `http://localhost:7860`.*

---

## Testing & Verification

### 1. Data Validation
```bash
rasa data validate
```

### 2. Core Story Evaluation (18/18 Passed)
```bash
rasa test core --stories tests/test_stories.yml
```

### 3. Response Latency Measurement
```bash
python scratch/test_latency.py
```
*Results saved to `results/latency_results.csv`, `results/latency_summary.json`, and `results/latency_summary.png`.*

---

## External API Integrations & Limitations

1. **Climatiq Travel API**: Integrated for live distance emissions calculations (`POST https://api.climatiq.io/travel/v1/distance`). Free plan accounts receive an HTTP 403 subscription notification; the system provides clear user guidance.
2. **Amadeus Travel API**: Integrated for eco-accommodation and flight options (`https://test.api.amadeus.com`). Transparently falls back to local structured datasets (`data/external/fallback_hotels.json`, `fallback_flights.json`) when sandbox credentials or DNS restrictions apply.

---

## Security & Privacy

- `.env` is strictly excluded from version control via `.gitignore` and `.dockerignore`.
- Secrets are read at runtime via environment variables (`os.getenv`) and are never logged, printed, or baked into Docker image layers.
- No user PII or GPS data is permanently stored.
