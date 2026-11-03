# Household FIRE Dashboard & Strategy Lab

A deterministic, self-hosted financial dashboard and early retirement (FIRE) portfolio analyzer powered by Plaid Link and Google Gemini.

Designed for multi-custodian households (Vanguard, Charles Schwab, Fidelity, Merrill, etc.) requiring clean asset location classification, deduplicated wrapper accounting (e.g., PCRA / BrokerageLink self-directed 401(k) shells), cash reserve monitoring, and AI-driven withdrawal strategy modeling.

---

## Key Features

- **Deterministic Multi-Custodian Aggregation**: Direct read-only connection via Plaid to pull real balances, lot values, and underlying ETF/mutual fund holdings.
- **Deduplication Engine**: Accurately filters out parent 401(k) wrapper shells (such as Google 401(k) or TPMG plan accounts) to eliminate double-counting against underlying PCRA or BrokerageLink brokerage windows.
- **Accurate Cash Accounting**: Separates depository bank cash, uninvested settlement sweep cash (e.g., VMFXX, SPAXX, SWVXX), and distinguishes true brokerage sweep cash from institutional pooled trust daily NAV unit valuation lags.
- **Configurable Governance (`config.json`)**: Manage household partner ownership labels, custom cash reserve floors, Safe Withdrawal Rates (SWR), and account roles without touching application code.
- **Gemini Strategy Advisor**: Chat directly with Google Gemini (with automatic model failover, output budgeting up to 8,192 tokens, and markdown table rendering) grounded strictly in active liquid holdings.

---

## Architecture Overview

```
.
├── main.py               # FastAPI backend, portfolio calculation engine & Gemini router
├── index.html            # Single-page dashboard UI (vanilla JS, CSS, marked.js)
├── config.example.json   # Template for household ownership & account role overrides
├── .env.example          # Template for Plaid & Gemini API keys
├── requirements.txt      # Python package dependencies
├── config.json           # [Ignored by git] Your local household configuration
├── tokens.json           # [Ignored by git] Local persistent Plaid access tokens
└── .env                  # [Ignored by git] Your secret credentials
```

---

## Security & Privacy Notice

This application is strictly **self-hosted and local-first**.
- Your bank credentials and access tokens are never transmitted to any third-party server besides direct TLS communication with Plaid and Google Gemini.
- The `.gitignore` file is pre-configured to strictly block `.env`, `tokens.json`, and `config.json`. **Never commit or push these files to any public or shared repository.**

---

## Setup & Installation

### 1. Prerequisites
- Python 3.10 or higher
- A free [Google AI Studio API Key](https://aistudio.google.com/app/apikey)
- A [Plaid Developer Account](https://dashboard.plaid.com/signup) with client ID and production secret

### 2. Clone the Repository
```bash
git clone https://github.com/<YOUR_GITHUB_USERNAME>/household-fire-dashboard.git
cd household-fire-dashboard
```

### 3. Create a Virtual Environment & Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure Environment Secrets
Copy the environment template:
```bash
cp .env.example .env
```
Open `.env` in any text editor and fill in your keys:
```ini
PLAID_CLIENT_ID=your_actual_plaid_client_id
PLAID_SECRET=your_actual_plaid_production_secret
PLAID_ENV=production

GEMINI_API_KEY=your_actual_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODEL=gemini-2.5-pro
```

### 5. Configure Household Settings
Copy the example config:
```bash
cp config.example.json config.json
```
Adjust parameters in `config.json`:
- `cash_floor`: Target minimum liquid cash reserve (e.g., `50000.0`).
- `swr_rate`: Safe Withdrawal Rate percentage (e.g., `0.0325` for 3.25%).
- `owners`: List of household member names (e.g., `["Anand", "Joan", "Joint"]`).
- `account_overrides`: Define custom roles for specific Plaid account IDs:
  - `role: "wrapper_shell"`: Omits the account from net worth calculations (used when a parent 401(k) already has its assets broken out in a PCRA or BrokerageLink sub-account).
  - `role: "future_income"`: Isolates future vested pensions/annuities from liquid rebalancing.
  - `role: "liquid"`: Standard investment or cash account.

---

## Running the Application

Start the local server with hot reloading:
```bash
uvicorn main:app --reload --port 8000
```

1. Open your browser to: `http://localhost:8000`
2. Click **Connect Custodian** to authenticate your financial institutions via Plaid Link.
3. Once authenticated, your accounts and live holdings will display automatically.
4. Use the checkboxes in the inventory table to dynamically simulate what-if asset exclusion scenarios.
5. Use the **Gemini Strategy Advisor** prompt box to evaluate tax location strategies, cash runways, or owner-level balance sheet splits.

---

## Git Safe Sharing Checklist

Before pushing commits to GitHub or sharing with others, always check your status:

```bash
git status
```

Ensure only clean repository files are staged:
- `main.py`
- `index.html`
- `config.example.json`
- `.env.example`
- `.gitignore`
- `requirements.txt`
- `README.md`

`tokens.json`, `.env`, and `config.json` should **never** appear in `Changes to be committed`.