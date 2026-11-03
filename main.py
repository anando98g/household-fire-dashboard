import os
import json
import time
import uuid
import requests
from enum import Enum
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------
# 1. Environment & Initialization
# ---------------------------------------------------------
load_dotenv(override=True)
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENV", "production").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

ENV_PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ENV_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-pro")

if not PLAID_CLIENT_ID or not PLAID_SECRET:
    print("[WARN] PLAID_CLIENT_ID or PLAID_SECRET is missing from environment.")

PLAID_HOST = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}.get(PLAID_ENV, "https://production.plaid.com")

app = FastAPI(title="Household FIRE Dashboard & Strategy Lab")
TOKENS_FILE = "tokens.json"
CONFIG_FILE = "config.json"

# ---------------------------------------------------------
# 2. Config & Declarative Registries
# ---------------------------------------------------------
def load_app_config() -> Dict[str, Any]:
    default_config = {
        "cash_floor": 50000.0,
        "swr_rate": 0.0325,
        "owners": ["Primary", "Secondary", "Joint"],
        "account_overrides": {}
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] Could not parse {CONFIG_FILE}: {e}")
    elif os.path.exists("config.example.json"):
        try:
            with open("config.example.json", "r") as f:
                return json.load(f)
        except Exception:
            pass
    return default_config

class AccountRole(str, Enum):
    LIQUID = "liquid"
    WRAPPER_SHELL = "wrapper_shell"
    FUTURE_INCOME = "future_income"
    LIABILITY = "liability"

class AssetClass(str, Enum):
    EQUITY = "equity"
    BOND = "bond"
    CASH = "cash"
    OTHER = "other"

SECURITY_REGISTRY: Dict[str, AssetClass] = {
    # Equities
    "VTI": AssetClass.EQUITY, "VOO": AssetClass.EQUITY, "SCHB": AssetClass.EQUITY,
    "VXUS": AssetClass.EQUITY, "VEA": AssetClass.EQUITY, "VWO": AssetClass.EQUITY,
    "VT": AssetClass.EQUITY, "VTSAX": AssetClass.EQUITY, "VTIAX": AssetClass.EQUITY,
    "SCHA": AssetClass.EQUITY, "SCHM": AssetClass.EQUITY, "SCHE": AssetClass.EQUITY,
    "BTC.US.EQUITY.INDEX": AssetClass.EQUITY, "ONJT": AssetClass.EQUITY,
    
    # Bonds
    "BND": AssetClass.BOND, "BNDX": AssetClass.BOND, "VTEB": AssetClass.BOND,
    "VBTLX": AssetClass.BOND, "FXNAX": AssetClass.BOND, "SWAGX": AssetClass.BOND,
    "09258C814": AssetClass.BOND, "BTC.TOTAL.RETURN.F": AssetClass.BOND,
    
    # Cash & Money Markets
    "VMFXX": AssetClass.CASH, "SPAXX": AssetClass.CASH, "FDRXX": AssetClass.CASH,
    "SPRXX": AssetClass.CASH, "SWVXX": AssetClass.CASH, "SNVXX": AssetClass.CASH,
    "CUR:USD": AssetClass.CASH
}

class AskGeminiRequest(BaseModel):
    prompt: str
    excluded_accounts: List[str] = Field(default_factory=list)
    history: List[Dict[str, str]] = Field(default_factory=list)

def get_configured_gemini_models() -> List[str]:
    raw_models = []
    for item in [ENV_PRIMARY_MODEL, ENV_FALLBACK_MODEL]:
        if item:
            raw_models.extend([m.strip() for m in item.split(",") if m.strip()])
    cleaned = []
    seen = set()
    for m in raw_models:
        c = m.replace("models/", "").strip()
        if c and c not in seen:
            seen.add(c)
            cleaned.append(c)
    return cleaned or ["gemini-2.5-flash", "gemini-2.5-pro"]

def load_saved_tokens() -> List[Dict[str, str]]:
    if not os.path.exists(TOKENS_FILE):
        return []
    try:
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def save_token(access_token: str, institution_name: str = "Unknown"):
    tokens = load_saved_tokens()
    tokens = [t for t in tokens if t.get("access_token") != access_token]
    tokens.append({"access_token": access_token, "institution": institution_name})
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

