# Backend-FP-Biomed-ParkinStep

Companion REST & WebSocket backend for **ParkinStep (Mobile-FOG)** — an Edge-AI *Freezing of Gait* (FoG) screening and rhythmic cueing system for Parkinson's patients.

> **Offline-First Architecture Note:** Core pose estimation (`YOLO26n-Pose`) and FoG classification (`LightGBM+FFT`, `B_15hz`) run **100% locally on the patient's mobile device** via C++17 & ONNX Runtime Mobile with zero internet required. This companion backend provides optional telemedicine sync, UU PDP No. 27/2022 consent/erasure management, medication tracking, caregiver emergency alerts, OTA model manifest distribution, and opt-in cloud fallback.

## Architecture & Standards

- **Clean Architecture + DDD:** Strictly enforces the Dependency Rule (`presentation` → `application` → `domain`; `infrastructure` → `application` → `domain`). `src/domain/` has zero third-party dependencies.
- **Anti-Drift Guardrails (OpenAPI 3.1.0):**
  - Explicit distinction between optional (`UNSET`) and nullable (`null`) fields.
  - All timestamps enforced as ISO-8601 UTC ending in `Z`.
  - All enums serialized as uppercase `StrEnum` literals.
  - Mandatory `Idempotency-Key` (UUID) protection on mutating offline-first `POST` endpoints.
  - Standardized **RFC 7807** (`application/problem+json`) error responses with stable `error_code` values.
- **UU PDP No. 27/2022 Privacy & Clinical Safety:**
  - Zero raw-video retention by default (only anonymized LB6 keypoints and session metrics).
  - Granular consent tracking with audit trail (`consent_local`, `consent_skeleton_sync`, `consent_cloud_video`).
  - Password re-authenticated Right to Erasure (`DELETE /api/v1/patients/{patient_id}`) cascading across clinical records, tokens, and idempotency cache.
  - Automatic PII scrubbing in structured logs.

## Quickstart

```bash
# 1. Configure environment variables (never commit .env)
cp .env.example .env

# 2. Install dependencies into .venv
uv sync --python 3.12

# 3. Apply PostgreSQL migrations
uv run alembic upgrade head

# 4. Run development server
uv run uvicorn src.main:app --reload

# 5. Run lint, strict type-checking, and test suite
uv run ruff check src tests migrations
uv run mypy src
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85
```

## Implementation Phases

- [x] **Phase 1:** Clean Architecture scaffold, PostgreSQL schema + Alembic migrations, JWT auth (`register`/`login`/`refresh`/`logout`) with token rotation & reuse detection, Patients & UU PDP (`GET`/`PATCH`/`DELETE`), Idempotency middleware, RFC 7807 error handler.
- [x] **Phase 2:** Medication logs, Clinical sessions, LB6 skeleton frames (`[T][6][3]`), Session results, Cloud video fallback opt-in, Longitudinal analytics trends, Emergency alerts, OTA model manifest (`B_15hz`).
- [ ] **Phase 3:** Clinical PDF/JSON report export, WebSocket `CLOUD_FALLBACK` streaming (`126` FFT features), OpenAPI 3.1 contract CI export, Rootless hardened Dockerfile & Compose.
