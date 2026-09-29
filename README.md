# SAT-SA: Supervisory Analytics Tool for SOC Assessment
> **Smart India Hackathon 2024 / 2026 — Problem Statement SIH-26157 (NCIIPC)**  
> *Offline, Air-Gapped Supervisory Analytics & Anomaly Detection Dashboard for Critical Sector Entity (CSE) SOC Audits.*

> 🌐 **Network Requirement Notice:**  
> **Internet connectivity is ONLY required during the first-time setup** to download initial software dependencies (pip packages from `requirements.txt`, npm modules, and the local Ollama LLM model). Once downloaded, **SAT-SA operates 100% offline in strictly air-gapped environments with ZERO network calls or external data egress.**

---

## 📌 Problem Statement & Context
The **National Critical Information Infrastructure Protection Centre (NCIIPC)** conducts supervisory reviews of security alerts, escalation histories, and case-management logs from **Critical Sector Entities (CSEs)** to audit cyber resilience. 

Manual audits present severe challenges:
- **Massive Alert Volumes:** Hundreds of thousands of alerts make comprehensive manual review impossible.
- **Operational Execution Gaps:** Missed SLAs, premature closures without investigation, alert fatigue, and delayed containment.
- **Monitoring Negative Space:** Blind spots in detection rule coverage where high-criticality assets lack monitoring telemetry.
- **Air-Gap & Data Sovereignty Constraints:** All processing must execute **100% locally and offline** without sending sensitive entity logs to external cloud APIs or 3rd-party services.

---

## 💡 The SAT-SA Solution
**SAT-SA** provides an end-to-end, localized intelligence layer for NCIIPC auditors:
1. **Multi-Source SOC Telemetry Ingestion:** Ingests alert exports, asset inventories, escalation matrices, and case management records (CSV / JSON format).
2. **Offline ML Anomaly Detection:** Utilizes unsupervised **Scikit-Learn Isolation Forest** models to uncover anomalous triage delays, irregular closure ratios, and suspicious incident handling patterns.
3. **Supervisory Prioritization Engine:** Ranks alerts dynamically using entity criticality, MITRE ATT&CK coverage, and anomaly weights into high-value review queues.
4. **Local LLM Explainability (Ollama):** Translates complex machine learning anomaly vectors and rule violations into plain-language audit rationales via a local **Llama 3** instance (zero cloud communication).
5. **Deterministic Rule Engine Fallback:** Automatically switches to an offline heuristics rule engine if Ollama is not installed or running.
6. **Regulatory Audit PDF Generation:** One-click automated export of comprehensive compliance inspection reports.

---

## 🏗️ Architecture & Technology Stack

| Layer | Technology | Description |
|---|---|---|
| **Frontend** | Next.js 16 (React 19), Tailwind CSS v4, Recharts, Lucide Icons | Responsive, high-contrast dark/light mode dashboard designed for supervisory audit workflows. |
| **Backend API** | Python 3.10 - 3.14+, FastAPI, Uvicorn | Asynchronous REST backend handling data processing, ML scoring, and database operations. |
| **Database** | PostgreSQL 14 - 17+ (SQLAlchemy 2.0 ORM) | Relational persistence of ingested alerts, entity metadata, risk scores, and audit trails. |
| **Analytics Engine** | Scikit-Learn (Isolation Forest), Pandas, NumPy | Local unsupervised anomaly detection and telemetry aggregation. |
| **Local AI Engine** | Ollama (`llama3` model via LangChain) | Local zero-cloud LLM providing human-readable supervisory findings. |

---

## 🛠️ Required Software & Prerequisites

Before setting up the project, install the following required software packages on your machine:

