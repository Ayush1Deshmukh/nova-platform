import os
import time
import json
import logging
import base64
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BaseAgent(ABC):
    def __init__(self, name: str = "BaseAgent"):
        self.name = name
        self.logger = logging.getLogger(self.name)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            self.logger.warning("GEMINI_API_KEY not found. LLM calls will fail.")
        
        self.client = genai.Client(api_key=api_key or "sk-placeholder")
        self.total_cost = 0.0  # Gemini free tier
        self.total_latency = 0.0

    @abstractmethod
    def run(self, *args, **kwargs) -> Any:
        pass

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Attempt to parse JSON from the response text, ignoring markdown formatting."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
            if match:
                try:
                    return json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    pass
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end+1])
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Could not extract valid JSON from response: {text[:100]}...")

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> tuple[Optional[str], List[types.Content]]:
        """Converts OpenAI-style messages to Gemini format."""
        system_instruction = None
        contents = []
        
        for m in messages:
            if m["role"] == "system":
                system_instruction = m["content"]
            else:
                role = "user" if m["role"] == "user" else "model"
                contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))
                
        return system_instruction, contents

    @retry(
        wait=wait_exponential(multiplier=1.5, min=2, max=12),
        stop=stop_after_attempt(4),
        retry=retry_if_exception_type(Exception)
    )
    def call_llm(self, messages: List[Dict[str, Any]], model: str = "gemini-3.1-flash-lite", response_format: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        start_time = time.time()
        self.logger.info(f"Calling LLM ({model})...")
        
        try:
            sys_inst, contents = self._convert_messages(messages)
            
            config = types.GenerateContentConfig(
                system_instruction=sys_inst,
                temperature=0.0
            )
            
            wants_json = (response_format and response_format.get("type") == "json_object")
            if wants_json:
                config.response_mime_type = "application/json"

            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
            except Exception as model_err:
                err_str = str(model_err)
                if ("404" in err_str or "503" in err_str) and model != "gemini-3.1-flash-lite":
                    self.logger.warning(f"Model {model} unavailable ({err_str[:60]}). Falling back to gemini-3.1-flash-lite.")
                    response = self.client.models.generate_content(
                        model="gemini-3.1-flash-lite",
                        contents=contents,
                        config=config
                    )
                else:
                    raise

            latency = time.time() - start_time
            self.total_latency += latency
            
            self.logger.info(f"LLM call completed in {latency:.2f}s")
            
            content = response.text
            if wants_json:
                return self._extract_json(content)
            return {"content": content}
            
        except Exception as e:
            self.logger.error(f"Error calling LLM: {str(e)}")
            raise

    @retry(
        wait=wait_exponential(multiplier=1.5, min=2, max=12),
        stop=stop_after_attempt(4),
        retry=retry_if_exception_type(Exception)
    )
    def call_vision_llm(self, messages: List[Dict[str, Any]], image_data_list: List[str], model: str = "gemini-3.1-flash-lite") -> Dict[str, Any]:
        start_time = time.time()
        self.logger.info(f"Calling Vision LLM ({model}) with {len(image_data_list)} images...")
        
        try:
            sys_inst, contents = self._convert_messages(messages)
            
            parts = []
            for b64_img in image_data_list:
                img_bytes = base64.b64decode(b64_img)
                parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
                
            last_msg = contents[-1]
            for part in last_msg.parts:
                parts.append(part)
                
            contents[-1] = types.Content(role="user", parts=parts)

            config = types.GenerateContentConfig(
                system_instruction=sys_inst,
                temperature=0.0,
                response_mime_type="application/json"
            )

            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
            except Exception as model_err:
                err_str = str(model_err)
                if ("404" in err_str or "503" in err_str) and model != "gemini-3.1-flash-lite":
                    self.logger.warning(f"Model {model} unavailable ({err_str[:60]}). Falling back to gemini-3.1-flash-lite.")
                    response = self.client.models.generate_content(
                        model="gemini-3.1-flash-lite",
                        contents=contents,
                        config=config
                    )
                else:
                    raise

            latency = time.time() - start_time
            self.total_latency += latency
            
            self.logger.info(f"Vision LLM call completed in {latency:.2f}s")
            
            return self._extract_json(response.text)
            
        except Exception as e:
            self.logger.error(f"Error calling Vision LLM: {str(e)}")
            raise
