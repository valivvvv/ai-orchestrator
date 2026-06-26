"""STDIO smoke client for the ai-orchestrator MCP server.

Spawns src/mcp_server.py as a subprocess, performs the JSON-RPC lifecycle
(initialize -> tools/list -> tools/call) and prints a readable trace.

Run: python scripts/smoke_mcp.py
"""
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).parent.parent
SERVER_PATH = REPO_ROOT / "src" / "mcp_server.py"


def _line(char: str = "-") -> None:
    print(char * 70)


async def run() -> None:
    server_parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
    )

    async with stdio_client(server_parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            _line("=")
            print("INITIALIZE (capabilities negotiation)")
            _line("=")
            init_result = await session.initialize()
            print(f"server   : {init_result.serverInfo.name} v{init_result.serverInfo.version}")
            print(f"protocol : {init_result.protocolVersion}")
            print(f"caps     : tools={init_result.capabilities.tools}")

            _line("=")
            print("TOOLS/LIST")
            _line("=")
            tools = (await session.list_tools()).tools
            assert len(tools) == 2, f"expected 2 tools, got {len(tools)}"
            tool_names = {tool.name for tool in tools}
            assert tool_names == {"data_analyst", "document_qa"}, f"unexpected tools: {tool_names}"
            for tool in tools:
                print(f"name        : {tool.name}")
                print(f"description : {tool.description}")
                print(f"required    : {tool.inputSchema.get('required')}")
                print(f"properties  : {list(tool.inputSchema.get('properties', {}))}")
                _line("-")

            _line("=")
            print("TOOLS/CALL  data_analyst")
            _line("=")
            question = "Cate achizitii directe sunt in total?"
            print(f"request.arguments : {{'question': {question!r}}}")
            analyst_result = await session.call_tool("data_analyst", {"question": question})
            analyst_answer = analyst_result.content[0].text
            assert analyst_answer.strip(), "empty data_analyst answer"
            print(f"isError           : {analyst_result.isError}")
            print(f"content[0].type   : {analyst_result.content[0].type}")
            print(f"answer            :\n{analyst_answer}")

            _line("=")
            print("TOOLS/CALL  document_qa")
            _line("=")
            query = "Ce contact are DataPro?"
            print(f"request.arguments : {{'query': {query!r}, 'session_id': ''}}")
            qa_result = await session.call_tool("document_qa", {"query": query, "session_id": ""})
            qa_answer = qa_result.content[0].text
            assert qa_answer.strip(), "empty document_qa answer"
            print(f"isError           : {qa_result.isError}")
            print(f"content[0].type   : {qa_result.content[0].type}")
            print(f"answer            :\n{qa_answer}")

    _line("=")
    print("SMOKE v2 PASSED: 2 tools listed; data_analyst and document_qa both returned non-empty answers.")
    _line("=")


if __name__ == "__main__":
    asyncio.run(run())
