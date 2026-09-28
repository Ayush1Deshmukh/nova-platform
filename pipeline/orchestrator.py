import os
import json
import logging
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from storage.models import (
    PipelineRun, PipelineStatus, ShipmentRecord, ShipmentStatus,
    DecisionType, generate_id
)
from storage.database import Database
from pipeline.state_manager import StateManager
from agents.extractor_agent import ExtractorAgent
from agents.validator_agent import ValidatorAgent
from agents.router_agent import RouterAgent
from pipeline.cross_validator import CrossValidator

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(self, customer_rules_path: str = None, db: Database = None):
        if customer_rules_path is None:
            customer_rules_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "config", "customer_rules.json"
            )
        self.customer_rules_path = customer_rules_path

        if db is None:
            db = Database()
            db.init_db()
        self.db = db
        self.state_manager = StateManager()

        self.extractor = ExtractorAgent()
        self.validator = ValidatorAgent()
        self.router = RouterAgent()
        self.cross_validator = CrossValidator()

        self.customer_rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        try:
            with open(self.customer_rules_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading customer rules from {self.customer_rules_path}: {e}")
            return {}

    def process_document(self, file_path: str, customer_id: str = "CUST-001") -> PipelineRun:
        start_time = time.time()
        run = PipelineRun(
            run_id=generate_id(),
            document_id=generate_id(),
            file_name=os.path.basename(file_path),
            customer_id=customer_id,
            status=PipelineStatus.PENDING
        )

        try:
            self.state_manager.save_checkpoint(run)

            # Step 1: Extract
            run.status = PipelineStatus.EXTRACTING
            run.updated_at = datetime.utcnow()
            self.state_manager.save_checkpoint(run)
            logger.info(f"[{run.run_id}] Extracting from {file_path}")

            extraction_result = self.extractor.run(file_path)
            run.extraction_result = extraction_result
            run.document_type = extraction_result.document_type

            # Step 2: Validate
            run.status = PipelineStatus.VALIDATING
            run.updated_at = datetime.utcnow()
            self.state_manager.save_checkpoint(run)
            logger.info(f"[{run.run_id}] Validating extracted fields")

            validation_result = self.validator.run(extraction_result, self.customer_rules)
            run.validation_result = validation_result

            # Step 3: Route
            run.status = PipelineStatus.ROUTING
            run.updated_at = datetime.utcnow()
            self.state_manager.save_checkpoint(run)
            logger.info(f"[{run.run_id}] Making routing decision")

            routing_decision = self.router.run(validation_result)
            run.routing_decision = routing_decision

            # Complete
            run.status = PipelineStatus.COMPLETED
            run.processing_time_ms = int((time.time() - start_time) * 1000)
            run.total_cost_usd = (
                self.extractor.total_cost +
                self.validator.total_cost +
                self.router.total_cost
            )
            run.updated_at = datetime.utcnow()

            self.db.save_pipeline_run(run)
            self.state_manager.delete_checkpoint(run.run_id)

            logger.info(
                f"[{run.run_id}] Pipeline completed. Decision: {routing_decision.decision.value}. "
                f"Time: {run.processing_time_ms}ms. Cost: ${run.total_cost_usd:.4f}"
            )
            return run

        except Exception as e:
            logger.error(f"[{run.run_id}] Pipeline failed for {file_path}: {e}")
            run.status = PipelineStatus.FAILED
            run.error = str(e)
            run.processing_time_ms = int((time.time() - start_time) * 1000)
            run.updated_at = datetime.utcnow()
            self.state_manager.save_checkpoint(run)
            self.db.save_pipeline_run(run)
            raise

    def process_shipment(self, email_dir: str, customer_id: str = "CUST-001") -> ShipmentRecord:
        shipment = ShipmentRecord(
            shipment_id=generate_id(),
            customer_id=customer_id,
            status=ShipmentStatus.PROCESSING
        )

        try:
            metadata_path = os.path.join(email_dir, "metadata.json")
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    shipment.email_subject = meta.get("subject", "")
                    shipment.email_from = meta.get("from", "")
                    customer_id = meta.get("customer_id", customer_id)
                    shipment.customer_id = customer_id

            doc_files = []
            for filename in sorted(os.listdir(email_dir)):
                if filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff')):
                    doc_files.append(os.path.join(email_dir, filename))

            if not doc_files:
                logger.warning(f"No document files found in {email_dir}")
                shipment.status = ShipmentStatus.FAILED
                self.db.save_shipment(shipment)
                return shipment

            logger.info(f"[{shipment.shipment_id}] Processing {len(doc_files)} documents from {email_dir}")

            pipeline_runs = []
            for file_path in doc_files:
                try:
                    run = self.process_document(file_path, customer_id)
                    pipeline_runs.append(run)
                except Exception as e:
                    logger.error(f"[{shipment.shipment_id}] Failed to process {file_path}: {e}")

            shipment.documents = pipeline_runs
            shipment.document_count = len(pipeline_runs)

            # Cross-document validation
            cross_rules = self.customer_rules.get("cross_document_rules", {})
            if cross_rules and len(pipeline_runs) > 1:
                extractions = [
                    run.extraction_result for run in pipeline_runs
                    if run.extraction_result is not None
                ]
                if len(extractions) > 1:
                    logger.info(f"[{shipment.shipment_id}] Running cross-document validation")
                    cross_result = self.cross_validator.validate(extractions, cross_rules)
                    shipment.cross_validation_result = cross_result

            # Determine overall shipment decision
            has_amendment = any(
                r.routing_decision and r.routing_decision.decision == DecisionType.DRAFT_AMENDMENT
                for r in pipeline_runs
            )
            has_review = any(
                r.routing_decision and r.routing_decision.decision == DecisionType.FLAG_FOR_REVIEW
                for r in pipeline_runs
            )
            cross_inconsistent = (
                shipment.cross_validation_result is not None
                and not shipment.cross_validation_result.overall_consistent
            )

            if has_amendment or cross_inconsistent:
                shipment.status = ShipmentStatus.AMENDMENT_REQUESTED
                shipment.decision = DecisionType.DRAFT_AMENDMENT
                # Combine amendment drafts
                drafts = [
                    r.routing_decision.amendment_draft
                    for r in pipeline_runs
                    if r.routing_decision and r.routing_decision.amendment_draft
                ]
                if drafts:
                    shipment.amendment_draft = "\n\n---\n\n".join(drafts)
            elif has_review:
                shipment.status = ShipmentStatus.PENDING_REVIEW
                shipment.decision = DecisionType.FLAG_FOR_REVIEW
            else:
                shipment.status = ShipmentStatus.APPROVED
                shipment.decision = DecisionType.AUTO_APPROVE

            shipment.updated_at = datetime.utcnow()
            self.db.save_shipment(shipment)

            logger.info(
                f"[{shipment.shipment_id}] Shipment processing complete. "
                f"Status: {shipment.status.value}. Documents: {len(pipeline_runs)}"
            )
            return shipment

        except Exception as e:
            logger.error(f"[{shipment.shipment_id}] Shipment processing failed: {e}")
            shipment.status = ShipmentStatus.FAILED
            shipment.updated_at = datetime.utcnow()
            self.db.save_shipment(shipment)
            raise

    def resume_incomplete(self) -> List[PipelineRun]:
        incomplete = self.state_manager.get_last_incomplete()
        logger.info(f"Found {len(incomplete)} incomplete runs to resume.")
        resumed = []
        for run in incomplete:
            logger.info(f"Found incomplete run {run.run_id} at status {run.status.value}")
            resumed.append(run)
        return resumed
