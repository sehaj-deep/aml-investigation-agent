"""Alert queue, cases and review API.

Alerts come from transaction monitoring (scripts/train_detection.py) and are loaded
into Postgres at startup when the table is empty (or with scripts/load_alerts.py).
Opening an alert creates its case once; the worker then runs the AI review.
There is deliberately no endpoint that finalizes a case: only the worker
finalizes, and only after a decision recorded here.

    uvicorn aml_agent.api.app:app
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, model_validator

from aml_agent import store
from aml_agent.alerts.io import read_alerts, read_queue
from aml_agent.alerts.models import Alert
from aml_agent.audit import PostgresAudit, timeline, verify_chain
from aml_agent.schemas.case import Decision

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
