"""Alert queue, cases and review API.

Alerts come from transaction monitoring (scripts/train_detection.py) and are loaded
into Postgres at startup when the table is empty (or with scripts/load_alerts.py).
Opening an alert creates its case once; the worker then runs the AI review.
There is deliberately no endpoint that finalizes a case: only the worker
finalizes, and only after a decision recorded here.

    uvicorn aml_agent.api.app:app
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from aml_agent import store
from aml_agent.agent import copilot, sar
from aml_agent.alerts.io import read_alerts, read_queue
from aml_agent.alerts.models import Alert
from aml_agent.audit import PostgresAudit, timeline, verify_chain
from aml_agent.llm.base import get_provider
from aml_agent.schemas.case import Decision
from aml_agent.tools.client import connect_graph

log = logging.getLogger("aml_agent.api")


class NewCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: str | None = None
    alert_set: Literal["dev", "eval"] = "dev"
    alert: Alert | None = None

    @model_validator(mode="after")
    def _one_source(self) -> NewCase:
        if (self.alert_id is None) == (self.alert is None):
            raise ValueError("give exactly one of alert_id or alert")
        return self


class SarEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: sar.SarNarrative
    author: str = Field(min_length=1, max_length=100)
    role: Literal["analyst", "supervisor"] = "analyst"


class SarApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=100)
    role: Literal["analyst", "supervisor"] = "analyst"


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=1000)


def create_app(pool=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        p = pool or store.make_pool()
        await p.open()
        await store.init_schema(p)
        app.state.pool = p
        app.state.audit = PostgresAudit(p)
        await app.state.audit.init_schema()
        if await store.count_alerts(p) == 0:
            n = await store.load_alerts(p, (a.model_dump(mode="json") for a in read_queue()))
            log.info("loaded %d monitoring alerts", n)
        yield
        await p.close()

    app = FastAPI(title="AML Investigation Agent", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict:
        async with app.state.pool.connection() as conn:
            await conn.execute("SELECT 1")
        return {"status": "ok"}

    @app.post("/cases", status_code=201)
    async def create_case(body: NewCase) -> dict:
        if body.alert is not None:
            alert = body.alert
        else:
            matches = [a for a in read_alerts(body.alert_set) if a.alert_id == body.alert_id]
            if not matches:
                raise HTTPException(404, f"alert {body.alert_id} not in {body.alert_set}")
            alert = matches[0]
        payload = alert.model_dump(mode="json")
        case_id = await store.create_case(app.state.pool, payload)
        await app.state.audit.emit(case_id, "case_created", {"alert": payload}, actor="api")
        return {"case_id": case_id, "status": "queued"}

    @app.get("/alerts")
    async def list_alerts(
        priority: Literal["high", "medium", "low", "sample"] | None = None,
        status: str | None = None,
        q: str | None = Query(None, max_length=40),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict:
        """One page of the monitoring alert queue, highest score first. Labels are
        never served."""
        return await store.list_alerts(app.state.pool, priority, status, q, limit, offset)

    @app.get("/alerts/summary")
    async def alert_summary() -> dict:
        return await store.alert_summary(app.state.pool)

    @app.get("/alerts/{alert_id}")
    async def get_alert(alert_id: str) -> dict:
        alert = await store.get_alert(app.state.pool, alert_id)
        if alert is None:
            raise HTTPException(404, "no such alert")
        return alert

    @app.post("/alerts/{alert_id}/open")
    async def open_alert(alert_id: str) -> dict:
        """The alert's case; the first open creates it and starts the AI review."""
        opened = await store.open_alert(app.state.pool, alert_id)
        if opened is None:
            raise HTTPException(404, "no such alert")
        case_id, created = opened
        if created:
            alert = await store.get_alert(app.state.pool, alert_id)
            await app.state.audit.emit(
                case_id, "case_created", {"alert": alert["alert"]}, actor="api"
            )
        return {"case_id": case_id, "created": created}

    @app.get("/cases")
    async def list_cases(status: str | None = None) -> list[dict]:
        return await store.list_cases(app.state.pool, status)

    @app.get("/stats")
    async def stats() -> dict:
        return await store.stats(app.state.pool)

    @app.get("/cases/{case_id}")
    async def get_case(case_id: str) -> dict:
        case = await store.get_case(app.state.pool, case_id)
        if case is None:
            raise HTTPException(404, "no such case")
        return case

    @app.post("/cases/{case_id}/decision")
    async def decide(case_id: str, decision: Decision) -> dict:
        try:
            await store.record_decision(app.state.pool, case_id, decision)
        except KeyError:
            raise HTTPException(404, "no such case") from None
        except store.CaseStateError as exc:
            raise HTTPException(409, str(exc)) from None
        await app.state.audit.emit(
            case_id, "decision_recorded", decision.model_dump(mode="json"), actor="api"
        )
        return {"case_id": case_id, "status": "decision_recorded"}

    @app.post("/cases/{case_id}/retry")
    async def retry(case_id: str) -> dict:
        """Run a failed AI review again, from its last checkpoint."""
        try:
            await store.retry_failed(app.state.pool, case_id)
        except KeyError:
            raise HTTPException(404, "no such case") from None
        except store.CaseStateError as exc:
            raise HTTPException(409, str(exc)) from None
        await app.state.audit.emit(case_id, "retry_requested", {}, actor="analyst")
        return {"case_id": case_id, "status": "queued"}

    async def _escalated_case(case_id: str) -> dict:
        case = await store.get_case(app.state.pool, case_id)
        if case is None:
            raise HTTPException(404, "no such case")
        if case["status"] != "escalated":
            raise HTTPException(409, "a SAR draft is available once an escalation is confirmed")
        return case

    @app.get("/cases/{case_id}/sar")
    async def get_sar(case_id: str) -> dict:
        out = await store.latest_sar(app.state.pool, case_id)
        return {**out, "ai_limit": sar.MAX_AI_DRAFTS, "sections": list(sar.SECTIONS)}

    @app.post("/cases/{case_id}/sar/draft")
    async def draft_sar(case_id: str) -> dict:
        """The AI drafts the narrative from code-built facts (one model call, no tools)."""
        case = await _escalated_case(case_id)
        current = await store.latest_sar(app.state.pool, case_id)
        if current["ai_drafts"] >= sar.MAX_AI_DRAFTS:
            raise HTTPException(429, f"AI draft limit reached ({sar.MAX_AI_DRAFTS} per case)")
        if getattr(app.state, "copilot_provider", None) is None:
            app.state.copilot_provider = get_provider()
        try:
            out = await sar.draft(app.state.copilot_provider, case)
        except ValueError as exc:
            raise HTTPException(502, f"the model gave no valid draft: {exc}") from None
        try:
            saved = await store.add_sar_version(
                app.state.pool, case_id, {**out, "source": "ai", "author": "AI drafter"}
            )
        except store.CaseStateError as exc:
            raise HTTPException(409, str(exc)) from None
        await app.state.audit.emit(
            case_id,
            "sar_drafted",
            {"version_no": saved["version_no"], "warnings": out["warnings"], "model": out["model"]},
            actor="ai",
        )
        return saved

    @app.put("/cases/{case_id}/sar")
    async def edit_sar(case_id: str, body: SarEdit) -> dict:
        """The analyst's reviewed narrative, saved as a new version and checked again."""
        await _escalated_case(case_id)
        current = (await store.latest_sar(app.state.pool, case_id))["sar"]
        if current is None:
            raise HTTPException(409, "draft the report first")
        sections = body.sections.model_dump()
        version = {
            "sections": sections,
            "facts": current["facts"],
            "warnings": sar.check(sections, current["facts"]),
            "source": "analyst",
            "author": body.author,
            "role": body.role,
        }
        try:
            saved = await store.add_sar_version(app.state.pool, case_id, version)
        except store.CaseStateError as exc:
            raise HTTPException(409, str(exc)) from None
        await app.state.audit.emit(
            case_id,
            "sar_edited",
            {"version_no": saved["version_no"], "warnings": saved["warnings"]},
            actor=body.author,
        )
        return saved

    @app.post("/cases/{case_id}/sar/approve")
    async def approve_sar(case_id: str, body: SarApproval) -> dict:
        try:
            saved = await store.approve_sar(app.state.pool, case_id, body.reviewer, body.role)
        except KeyError:
            raise HTTPException(404, "no report to approve") from None
        except store.CaseStateError as exc:
            raise HTTPException(409, str(exc)) from None
        await app.state.audit.emit(
            case_id, "sar_approved", {"version_no": saved["version_no"]}, actor=body.reviewer
        )
        return saved

    @app.get("/cases/{case_id}/sar/export")
    async def export_sar(case_id: str) -> PlainTextResponse:
        current = (await store.latest_sar(app.state.pool, case_id))["sar"]
        if current is None:
            raise HTTPException(404, "no report")
        return PlainTextResponse(
            sar.markdown(current),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="SAR-{case_id}.md"'},
        )

    @app.get("/cases/{case_id}/copilot")
    async def copilot_history(case_id: str) -> dict:
        answers = await store.copilot_history(app.state.pool, case_id)
        return {"answers": answers, "used": len(answers), "limit": copilot.MAX_QUESTIONS}

    @app.post("/cases/{case_id}/copilot")
    async def ask_copilot(case_id: str, body: Question) -> StreamingResponse:
        """Answer an analyst's question about the case, streamed as server-sent events:
        one event per data lookup, then the answer. The copilot cannot change a case."""
        case = await store.get_case(app.state.pool, case_id)
        if case is None:
            raise HTTPException(404, "no such case")
        if not (case.get("analysis") or {}).get("case_file"):
            raise HTTPException(409, "the copilot is available once the case file is ready")
        history = await store.copilot_history(app.state.pool, case_id)
        if len(history) >= copilot.MAX_QUESTIONS:
            raise HTTPException(429, f"question limit reached ({copilot.MAX_QUESTIONS} per case)")
        if getattr(app.state, "copilot_provider", None) is None:
            app.state.copilot_provider = get_provider()

        async def events():
            try:
                async with connect_graph() as client:
                    async for event in copilot.ask(
                        app.state.copilot_provider,
                        client,
                        case,
                        body.question,
                        history,
                        app.state.audit,
                    ):
                        if event["type"] == "answer":
                            event["id"] = await store.save_copilot_answer(
                                app.state.pool, case_id, event
                            )
                        yield f"data: {json.dumps(event, default=str)}\n\n"
            except Exception as exc:  # report, do not drop the stream silently
                log.exception("copilot failed for %s", case_id)
                error = {"type": "error", "message": f"The copilot failed: {type(exc).__name__}"}
                yield f"data: {json.dumps(error)}\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/cases/{case_id}/audit")
    async def audit_events(case_id: str) -> dict:
        events = await app.state.audit.events(case_id)
        if not events:
            raise HTTPException(404, "no audit events for this case")
        return {"case_id": case_id, "chain_valid": verify_chain(events), "events": events}

    @app.get("/cases/{case_id}/timeline")
    async def case_timeline(case_id: str) -> dict:
        events = await app.state.audit.events(case_id)
        if not events:
            raise HTTPException(404, "no audit events for this case")
        return {"case_id": case_id, "chain_valid": verify_chain(events), "lines": timeline(events)}

    return app


app = create_app()
