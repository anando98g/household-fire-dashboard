# Guided Setup: Household FIRE Dashboard

This guide walks you step-by-step through setting up and running the dashboard on your personal computer. **No background in programming or Git is required.**

---

## Overview: What You Need
To run this dashboard locally, you will need:
1. **The project files** (downloaded as a ZIP folder from GitHub).
2. **Python** (a standard programming runtime installed on your computer).
3. **Two free API keys**:
   - A **Google Gemini API Key** (to enable the plain-English financial assistant).
   - A **Plaid Account** (to securely link your bank and brokerage accounts in read-only mode).

---

## Step 1: Download the Project Files

You do **not** need to install or use Git.

1. Go to the project page on GitHub: [https://github.com/anando98g/household-fire-dashboard](https://github.com/anando98g/household-fire-dashboard).
2. Click the green **`<> Code`** button near the top right.
3. Click **Download ZIP**.
4. Once downloaded, double-click the ZIP file to extract (unzip) it.
5. Move the unzipped folder (`household-fire-dashboard-main` or `household-fire-dashboard`) to a convenient location, such as your **Desktop** or **Documents** folder.

---

## Step 2: Make Sure Python is Installed

This application runs locally using Python.

### On Windows:
1. Visit the official Python download page: [https://www.python.org/downloads/](https://www.python.org/downloads/).
2. Click **Download Python 3.12** (or the latest stable 3.x release).
3. Open the downloaded installer file.
4. ⚠️ **CRITICAL STEP:** On the very first installation screen, check the box at the bottom that says:  
   **"Add python.exe to PATH"** (or **"Add Python to PATH"**).  
   *If you skip this box, your system will not recognize the `python` command.*
5. Click **Install Now** and wait for it to finish.

### On macOS:
* Modern versions of macOS come with Python 3 pre-installed.
* To verify, open **Terminal** (press `Cmd + Space`, type `Terminal`, and press `Enter`), type:
  ```bash
  python3 --version
  ```
* If a version number appears (e.g., `Python 3.10.x` or higher), you are ready. If prompted to install Developer Tools, click **Install** and proceed.

---

## Step 3: Get Your Free API Keys

### 1. Google Gemini API Key (Free)
1. Visit [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Sign in with your standard Google account.
3. Click **Create API Key**.
4. Copy the generated key and keep it handy (you will paste it into your configuration file in the next step).

### 2. Plaid Developer Keys (Free)
1. Sign up for a free developer account at [Plaid Dashboard](https://dashboard.plaid.com/signup).
2. Once signed in, navigate to **Team Settings** $\rightarrow$ **Keys**.
3. Locate your **Client ID** and your **Secret** (you can start with the Sandbox or Development secret). Copy both values.

---

## Step 4: Configure Your Settings (`.env` and `config.json`)

Inside the project folder you unzipped, you will see two template files:
* `.env.example`
* `config.example.json`

### Creating Your Private Configuration Files:

#### On Windows:
1. Open the project folder in File Explorer.
2. Right-click `.env.example` $\rightarrow$ select **Copy**, then right-click in an empty space $\rightarrow$ select **Paste**.
3. Rename the newly pasted file to `.env` *(if Windows warns you about changing the file extension, click Yes)*.
4. Do the same for `config.example.json`: make a copy and rename the copy to `config.json`.

#### On macOS:
1. Open the project folder in Finder.
2. Duplicate `.env.example` and rename it to `.env`.  
   *(Tip: Files beginning with a dot are hidden by macOS default. Press `Cmd + Shift + .` to show or hide hidden files).*
3. Duplicate `config.example.json` and rename it to `config.json`.

---

### Filling In Your API Keys:
1. Right-click `.env` and open it with **Notepad** (Windows) or **TextEdit** (Mac).
2. Replace the placeholders with your actual keys:
   ```ini
   PLAID_CLIENT_ID=paste_your_plaid_client_id_here
   PLAID_SECRET=paste_your_plaid_secret_here
   PLAID_ENV=production

   GEMINI_API_KEY=paste_your_gemini_api_key_here
   GEMINI_MODEL=gemini-2.5-flash
   GEMINI_FALLBACK_MODEL=gemini-2.5-pro
   ```
3. Save and close the file.

---

## Step 5: Start the Dashboard

### On Windows:
1. Press `Win + S`, type `Command Prompt` (or `cmd`), and hit `Enter`.
2. Navigate into your project folder. The easiest way is to type `cd ` (with a space after it), then **drag and drop your project folder directly from File Explorer into the Command Prompt window**, and hit `Enter`.
3. Create the local environment and install required libraries by pasting this single command:
   ```cmd
   python -m venv venv && venv\Scripts\activate && pip install -r requirements.txt
   ```
   *(This only takes 1–2 minutes the first time you run it).*
4. Start the dashboard server:
   ```cmd
   uvicorn main:app --reload --port 8000
   ```

### On macOS:
1. Open **Terminal** (press `Cmd + Space`, type `Terminal`, and hit `Enter`).
2. Navigate into your project folder: type `cd ` (with a space), **drag and drop your project folder from Finder into Terminal**, and hit `Enter`.
3. Create the local environment and install required libraries:
   ```bash
   python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
   ```
4. Start the dashboard server:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

---

## Step 6: Open the Dashboard

1. Open your favorite web browser (Chrome, Safari, Edge, or Firefox).
2. Go to: **`http://localhost:8000`**
3. Click the **Connect Custodian** button.
4. Follow the secure Plaid Link prompts to connect your financial institutions (Schwab, Vanguard, Fidelity, etc.).
5. Your accounts, aggregated holdings, and the Gemini Strategy Advisor will appear on your screen.

---

## How to Reopen the Dashboard Later

Whenever you want to use the dashboard in the future:
1. Open Command Prompt (Windows) or Terminal (Mac).
2. Navigate to your folder (`cd path/to/folder`).
3. Run:
   - **Windows:** `venv\Scripts\activate && uvicorn main:app --port 8000`
   - **Mac:** `source venv/bin/activate && uvicorn main:app --port 8000`
4. Visit `http://localhost:8000` in your browser.

---

## Security & Privacy Guarantee
* All bank tokens, credentials, and API calls are executed **locally on your device**.
* Your personal net worth and account numbers are never sent to any external server or stored in the cloud.