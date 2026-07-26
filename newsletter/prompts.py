import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_PROMPTS_DIR = _ROOT / "prompts"
_MEMORY_FILE = _ROOT / "memory" / "agent_memory.md"


def load(name: str) -> str:
    """Load a prompt file from the prompts/ directory by name (without .md)."""
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def load_memory() -> str:
    """Load the agent memory file, or "" if it holds nothing worth injecting.

    The file ships as a template: section headings with guidance in HTML
    comments and nothing under them. Those headings must not reach a prompt —
    they arrive labelled "additional instructions" while containing no
    instructions, which is pure noise in a prompt already asking a small model
    for careful batch judgement. So an untouched template counts as empty.
    """
    if not _MEMORY_FILE.exists():
        return ""

    # Whole comment blocks, not lines starting with "<!--" — the template's
    # guidance spans several lines per comment.
    raw = _MEMORY_FILE.read_text(encoding="utf-8")
    content = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL).strip()

    # Anything that is not a heading, a horizontal rule, or blank is real content.
    has_content = any(
        stripped and not stripped.startswith("#") and set(stripped) != {"-"}
        for stripped in (line.strip() for line in content.splitlines())
    )
    return content if has_content else ""


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
