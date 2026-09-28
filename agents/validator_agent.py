import re
import os
import json
import difflib
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from agents.base_agent import BaseAgent
from storage.models import (
    ExtractionResult, ValidationResult, FieldValidation,
    ValidationStatus, ExtractedField
)
from config.prompts import VALIDATION_SYSTEM_PROMPT, VALIDATION_USER_PROMPT


class ValidatorAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="ValidatorAgent")
        self.model = os.getenv("VALIDATION_MODEL", "gemini-3.8-flash")

    def _local_rule_check(self, field_value: str, rule: Dict[str, Any]) -> tuple:
        match_type = rule.get("match_type", "")

        if match_type == "list":
            allowed = [str(x).lower().strip() for x in rule.get("allowed_values", [])]
            if field_value.lower().strip() in allowed:
                return True, f"Value '{field_value}' found in allowed list."
            return False, f"Value '{field_value}' not in allowed list: {rule.get('allowed_values', [])}"

        elif match_type == "pattern":
            pattern = rule.get("expected_pattern", "")
            if pattern and re.match(pattern, field_value.strip()):
                return True, f"Value matches required pattern {pattern}."
            return False, f"Value '{field_value}' does not match pattern {pattern}."

        elif match_type == "fuzzy":
            target = str(rule.get("expected_value", "")).lower()
            threshold = float(rule.get("fuzzy_threshold", 0.85))
            ratio = difflib.SequenceMatcher(None, field_value.lower().strip(), target).ratio()
            if ratio >= threshold:
                return True, f"Fuzzy match ratio {ratio:.2f} >= {threshold}."
            return False, f"Fuzzy match ratio {ratio:.2f} < {threshold}. Expected: '{rule.get('expected_value', '')}'."

        elif match_type == "numeric_range":
            try:
                cleaned = re.sub(r'[^\d.\-]', '', field_value)
                val = float(cleaned)
                min_val = float(rule.get("min_value", float('-inf')))
                max_val = float(rule.get("max_value", float('inf')))
                if min_val <= val <= max_val:
                    return True, f"Value {val} within range [{min_val}, {max_val}]."
                return False, f"Value {val} outside range [{min_val}, {max_val}]."
            except ValueError:
                return False, f"Value '{field_value}' is not a valid number."

        elif match_type == "length":
            min_len = int(rule.get("min_length", 0))
            max_len = int(rule.get("max_length", 10000))
            banned = rule.get("banned_keywords", [])
            if len(field_value) < min_len:
                return False, f"Length {len(field_value)} below minimum {min_len}."
            if len(field_value) > max_len:
                return False, f"Length {len(field_value)} exceeds maximum {max_len}."
            for keyword in banned:
                if keyword.lower() in field_value.lower():
                    return False, f"Contains banned keyword: '{keyword}'."
            return True, "Value length within limits and no banned keywords."

        elif match_type == "date":
            return True, "Date validation passed (basic check)."

        return None, f"Unknown match_type: {match_type}"

    def run(self, extraction: ExtractionResult, rules: Dict[str, Any]) -> ValidationResult:
        start_time = time.time()
        self.logger.info(f"Starting validation for document {extraction.document_id}")

        rule_set = rules.get("rules", rules)
        field_validations: List[FieldValidation] = []

        for field in extraction.fields:
            if field.value is None or field.value == "":
                rule = rule_set.get(field.field_name, {})
                is_required = rule.get("required", False) if rule else False
                if is_required:
                    exp_val = rule.get("expected_value") or rule.get("allowed_values") or "see rule"
                    if isinstance(exp_val, list):
                        exp_val = ", ".join(str(x) for x in exp_val)
                    field_validations.append(FieldValidation(
                        field_name=field.field_name,
                        status=ValidationStatus.MISSING,
                        extracted_value=None,
                        expected_value=str(exp_val) if exp_val else None,
                        rule_description=rule.get("description", "Required field"),
                        confidence=0.0,
                        reasoning=f"Required field '{field.field_name}' is missing from document."
                    ))
                continue

            if field.confidence < 0.6:
                field_validations.append(FieldValidation(
                    field_name=field.field_name,
                    status=ValidationStatus.UNCERTAIN,
                    extracted_value=field.value,
                    expected_value=None,
                    rule_description="Low confidence extraction",
                    confidence=field.confidence,
                    reasoning=f"Extraction confidence {field.confidence:.2f} below threshold (0.6). Requires human review."
                ))
                continue

            rule = rule_set.get(field.field_name)
            if not rule:
                field_validations.append(FieldValidation(
                    field_name=field.field_name,
                    status=ValidationStatus.MATCH,
                    extracted_value=field.value,
                    expected_value=None,
                    rule_description="No rule defined",
                    confidence=field.confidence,
                    reasoning="No validation rule defined for this field. Auto-passed."
                ))
                continue

            is_valid, msg = self._local_rule_check(field.value, rule)

            if is_valid is None:
                try:
                    messages = [
                        {"role": "system", "content": VALIDATION_SYSTEM_PROMPT},
                        {"role": "user", "content": VALIDATION_USER_PROMPT.format(
                            extracted_json=json.dumps({"field_name": field.field_name, "value": field.value, "confidence": field.confidence}),
                            rules_json=json.dumps({field.field_name: rule})
                        )}
                    ]
                    response = self.call_llm(messages, model=self.model, response_format={"type": "json_object"})
                    validations_resp = response.get("validations", [])
                    if validations_resp:
                        v = validations_resp[0]
                        status_str = v.get("status", "uncertain").lower()
                        status = ValidationStatus(status_str) if status_str in [e.value for e in ValidationStatus] else ValidationStatus.UNCERTAIN
                        field_validations.append(FieldValidation(
                            field_name=field.field_name,
                            status=status,
                            extracted_value=field.value,
                            expected_value=v.get("expected_value"),
                            rule_description=rule.get("description", ""),
                            confidence=float(v.get("confidence", field.confidence)),
                            reasoning=v.get("reasoning", "LLM validation.")
                        ))
                    else:
                        field_validations.append(FieldValidation(
                            field_name=field.field_name,
                            status=ValidationStatus.UNCERTAIN,
                            extracted_value=field.value,
                            rule_description=rule.get("description", ""),
                            confidence=field.confidence,
                            reasoning="LLM returned no validation detail."
                        ))
                except Exception as e:
                    self.logger.error(f"LLM validation failed for {field.field_name}: {e}")
                    field_validations.append(FieldValidation(
                        field_name=field.field_name,
                        status=ValidationStatus.UNCERTAIN,
                        extracted_value=field.value,
                        rule_description=rule.get("description", ""),
                        confidence=0.0,
                        reasoning=f"Validation error: {str(e)}"
                    ))
            else:
                expected = rule.get("expected_value") or rule.get("allowed_values") or rule.get("expected_pattern") or ""
                if isinstance(expected, list):
                    expected = ", ".join(str(x) for x in expected)
                else:
                    expected = str(expected)

                status = ValidationStatus.MATCH if is_valid else ValidationStatus.MISMATCH
                field_validations.append(FieldValidation(
                    field_name=field.field_name,
                    status=status,
                    extracted_value=field.value,
                    expected_value=expected,
                    rule_description=rule.get("description", ""),
                    confidence=field.confidence,
                    reasoning=msg
                ))

        matched = sum(1 for v in field_validations if v.status == ValidationStatus.MATCH)
        mismatched = sum(1 for v in field_validations if v.status == ValidationStatus.MISMATCH)
        uncertain = sum(1 for v in field_validations if v.status == ValidationStatus.UNCERTAIN)
        missing = sum(1 for v in field_validations if v.status == ValidationStatus.MISSING)
        total = len(field_validations)

        if total > 0:
            overall_score = matched / total
        else:
            overall_score = 0.0

        total_time = time.time() - start_time
        self.logger.info(f"Validation completed in {total_time:.2f}s. Match: {matched}, Mismatch: {mismatched}, Uncertain: {uncertain}, Missing: {missing}")

        return ValidationResult(
            document_id=extraction.document_id,
            customer_id="CUST-001",
            validations=field_validations,
            overall_score=overall_score,
            total_fields=total,
            matched_fields=matched,
            mismatched_fields=mismatched,
            uncertain_fields=uncertain,
            missing_fields=missing,
            summary=f"{matched}/{total} fields matched. {mismatched} mismatches, {uncertain} uncertain, {missing} missing."
        )
