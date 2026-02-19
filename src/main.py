from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import shlex
import shutil
from typing import Any

from dotenv import load_dotenv
try:
    from rich import print as console_print
except ImportError:
    console_print = print

from src.agent.loop import AgentLoop
from src.browser.devtools_adapter import DevToolsAdapter
from src.llm.groq_client import GroqClient
from src.mcp_client.session import McpSession
from src.mcp_client.transport import StdioTransport


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Autonomous web test agent via MCP")
    parser.add_argument("--prompt", required=True, help="Natural language test objective")
    return parser.parse_args()


def _server_args(args_str: str) -> list[str]:
    args = shlex.split(args_str, posix=False)

    has_isolated = "--isolated" in args
    has_custom_session_target = any(
        token in {"-u", "--browserUrl", "-w", "--wsEndpoint", "--userDataDir"}
        or token.startswith("--browserUrl=")
        or token.startswith("--wsEndpoint=")
        or token.startswith("--userDataDir=")
        for token in args
    )
    if not has_isolated and not has_custom_session_target:
        args.append("--isolated")

    has_executable_arg = any(
        token in {"-e", "--executablePath"} or token.startswith("--executablePath=")
        for token in args
    )
    if not has_executable_arg:
        browser_executable = _resolve_browser_executable()
        if browser_executable:
            args.extend(["--executablePath", browser_executable])

    return args


def _resolve_browser_executable() -> str | None:
    configured = os.getenv("CHROME_PATH", "").strip().strip('"')
    if configured and os.path.exists(configured):
        return configured

    local_app_data = os.getenv("LOCALAPPDATA", "")
    program_files = os.getenv("ProgramFiles", "C:\\Program Files")
    program_files_x86 = os.getenv("ProgramFiles(x86)", "C:\\Program Files (x86)")

    candidates = [
        os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _resolve_command(command: str) -> str:
    candidate = command.strip().strip('"')
    resolved = shutil.which(candidate)
    if resolved and os.name == "nt" and resolved.lower().endswith(".ps1"):
        cmd_candidate = str(resolved)[:-4] + ".cmd"
        if os.path.exists(cmd_candidate):
            return cmd_candidate
    if resolved:
        return resolved
    if os.name == "nt" and not candidate.lower().endswith(".cmd"):
        resolved_cmd = shutil.which(f"{candidate}.cmd")
        if resolved_cmd:
            return resolved_cmd
    raise RuntimeError(
        f"MCP server command not found: {command}. Ensure Node.js/npx is installed and available in PATH."
    )


async def _run(prompt: str) -> dict[str, Any]:
    load_dotenv()
    verbose = os.getenv("VERBOSE", "0").lower() in {"1", "true", "yes", "on"}

    groq_api_key = os.getenv("GROQ_API_KEY", "")
    if not groq_api_key:
        raise RuntimeError("Missing GROQ_API_KEY in environment")

    server_command = os.getenv("MCP_SERVER_COMMAND", "npx")
    server_args = _server_args(os.getenv("MCP_SERVER_ARGS", "-y chrome-devtools-mcp@latest"))
    
    if verbose:
        executable_index = None
        with contextlib.suppress(ValueError):
            executable_index = server_args.index("--executablePath")
        if executable_index is not None and executable_index + 1 < len(server_args):
            console_print(f"[agent] Browser: {server_args[executable_index + 1]}")

    resolved_server_command = _resolve_command(server_command)
    transport = StdioTransport(resolved_server_command, server_args)
    session = McpSession(transport, timeout_seconds=float(os.getenv("STEP_TIMEOUT_SECONDS", "20")))

    await session.start()
    try:
        await session.initialize()
        tools = await session.list_tools()
        tool_names = [tool.get("name") for tool in tools.get("tools", []) if tool.get("name")]

        groq = GroqClient(
            api_key=groq_api_key,
            model=os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile"),
        )

        console_print(f"\n🎯 Objective: {prompt}\n")
        adapter = DevToolsAdapter(session)
        enable_ocr = os.getenv("ENABLE_OCR", "0").lower() in {"1", "true", "yes", "on"}
        loop = AgentLoop(
            adapter,
            groq_client=groq,
            max_steps=int(os.getenv("MAX_STEPS", "20")),
            enable_ocr=enable_ocr,
            verbose=verbose,
        )
        memory = await loop.run(objective=prompt)

        close_results: list[dict[str, Any]] = []
        with contextlib.suppress(Exception):
            close_results = await adapter.close_all_pages()

        return {
            "tool_count": len(tool_names),
            "tool_names": tool_names,
            "objective": prompt,
            "success": memory.success,
            "last_error": memory.last_error,
            "close_pages": close_results,
            "history_length": len(memory.history),
            "history_tail": memory.history[-3:],
        }
    finally:
        with contextlib.suppress(Exception):
            await session.stop()


def main() -> None:
    args = _parse_args()
    result = asyncio.run(_run(args.prompt))
    
    # Clean summary output
    success = result.get("success", False)
    steps = result.get("history_length", 0)
    error = result.get("last_error")
    
    console_print("\n" + "="*60)
    if success:
        console_print("✅ TEST PASSED")
    else:
        console_print("❌ TEST FAILED")
    
    console_print(f"Steps executed: {steps}")
    if error:
        console_print(f"Error: {error}")
    console_print("="*60 + "\n")
    
    verbose = os.getenv("VERBOSE", "0").lower() in {"1", "true", "yes", "on"}
    if verbose:
        console_print("\nDetailed result:")
        console_print(result)


if __name__ == "__main__":
    main()
