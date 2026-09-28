import os
import json
import logging
import re
from typing import Dict, Any
from google import genai
from google.genai import types

from config.prompts import QUERY_SYSTEM_PROMPT, QUERY_USER_PROMPT
from storage.database import Database

logger = logging.getLogger(__name__)

class QueryEngine:
    def __init__(self, db: Database, api_key: str = None):
        self.db = db
        api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.client = genai.Client(api_key=api_key or "sk-placeholder")
        self.model = os.getenv("QUERY_MODEL", "gemini-3.8-flash")

    def query(self, question: str) -> Dict[str, Any]:
        prompt = QUERY_USER_PROMPT.format(question=question)
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=QUERY_SYSTEM_PROMPT,
                    temperature=0.0,
                    response_mime_type="application/json"
                )
            )
            
            reply = response.text
            
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
            answer_response = self.client.models.generate_content(
                model=self.model,
                contents=answer_prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are a helpful assistant. Given a user question, a SQL query, and its results, provide a clear, concise natural language answer.",
                    temperature=0.0
                )
            )
            answer = answer_response.text
            
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
