#!/usr/bin/env python3

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


CODEX_HOME = Path.home() / ".codex"
SESSIONS_DIR = CODEX_HOME / "sessions"
CACHE_DIR = CODEX_HOME / "pane_summary_cache"
CACHE_DIR.mkdir(exist_ok=True)


def git_root(cwd: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        )
        root = result.stdout.strip()
        return Path(root) if root else cwd
    except Exception:
        return cwd


def repo_name(cwd: Path) -> str:
    return git_root(cwd).name or cwd.name or "workspace"


def session_matches(session_cwd: str, target_cwd: Path) -> bool:
    if not session_cwd:
        return False
    try:
        session_path = Path(session_cwd).resolve()
        target_path = target_cwd.resolve()
    except Exception:
        return False

    return session_path == target_path or session_path in target_path.parents or target_path in session_path.parents


def find_latest_session(cwd: Path) -> Path | None:
    if not SESSIONS_DIR.exists():
        return None

    target = git_root(cwd)
    best_path = None
    best_mtime = -1.0

    for path in SESSIONS_DIR.rglob("*.jsonl"):
        try:
            stat = path.stat()
            if time.time() - stat.st_mtime > 60 * 60 * 24:
                continue
            with path.open("r", encoding="utf-8") as handle:
                first_line = handle.readline()
            if not first_line:
                continue
            first = json.loads(first_line)
            if first.get("type") != "session_meta":
                continue
            session_cwd = first.get("payload", {}).get("cwd", "")
            if not session_matches(session_cwd, target):
                continue
            if stat.st_mtime > best_mtime:
                best_path = path
                best_mtime = stat.st_mtime
        except Exception:
            continue

    return best_path


