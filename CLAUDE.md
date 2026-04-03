# growatt-bridge Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-03

## Active Technologies
- Python ≥3.11 (`pyproject.toml`) + FastAPI ≥0.115, Uvicorn, Pydantic v2, pydantic-settings, requests, growattServer (001-api-redesign)
- N/A for bridge state beyond optional append-only audit JSONL (`BRIDGE_AUDIT_LOG`) (001-api-redesign)

- Python ≥3.11 (see `pyproject.toml` `requires-python`) + FastAPI ≥0.115, Uvicorn, Pydantic v2, pydantic-settings, requests, growattServer (password hashing / legacy helpers as needed) (001-api-redesign)

## Project Structure

```text
backend/
frontend/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python ≥3.11 (see `pyproject.toml` `requires-python`): Follow standard conventions

## Recent Changes
- 001-api-redesign: Added Python ≥3.11 (`pyproject.toml`) + FastAPI ≥0.115, Uvicorn, Pydantic v2, pydantic-settings, requests, growattServer

- 001-api-redesign: Added Python ≥3.11 (see `pyproject.toml` `requires-python`) + FastAPI ≥0.115, Uvicorn, Pydantic v2, pydantic-settings, requests, growattServer (password hashing / legacy helpers as needed)

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
