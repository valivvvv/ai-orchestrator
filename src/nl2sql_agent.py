"""
NL2SQL Agent - TODO: Implementează nodurile
"""
import json
import logging
import re
from pathlib import Path
from typing import Literal

import pandas as pd
import sqlparse
from langgraph.graph import StateGraph, END
from sqlalchemy import text
from skillab import get_llm
from skillab.llm.base import LLMProvider
from skillab.prompts import PromptRegistry

from database import transaction
from state import NL2SQLState

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class NL2SQLAgent:
    """
    Flow:
        get_context → generate_sql → validate → execute
                                        ↓
                                    handle_error
    """

    def __init__(
        self,
        table_name: str,
        schema_path: str,
        db_url: str = "postgresql://demo:demo123@localhost:5434/rag_demo",
        max_retries: int = 2,
        llm: LLMProvider | None = None,
    ):
        self.table_name = table_name
        self.db_url = db_url
        self.max_retries = max_retries
        self.llm = llm or get_llm()
        self.prompts = PromptRegistry(str(PROMPTS_DIR))

        # Load schema
        self.schema = json.loads(Path(schema_path).read_text())

        self.graph = self._build_graph()

    # === NODES ===

    def node_get_context(self, state: NL2SQLState) -> dict:
        """COMPLET."""
        return {
            "schema_context": self.schema,
            "table_name": self.table_name,
        }

    def node_generate_sql(self, state: NL2SQLState) -> dict:
        """
        Generate SQL. Error-aware node: if a prior error exists, render
        nl2sql_error (correction); otherwise render nl2sql_generate (first pass).
        """
        logger.info(f"[GENERATE] {state.question}")

        schema = state.schema_context
        columns = schema.get("columns", {})
        is_retry = bool(state.execution_error or state.validation_error)

        if is_retry:
            error_message = state.execution_error or state.validation_error
            prompt = self.prompts.render(
                "nl2sql_error",
                table_name=state.table_name,
                question=state.question,
                failed_sql=state.sql_query,
                error_message=error_message,
                columns=columns,
            )
        else:
            prompt = self.prompts.render(
                "nl2sql_generate",
                table_name=state.table_name,
                table_description=schema.get("description", ""),
                columns=columns,
                business_rules={},
                question=state.question,
            )

        response = self.llm.generate_sync([{"role": "user", "content": prompt}])

        cleaned = response.strip()
        cleaned = re.sub(r"^```(?:sql)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

        # On retry, clear both errors so validate/execute writes the current error if it fails again.
        if is_retry:
            return {"sql_query": cleaned, "execution_error": "", "validation_error": ""}
        return {"sql_query": cleaned}

    def node_validate_sql(self, state: NL2SQLState) -> dict:
        """
        Validate SQL: this is the security boundary. Accept only a single
        read-only SELECT; reject DDL/DML, statement chaining, and injection.
        """
        sql = state.sql_query
        logger.info(f"[VALIDATE] {sql[:50]}...")

        if not sql or not sql.strip():
            return {"is_valid": False, "validation_error": "Empty SQL query"}

        statements = [parsed for parsed in sqlparse.parse(sql) if parsed.value.strip().strip(";").strip()]
        if len(statements) != 1:
            return {"is_valid": False, "validation_error": "Only a single statement is allowed"}

        statement = statements[0]
        if statement.get_type() != "SELECT":
            return {
                "is_valid": False,
                "validation_error": f"Only SELECT statements are allowed (got {statement.get_type()})",
            }

        forbidden = {
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
            "GRANT", "REVOKE", "EXEC", "EXECUTE", "MERGE", "REPLACE", "CALL",
        }
        keywords = {
            token.value.upper()
            for token in statement.flatten()
            if token.ttype in (sqlparse.tokens.Keyword, sqlparse.tokens.DDL, sqlparse.tokens.DML)
        }
        forbidden_hit = forbidden & keywords
        if forbidden_hit:
            return {
                "is_valid": False,
                "validation_error": f"Forbidden keyword(s): {', '.join(sorted(forbidden_hit))}",
            }

        return {"is_valid": True, "validation_error": ""}

    def node_execute_sql(self, state: NL2SQLState) -> dict:
        """
        Execute the validated SQL inside a transaction and return rows as a
        DataFrame. On failure, surface the error so the retry loop can correct it.
        """
        logger.info("[EXECUTE]")

        try:
            with transaction() as session:
                result = session.execute(text(state.sql_query))
                dataframe = pd.DataFrame(result.mappings().all())
            return {"result": dataframe, "status": "success", "execution_error": ""}
        except Exception as error:
            logger.warning(f"[EXECUTE] failed: {error}")
            return {"execution_error": str(error), "status": "failed"}

    def node_handle_error(self, state: NL2SQLState) -> dict:
        """
        Retry counter only. The error-aware correction happens in node_generate_sql
        on the next pass, so this node neither generates SQL nor clears errors.
        """
        logger.info("[ERROR]")

        new_count = state.retry_count + 1
        if new_count >= state.max_retries:
            return {"retry_count": new_count, "status": "failed"}
        return {"retry_count": new_count}

    # === ROUTING ===

    def _route_after_validate(self, state: NL2SQLState) -> str:
        return "execute_sql" if state.is_valid else "handle_error"

    def _route_after_execute(self, state: NL2SQLState) -> str:
        return END if not state.execution_error else "handle_error"

    def _route_after_error(self, state: NL2SQLState) -> str:
        return "generate_sql" if state.retry_count < self.max_retries else END

    # === GRAPH ===

    def _build_graph(self):
        graph = StateGraph(NL2SQLState)

        graph.add_node("get_context", self.node_get_context)
        graph.add_node("generate_sql", self.node_generate_sql)
        graph.add_node("validate_sql", self.node_validate_sql)
        graph.add_node("execute_sql", self.node_execute_sql)
        graph.add_node("handle_error", self.node_handle_error)

        graph.set_entry_point("get_context")
        graph.add_edge("get_context", "generate_sql")
        graph.add_edge("generate_sql", "validate_sql")
        graph.add_conditional_edges("validate_sql", self._route_after_validate, ["execute_sql", "handle_error"])
        graph.add_conditional_edges("execute_sql", self._route_after_execute, [END, "handle_error"])
        graph.add_conditional_edges("handle_error", self._route_after_error, ["generate_sql", END])

        return graph.compile()

    def run(self, question: str) -> NL2SQLState:
        """Execută agentul."""
        initial = NL2SQLState(
            question=question,
            table_name=self.table_name,
            max_retries=self.max_retries,
        )
        return NL2SQLState(**self.graph.invoke(initial))