def classify_holding(ticker: Optional[str], name: str, sec_type: Optional[str]) -> AssetClass:
    t = (ticker or "").upper().strip()
    if t in SECURITY_REGISTRY:
        return SECURITY_REGISTRY[t]
    n_lower = name.lower()
    if any(k in n_lower for k in ["total return", "bond", "fixed income", "treasury"]):
        return AssetClass.BOND
    if sec_type == "cash" or any(k in n_lower for k in ["money market", "core cash", "cash sweep", "federal money market"]):
        return AssetClass.CASH
    if sec_type in ["equity", "etf", "mutual fund"]:
        return AssetClass.EQUITY
    return AssetClass.OTHER

# ---------------------------------------------------------
# 3. Core Engine (Deterministic Multi-Custodian Math)
# ---------------------------------------------------------
_PORTFOLIO_CACHE = None
_CACHE_TIMESTAMP = 0
CACHE_TTL = 60

def fetch_and_calculate_portfolio(force: bool = False, excluded_ids: Optional[set] = None) -> Dict[str, Any]:
    global _PORTFOLIO_CACHE, _CACHE_TIMESTAMP
    now = time.time()
    config = load_app_config()
    account_overrides = config.get("account_overrides", {})

    if not force and _PORTFOLIO_CACHE and (now - _CACHE_TIMESTAMP < CACHE_TTL):
        raw_data = _PORTFOLIO_CACHE
    else:
        tokens = load_saved_tokens()
        all_accounts = []
        all_holdings = []
        seen_account_ids = set()
        seen_holding_keys = set()

        for item in tokens:
            access_token = item["access_token"]
            inst_label = item.get("institution", "Unknown")
            payload = {"client_id": PLAID_CLIENT_ID, "secret": PLAID_SECRET, "access_token": access_token}
            
            try:
                resp = requests.post(f"{PLAID_HOST}/investments/holdings/get", json=payload, headers={"Connection": "close"}, timeout=20)
                if resp.status_code != 200:
                    continue
                data = resp.json()
            except Exception:
                continue

            securities = {sec["security_id"]: sec for sec in data.get("securities", [])}

            for acc in data.get("accounts", []):
                acc_id = acc.get("account_id")
                if acc_id in seen_account_ids:
                    continue
                seen_account_ids.add(acc_id)

                raw_bal = (acc.get("balances", {}) or {}).get("current", 0.0) or 0.0
                acc_type = (acc.get("type") or "").lower()
                subtype = (acc.get("subtype") or "").lower()
                name = acc.get("name", "")
                official_name = acc.get("official_name") or ""
                mask = acc.get("mask") or ""

                display_name = f"{name} ({official_name})" if (official_name and official_name.lower() != name.lower()) else name
                if mask and f"****{mask}" not in display_name and f"**{mask}" not in display_name:
                    display_name = f"{display_name} - ****{mask}"

                # 1. Resolve Account Role
                override = account_overrides.get(acc_id, {})
                role = override.get("role")
                if not role:
                    if acc_type in ["credit", "loan"] or subtype in ["credit card", "loan"]:
                        role = AccountRole.LIABILITY.value
                    else:
                        role = AccountRole.LIQUID.value

                # 2. Resolve Owner
                owner = override.get("owner")
                if not owner:
                    name_l = display_name.lower()
                    owner = "Unknown"
                    for o in config.get("owners", []):
                        if o.lower() in name_l:
                            owner = o
                            break

                bal = -abs(raw_bal) if role == AccountRole.LIABILITY.value else raw_bal

                all_accounts.append({
                    "account_id": acc_id,
                    "institution": inst_label,
                    "name": display_name,
                    "official_name": official_name,
                    "mask": mask,
                    "type": acc_type,
                    "subtype": subtype,
                    "role": role,
                    "owner": owner,
                    "current_balance": bal,
                    "notes": override.get("note", "")
                })

            for h in data.get("holdings", []):
                acc_id = h.get("account_id")
                sec_id = h.get("security_id")
                key = f"{acc_id}_{sec_id}"
                if key in seen_holding_keys:
                    continue
                seen_holding_keys.add(key)

                sec = securities.get(sec_id, {})
                ticker = sec.get("ticker_symbol")
                market_val = h.get("institution_value", 0.0) or 0.0

                all_holdings.append({
                    "account_id": acc_id,
                    "ticker": ticker,
                    "name": sec.get("name") or "Unknown Security",
                    "type": sec.get("type"),
                    "market_value": market_val,
                })

        raw_data = {"accounts": all_accounts, "holdings": all_holdings}
        _PORTFOLIO_CACHE = raw_data
        _CACHE_TIMESTAMP = now

    excluded = excluded_ids or set()
    active_accounts = [a for a in raw_data["accounts"] if a["account_id"] not in excluded]
    active_ids = {a["account_id"] for a in active_accounts}

    total_net_worth = 0.0
    stocks = 0.0
    bonds = 0.0
    total_cash = 0.0
    future_income_items = []

    cash_breakdown = []
    equity_breakdown = {}
    bond_breakdown = {}

    holdings_by_account: Dict[str, List[Dict[str, Any]]] = {}
    for h in raw_data["holdings"]:
        if h["account_id"] in active_ids:
            holdings_by_account.setdefault(h["account_id"], []).append(h)

    for acc in active_accounts:
        acc_id = acc["account_id"]
        acc_role = acc["role"]
        bal = acc["current_balance"]
        inst = acc["institution"]
        name = acc["name"]
        owner = acc["owner"]
        acc_label = f"[{owner}] {inst} - {name}"

        if acc_role == AccountRole.WRAPPER_SHELL.value:
            continue
        if acc_role == AccountRole.FUTURE_INCOME.value:
            future_income_items.append({"name": acc_label, "balance": bal})
            continue

        total_net_worth += bal
        acc_holdings = holdings_by_account.get(acc_id, [])

        # Pure Depository Accounts (Checking / Savings)
        if acc["type"] == "depository" and not acc_holdings:
            total_cash += bal
            if abs(bal) >= 1.0:
                cash_breakdown.append(f"{acc_label}: ${bal:,.0f}")
            continue

        # Investment Accounts (Process Real Holdings + Uninvested Cash)
        invested_non_cash = 0.0
        for h in acc_holdings:
            val = h["market_value"]
            if val <= 5.0:
                continue

            h_name = h["name"].lower()
            if "self-directed brokerage fund" in h_name or "brokeragelink" in h_name:
                continue

            cls = classify_holding(h["ticker"], h["name"], h["type"])
            if cls == AssetClass.BOND:
                bonds += val
                invested_non_cash += val
                bond_breakdown[acc_label] = bond_breakdown.get(acc_label, 0.0) + val
            elif cls == AssetClass.CASH:
                total_cash += val
                sec_disp = h["ticker"] if h["ticker"] else h["name"]
                cash_breakdown.append(f"{acc_label} [{sec_disp}]: ${val:,.0f}")
            else:
                stocks += val
                invested_non_cash += val
                equity_breakdown[acc_label] = equity_breakdown.get(acc_label, 0.0) + val

        # Clean Residual Cash Logic: Self-Directed vs Institutional Plans
        name_l = name.lower()
        subtype_l = acc.get("subtype", "").lower()
        
        is_self_directed = any(k in name_l or k in subtype_l for k in [
            "pcra", "brokeragelink", "self-employed", "individual", "brokerage", "tod", "ira", "roth"
        ])
        is_institutional_plan = any(k in name_l for k in [
            "permanente contribution", "salary deferral", "contribution plan"
        ]) and not is_self_directed

        residual_cash = bal - invested_non_cash
        if residual_cash > 1.0 and acc["type"] != "credit":
            cash_in_holdings = sum(
                h["market_value"] for h in acc_holdings 
                if classify_holding(h["ticker"], h["name"], h["type"]) == AssetClass.CASH
            )
            unaccounted_cash = residual_cash - cash_in_holdings

            # Self-directed accounts capture uninvested sweep cash (> $5)
            # Institutional pooled trust plans ignore daily CIT NAV valuation noise
            if is_self_directed and unaccounted_cash > 5.0:
                total_cash += unaccounted_cash
                cash_breakdown.append(f"{acc_label} [USD Cash / Sweep]: ${unaccounted_cash:,.0f}")
            elif not is_institutional_plan and unaccounted_cash > 50.0:
                total_cash += unaccounted_cash
                cash_breakdown.append(f"{acc_label} [Settlement Cash]: ${unaccounted_cash:,.0f}")

    invested = stocks + bonds
    stock_pct = round((stocks / invested * 100), 1) if invested > 0 else 0.0
    bond_pct = round((bonds / invested * 100), 1) if invested > 0 else 0.0
    swr_rate = config.get("swr_rate", 0.0325)
    swr_annual = total_net_worth * swr_rate
    swr_monthly = swr_annual / 12.0

    return {
        "metrics": {
            "total_net_worth": round(total_net_worth, 2),
            "liquid_invested": round(invested, 2),
            "total_cash": round(total_cash, 2),
            "equities": round(stocks, 2),
            "bonds": round(bonds, 2),
            "stock_pct": stock_pct,
            "bond_pct": bond_pct,
            "swr_annual": round(swr_annual, 2),
            "swr_monthly": round(swr_monthly, 2),
            "cash_floor": config.get("cash_floor", 50000.0),
            "swr_rate_pct": round(swr_rate * 100, 2),
            "future_income": future_income_items
        },
        "locations": {
            "cash": cash_breakdown,
            "equities": [f"{k}: ${v:,.0f}" for k, v in sorted(equity_breakdown.items(), key=lambda x: x[1], reverse=True)],
            "bonds": [f"{k}: ${v:,.0f}" for k, v in sorted(bond_breakdown.items(), key=lambda x: x[1], reverse=True)]
        },
        "accounts": raw_data["accounts"]
    }

