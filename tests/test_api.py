"""
tests/test_api.py

API contract tests using FastAPI's TestClient.

Every external dependency (database, LLM) is mocked in the api_client fixture
defined in conftest.py.  No real Postgres or Ollama server is needed.

Endpoints under test
--------------------
GET  /health        — liveness + DB status
GET  /summary       — revenue KPIs
GET  /quality       — data quality audit
GET  /forecast      — precomputed forecast points
POST /ingest        — trigger ingestion pipeline
POST /insights      — aggregate insights (LLM-fallback and LLM paths)
POST /ask           — natural-language Q&A (LLM-fallback and LLM paths)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_ok(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db_connected"] is True
    assert "version" in body


def test_health_degraded():
    """When ping() returns False the status is 'degraded'."""
    from src.api.main import app
    from contextlib import ExitStack
    from fastapi.testclient import TestClient

    patches = [
        patch("src.api.main.ping", return_value=False),
        patch("src.api.routes.health.ping", return_value=False),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        with TestClient(app) as client:
            resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db_connected"] is False


# ── /summary ──────────────────────────────────────────────────────────────────

def test_summary_shape(api_client):
    resp = api_client.get("/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_revenue" in body
    assert "top_category" in body
    assert "top_region" in body
    assert "transaction_count" in body
    assert isinstance(body["revenue_by_category"], list)
    assert isinstance(body["revenue_by_region"], list)


def test_summary_values(api_client):
    """Values from the mock KPI dict pass through unchanged."""
    resp = api_client.get("/summary")
    body = resp.json()
    assert body["total_revenue"] == 170.0
    assert body["top_category"] == "Beverages"
    assert body["top_region"] == "NORTHEAST"
    assert body["transaction_count"] == 4


def test_summary_category_list_structure(api_client):
    resp = api_client.get("/summary")
    cats = resp.json()["revenue_by_category"]
    assert len(cats) >= 1
    assert "category" in cats[0]
    assert "revenue" in cats[0]


# ── /quality ──────────────────────────────────────────────────────────────────

def test_quality_shape(api_client):
    resp = api_client.get("/quality")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_issues" in body
    assert "by_issue_type" in body
    assert "by_action_taken" in body
    assert "total_batches" in body


def test_quality_latest_batch(api_client):
    resp = api_client.get("/quality")
    batch = resp.json()["latest_batch"]
    assert batch is not None
    assert batch["load_type"] == "HISTORICAL"
    assert batch["inserted"] == 8


def test_quality_issue_list(api_client):
    resp = api_client.get("/quality")
    issues = resp.json()["by_issue_type"]
    assert len(issues) >= 1
    assert "issue_type" in issues[0]
    assert "count" in issues[0]


# ── /forecast ─────────────────────────────────────────────────────────────────

def test_forecast_shape(api_client):
    resp = api_client.get("/forecast")
    assert resp.status_code == 200
    body = resp.json()
    assert "horizon" in body
    assert "points" in body
    assert len(body["points"]) > 0


def test_forecast_point_fields(api_client):
    resp = api_client.get("/forecast")
    point = resp.json()["points"][0]
    assert "target_date" in point
    assert "predicted_revenue" in point
    assert "yhat_lower" in point
    assert "yhat_upper" in point


def test_forecast_404_when_no_data():
    """When the DB returns no forecast rows the endpoint returns 404."""
    from contextlib import ExitStack
    from fastapi.testclient import TestClient
    from src.api.main import app

    empty = {"run_date": None, "model_version": None, "points": []}
    patches = [
        patch("src.api.main.ping", return_value=True),
        patch("src.api.routes.forecast.get_forecast_rows", return_value=empty),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        with TestClient(app) as client:
            resp = client.get("/forecast")

    assert resp.status_code == 404


# ── /ingest ───────────────────────────────────────────────────────────────────

def test_ingest_historical(api_client):
    resp = api_client.post("/ingest?mode=historical")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mode"] == "historical"
    assert "files_processed" in body
    assert "batch" in body


def test_ingest_incremental(api_client):
    resp = api_client.post("/ingest?mode=incremental")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "incremental"


def test_ingest_invalid_mode(api_client):
    resp = api_client.post("/ingest?mode=bogus")
    assert resp.status_code == 400


# ── /insights (fallback path) ──────────────────────────────────────────────────

def test_insights_shape(api_client):
    resp = api_client.post("/insights")
    assert resp.status_code == 200
    body = resp.json()
    assert "summary" in body
    assert "llm_used" in body
    assert isinstance(body["revenue_by_category"], list)
    assert isinstance(body["revenue_by_region"], list)


def test_insights_fallback_llm_flag(api_client):
    """Mocked generate_insights returns llm_used=False (fallback)."""
    resp = api_client.post("/insights")
    assert resp.json()["llm_used"] is False


def test_insights_llm_path():
    """When generate_insights returns llm_used=True the flag propagates."""
    from contextlib import ExitStack
    from fastapi.testclient import TestClient
    from src.api.main import app

    mock_agg = {
        "total_revenue": 170.0,
        "by_category": [{"category": "Beverages", "revenue": 90.0}],
        "by_region": [{"region": "NORTHEAST", "revenue": 80.0}],
    }
    patches = [
        patch("src.api.main.ping", return_value=True),
        patch("src.api.routes.insights.get_insights_aggregates", return_value=mock_agg),
        patch(
            "src.api.routes.insights.generate_insights",
            new=AsyncMock(return_value=("AI-generated summary", True)),
        ),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        with TestClient(app) as client:
            resp = client.post("/insights")

    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_used"] is True
    assert body["summary"] == "AI-generated summary"


def test_insights_503_when_data_missing():
    """FileNotFoundError from aggregation → 503."""
    from contextlib import ExitStack
    from fastapi.testclient import TestClient
    from src.api.main import app

    patches = [
        patch("src.api.main.ping", return_value=True),
        patch(
            "src.api.routes.insights.get_insights_aggregates",
            side_effect=FileNotFoundError("no csv"),
        ),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        with TestClient(app) as client:
            resp = client.post("/insights")

    assert resp.status_code == 503


# ── /ask (fallback path) ───────────────────────────────────────────────────────

def test_ask_shape(api_client):
    resp = api_client.post("/ask", json={"question": "Which region has the highest revenue?"})
    assert resp.status_code == 200
    body = resp.json()
    assert "question" in body
    assert "answer" in body
    assert "llm_used" in body
    assert "context_preview" in body


def test_ask_returns_question_echo(api_client):
    question = "What is the total revenue?"
    resp = api_client.post("/ask", json={"question": question})
    assert resp.json()["question"] == question


def test_ask_fallback_llm_flag(api_client):
    resp = api_client.post("/ask", json={"question": "test?"})
    assert resp.json()["llm_used"] is False


def test_ask_llm_path():
    """When answer_question returns llm_used=True the flag propagates."""
    from contextlib import ExitStack
    from fastapi.testclient import TestClient
    from src.api.main import app

    patches = [
        patch("src.api.main.ping", return_value=True),
        patch("src.api.routes.ask.build_bounded_context", return_value="context text"),
        patch(
            "src.api.routes.ask.answer_question",
            new=AsyncMock(return_value=("LLM answered", True)),
        ),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        with TestClient(app) as client:
            resp = client.post("/ask", json={"question": "top category?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_used"] is True
    assert body["answer"] == "LLM answered"


def test_ask_empty_question_rejected(api_client):
    """An empty question string must return 400."""
    resp = api_client.post("/ask", json={"question": "   "})
    assert resp.status_code == 400


def test_ask_503_when_data_missing():
    """FileNotFoundError from context build → 503."""
    from contextlib import ExitStack
    from fastapi.testclient import TestClient
    from src.api.main import app

    patches = [
        patch("src.api.main.ping", return_value=True),
        patch(
            "src.api.routes.ask.build_bounded_context",
            side_effect=FileNotFoundError("no csv"),
        ),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        with TestClient(app) as client:
            resp = client.post("/ask", json={"question": "revenue?"})

    assert resp.status_code == 503


# ── LLM unit tests (llm.py, no HTTP call) ─────────────────────────────────────

def test_llm_insights_fallback_deterministic():
    """generate_insights returns a deterministic string when Ollama is unreachable."""
    import asyncio
    from unittest.mock import patch as _patch
    from src.api.llm import generate_insights

    agg = {
        "total_revenue": 300.0,
        "by_category": [
            {"category": "Beverages", "revenue": 200.0},
            {"category": "Snacks", "revenue": 100.0},
        ],
        "by_region": [{"region": "EAST", "revenue": 300.0}],
    }

    with _patch("src.api.llm._call_llm", return_value=None):
        summary, llm_used = asyncio.run(generate_insights(agg))

    assert llm_used is False
    assert "300" in summary or "300.00" in summary
    assert "Beverages" in summary


def test_llm_ask_fallback_includes_context():
    """answer_question fallback embeds the bounded context in the reply."""
    import asyncio
    from unittest.mock import patch as _patch
    from src.api.llm import answer_question

    context = "Total revenue: $500"
    question = "How much revenue?"

    with _patch("src.api.llm._call_llm", return_value=None):
        answer, llm_used = asyncio.run(answer_question(context, question))

    assert llm_used is False
    assert "LLM unavailable" in answer
    assert context in answer


def test_llm_insights_uses_llm_when_available():
    """generate_insights returns llm_used=True when _call_llm succeeds."""
    import asyncio
    from unittest.mock import patch as _patch
    from src.api.llm import generate_insights

    agg = {
        "total_revenue": 100.0,
        "by_category": [{"category": "Dairy", "revenue": 100.0}],
        "by_region": [{"region": "WEST", "revenue": 100.0}],
    }

    with _patch("src.api.llm._call_llm", return_value="• Revenue is $100"):
        summary, llm_used = asyncio.run(generate_insights(agg))

    assert llm_used is True
    assert summary == "• Revenue is $100"


def test_llm_ask_uses_llm_when_available():
    import asyncio
    from unittest.mock import patch as _patch
    from src.api.llm import answer_question

    with _patch("src.api.llm._call_llm", return_value="Beverages leads revenue."):
        answer, llm_used = asyncio.run(
            answer_question("ctx", "top?")
        )

    assert llm_used is True
    assert answer == "Beverages leads revenue."
