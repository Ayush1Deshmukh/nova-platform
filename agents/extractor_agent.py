import os
import base64
import time
from typing import List

from agents.base_agent import BaseAgent
from storage.models import ExtractionResult, ExtractedField, confidence_level, generate_id
from config.prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_PROMPT


class ExtractorAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="ExtractorAgent")
        self.model = os.getenv("EXTRACTION_MODEL", "gemini-2.5-flash")

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def _process_pdf(self, pdf_path: str, max_pages: int = 3) -> List[str]:
        try:
            import fitz
        except ImportError:
            self.logger.error("PyMuPDF (fitz) is not installed. Run: pip install PyMuPDF")
            raise

        doc = fitz.open(pdf_path)
        base64_images = []
        num_pages = min(len(doc), max_pages)

        for page_num in range(num_pages):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_bytes = pix.tobytes("jpeg")
            b64_str = base64.b64encode(img_bytes).decode("utf-8")
            base64_images.append(b64_str)

        doc.close()
        return base64_images

    def run(self, file_path: str) -> ExtractionResult:
        start_time = time.time()
        self.logger.info(f"Starting extraction for file: {file_path}")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = file_path.lower().rsplit('.', 1)[-1]

        image_data_list = []
        if ext == 'pdf':
            image_data_list = self._process_pdf(file_path, max_pages=3)
        elif ext in ['jpg', 'jpeg', 'png', 'tiff', 'bmp']:
            image_data_list = [self._encode_image(file_path)]
        else:
            raise ValueError(f"Unsupported file extension: {ext}")

        if not image_data_list:
            raise ValueError("No images extracted from document")

        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": EXTRACTION_USER_PROMPT}
        ]

        try:
            response_data = self.call_vision_llm(messages, image_data_list, model=self.model)
        except Exception as e:
            self.logger.error(f"Vision LLM extraction failed: {str(e)}")
            raise

        extracted_fields = []
        raw_fields = response_data.get("fields", [])
        for f in raw_fields:
            field_name = f.get("field_name", f.get("name", "unknown"))
            value = f.get("value")
            score = float(f.get("confidence", 0.0))
            source = f.get("source_location", f.get("bounding_box", ""))

            if value is not None:
                value = str(value).strip()
                if value.lower() in ["null", "none", "n/a", ""]:
                    value = None

            extracted_fields.append(ExtractedField(
                field_name=field_name,
                value=value,
                confidence=score,
                source_location=source if source else None
            ))

        doc_type = response_data.get("document_type", "unknown")
        total_time_ms = int((time.time() - start_time) * 1000)

        self.logger.info(f"Extraction completed in {total_time_ms}ms. Fields: {len(extracted_fields)}. Cost: ${self.total_cost:.6f}")

        return ExtractionResult(
            document_id=generate_id(),
            document_type=doc_type,
            file_name=os.path.basename(file_path),
            fields=extracted_fields,
            raw_text_preview=response_data.get("raw_text_preview", ""),
            model_used=self.model,
            processing_time_ms=total_time_ms,
            total_cost_usd=self.total_cost
        )
