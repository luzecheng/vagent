"""Structured LLM calls through the logged-in Claude Code CLI (no API key needed).

Every call has a pydantic model: the JSON schema is sent to the CLI for
structured output, the reply is validated locally, and on failure the
validation error is fed back for another attempt (config.llm.retries).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import TypeVar

from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def claude_binary() -> str:
    configured = os.environ.get("VAGENT_CLAUDE_BIN", "").strip()
    return configured or str(Path.home() / ".local/bin/claude")


def _environment() -> dict:
    env = dict(os.environ)
    proxy = env.get("VAGENT_CLAUDE_PROXY", "").strip()
    if proxy:
        for name in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
            env.pop(name, None)
        env["HTTP_PROXY"] = env["HTTPS_PROXY"] = proxy
    return env


def _call_cli(system: str, user: str, schema: dict, model: str, timeout: int) -> dict:
    command = [claude_binary(), "-p", "--model", model, "--tools", "", "--no-session-persistence",
               "--setting-sources", "", "--strict-mcp-config", "--system-prompt", system,
               "--output-format", "json", "--json-schema", json.dumps(schema)]
    with tempfile.TemporaryDirectory(prefix="vagent-llm-") as workdir:
        try:
            done = subprocess.run(command, input=user, capture_output=True, text=True, timeout=timeout,
                                  cwd=workdir, env=_environment())
        except subprocess.TimeoutExpired as exc:
            raise LLMError(f"Claude CLI gave no answer within {timeout}s") from exc
        except OSError as exc:
            raise LLMError(f"cannot start Claude CLI ({claude_binary()}): {exc}") from exc
    try:
        payload = json.loads(done.stdout)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Claude CLI exit {done.returncode}: {(done.stderr or done.stdout).strip()[-300:]}") from exc
    if payload.get("is_error"):
        raise LLMError(f"Claude CLI error: {str(payload.get('result'))[:300]}")
    result = payload.get("structured_output")
    if not isinstance(result, dict):
        raise LLMError("Claude CLI returned no structured output")
    return result


def structured(model_cls: type[M], system: str, user: str, config: dict, log=None, validate=None) -> M:
    """Ask for JSON matching model_cls; `validate(obj)` may return extra error strings (semantic checks)."""
    settings = config["llm"]
    schema = model_cls.model_json_schema()
    feedback = ""
    last_error = ""
    for attempt in range(1, settings["retries"] + 1):
        prompt = user if not feedback else (
            user + "\n\nYour previous answer was rejected for these reasons; fix all of them:\n" + feedback)
        try:
            raw = _call_cli(system, prompt, schema, settings["model"], settings["timeout_s"])
            obj = model_cls.model_validate(raw)
            problems = list(validate(obj)) if validate else []
            if not problems:
                if log:
                    log.event("llm", f"{model_cls.__name__} ok (attempt {attempt})")
                return obj
            feedback = "\n".join(f"- {p}" for p in problems)
            last_error = feedback
        except ValidationError as exc:
            feedback = f"- schema validation failed: {exc.errors()[:5]}"
            last_error = feedback
        except LLMError as exc:
            last_error = str(exc)
            feedback = ""
        if log:
            log.event("llm", f"{model_cls.__name__} attempt {attempt} rejected: {last_error[:200]}", autofix=True)
    raise LLMError(f"{model_cls.__name__}: no valid answer after {settings['retries']} attempts: {last_error}")
