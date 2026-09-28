import os
import re
import logging
import json
import difflib
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types

from storage.models import ExtractionResult, CrossValidationResult, CrossValidation, generate_id
from config.prompts import CROSS_VALIDATION_PROMPT

load_dotenv()
logger = logging.getLogger(__name__)


class CrossValidator:
    def __init__(self):
        self._client = None
        self.model = os.getenv("VALIDATION_MODEL", "gemini-3.8-flash")

    @property
    def client(self):
        if self._client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                self._client = genai.Client(api_key=api_key)
        return self._client

    def validate(self, extractions: List[ExtractionResult], cross_rules: Dict[str, Any]) -> CrossValidationResult:
        cross_validations = []
        overall_consistent = True

        for rule_name, rule_def in cross_rules.items():
            try:
                fields_to_check = rule_def.get("fields", [])
                doc_types = rule_def.get("across", [])
                tolerance = rule_def.get("tolerance_percent")

                for field_name in fields_to_check:
                    values_found = {}
                    for ext in extractions:
                        doc_type = ext.document_type or "unknown"
                        if doc_types and doc_type not in doc_types:
                            for dt in doc_types:
                                if dt.replace("_", "") in doc_type.replace("_", "").replace(" ", "").lower():
                                    doc_type = dt
                                    break

                        field_val = ext.get_field_value(field_name)
                        if field_val is not None:
                            values_found[doc_type] = field_val

                    if len(values_found) < 2:
                        cross_validations.append(CrossValidation(
                            rule_name=rule_name,
                            field_name=field_name,
                            status="consistent",
                            values_found=values_found,
                            reasoning=f"Field '{field_name}' found in fewer than 2 documents. Skipping cross-check."
                        ))
                        continue

                    # Fallback to LLM if it's too complex or specifically requested
                    comparison_type = rule_def.get("type", "exact")
                    if comparison_type == "llm" and self.client:
                        is_consistent, reasoning = self._llm_compare(rule_def, values_found)
                    else:
                        is_consistent, reasoning = self._check_consistency(
                            field_name, values_found, tolerance, rule_def.get("description", "")
                        )

                    if not is_consistent:
                        overall_consistent = False

                    cross_validations.append(CrossValidation(
                        rule_name=rule_name,
                        field_name=field_name,
                        status="consistent" if is_consistent else "inconsistent",
                        values_found=values_found,
                        reasoning=reasoning
                    ))

            except Exception as e:
                logger.error(f"Error in cross-validation rule {rule_name}: {e}")
                cross_validations.append(CrossValidation(
                    rule_name=rule_name,
                    field_name=str(rule_def.get("fields", ["unknown"])),
                    status="inconsistent",
                    values_found={},
                    reasoning=f"Error: {str(e)}"
                ))
                overall_consistent = False

        summary_parts = []
        consistent_count = sum(1 for cv in cross_validations if cv.status == "consistent")
        total_count = len(cross_validations)
        summary_parts.append(f"{consistent_count}/{total_count} cross-document checks passed.")
        if not overall_consistent:
            inconsistent = [cv for cv in cross_validations if cv.status == "inconsistent"]
            for cv in inconsistent:
                summary_parts.append(f"  - {cv.field_name}: {cv.reasoning}")

        return CrossValidationResult(
            shipment_id="",
            cross_validations=cross_validations,
            overall_consistent=overall_consistent,
            summary=" ".join(summary_parts)
        )

    def _llm_compare(self, rule_def: Dict[str, Any], values_found: Dict[str, Any]) -> tuple:
        prompt = CROSS_VALIDATION_PROMPT.format(
            rule=json.dumps(rule_def),
            values=json.dumps(values_found, default=str)
        )
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are a validation assistant. Output ONLY valid JSON.",
                    temperature=0.0,
                    response_mime_type="application/json"
                )
            )
            parsed = json.loads(response.text)
            return parsed.get("is_consistent", False), parsed.get("reasoning", "No reasoning provided.")
        except Exception as e:
            logger.error(f"LLM comparison failed: {e}")
            return False, f"Error evaluating rule: {e}"

    def _check_consistency(
        self, field_name: str, values_found: Dict[str, Optional[str]],
        tolerance: Optional[float], description: str
    ) -> tuple:
        values = list(values_found.values())
        docs = list(values_found.keys())

        if tolerance is not None:
            try:
                numeric_vals = [float(re.sub(r'[^\d.\-]', '', str(v))) for v in values]
                max_val = max(numeric_vals)
                min_val = min(numeric_vals)
                if max_val == 0:
                    diff_pct = 0.0
                else:
                    diff_pct = ((max_val - min_val) / max_val) * 100

                if diff_pct <= tolerance:
                    return True, f"Numeric values match within {tolerance}% tolerance (diff: {diff_pct:.1f}%)."
                else:
                    return False, (
                        f"Numeric mismatch: values differ by {diff_pct:.1f}% (tolerance: {tolerance}%). "
                        f"Values: {dict(zip(docs, numeric_vals))}"
                    )
            except (ValueError, TypeError):
                pass

        first = str(values[0]).strip().lower()
        all_match = all(str(v).strip().lower() == first for v in values)

        if all_match:
            return True, f"All values match: '{values[0]}'"

        ratios = []
        for i, v in enumerate(values):
            ratio = difflib.SequenceMatcher(None, first, str(v).strip().lower()).ratio()
            ratios.append(ratio)

        if all(r >= 0.90):
            return True, f"Values are similar (fuzzy match >= 0.90). Values: {dict(zip(docs, values))}"

        return False, (
            f"Values do not match across documents. "
            f"Found: {dict(zip(docs, values))}"
        )
