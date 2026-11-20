"""
A tiny STAND-IN for the real Ingest API, so you can test the replay generator before the backend exists.
It follows SRS 3.2.1: validates the schema, answers HTTP 202 {transactionId, ingestSeq}, returns 400 with
the failing fields, and treats a repeated transactionId as an idempotent retry (same answer, no duplicate).

Run:   python -m uvicorn mock_ingest_api:app --port 8080
Env:   MOCK_LATENCY_MS=5   add artificial latency      MOCK_FAIL_RATE=0.02   random 503s
       MOCK_STRICT=1       reject unknown fields (shows what happens if the schema is not extended)
GET /stats shows how many unique transactions were accepted.
"""
import asyncio, os, random, re, uuid
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

LATENCY = float(os.environ.get("MOCK_LATENCY_MS", "0")) / 1000
FAIL_RATE = float(os.environ.get("MOCK_FAIL_RATE", "0"))
STRICT = os.environ.get("MOCK_STRICT") == "1"
CHANNELS = {"CARD_PRESENT", "CARD_NOT_PRESENT", "ONLINE", "MOBILE", "ATM"}

app = FastAPI(title="Mock FraudGuard Ingest API")
SEEN = {}          # transactionId -> original response (idempotency)
SEQ = [0]


class Txn(BaseModel):
    model_config = ConfigDict(extra="forbid" if STRICT else "allow")
    transactionId: str
    timestamp: str
    customerId: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    merchantId: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    amount: int = Field(gt=0, le=10_000_000)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    merchantCategory: str = Field(pattern=r"^\d{4}$")
    channel: str
    deviceId: Optional[str] = Field(default=None, max_length=128)

    @field_validator("transactionId")
    @classmethod
    def v4(cls, v):
        if uuid.UUID(v).version != 4:
            raise ValueError("must be a UUID v4")
        return v

    @field_validator("channel")
    @classmethod
    def chan(cls, v):
        if v not in CHANNELS:
            raise ValueError(f"must be one of {sorted(CHANNELS)}")
        return v


@app.exception_handler(RequestValidationError)
async def bad_request(_: Request, exc: RequestValidationError):
    errs = [{"field": ".".join(str(x) for x in e["loc"] if x != "body"), "reason": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=400, content={"errors": errs})


@app.post("/api/transactions", status_code=202)
async def submit(txn: Txn):
    if LATENCY:
        await asyncio.sleep(LATENCY)
    if FAIL_RATE and random.random() < FAIL_RATE:
        return JSONResponse(status_code=503, content={"error": "temporarily unavailable"})
    if txn.transactionId in SEEN:                       # idempotent retry: same answer, nothing new
        return SEEN[txn.transactionId]
    SEQ[0] += 1
    resp = {"transactionId": txn.transactionId, "ingestSeq": SEQ[0]}
    SEEN[txn.transactionId] = resp
    return resp


@app.get("/stats")
def stats():
    return {"uniqueAccepted": len(SEEN), "lastIngestSeq": SEQ[0]}