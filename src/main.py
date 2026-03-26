from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
from pathlib import Path
from pydantic import ValidationError

import httpx
from pydantic import Field

from dotenv import load_dotenv

from src.config.schemas import JsonSchemaModel
from src.config.settings import RuntimeSettings
from src.llm.providers import validate_provider_keys
from src.pipeline.runner import LinearPipelineRunner
from src.step1_extract.extractor import Step1Extractor
from src.step2_generate.generator import Step2Generator
from src.step3_execute.executor import Step3Executor
from src.step4_log.writer import JsonFileStep4Logger


class PromptIntent(JsonSchemaModel):
    url: str
    objective: str = Field(min_length=1)


class PromptIntentParser:
    def __init__(self, *, model: str | None = None, timeout_seconds: float = 12.0) -> None:
        self._model = model or "llama-3.1-8b-instant"
        self._timeout_seconds = timeout_seconds

    async def parse_prompt(self, *, prompt: str) -> PromptIntent:
        text = (prompt or "").strip()
        if not text:
            raise ValueError("Prompt cannot be empty.")

        api_key = (os.getenv("GROQ_API_KEY") or "").strip()
        if not api_key:
            raise ValueError("Missing GROQ_API_KEY for prompt intent parsing.")

        llm_prompt = self._build_prompt(prompt=text)
        raw = await self._call_groq(prompt=llm_prompt, api_key=api_key)
        content = self._extract_response_text(raw)
        payload = self._parse_json_payload(content)

        if not isinstance(payload.get("url"), str):
            raise ValueError("Prompt parser returned invalid structure: missing 'url' string.")
        if not isinstance(payload.get("objective"), str) or not str(payload.get("objective", "")).strip():
            raise ValueError("Prompt parser returned invalid structure: missing 'objective' string.")

        if not payload["url"].strip():
            raise ValueError(
                "Could not resolve a starting URL from your prompt. "
                "Please mention the target site more clearly."
            )

        try:
            intent = PromptIntent.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Prompt parser returned invalid structure: {exc}") from exc
        return intent

    def _build_prompt(self, *, prompt: str) -> str:
        return (
            "You are a routing parser for a web automation agent.\n"
            "Return STRICT JSON only with exactly two keys: url and objective.\n"
            "Rules:\n"
            "1) If the user provides an explicit URL, keep it as the starting url.\n"
            "2) If the URL is implicit, infer the most relevant starting URL from intent.\n"
            "3) objective must be a concise cleaned objective for browser automation.\n"
            "4) If URL cannot be confidently inferred, return url as an empty string and still provide best effort objective.\n"
            "No markdown. No explanation.\n\n"
            f"USER_PROMPT:\n{prompt}\n"
        )

    async def _call_groq(self, *, prompt: str, api_key: str) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _extract_response_text(raw: dict) -> str:
        try:
            text = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Prompt parser LLM returned invalid response shape: {exc}") from exc
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Prompt parser LLM returned empty content.")
        return text.strip()

    @staticmethod
    def _parse_json_payload(text: str) -> dict:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1]).strip()

        payload = json.loads(cleaned)
        if not isinstance(payload, dict):
            raise ValueError("Prompt parser payload must be a JSON object.")
        return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Linear web test automation pipeline skeleton")
    parser.add_argument("--prompt", default="", help="Single natural-language prompt containing URL and objective")
    parser.add_argument("--url", default="", help="Target page URL")
    parser.add_argument("--objective", default="", help="Test objective")
    parser.add_argument("--run-id", default="", help="Optional run id")
    args = parser.parse_args()

    if not args.prompt and (not args.url or not args.objective):
        parser.error("Either provide --prompt, or provide both --url and --objective")

    return args


async def _run(url: str, objective: str, run_id: str) -> None:
    load_dotenv()
    settings = RuntimeSettings()
    terminal_lines: list[str] = []

    def _emit(message: str) -> None:
        print(message)
        terminal_lines.append(message)

    missing_keys = validate_provider_keys(settings.provider_matrix)
    if missing_keys:
        _emit("Missing provider API keys in .env: " + ", ".join(missing_keys))

    computed_run_id = run_id or f"run_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    run_dir = settings.artifacts_root / computed_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    runner = LinearPipelineRunner(
        settings=settings,
        step1=Step1Extractor(),
        step2=Step2Generator(),
        step3=Step3Executor(),
        step4=JsonFileStep4Logger(settings.artifacts_root),
    )

    trace = await runner.run(run_id=computed_run_id, url=url, objective=objective)
    _emit(f"Run completed with status: {trace.status.value}")
    if trace.error:
        _emit(f"Error: {trace.error}")

    _persist_terminal_output(run_dir=run_dir, lines=terminal_lines)


async def _run_with_prompt(*, prompt: str, run_id: str) -> None:
    load_dotenv()
    settings = RuntimeSettings()
    terminal_lines: list[str] = []

    def _emit(message: str) -> None:
        print(message)
        terminal_lines.append(message)

    computed_run_id = run_id or f"run_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    run_dir = settings.artifacts_root / computed_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    parser = PromptIntentParser(model=os.getenv("PROMPT_PARSER_MODEL", "llama-3.1-8b-instant"))
    try:
        intent = await parser.parse_prompt(prompt=prompt)
    except Exception as exc:
        _emit(f"Prompt parsing error: {exc}")
        _persist_terminal_output(run_dir=run_dir, lines=terminal_lines)
        return

    await _run(url=intent.url, objective=intent.objective, run_id=computed_run_id)


def _persist_terminal_output(*, run_dir: Path, lines: list[str]) -> None:
    if not lines:
        return

    terminal_log_path = run_dir / "terminal_output.log"
    terminal_log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    trace_path = run_dir / "execution_trace.json"
    if trace_path.exists():
        try:
            payload = json.loads(trace_path.read_text(encoding="utf-8"))
            payload["terminal_output"] = lines
            trace_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            # Do not fail the run if trace augmentation is not possible.
            pass


def main() -> None:
    args = _parse_args()
    try:
        if args.prompt:
            asyncio.run(_run_with_prompt(prompt=args.prompt, run_id=args.run_id))
        else:
            asyncio.run(_run(url=args.url, objective=args.objective, run_id=args.run_id))
    except RuntimeError as exc:
        print(f"Pipeline skeleton is active but not fully implemented yet: {exc}")


if __name__ == "__main__":
    main()