def extract_text_parts(content: list[dict]) -> list[str]:
    parts: list[str] = []
    for item in content or []:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("input_text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return parts


def load_session_context(session_path: Path) -> dict:
    users: list[str] = []
    assistant: list[str] = []

    with session_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")
            payload = event.get("payload", {})

            if event_type == "event_msg" and payload.get("type") == "user_message":
                message = payload.get("message")
                if isinstance(message, str) and message.strip():
                    users.append(clean_text(message))
                continue

            if event_type == "response_item" and payload.get("type") == "message":
                if payload.get("role") != "assistant":
                    continue
                content = payload.get("content")
                if isinstance(content, list):
                    text = " ".join(extract_text_parts(content))
                    text = clean_text(text)
                    if text:
                        assistant.append(text)

    return {
        "users": users[-4:],
        "assistant": assistant[-2:],
    }


def clean_text(text: str) -> str:
    text = re.sub(r"\[Image #[0-9]+\]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def heuristic_summary(cwd: Path, context: dict) -> str:
    latest = context["users"][-1] if context["users"] else ""
    if latest:
        latest = re.sub(r"^(can you|could you|please)\s+", "", latest, flags=re.IGNORECASE)
        latest = latest.rstrip("?.! ")
        if len(latest) > 72:
            latest = latest[:69].rstrip() + "..."
        return latest
    return f"Working in {repo_name(cwd)}"


def context_hash(cwd: Path, context: dict, session_path: Path | None) -> str:
    payload = {
        "cwd": str(git_root(cwd)),
        "session": str(session_path) if session_path else "",
        "users": context.get("users", []),
        "assistant": context.get("assistant", []),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def cache_path(cwd: Path) -> Path:
    key = hashlib.sha256(str(git_root(cwd)).encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{key}.json"


def tty_cache_path(tty_path: str) -> Path:
    key = hashlib.sha256(tty_path.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"tty-{key}.json"


def read_cache(cwd: Path) -> dict | None:
    path = cache_path(cwd)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_tty_cache(tty_path: str) -> dict | None:
    path = tty_cache_path(tty_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_cache(cwd: Path, payload: dict) -> None:
    path = cache_path(cwd)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_tty_cache(tty_path: str, payload: dict) -> None:
    path = tty_cache_path(tty_path)
    path.write_text(json.dumps(payload), encoding="utf-8")


def find_codex_pid_for_tty(tty_path: str) -> int | None:
    tty_name = Path(tty_path).name
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,tty=,command="],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return None

    candidates: list[int] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid_text, tty_text, command = parts
        if tty_text != tty_name:
            continue
        if re.search(r"(^|/)\bcodex\b", command) or re.search(r"\bcodex\b", command):
            try:
                candidates.append(int(pid_text))
            except ValueError:
                continue

    return max(candidates) if candidates else None


def session_path_from_pid(pid: int) -> Path | None:
    try:
        result = subprocess.run(
            ["lsof", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return None

    for line in result.stdout.splitlines():
        match = re.search(r"(/Users/.+?/\.codex/sessions/.+?\.jsonl)\s*$", line)
        if match:
            return Path(match.group(1))
    return None


def generate_llm_summary(cwd: Path, context: dict) -> str | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or os.environ.get("CODEX_PANE_SUMMARY_DISABLE_LLM") == "1":
        return None

    prompt = {
        "model": os.environ.get("CODEX_PANE_SUMMARY_MODEL", "gpt-4.1-mini"),
        "input": [
            {
                "role": "system",
                "content": (
                    "Write a terse present-tense summary of the coding task in this pane. "
                    "Return one line only, no quotes, no trailing period, max 10 words."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Repository: {repo_name(cwd)}\n"
                    f"Recent user asks:\n- " + "\n- ".join(context.get("users", []) or ["none"]) + "\n"
                    f"Recent assistant progress:\n- " + "\n- ".join(context.get("assistant", []) or ["none"])
                ),
            },
        ],
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(prompt).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return clean_text(output_text)

    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return clean_text(text)
    return None


def resolve_summary(cwd: Path, quick: bool, ttl_seconds: int, tty_path: str | None = None) -> str:
    session_path = None
    tty_state = read_tty_cache(tty_path) if tty_path else None
    now = time.time()

    if tty_state:
        tty_summary = tty_state.get("summary")
        tty_updated_at = float(tty_state.get("updated_at", 0))
        if isinstance(tty_summary, str) and tty_summary.strip():
            if quick or now - tty_updated_at <= ttl_seconds:
                return tty_summary.strip()

    if tty_path:
        pid = find_codex_pid_for_tty(tty_path)
        if pid is not None:
            session_path = session_path_from_pid(pid)
        if session_path is None and tty_state:
            cached_session_path = tty_state.get("session_path")
            if isinstance(cached_session_path, str) and cached_session_path:
                cached_path = Path(cached_session_path)
                if cached_path.exists():
                    session_path = cached_path

    if session_path is None:
        session_path = find_latest_session(cwd)

    if not session_path:
        return f"Codex: {repo_name(cwd)}"

    context = load_session_context(session_path)
    fallback = heuristic_summary(cwd, context)
    digest = context_hash(cwd, context, session_path)
    cached = read_cache(cwd)

    if cached and cached.get("digest") == digest:
        summary = cached.get("summary")
        if isinstance(summary, str) and summary.strip():
            age = now - float(cached.get("updated_at", 0))
            if quick or age <= ttl_seconds:
                return summary.strip()

    if quick:
        return fallback

    summary = generate_llm_summary(cwd, context) or fallback
    payload = {
        "summary": summary,
        "digest": digest,
        "updated_at": now,
        "session_path": str(session_path),
    }
    write_cache(cwd, payload)
    if tty_path:
        write_tty_cache(tty_path, payload)
    return summary


def emit_to_tty(tty_path: str, summary: str) -> None:
    encoded = base64.b64encode(summary.encode("utf-8")).decode("ascii")
    payload = (
        f"\033]0;{summary}\007"
        f"\033]1;{summary}\007"
        f"\033]2;{summary}\007"
        f"\033]1337;SetUserVar=task={encoded}\007"
    )
    with open(tty_path, "w", encoding="utf-8", buffering=1) as handle:
        handle.write(payload)


def watch(cwd: Path, tty_path: str, interval_seconds: int, ttl_seconds: int) -> int:
    last_summary = None
    while True:
        summary = resolve_summary(cwd, quick=False, ttl_seconds=ttl_seconds, tty_path=tty_path)
        if summary != last_summary:
            try:
                emit_to_tty(tty_path, summary)
                last_summary = summary
            except OSError:
                return 1
        time.sleep(interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--tty")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--interval", type=int, default=4)
    parser.add_argument("--ttl", type=int, default=120)
    args = parser.parse_args()

    cwd = Path(args.cwd).expanduser()

    if args.watch:
        if not args.tty:
            return 2
        return watch(cwd, args.tty, args.interval, args.ttl)

    summary = resolve_summary(cwd, quick=args.quick, ttl_seconds=args.ttl, tty_path=args.tty)
    if args.tty:
        emit_to_tty(args.tty, summary)
    else:
        print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
