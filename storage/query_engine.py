import os
import json
import logging
import re
from typing import Dict, Any
from openai import OpenAI

from config.prompts import QUERY_SYSTEM_PROMPT, QUERY_USER_PROMPT
from storage.database import Database

logger = logging.getLogger(__name__)

class QueryEngine:
    def __init__(self, db: Database, api_key: str = None):
        self.db = db
        api_key = api_key or os.getenv("OPENAI_API_KEY", "sk-placeholder")
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4o-mini"

    def query(self, question: str) -> Dict[str, Any]:
        prompt = QUERY_USER_PROMPT.format(question=question)
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": QUERY_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            
            reply = response.choices[0].message.content
            
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
            
            answer_response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Given a user question, a SQL query, and its results, provide a clear, concise natural language answer."},
                    {"role": "user", "content": f"Question: {question}\nSQL: {sql}\nResults: {json.dumps(results, default=str)}"}
                ],
                temperature=0
            )
            answer = answer_response.choices[0].message.content
            
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
