# E-Business Card API

FastAPI backend for parsing raw OCR text via OpenRouter (Gemini) and persisting hybrid-schema cards to MongoDB.

## Quick start

```bash
cp .env.example .env
# Edit .env with real credentials

docker compose up --build
```

API docs: http://localhost:8000/docs

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/cards/process` | Parse OCR text, persist to `captured_cards` |

## Contract

`openapi.yaml` is the source of truth shared with the mobile repo.

## Local Python development (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export MONGO_URI=mongodb://localhost:27017
export OPENROUTER_API_KEY=your-key

uvicorn app.main:app --reload
```
