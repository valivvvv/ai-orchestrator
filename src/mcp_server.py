"""MCP server exposing the ai-orchestrator agents as tools (L10).

Transport is STDIO: stdin/stdout carry JSON-RPC, stderr carries logs. Nothing
must ever be written to stdout except the protocol, so logging is pinned to
stderr and the agents run on Anthropic (which, unlike the Google provider, does
not print to stdout).
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# sys.path bootstrap MUST run before importing the agents: Claude Code spawns
# this server from an arbitrary working directory, so the package roots are
# added explicitly (mirrors src/main.py).
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "skillab-py" / "src"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("mcp_server")

import mcp.types as types
from mcp import McpError
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from skillab import get_llm
from analyst_agent import AnalystAgent

DATA_DIR = REPO_ROOT / "data"

# Declared in the tool's inputSchema so a well-behaved client (e.g. Claude Code)
# shapes its calls; the actual enforcement lives in guardrails.validate_input
# (wired in Phase 3). Phase 3 replaces this local copy with an import from
# guardrails, which owns the canonical value.
MAX_INPUT_LENGTH = 5000

server = Server("ai-orchestrator")

_analyst: AnalystAgent | None = None


def build_agents() -> None:
    """Construct the agent singletons once, forcing Anthropic for stdout hygiene."""
    global _analyst

    language_model = get_llm(provider="anthropic", model=os.getenv("ANTHROPIC_MODEL"))
    logger.info(f"Building agents on anthropic / {language_model.model}")

    _analyst = AnalystAgent(
        tables_config={
            "achizitii_directe": {
                "schema_path": str(DATA_DIR / "nl2sql_agent" / "schema_achizitii_directe.json"),
                "business_path": str(DATA_DIR / "nl2sql_agent" / "business_achizitii_directe.json"),
            },
            "anunturi_initiere": {
                "schema_path": str(DATA_DIR / "nl2sql_agent" / "schema_anunturi_initiere.json"),
                "business_path": str(DATA_DIR / "nl2sql_agent" / "business_anunturi_initiere.json"),
            },
        },
        llm=language_model,
    )
    logger.info("Agents built: data_analyst ready")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="data_analyst",
            description=(
                "Answer analytical questions over the procurement database "
                "(direct awards & tender announcements) using NL→SQL and data tools."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural-language analytical question about the procurement data.",
                        "maxLength": MAX_INPUT_LENGTH,
                    },
                },
                "required": ["question"],
                "additionalProperties": False,
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    # The whole blocking body runs in a worker thread. AnalystAgent.chat (and,
    # from Phase 3, the optional LLM-as-Judge) bottom out in generate_sync,
    # which calls loop.run_until_complete in the CALLING thread; doing that
    # inside this already-running event loop raises RuntimeError. to_thread
    # gives it a thread with no running loop. Calls stay sequential.
    answer = await asyncio.to_thread(_handle_call, name, arguments)
    return [types.TextContent(type="text", text=answer)]


def _handle_call(name: str, arguments: dict) -> str:
    # TODO(Phase 3): guard_call(name, arguments, _validator) gate goes here, first.
    if name == "data_analyst":
        result = _analyst.chat(arguments["question"])
    else:
        raise McpError(types.ErrorData(code=-32601, message=f"Unknown tool: {name}"))

    answer = str(result.get("answer", ""))
    status = result.get("status")
    if status and status != "success":
        answer = f"[status={status}] {answer}"
    return answer


async def main() -> None:
    build_agents()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="ai-orchestrator",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
