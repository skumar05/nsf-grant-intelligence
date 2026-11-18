"""NSFAgent: a LangChain agent wired to this MCP server over stdio, traced to Phoenix.

Smoke test:  python agent.py "What is the title of NSF award 1753742?"
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from llm import make_chat_model

HERE = Path(__file__).parent
REPO_ROOT = HERE.parent.parent
# The server runs in the project's own .venv (mcp 2.x); this process uses a separate eval env (mcp 1.x).
SERVER_PYTHON = os.getenv("NSF_SERVER_PYTHON") or str(
    REPO_ROOT / ".venv" / "bin" / "python"
    if (REPO_ROOT / ".venv" / "bin" / "python").exists()
    else sys.executable
)
RECURSION_LIMIT = 80  # multi-step questions page through results, so allow many tool calls


class NSFAgent:
    def __init__(
        self,
        system_prompt_version: str = "v1",
        project_name: str = "nsf-grant-intelligence",
        phoenix_endpoint: str = "http://localhost:6006",
    ):
        self.system_prompt_version = system_prompt_version
        self.project_name = project_name
        self.phoenix_endpoint = phoenix_endpoint
        self.client: MultiServerMCPClient | None = None
        self.tools: list = []
        self._tracing_ready = False

    def _load_system_prompt(self) -> str:
        path = HERE / "prompts" / f"system_prompt_{self.system_prompt_version}.txt"
        return path.read_text().strip()

    def _setup_tracing(self) -> None:
        """Send LangChain spans to Phoenix. Safe to call once; a missing server only logs errors."""
        if self._tracing_ready:
            return
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from phoenix.otel import register

        provider = register(
            project_name=self.project_name,
            endpoint=f"{self.phoenix_endpoint.rstrip('/')}/v1/traces",
            set_global_tracer_provider=False,
            verbose=False,
        )
        LangChainInstrumentor().instrument(tracer_provider=provider)
        self._tracing_ready = True

    async def initialize(self) -> None:
        """Start tracing and load the server's tools by launching it over stdio."""
        self._setup_tracing()
        if self.client is None:
            self.client = MultiServerMCPClient(
                {
                    "nsf_grant_intelligence": {
                        "transport": "stdio",
                        "command": SERVER_PYTHON,
                        "args": ["-m", "nsf_grant_intelligence"],
                        "cwd": str(REPO_ROOT),
                    }
                }
            )
            self.tools = await self.client.get_tools()

    async def run(self, query: str) -> str:
        """Answer one question and return the final text."""
        await self.initialize()
        # A fresh agent per question: experiments call this from short-lived event loops.
        agent = create_agent(
            model=make_chat_model(), tools=self.tools, system_prompt=self._load_system_prompt()
        )
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": query}]},
            config={"recursion_limit": RECURSION_LIMIT},
        )
        return _text(result["messages"][-1].content)

    def create_experiment_task(self):
        """Phoenix experiments need a synchronous task(example) function."""

        def task(example) -> str:
            return asyncio.run(self.run(example.input["query"]))

        return task


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


async def _main() -> None:
    question = " ".join(sys.argv[1:]) or "What is the title of NSF award 1753742?"
    agent = NSFAgent(system_prompt_version=os.getenv("PROMPT_VERSION", "v1"))
    print(await agent.run(question))


if __name__ == "__main__":
    asyncio.run(_main())
