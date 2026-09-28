import os
import time
import json
from typing import Dict, Any

from agents.base_agent import BaseAgent
from storage.models import (
    ValidationResult, RoutingDecision, DecisionType,
    Discrepancy, ValidationStatus
)
from config.prompts import ROUTING_SYSTEM_PROMPT, ROUTING_USER_PROMPT


class RouterAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="RouterAgent")
        self.model = os.getenv("ROUTING_MODEL", "gemini-3.8-flash")

    def run(self, validation: ValidationResult, thresholds: Dict[str, float] = None) -> RoutingDecision:
        start_time = time.time()
        self.logger.info(f"Starting routing for document {validation.document_id}")

        if thresholds is None:
            thresholds = {}

        auto_approve_thresh = thresholds.get("auto_approve", float(os.getenv("AUTO_APPROVE_THRESHOLD", "0.95")))
        flag_review_thresh = thresholds.get("flag_review", float(os.getenv("FLAG_REVIEW_THRESHOLD", "0.70")))

        mismatches = [v for v in validation.validations if v.status == ValidationStatus.MISMATCH]
        uncertains = [v for v in validation.validations if v.status == ValidationStatus.UNCERTAIN]
        missing = [v for v in validation.validations if v.status == ValidationStatus.MISSING]

        discrepancies = []
        for m in mismatches:
            discrepancies.append(Discrepancy(
                field_name=m.field_name,
                found=m.extracted_value,
                expected=m.expected_value,
                severity="critical"
            ))
        for u in uncertains:
            discrepancies.append(Discrepancy(
                field_name=u.field_name,
                found=u.extracted_value,
                expected="Requires verification",
                severity="warning"
            ))
        for ms in missing:
            discrepancies.append(Discrepancy(
                field_name=ms.field_name,
                found="MISSING",
                expected=ms.expected_value,
                severity="critical"
            ))

        decision_type = DecisionType.FLAG_FOR_REVIEW
        reasoning = ""
        amendment_draft = None

        if (validation.overall_score >= auto_approve_thresh
                and len(mismatches) == 0
                and len(uncertains) == 0
                and len(missing) == 0):
            decision_type = DecisionType.AUTO_APPROVE
            reasoning = (
                f"All fields validated successfully. Overall score {validation.overall_score:.2f} "
                f">= {auto_approve_thresh}. Zero mismatches, uncertain, or missing fields."
            )

        elif len(mismatches) > 0 or len(missing) > 0 or validation.overall_score < flag_review_thresh:
            decision_type = DecisionType.DRAFT_AMENDMENT
            reasoning = f"Found {len(mismatches)} mismatch(es) and {len(missing)} missing field(s). Overall score: {validation.overall_score:.2f}."

            validation_summary = json.dumps({
                "overall_score": validation.overall_score,
                "mismatches": [{"field": d.field_name, "found": d.found, "expected": d.expected} for d in discrepancies if d.severity == "critical"],
                "uncertain": [{"field": d.field_name, "found": d.found} for d in discrepancies if d.severity == "warning"]
            })

            messages = [
                {"role": "system", "content": ROUTING_SYSTEM_PROMPT},
                {"role": "user", "content": ROUTING_USER_PROMPT.format(
                    validation_json=validation_summary,
                    auto_approve_threshold=auto_approve_thresh,
                    flag_review_threshold=flag_review_thresh
                )}
            ]

            try:
                response = self.call_llm(messages, model=self.model, response_format={"type": "json_object"})
                amendment_draft = response.get("amendment_draft", response.get("email_draft"))
                llm_reasoning = response.get("reasoning", "")
                if llm_reasoning:
                    reasoning += " " + llm_reasoning
            except Exception as e:
                self.logger.error(f"Failed to generate amendment email: {e}")
                disc_lines = []
                for d in discrepancies:
                    if d.severity == "critical":
                        disc_lines.append(f"- {d.field_name}: Found '{d.found}', Expected '{d.expected}'")
                amendment_draft = (
                    "Dear Supplier,\n\n"
                    "During verification, the following discrepancies were identified:\n\n"
                    + "\n".join(disc_lines) + "\n\n"
                    "Please review and resubmit corrected documents.\n\n"
                    "Best regards,\nCargo Verification Team"
                )
        else:
            decision_type = DecisionType.FLAG_FOR_REVIEW
            reasoning = (
                f"Overall score {validation.overall_score:.2f} is between {flag_review_thresh} and {auto_approve_thresh}. "
                f"{len(uncertains)} uncertain field(s) require human review."
            )

        total_time = time.time() - start_time
        self.logger.info(f"Routing completed in {total_time:.2f}s. Decision: {decision_type.value}")

        return RoutingDecision(
            document_id=validation.document_id,
            decision=decision_type,
            reasoning=reasoning.strip(),
            confidence=validation.overall_score,
            discrepancies=discrepancies,
            amendment_draft=amendment_draft
        )