# ---------------------------------------------------------
# 4. REST Endpoints
# ---------------------------------------------------------
@app.get("/")
def serve_dashboard():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "index.html not found."}

@app.post("/create_link_token")
def create_link_token():
    payload = {
        "client_id": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
        "client_name": "Household FIRE Dashboard",
        "country_codes": ["US"],
        "language": "en",
        "user": {"client_user_id": f"usr_{uuid.uuid4().hex[:8]}"},
        "products": ["investments"]
    }
    resp = requests.post(f"{PLAID_HOST}/link/token/create", json=payload, headers={"Connection": "close"}, timeout=15)
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=resp.text)
    return {"link_token": resp.json().get("link_token")}

@app.post("/exchange_public_token")
async def exchange_public_token(request: Request):
    body = await request.json()
    resp = requests.post(
        f"{PLAID_HOST}/item/public_token/exchange",
        json={"client_id": PLAID_CLIENT_ID, "secret": PLAID_SECRET, "public_token": body.get("public_token")},
        headers={"Connection": "close"},
        timeout=15
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=resp.text)

    token = resp.json()["access_token"]
    save_token(token, body.get("institution_name", "Unknown"))
    global _PORTFOLIO_CACHE
    _PORTFOLIO_CACHE = None
    return {"status": "success"}

