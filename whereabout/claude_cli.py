from __future__ import annotations
import subprocess


def call_claude(prompt: str, system_prompt: str = "", model: str = "sonnet") -> str:
    """
    Call the claude CLI in non-interactive mode using subscription OAuth auth.
    Raises RuntimeError if the process fails.
    """
    cmd = [
        "claude", "-p", prompt,
        "--tools", "",
        "--no-session-persistence",
        "--model", model,
    ]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error: {result.stderr.strip() or 'unknown error'}")
    return result.stdout.strip()
