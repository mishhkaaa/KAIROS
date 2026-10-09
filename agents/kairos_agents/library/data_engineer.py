"""DataEngineerAgent — answers a data question with one SQL query on the demo company database (the db tool).

Owner: P3 — Agents & Models

Reads the schema (db.schema), asks the model for one PostgreSQL SELECT, runs it through ctx.syscall (the kernel checks
it: one statement, read-only, no DDL, a LIMIT), and when the kernel refuses it or the database rejects it, sends the
reason back to the model once. The rows are the output; the kernel shows the query and the table to the UI
(tool.query, task.data). Thoughts are counts, never the SQL's text or the rows.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from kairos_contracts.schema import AgentResult, AgentResultStatus, ErrorInfo, Risk, SyscallStatus

from kairos_agents.prompts import SqlOut
from kairos_agents.sdk import KairosAgent, ask_json, plural, propose_action, role_of, think

log = logging.getLogger("kairos.agents.data_engineer")

SQL_RULES = """Write exactly ONE PostgreSQL SELECT statement that answers the task.
- Use only the tables and columns in the schema, and follow its notes.
- Include the identifying columns a reader needs (for example the vendor's name), not only the numbers.
- No comments, no semicolons, nothing but the statement. End it with LIMIT 200.
- Return JSON: {"sql": "...", "explanation": "one sentence"}."""
MAX_ATTEMPTS = 2  # the first query, and one rewrite with the reason it was refused


class DataEngineerAgent(KairosAgent):
    async def run(self, goal: str, ctx: Any) -> AgentResult:
        role = role_of(ctx)
        await think(ctx, "schema", "Reading the database schema.")
        schema = await ctx.syscall(propose_action(ctx, "db.query", "db", "schema", {}, "Read the schema to write the query",
                                                  [], risk=Risk.LOW))
        if schema.status != SyscallStatus.COMPLETED or not schema.tool_result:
            return self._failed(ctx, f"could not read the database schema ({schema.status.value})", schema)
        system = f"{ctx.manifest.system_prompt or 'You are a Data Engineer agent in KAIROS.'}\n{SQL_RULES}"
        prompt = f"Task: {goal}\n\nDatabase schema (JSON):\n{json.dumps(schema.tool_result.output, indent=1)}"

        feedback = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            out = await ask_json(ctx, system, prompt + feedback, SqlOut, max_tokens=600)
            sql = (out.sql if out else "").strip()
            if not sql:
                feedback = '\n\nYour last answer had no SQL. Return the JSON with one SELECT in "sql".'
                continue
            await think(ctx, "query", "Running one read-only query on the company database." if attempt == 1
                        else "Rewriting the query once, with the reason it was refused.")
            result = await ctx.syscall(propose_action(ctx, "db.query", "db", "query", {"sql": sql},
                                                      f"Answer: {goal[:150]}", [], risk=Risk.LOW))
            if result.status == SyscallStatus.COMPLETED and result.tool_result:
                rows = result.tool_result.output.get("rows", [])
                columns = result.tool_result.output.get("columns", [])
                await think(ctx, "analyze", f"The query returned {plural(len(rows), 'row')}.")
                await ctx.log(f"{role}: {len(rows)} rows from one query (attempt {attempt})")
                findings = [{"claim": ", ".join(f"{c}: {v}" for c, v in zip(columns, r, strict=False)), "source": "db.query"}
                            for r in rows[:50]]
                return self.result(ctx, f"{len(rows)} rows answer the question", output={
                    "sql": sql, "columns": columns, "rows": rows, "findings": findings, "attempts": attempt})
            reason = (result.decision.reason if result.status == SyscallStatus.DENIED and result.decision
                      else result.error.message if result.error else result.status.value)
            await ctx.log(f"{role}: query attempt {attempt} {result.status.value}: {reason}", level="warning")
            if result.error and result.error.code in ("TIMEOUT", "TOOL_FAILED"):
                return self._failed(ctx, f"the database did not answer: {reason}", result)
            feedback = f"\n\nYour previous SQL was refused: {reason}\nPrevious SQL: {sql}\nWrite a corrected statement."
        return self.result(ctx, f"no usable query after {MAX_ATTEMPTS} attempts", status=AgentResultStatus.FAILED,
                           output={"rows": [], "findings": []})

    def _failed(self, ctx: Any, message: str, result: Any) -> AgentResult:
        code = result.error.code if getattr(result, "error", None) else "TOOL_FAILED"
        r = self.result(ctx, message, status=AgentResultStatus.FAILED, output={"rows": [], "findings": []})
        return r.model_copy(update={"error": ErrorInfo(code=code, message=message, retriable=code in ("TIMEOUT", "TOOL_FAILED"))})
