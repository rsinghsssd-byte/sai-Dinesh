# Quickstart — Running Case File (Plagiarism Detector) Locally

You were sent a folder called `plagiarism-detector`. Here's how to get it
running on your own machine. Pick **Option A** if you have Docker Desktop
(easiest, one command). Pick **Option B** if you'd rather run it with plain
Python (also easy, a few more steps).

You do **not** need to be a developer to do either of these — just follow
the steps in order.

---

## Option A: Docker (one command)

### Prerequisite
Install **Docker Desktop**: https://www.docker.com/products/docker-desktop/
After installing, restart your computer, then open Docker Desktop once and
wait until it says "Engine running."

### Run it
Open a terminal (Command Prompt / PowerShell on Windows, Terminal on Mac),
navigate into the folder you were given, and run:

```
cd plagiarism-detector
docker compose up --build
```

Wait for it to finish building (first run takes a couple of minutes), then
open your browser to:

```
http://localhost:8000
```

To stop it later, go back to that terminal window and press `Ctrl+C`.

---

## Option B: Plain Python (no Docker)

### Prerequisites
1. **Python 3.10 or newer**: https://www.python.org/downloads/
   - On the install screen, check the box **"Add python.exe to PATH"**
     (Windows) before clicking Install.
2. **Git**: https://git-scm.com/downloads
   - Needed because the app clones GitHub repositories on your behalf.

After installing either one, close and reopen your terminal so it picks up
the new programs.

### Run it

**Windows (PowerShell):**
```powershell
cd plagiarism-detector\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

**Mac / Linux:**
```bash
cd plagiarism-detector/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn app.main:app --reload --port 8000
```

Once you see a line like `Uvicorn running on http://0.0.0.0:8000`, open your
browser to:

```
http://localhost:8000
```

To stop it later, click into that terminal window and press `Ctrl+C`.

### If something doesn't work
- **"python is not recognized"** → Python isn't installed or wasn't added to
  PATH. Reinstall and make sure to check that box.
- **"running scripts is disabled on this system"** (Windows, when activating
  the venv) → run this once, then try activating again:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
- **"uvicorn is not recognized"** → your virtual environment likely isn't
  active. Your prompt should show `(.venv)` at the start of the line before
  you run the `uvicorn`/`python -m uvicorn` command. Re-run the `activate`
  line above.
- Anything else → send the exact error message to whoever shared this with
  you.

---

## Using the app once it's running

1. Open **http://localhost:8000** in your browser.
2. Paste in 2–20 GitHub repository URLs to compare.
3. Pick the programming language, branch (defaults to `main`), and a
   similarity threshold.
4. Click **Run analysis** and wait for the progress bar.
5. Review the similarity matrix and flagged pairs, click into any pair for
   file-level and commit-level detail.
6. Click **Download report** for a shareable HTML summary (open it and
   print to PDF from your browser if you need a PDF copy).

No data leaves your machine except the GitHub repositories being cloned —
everything else (the analysis, the report) runs locally.
