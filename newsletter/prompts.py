from pathlib import Path

_ROOT = Path(__file__).parent.parent
_PROMPTS_DIR = _ROOT / "prompts"
_MEMORY_FILE = _ROOT / "memory" / "agent_memory.md"


def load(name: str) -> str:
    """Load a prompt file from the prompts/ directory by name (without .md)."""
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def load_memory() -> str:
    """Load the agent memory file. Returns empty string if file is empty or missing."""
    if not _MEMORY_FILE.exists():
        return ""
    content = _MEMORY_FILE.read_text(encoding="utf-8").strip()
    # Strip template comments so they don't pollute prompts
    lines = [l for l in content.splitlines() if not l.strip().startswith("<!--")]
    return "\n".join(lines).strip()


def with_memory(base_prompt: str, memory: str) -> str:
    """Append memory content to a base prompt if memory is non-empty."""
    if not memory:
        return base_prompt
    return (
        f"{base_prompt}\n\n"
        "---\n"
        "Additional instructions from agent memory:\n"
        f"{memory}\n"
        "---"
    )
