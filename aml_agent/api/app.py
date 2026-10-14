"""Cases and review API.

There is deliberately no endpoint that finalizes a case: only the worker
finalizes, and only after a decision recorded here.

    uvicorn aml_agent.api.app:app
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, model_validator

from aml_agent import store
from aml_agent.alerts.io import read_alerts
from aml_agent.alerts.models import Alert
from aml_agent.schemas.case import Decision


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
        case_id = await store.create_case(app.state.pool, alert.model_dump(mode="json"))
        return {"case_id": case_id, "status": "queued"}

    @app.get("/cases")
    async def list_cases(status: str | None = None) -> list[dict]:
        return await store.list_cases(app.state.pool, status)

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
        return {"case_id": case_id, "status": "decision_recorded"}

    return app


app = create_app()
