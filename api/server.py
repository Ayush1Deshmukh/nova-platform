import os
import sys
import json
import logging
import tempfile
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from storage.database import Database, init_db
from storage.query_engine import QueryEngine
from pipeline.orchestrator import PipelineOrchestrator
from pydantic import BaseModel

logger = logging.getLogger(__name__)

db: Optional[Database] = None
orchestrator: Optional[PipelineOrchestrator] = None
query_engine: Optional[QueryEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, orchestrator, query_engine
    db = init_db()
    rules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "customer_rules.json")
    orchestrator = PipelineOrchestrator(customer_rules_path=rules_path, db=db)
    query_engine = QueryEngine(db=db)
    logger.info("Nova Platform API started")
    yield
    logger.info("Nova Platform API shutting down")


app = FastAPI(
    title="Nova Platform API",
    description="GoComet Multi-Agent Trade Document Intelligence",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str


@app.get("/api/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/process")
async def process_document(
    file: UploadFile = File(...),
    customer_id: str = Form("CUST-001")
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    suffix = "." + file.filename.rsplit(".", 1)[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        run = orchestrator.process_document(tmp_path, customer_id)
        return JSONResponse(content=json.loads(run.model_dump_json()), status_code=200)
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/api/shipment")
async def process_shipment(email_dir: str = Form(...), customer_id: str = Form("CUST-001")):
    if not os.path.isdir(email_dir):
        raise HTTPException(status_code=400, detail=f"Directory not found: {email_dir}")
    try:
        shipment = orchestrator.process_shipment(email_dir, customer_id)
        return JSONResponse(content=json.loads(shipment.model_dump_json()), status_code=200)
    except Exception as e:
        logger.error(f"Shipment processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/runs")
async def list_runs():
    return db.get_all_runs()


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    run = db.get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/api/shipments")
async def list_shipments():
    return db.get_shipments()


@app.get("/api/shipments/{shipment_id}")
async def get_shipment(shipment_id: str):
    shipment = db.get_shipment(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment


@app.post("/api/query")
async def query_data(request: QueryRequest):
    result = query_engine.query(request.question)
    return result
