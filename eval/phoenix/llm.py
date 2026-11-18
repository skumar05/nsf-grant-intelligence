"""Model wiring shared by the agent and the judges.

Two backends, chosen by environment variables (a root .env is loaded):
  USAI_API_KEY + USAI_BASE_URL  an OpenAI-compatible gateway (the hackathon template's default)
  ANTHROPIC_API_KEY             Anthropic directly

AGENT_MODEL and JUDGE_MODEL are separate so the judge can be a different (stronger) model
than the agent under test. Temperature is not set: claude-sonnet-5-5 rejects it.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_AGENT_MODEL = "claude-sonnet-5-5"
DEFAULT_JUDGE_MODEL = "claude-opus-5-5"


def uses_gateway() -> bool:
    return bool(os.getenv("USAI_API_KEY") and os.getenv("USAI_BASE_URL"))


def gateway_url() -> str:
    return os.environ["USAI_BASE_URL"].rstrip("/") + "/api/v1"


def agent_model_name() -> str:
    return os.getenv("AGENT_MODEL", DEFAULT_AGENT_MODEL)


def judge_model_name() -> str:
    return os.getenv("JUDGE_MODEL", DEFAULT_JUDGE_MODEL)


def make_chat_model():
    """LangChain chat model for the agent under test."""
    if uses_gateway():
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=agent_model_name(),
            api_key=os.environ["USAI_API_KEY"],
            base_url=gateway_url(),
            temperature=0,
        )
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=agent_model_name(), max_tokens=4096)


def make_judge_llm():
    """Phoenix evals LLM wrapper for the judges."""
    from phoenix.evals import LLM

    if uses_gateway():
        return LLM(
            provider="openai",
            model=judge_model_name(),
            sync_client_kwargs={"api_key": os.environ["USAI_API_KEY"], "base_url": gateway_url()},
            async_client_kwargs={"api_key": os.environ["USAI_API_KEY"], "base_url": gateway_url()},
        )
    return LLM(provider="anthropic", model=judge_model_name())
