import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError
from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_exception_type

from storage.models import (
    PipelineRun, PipelineStatus, ExtractionResult, ExtractedField,
    ValidationResult, FieldValidation, RoutingDecision, DecisionType,
    ValidationStatus, ShipmentRecord, ShipmentStatus
)

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_url: str = "sqlite:///nova_platform.db"):
        connect_args = {'timeout': 15} if db_url.startswith("sqlite") else {}
        self.engine = create_engine(
            db_url, 
            connect_args=connect_args,
            poolclass=NullPool
        )

    @retry(wait=wait_random_exponential(multiplier=0.5, max=5), stop=stop_after_attempt(10), retry=retry_if_exception_type(OperationalError))
    def init_db(self):
        with self.engine.begin() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL;"))
            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    document_id TEXT,
                    file_name TEXT,
                    document_type TEXT,
                    customer_id TEXT,
                    status TEXT,
                    decision TEXT,
                    overall_score REAL,
                    reasoning TEXT,
                    amendment_draft TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    error TEXT,
                    processing_time_ms INTEGER,
                    total_cost_usd REAL
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS extracted_fields (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    field_name TEXT,
                    value TEXT,
                    confidence REAL,
                    confidence_level TEXT,
                    source_location TEXT,
                    FOREIGN KEY(run_id) REFERENCES pipeline_runs(run_id)
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS validation_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    field_name TEXT,
                    status TEXT,
                    extracted_value TEXT,
                    expected_value TEXT,
                    rule_description TEXT,
                    reasoning TEXT,
                    confidence REAL,
                    FOREIGN KEY(run_id) REFERENCES pipeline_runs(run_id)
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shipments (
                    shipment_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    email_subject TEXT,
                    email_from TEXT,
                    status TEXT,
                    decision TEXT,
                    amendment_draft TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    document_count INTEGER
                )
            """))
        logger.info("Database initialized successfully")

    @retry(wait=wait_random_exponential(multiplier=0.5, max=5), stop=stop_after_attempt(10), retry=retry_if_exception_type(OperationalError))
    def save_pipeline_run(self, run: PipelineRun):
        with self.engine.begin() as conn:
            decision_str = None
            reasoning = None
            amendment_draft = None
            overall_score = None

            if run.routing_decision:
                decision_str = run.routing_decision.decision.value
                reasoning = run.routing_decision.reasoning
                amendment_draft = run.routing_decision.amendment_draft

            if run.validation_result:
                overall_score = run.validation_result.overall_score

            conn.execute(text("""
                INSERT OR REPLACE INTO pipeline_runs
                (run_id, document_id, file_name, document_type, customer_id, status, decision,
                 overall_score, reasoning, amendment_draft, created_at, updated_at, error,
                 processing_time_ms, total_cost_usd)
                VALUES (:run_id, :document_id, :file_name, :document_type, :customer_id, :status,
                        :decision, :overall_score, :reasoning, :amendment_draft, :created_at,
                        :updated_at, :error, :processing_time_ms, :total_cost_usd)
            """), {
                "run_id": run.run_id,
                "document_id": run.document_id,
                "file_name": run.file_name,
                "document_type": run.document_type,
                "customer_id": run.customer_id,
                "status": run.status.value,
                "decision": decision_str,
                "overall_score": overall_score,
                "reasoning": reasoning,
                "amendment_draft": amendment_draft,
                "created_at": run.created_at.isoformat(),
                "updated_at": run.updated_at.isoformat(),
                "error": run.error,
                "processing_time_ms": run.processing_time_ms,
                "total_cost_usd": run.total_cost_usd
            })

            conn.execute(text("DELETE FROM extracted_fields WHERE run_id = :run_id"), {"run_id": run.run_id})
            conn.execute(text("DELETE FROM validation_results WHERE run_id = :run_id"), {"run_id": run.run_id})

            if run.extraction_result and run.extraction_result.fields:
                for field in run.extraction_result.fields:
                    conn.execute(text("""
                        INSERT INTO extracted_fields
                        (run_id, field_name, value, confidence, confidence_level, source_location)
                        VALUES (:run_id, :field_name, :value, :confidence, :confidence_level, :source_location)
                    """), {
                        "run_id": run.run_id,
                        "field_name": field.field_name,
                        "value": str(field.value) if field.value is not None else None,
                        "confidence": field.confidence,
                        "confidence_level": field.confidence_level.value if field.confidence_level else None,
                        "source_location": field.source_location
                    })

            if run.validation_result and run.validation_result.validations:
                for v in run.validation_result.validations:
                    conn.execute(text("""
                        INSERT INTO validation_results
                        (run_id, field_name, status, extracted_value, expected_value,
                         rule_description, reasoning, confidence)
                        VALUES (:run_id, :field_name, :status, :extracted_value, :expected_value,
                                :rule_description, :reasoning, :confidence)
                    """), {
                        "run_id": run.run_id,
                        "field_name": v.field_name,
                        "status": v.status.value,
                        "extracted_value": str(v.extracted_value) if v.extracted_value else None,
                        "expected_value": str(v.expected_value) if v.expected_value else None,
                        "rule_description": v.rule_description,
                        "reasoning": v.reasoning,
                        "confidence": v.confidence
                    })

    @retry(wait=wait_random_exponential(multiplier=0.5, max=5), stop=stop_after_attempt(10), retry=retry_if_exception_type(OperationalError))
    def save_shipment(self, shipment: ShipmentRecord):
        with self.engine.begin() as conn:
            decision_str = shipment.decision.value if shipment.decision else None

            conn.execute(text("""
                INSERT OR REPLACE INTO shipments
                (shipment_id, customer_id, email_subject, email_from, status, decision,
                 amendment_draft, created_at, updated_at, document_count)
                VALUES (:shipment_id, :customer_id, :email_subject, :email_from, :status,
                        :decision, :amendment_draft, :created_at, :updated_at, :document_count)
            """), {
                "shipment_id": shipment.shipment_id,
                "customer_id": shipment.customer_id,
                "email_subject": shipment.email_subject,
                "email_from": shipment.email_from,
                "status": shipment.status.value,
                "decision": decision_str,
                "amendment_draft": shipment.amendment_draft,
                "created_at": shipment.created_at.isoformat(),
                "updated_at": shipment.updated_at.isoformat(),
                "document_count": shipment.document_count
            })

        # Process pipeline runs outside the main shipment transaction to avoid SQLite deadlock
        if shipment.documents:
            for run in shipment.documents:
                self.save_pipeline_run(run)

    def get_pipeline_run(self, run_id: str) -> Optional[Dict]:
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM pipeline_runs WHERE run_id = :run_id"),
                {"run_id": run_id}
            ).mappings().first()
            if not result:
                return None
            run_dict = dict(result)
            fields = conn.execute(
                text("SELECT * FROM extracted_fields WHERE run_id = :run_id"),
                {"run_id": run_id}
            ).mappings().all()
            run_dict["extracted_fields"] = [dict(f) for f in fields]
            validations = conn.execute(
                text("SELECT * FROM validation_results WHERE run_id = :run_id"),
                {"run_id": run_id}
            ).mappings().all()
            run_dict["validations"] = [dict(v) for v in validations]
            return run_dict

    def get_all_runs(self) -> List[Dict]:
        with self.engine.connect() as conn:
            results = conn.execute(text("SELECT * FROM pipeline_runs ORDER BY created_at DESC")).mappings().all()
            return [dict(r) for r in results]

    def get_runs_by_status(self, status: str) -> List[Dict]:
        with self.engine.connect() as conn:
            results = conn.execute(
                text("SELECT * FROM pipeline_runs WHERE status = :status ORDER BY created_at DESC"),
                {"status": status}
            ).mappings().all()
            return [dict(r) for r in results]

    def get_runs_by_customer(self, customer_id: str) -> List[Dict]:
        with self.engine.connect() as conn:
            results = conn.execute(
                text("SELECT * FROM pipeline_runs WHERE customer_id = :customer_id ORDER BY created_at DESC"),
                {"customer_id": customer_id}
            ).mappings().all()
            return [dict(r) for r in results]

    def get_shipments(self) -> List[Dict]:
        with self.engine.connect() as conn:
            results = conn.execute(text("SELECT * FROM shipments ORDER BY created_at DESC")).mappings().all()
            return [dict(r) for r in results]

    def get_shipment(self, shipment_id: str) -> Optional[Dict]:
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT * FROM shipments WHERE shipment_id = :shipment_id"),
                {"shipment_id": shipment_id}
            ).mappings().first()
            return dict(result) if result else None

    def execute_query(self, sql: str) -> List[Dict]:
        sql_stripped = sql.strip()
        if not sql_stripped.upper().startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed")
        with self.engine.connect() as conn:
            results = conn.execute(text(sql_stripped)).mappings().all()
            return [dict(r) for r in results]

    @retry(wait=wait_random_exponential(multiplier=0.5, max=5), stop=stop_after_attempt(10), retry=retry_if_exception_type(OperationalError))
    def update_run_status(self, run_id: str, status: PipelineStatus):
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE pipeline_runs SET status = :status, updated_at = :updated_at WHERE run_id = :run_id"),
                {"status": status.value, "updated_at": datetime.utcnow().isoformat(), "run_id": run_id}
            )


def init_db(db_url: str = "sqlite:///nova_platform.db") -> Database:
    db = Database(db_url)
    db.init_db()
    return db