### 1. Python (Version 3.10 to 3.14+)
- **Download:** [https://www.python.org/downloads/](https://www.python.org/downloads/)
- **Installation Note for Windows:**  
  ⚠️ **Important:** During installation, check the box **"Add python.exe to PATH"**.
- **Verify in terminal:**
  ```powershell
  python --version
  ```

### 2. Node.js & npm (v18.x or v20.x+ LTS)
- **Download:** [https://nodejs.org/](https://nodejs.org/)
- **Verify in terminal:**
  ```powershell
  node -v
  npm -v
  ```

### 3. PostgreSQL Database (v14, v15, v16, or v17)
- **Download:** [https://www.postgresql.org/download/](https://www.postgresql.org/download/)
- **Configuration:**
  - Port: `5432` (default)
  - Superuser: `postgres` (default)
  - Password: Set any password you prefer during installation.  
    *(Our setup script does **not** rely on any hardcoded passwords — it interactively asks for your password and database name during first-time setup and configures your `.env` file automatically!)*
- **Verify Service is Running:**
  - **Windows:** Open `services.msc` and verify `postgresql-x64-XX` is **Running** (or run `net start postgresql-x64-16` in admin cmd).
  - **Linux / macOS:** `sudo systemctl status postgresql` or `brew services list`

### 4. Ollama — Local LLM Engine (Offline AI Explainability)
- **Download:** [https://ollama.com/download](https://ollama.com/download)
- **Model Used:** **`llama3`** (8B parameter model)
- **Install & Pull the Model (Internet required only for initial download):**
  After installing Ollama, open any terminal and execute:
  ```bash
  ollama pull llama3
  ```
  *(To test local generation: `ollama run llama3`)*
- **Deterministic Offline Fallback:**  
  *If Ollama is not installed or your machine has low RAM/GPU, SAT-SA automatically falls back to its built-in **Deterministic Rule Engine**. All anomaly detection, data ingestion, analytics, and scoring work with 100% functionality without Ollama!*

### 5. Git
- **Download:** [https://git-scm.com/downloads](https://git-scm.com/downloads)

---

## 🚀 Quick Start (Automated One-Click Setup)

> 💡 **Reminder:** Make sure you are connected to the internet for this initial setup so required packages and models can be downloaded. Subsequent runs are **100% offline**.

### Step 1: Clone the Repository
```bash
git clone https://github.com/PiyushTheProgrammer/SIH-157_SOC-SA.git
cd SIH2026-SOC-SA-PS157
```

### Step 2: One-Click Setup & Launch

#### On Windows (Recommended):
Double-click `run.bat` or run in your terminal:
```powershell
.\run.bat
```

> **What `run.bat` does automatically:**
> 1. Detects first-time setup and invokes `python setup.py`.
> 2. Creates the Python virtual environment (`backend/venv`).
> 3. Installs all Python dependencies from `backend/requirements.txt`.
> 4. Installs frontend packages via `npm install`.
> 5. **Interactive DB Setup:** Prompts you for your PostgreSQL password and database name (defaults to `sat_sa_db`).
> 6. Writes your database credentials securely to `backend/.env` (**no hardcoded passwords**).
> 7. Connects to PostgreSQL and **automatically creates the database** if it does not already exist.
> 8. Initializes all tables (`soc_alerts`, `asset_inventory`, etc.) in your chosen database.
> 9. Checks Ollama local status on `http://localhost:11434`.
> 10. Launches both the FastAPI Backend and Next.js Frontend in dedicated console windows.

#### On Linux / macOS:
```bash
python3 setup.py
```
Then start the backend and frontend as detailed in the manual steps below.

---

## 💻 Manual Setup & Execution (Step-by-Step)

If you prefer to configure and run the backend and frontend services manually or are on Linux/macOS:

### 1. Database Configuration
1. Ensure PostgreSQL is active on port `5432`.
2. Copy the template configuration file:
   ```bash
   cp backend/.env.example backend/.env
   ```
3. Open `backend/.env` and enter your actual PostgreSQL credentials:
   ```ini
   DATABASE_USER=postgres
   DATABASE_PASSWORD=your_actual_postgres_password
   DATABASE_HOST=localhost
   DATABASE_PORT=5432
   DATABASE_NAME=sat_sa_db
   ```
4. If the database does not exist, create it via psql or pgAdmin:
   ```sql
   CREATE DATABASE sat_sa_db;
   ```

### 2. Backend Setup
1. Open a terminal and navigate to `backend`:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   - **Windows:**
     ```powershell
     python -m venv venv
     .\venv\Scripts\activate
     ```
   - **Linux / macOS:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```
3. Install dependencies:
   ```bash
   pip install --upgrade pip setuptools wheel
   pip install -r requirements.txt
   ```
4. Initialize the database schema and tables:
   ```bash
   python -c "from database import init_db; init_db()"
   ```
5. Start the FastAPI development server:
   ```bash
   uvicorn main:app --reload --port 8000
   ```
   - API Docs (Swagger): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   - Health Check: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

### 3. Frontend Setup
1. Open a separate terminal and navigate to `frontend`:
   ```bash
   cd frontend
   ```
2. Install npm packages:
   ```bash
   npm install
   ```
   *(If your Node.js version produces peer dependency warnings: `npm install --legacy-peer-deps`)*
3. Start the Next.js development server:
   ```bash
   npm run dev
   ```
4. Open the Dashboard in your browser:
   - Dashboard: [http://localhost:3000](http://localhost:3000)

### 4. Local AI Engine (Ollama)
Ensure Ollama is running locally:
```bash
ollama serve
# Verify llama3 model is available
ollama list
```

---

## 📊 Endpoints & Verification Summary

| Service | Address | Purpose |
|---|---|---|
| **Web Dashboard** | [http://localhost:3000](http://localhost:3000) | Main Supervisory Interface |
| **Backend REST API** | [http://127.0.0.1:8000](http://127.0.0.1:8000) | Core Business Logic & Ingestion |
| **Interactive API Docs** | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | Swagger UI for testing API endpoints |
| **System & AI Health** | [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health) | Verifies DB and Ollama connectivity |
| **Ollama Local LLM** | [http://localhost:11434](http://localhost:11434) | Local inference endpoint |

---

## 🧪 Testing with Sample Datasets

Synthetic audit datasets simulating real-world Critical Sector Entity SOC telemetries are included in the repository in [`Sample Datasets/`](Sample%20Datasets/):

- `soc_alerts.csv` — Primary alert log dataset containing timestamps, severities, triage durations, analyst IDs, and resolution statuses.
- `asset_inventory.csv` — Critical asset registry with entity designations, IP mappings, and criticality tiers.
- `case_management.csv` — Incident escalation and investigation notes.
- `investigation_workflow.csv` — Granular workflow step timestamps for execution gap analysis.

### How to Test:
1. Open the Dashboard at [http://localhost:3000](http://localhost:3000).
2. Navigate to **Data Ingestion** / **Upload Logs**.
3. Upload `soc_alerts.csv` and `asset_inventory.csv`.
4. Review the generated **Anomaly Scores**, **Execution Gaps**, **Negative Space Radar**, and **Supervisory AI Audit Summaries**.

---

## 📦 Verified Backend Dependencies (`requirements.txt`)

Every package declared in `backend/requirements.txt` is verified and actively used in the codebase:

| Package | Purpose in SAT-SA | Where It Is Used |
|---|---|---|
| `fastapi` | High-performance asynchronous REST API framework | `backend/main.py` |
| `uvicorn[standard]` | Production ASGI web server | Server runner in `run.bat` & backend |
| `python-multipart` | Multipart/form-data handler for CSV dataset uploads | `backend/main.py` (File Ingestion) |
| `pandas` | Tabular data manipulation and aggregation | `backend/analytics_engine.py`, `backend/priority_engine.py`, etc. |
| `numpy` | Vector calculations, numerical anomaly scoring | `backend/analytics_engine.py`, `backend/priority_engine.py` |
| `scikit-learn` | Unsupervised machine learning (Isolation Forest) | `backend/analytics_engine.py` |
| `pydantic` | Data validation, request/response models | `backend/main.py`, `backend/models.py` |
| `pytest` | Unit and integration test suite | `backend/tests/` |
| `aiofiles` | Asynchronous file I/O for streaming file uploads | `backend/main.py` (line 1036) |
| `langchain-core` | Prompt templates and runnable chains | `backend/main.py` |
| `langchain-ollama` | Local LLM inference integration | `backend/main.py` |
| `reportlab` | Automated regulatory audit PDF generation | `backend/report_generator.py` |
| `sqlalchemy` | Object Relational Mapper for database schemas | `backend/database.py`, `backend/models.py` |
| `psycopg2-binary` | PostgreSQL DB-API driver (Python < 3.13) | PostgreSQL connection pool |
| `psycopg[binary]` | Modern PostgreSQL 3+ DB-API driver (Python 3.10 - 3.14+) | PostgreSQL connection pool |
| `python-dotenv` | Environment variable management (`.env`) | `backend/database.py`, `backend/main.py` |

---

## 🔧 Troubleshooting & Frequently Asked Questions (FAQ)

### 1. `Cannot find module 'sqlalchemy'` or Python Import Errors in Editor
- **Why this happens:**  
  Your IDE (e.g. VS Code, Antigravity) may have auto-selected an inactive or empty interpreter (such as a bare `.venv` created without installed packages) rather than the project virtual environment (`backend/venv`).
- **How to fix:**
  1. Ensure dependencies are installed in your active environment:
     ```bash
     cd backend
     .\venv\Scripts\pip.exe install -r requirements.txt
     ```
  2. In your IDE, press `Ctrl+Shift+P` (or `Cmd+Shift+P` on macOS) -> type **Python: Select Interpreter** -> select the environment located at `backend/venv` (or `backend/.venv`).

### 2. PostgreSQL Connection / Password Errors
- **Error:** `PostgreSQL authentication failed for user "postgres"`.
- **How to fix:**
  1. Open `backend/.env` and update `DATABASE_PASSWORD` to match your actual PostgreSQL password.
  2. Verify PostgreSQL service is active in `services.msc`.
  3. Rerun `python setup.py` — it will automatically prompt you for your password, test it, update `backend/.env`, and create the database for you.

### 3. Ollama Offline / Model Not Found
- If the `/api/health` endpoint reports `"ollama_available": false`:
  1. Ensure Ollama is started: run `ollama serve` in a terminal or launch the Ollama desktop app.
  2. Verify that the model is downloaded:
     ```bash
     ollama pull llama3
     ```
  3. **Note:** SAT-SA handles Ollama outages gracefully by automatically engaging its **Deterministic Rule Engine** fallback so workflows never fail.

### 4. Node.js `ERESOLVE` or Peer Dependency Warnings
- If `npm install` reports peer dependency issues:
  ```bash
  npm install --legacy-peer-deps
  ```

---

## 📁 Repository Directory Structure

```text
SIH2026-SOC-SA-PS157/
│
├── README.md                      # Complete Project Documentation & Instructions
├── run.bat                        # 1-Click Automated Setup & Launch Script (Windows)
├── setup.py                       # Cross-Platform Automated Self-Healing Setup Script
│
├── backend/                       # FastAPI Backend Service
│   ├── main.py                    # API Gateway & Route Controllers
│   ├── database.py                # PostgreSQL Connection & Session Management
│   ├── models.py                  # SQLAlchemy Database Schema Models
│   ├── analytics_engine.py        # ML Isolation Forest Anomaly Detection Engine
│   ├── priority_engine.py         # Entity & Alert Supervisory Prioritization Logic
│   ├── recommendation_engine.py   # Local AI & Heuristic Explainability Pipeline
│   ├── report_generator.py        # Automated Audit PDF Report Generation
│   ├── requirements.txt           # Python Dependency Declarations
│   ├── .env                       # Local Environment Secrets (Git-ignored)
│   └── .env.example               # Template Environment Variables
│
├── frontend/                      # Next.js 16 Dashboard Web Application
│   ├── src/                       # React Application Source (Pages & Components)
│   ├── package.json               # Frontend Node.js Dependencies & Build Scripts
│   ├── tailwind.config.ts         # Design System Styling Configuration
│   └── next.config.ts             # Next.js Framework Configuration
│
└── Sample Datasets/               # Synthetic SOC & CSE Audit Datasets
    ├── soc_alerts.csv             # Raw SOC Alert Logs
    ├── asset_inventory.csv        # Critical Sector Asset Registry
    ├── case_management.csv        # Case Escalation Records
    └── investigation_workflow.csv # Detailed Analyst Investigation Logs
```

---

## 📜 Compliance & Data Sovereignty
SAT-SA complies with strict **Air-Gapped Operational Requirements**:
- **Zero External Egress:** All data ingestion, database storage, unsupervised ML inference, and LLM explainability execute strictly on localhost.
- **No Cloud Dependencies:** No OpenAI, Azure, or remote cloud keys required.
- **Auditable & Deterministic:** Every AI-generated finding is backed by deterministic rule-based telemetry metrics for regulatory verification.