@app.get("/portfolio")
def get_portfolio(excluded: Optional[str] = None):
    ex_set = set(excluded.split(",")) if excluded else set()
    return fetch_and_calculate_portfolio(excluded_ids=ex_set)

@app.post("/ask_gemini")
def ask_gemini(req: AskGeminiRequest):
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("\n[GEMINI] [ERROR] GEMINI_API_KEY is not configured in .env.")
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured.")

    data = fetch_and_calculate_portfolio(excluded_ids=set(req.excluded_accounts))
    m = data["metrics"]
    loc = data["locations"]

    eq_str = "\n  * ".join(loc["equities"]) or "None"
    bd_str = "\n  * ".join(loc["bonds"]) or "None"
    cs_str = "\n  * ".join(loc["cash"]) or "None"
    fi_str = json.dumps(m["future_income"], indent=2)

    system_instruction = f"""You are an elite early retirement (FIRE) advisor and portfolio strategist.

PORTFOLIO STATE (ACTIVE LIQUID INVESTMENTS ONLY):
- Equities: ${m['equities']:,.0f} ({m['stock_pct']}%)
  * Locations:
  * {eq_str}
- Bonds: ${m['bonds']:,.0f} ({m['bond_pct']}%)
  * Locations:
  * {bd_str}
- Liquid Invested Assets: ${m['liquid_invested']:,.0f}
- Liquid Cash Reserve: ${m['total_cash']:,.0f} (Target Floor:${m['cash_floor']:,.0f})
  * Locations:
  * {cs_str}
- Total Net Worth: ${m['total_net_worth']:,.0f}
- Safe Withdrawal Rate ({m['swr_rate_pct']}%): ${m['swr_annual']:,.0f}/yr (${m['swr_monthly']:,.0f}/mo)

GUARANTEED FUTURE RETIREMENT CASH FLOW:
{fi_str}
- NOTE: Future income is strictly excluded from liquid rebalancing and current cash reserves.

OPERATING RULES:
1. Ground answers strictly in the figures above.
2. Quote asset allocation strictly as: {m['stock_pct']}% Stock / {m['bond_pct']}% Bond.
3. Every account has an explicit [Owner] tag in the breakdown. Group accounts strictly by these tags.
4. Deliver concise, structured insights using markdown tables and bullet points."""

    candidate_models = get_configured_gemini_models()
    headers = {"Content-Type": "application/json", "Connection": "close"}
    
    contents = []
    for turn in (req.history[-2:] if len(req.history) > 2 else req.history):
        r, t = turn.get("role"), turn.get("text", "")
        if r in ["user", "model"] and t:
            contents.append({"role": r, "parts": [{"text": t}]})
    contents.append({"role": "user", "parts": [{"text": req.prompt}]})

    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 8192
        }
    }

    print("\n" + "="*60)
    print(f"[GEMINI] Candidate models configured: {candidate_models}")
    print(f"[GEMINI] Primary model target: {candidate_models[0] if candidate_models else 'None'}")
    print(f"[GEMINI] Fallback models available: {candidate_models[1:] if len(candidate_models) > 1 else 'None'}")
    print("="*60)

    last_error = ""

    for model_idx, clean_model in enumerate(candidate_models, start=1):
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
        print(f"\n[GEMINI] [Model {model_idx}/{len(candidate_models)}] Connecting to: '{clean_model}'")

        for attempt in range(1, 3):
            try:
                print(f"[GEMINI] [{clean_model}] Dispatching prompt (Attempt {attempt}/2)...")
                t0 = time.time()
                resp = requests.post(endpoint, json=payload, headers=headers, timeout=60.0)
                elapsed = time.time() - t0

                if resp.status_code == 200:
                    data_json = resp.json()
                    candidates = data_json.get("candidates", [])
                    if candidates and "content" in candidates[0] and "parts" in candidates[0]["content"]:
                        text = candidates[0]["content"]["parts"][0]["text"]
                        finish_reason = candidates[0].get("finishReason", "UNKNOWN")
                        print(f"[GEMINI] [SUCCESS] Responded from: '{clean_model}' in {elapsed:.2f}s (finishReason: {finish_reason})")
                        print("="*60 + "\n")
                        return {"response": text, "active_model": clean_model}
                    else:
                        last_error = f"Malformed payload from '{clean_model}': {resp.text}"
                        print(f"[GEMINI] [WARN] {last_error}")
                        break
                elif resp.status_code == 503:
                    last_error = f"HTTP 503 Service Unavailable on '{clean_model}'"
                    print(f"[GEMINI] [OVERLOAD] '{clean_model}' returned 503. Backing off 3.0s...")
                    time.sleep(3.0)
                    continue
                elif resp.status_code == 429:
                    last_error = f"HTTP 429 Rate Limit Exceeded on '{clean_model}'"
                    print(f"[GEMINI] [RATE-LIMIT] '{clean_model}' quota reached. Moving to fallback...")
                    break
                else:
                    last_error = f"HTTP {resp.status_code} on '{clean_model}': {resp.text}"
                    print(f"[GEMINI] [ERROR] {last_error}")
                    break
            except Exception as e:
                last_error = f"Network exception on '{clean_model}': {str(e)}"
                print(f"[GEMINI] [FAIL] {last_error}")
                break

        if model_idx < len(candidate_models):
            print(f"[GEMINI] [FAILOVER] Shifting from '{clean_model}' to next candidate: '{candidate_models[model_idx]}'")

    print(f"[GEMINI] [FATAL] All candidate models exhausted. Last error: {last_error}")
    print("="*60 + "\n")
    raise HTTPException(status_code=500, detail=f"All models failed. Last error: {last_error}")