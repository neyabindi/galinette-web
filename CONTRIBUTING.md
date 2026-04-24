# Contributing to Galinette Web

Thanks for your interest! This project is a community effort to provide French-speaking
(and English-speaking) sysadmins with a modern alternative to the legendary Galinette cendrée.

## Ways to contribute

- **Report bugs** via GitHub Issues (use the bug template)
- **Suggest features** via GitHub Issues (use the feature template)
- **Submit pull requests** for fixes or new features
- **Share feedback** from your real-world deployments — tell us how it runs in your environment
- **Improve documentation** — README translations, screenshots, deployment guides

## Development setup

### Backend (FastAPI)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173 — the dev server proxies `/api` to the backend on port 8000.

### Full stack (Docker)

```bash
docker compose up --build
```

## Pull requests

1. Fork the repo and create a branch from `main`
2. Make your changes with clear commit messages
3. Test locally
4. Open a PR describing what you changed and why
5. Respond to review feedback

## Coding guidelines

- **Python**: PEP 8, type hints on public functions, docstrings in French or English
- **JavaScript/JSX**: follow the existing code style (no semicolons policy is whatever the file uses), prefer functional components with hooks
- **Avoid unnecessary dependencies** — keep the Docker images small
- **Don't break security**: never log credentials, always bind LDAP in read-only mode, keep the audit log intact

## Testing your changes

At minimum:
- The backend builds and starts without errors
- The frontend builds (`npm run build`) without warnings
- Login works against a test AD
- One session listing round-trip works end-to-end

## Questions?

Open a GitHub Discussion or Issue — we're friendly.
