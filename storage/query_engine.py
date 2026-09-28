import os
import json
import logging
import re
from typing import Dict, Any
from google import genai
from google.genai import types
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from config.prompts import QUERY_SYSTEM_PROMPT, QUERY_USER_PROMPT
from storage.database import Database

logger = logging.getLogger(__name__)

class QueryEngine:
    def __init__(self, db: Database, api_key: str = None):
        self.db = db
        api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.client = genai.Client(api_key=api_key or "sk-placeholder")
        self.model = os.getenv("QUERY_MODEL", "gemini-3.1-flash-lite")

    @retry(
        wait=wait_exponential(multiplier=1.5, min=2, max=12),
        stop=stop_after_attempt(4),
        retry=retry_if_exception_type(Exception)
    )
    def _generate_with_retry(self, contents: str, config: types.GenerateContentConfig) -> str:
        """Call Gemini with retries and automatic fallback to flash-lite on 503."""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )
            return response.text
        except Exception as e:
            err_str = str(e)
            if ("404" in err_str or "503" in err_str) and self.model != "gemini-3.1-flash-lite":
                logger.warning(f"QueryEngine model {self.model} unavailable ({err_str[:60]}). Falling back to gemini-3.1-flash-lite.")
                response = self.client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=contents,
                    config=config
                )
                return response.text
            raise

    def query(self, question: str) -> Dict[str, Any]:
        prompt = QUERY_USER_PROMPT.format(question=question)
        
        try:
            reply = self._generate_with_retry(
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=QUERY_SYSTEM_PROMPT,
                    temperature=0.0,
                    response_mime_type="application/json"
                )
            )
            
            # Extract JSON block
            json_match = re.search(r"```(?:json)?\n(.*?)\n```", reply, re.DOTALL | re.IGNORECASE)
            if json_match:
                parsed = json.loads(json_match.group(1).strip())
            else:
                parsed = json.loads(reply.strip())
                
            sql = parsed.get("sql", "")
            explanation = parsed.get("explanation", "")
            
            if not sql.strip().upper().startswith("SELECT"):
                return {
                    "sql": sql,
                    "explanation": explanation,
                    "results": [],
                    "answer": "Error: Only SELECT queries are permitted.",
                    "error": True
                }
                
            results = self.db.execute_query(sql)
            
            answer_prompt = f"Question: {question}\nSQL: {sql}\nResults: {json.dumps(results, default=str)}"
            answer = self._generate_with_retry(
                contents=answer_prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are a helpful assistant. Given a user question, a SQL query, and its results, provide a clear, concise natural language answer.",
                    temperature=0.0
                )
            )
            
            return {
                "sql": sql,
                "explanation": explanation,
                "results": results,
                "answer": answer,
                "error": False
            }
            
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return {
                "sql": "",
                "explanation": "",
                "results": [],
                "answer": f"Error processing query: {str(e)}",
                "error": True
            }
