# app/ — ProdAI Web Dashboard

FastAPI + Jinja2 server-rendered web app. Handles auth, breakdown logging, and RCA creation.

## Structure

```
app/
├── main.py           FastAPI app — all routes
├── database.py       SQLAlchemy models (User, BreakdownLog)
├── requirements.txt
├── Dockerfile
├── templates/
│   ├── base.html         Layout, nav, glassmorphism styles
│   ├── login.html        Login page
│   ├── dashboard.html    Overview, metrics, DataTable log list
│   ├── log_breakdown.html  Breakdown entry form
│   └── create_rca.html   AI assist + manual 5 Whys tree
├── static/
│   ├── favicon.svg
│   └── uploads/          User-uploaded documents
├── data/                 CSV files for bulk import
└── scripts/              DB migration helpers
```

## Routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Login page (redirects to dashboard if authenticated) |
| POST | `/login` | Authenticate, set JWT cookie |
| GET | `/logout` | Clear cookie, redirect to login |
| GET | `/dashboard` | Overview with metrics, chart, log table |
| GET | `/log-breakdown` | Breakdown entry form |
| POST | `/log-breakdown` | Submit breakdown — redirects to RCA page |
| GET | `/create-rca/{id}` | AI assist + manual 5 Whys tree |
| POST | `/save-rca/{id}` | Persist RCA JSON to DB |
| POST | `/update-status/{id}` | Change breakdown status inline |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_API_URL` | `http://localhost:8000` | URL browser uses for AI SSE stream |
| `APP_PORT` | `8080` | Web server port |
| `SECRET_KEY` | (insecure default) | JWT signing key — **change in production** |

## Database

SQLite file: `plant_dashboard_v2.db` (auto-created on startup).

`rca_data` column stores JSON in one of three formats:
- `{"type": "ai_generated", ...}` — full AI result + CAPA + team list
- `{"type": "manual_tree", "nodes": [...]}` — manual 5 Whys tree
- `[{id, parentId, text}, ...]` — legacy format (auto-migrated on read)
