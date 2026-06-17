import sys
from pathlib import Path

import streamlit as st
import yaml

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from newsletter import state, pipeline
from newsletter.cost import MODEL_PRICES

_CONFIG_FILE = _ROOT / "config.yaml"
_PROMPTS_DIR = _ROOT / "prompts"
_MEMORY_FILE = _ROOT / "memory" / "agent_memory.md"

st.set_page_config(page_title="Research Newsletter Pipeline", layout="wide")

# Model lists per provider — ordered cheapest to most capable
_PROVIDER_MODELS: dict[str, list[str]] = {
    "anthropic": ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8"],
    "openai":    ["gpt-4o-mini", "gpt-4o", "o3-mini", "o3"],
}

_FAST_RECOMMENDATIONS = {
    "anthropic": "claude-haiku-4-5",
    "openai":    "gpt-4o-mini",
}

_QUALITY_RECOMMENDATIONS = {
    "anthropic": "claude-sonnet-4-6",
    "openai":    "gpt-4o",
}


def _load_config() -> dict:
    with open(_CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save_config(cfg: dict) -> None:
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _model_cost_label(model: str) -> str:
    prices = MODEL_PRICES.get(model)
    if prices:
        return f"{model}  (${prices[0]:.2f}/${ prices[1]:.2f} per 1M tokens in/out)"
    return model


def _estimated_cost(fast_model: str, quality_model: str) -> str:
    fp = MODEL_PRICES.get(fast_model)
    qp = MODEL_PRICES.get(quality_model)
    if not fp or not qp:
        return "Cost estimate unavailable"
    # Rough estimate: fast=~5K tokens total, quality=~20K tokens total per run
    fast_cost = (2_000 * fp[0] + 3_000 * fp[1]) / 1_000_000
    quality_cost = (8_000 * qp[0] + 12_000 * qp[1]) / 1_000_000
    total = fast_cost + quality_cost
    return f"~${total:.4f} per run (rough estimate)"


# ── Sidebar navigation ────────────────────────────────────────────────────────

page = st.sidebar.radio("", ["Configure", "Run History", "Prompts & Memory"])


# ── Page 1: Configure ─────────────────────────────────────────────────────────

if page == "Configure":
    st.title("Configure Newsletter")

    cfg = _load_config()

    # ── LLM Provider & Models ─────────────────────────────────────────────────

    st.subheader("LLM Provider & Models")

    provider_options = ["anthropic", "openai"]
    current_provider = cfg.get("provider", "anthropic")
    provider = st.selectbox(
        "Provider",
        options=provider_options,
        index=provider_options.index(current_provider) if current_provider in provider_options else 0,
        help="Anthropic or OpenAI. Make sure the matching API key is set in your .env file.",
    )

    models_for_provider = _PROVIDER_MODELS[provider]

    col_fast, col_quality = st.columns(2)

    with col_fast:
        current_fast = cfg.get("fast_model", _FAST_RECOMMENDATIONS[provider])
        if current_fast not in models_for_provider:
            current_fast = _FAST_RECOMMENDATIONS[provider]
        fast_model = st.selectbox(
            "Fast model  (query generation + filter)",
            options=models_for_provider,
            index=models_for_provider.index(current_fast),
            format_func=_model_cost_label,
            help="Used for cheap, high-volume calls. Choose the fastest/cheapest model.",
        )

    with col_quality:
        current_quality = cfg.get("quality_model", _QUALITY_RECOMMENDATIONS[provider])
        if current_quality not in models_for_provider:
            current_quality = _QUALITY_RECOMMENDATIONS[provider]
        quality_model = st.selectbox(
            "Quality model  (writing + editing)",
            options=models_for_provider,
            index=models_for_provider.index(current_quality),
            format_func=_model_cost_label,
            help="Used for writing and editing. Higher quality = better output.",
        )

    st.caption(f"Estimated cost: {_estimated_cost(fast_model, quality_model)}")

    st.divider()

    # ── Research Settings ─────────────────────────────────────────────────────

    st.subheader("Research Settings")

    topics_text = st.text_area(
        "Research topics (one per line)",
        value="\n".join(cfg.get("topics", [])),
        height=160,
        help="Each line becomes a separate topic section in the newsletter.",
    )

    col1, col2 = st.columns(2)
    with col1:
        recency_days = st.number_input(
            "Recency window (days)",
            min_value=1, max_value=30,
            value=cfg.get("recency_days", 7),
        )
    with col2:
        max_articles = st.number_input(
            "Max articles per run",
            min_value=3, max_value=20,
            value=cfg.get("max_articles", 12),
        )

    if st.button("Save configuration"):
        topics = [t.strip() for t in topics_text.splitlines() if t.strip()]
        if not topics:
            st.error("Add at least one topic.")
        else:
            _save_config({
                "provider":      provider,
                "fast_model":    fast_model,
                "quality_model": quality_model,
                "topics":        topics,
                "recency_days":  int(recency_days),
                "max_articles":  int(max_articles),
            })
            st.success("Configuration saved to config.yaml")

    st.divider()

    if st.button("Run newsletter now", type="primary"):
        topics = [t.strip() for t in topics_text.splitlines() if t.strip()]
        if not topics:
            st.error("Save a valid configuration first.")
        else:
            with st.spinner("Running pipeline... this takes 1-2 minutes"):
                try:
                    result = pipeline.run()
                    st.success(
                        f"Done! {result.get('calls', '?')} LLM calls | "
                        f"Cost: ${result.get('cost_usd', 0):.4f} | "
                        f"Run ID: {result.get('run_id', '?')}"
                    )
                    pdf_path = Path(result.get("pdf_path", ""))
                    if pdf_path.exists():
                        with open(pdf_path, "rb") as f:
                            st.download_button(
                                "Download PDF",
                                data=f.read(),
                                file_name=pdf_path.name,
                                mime="application/pdf",
                            )
                except Exception as e:
                    st.error(f"Run failed: {e}")


# ── Page 2: Run History ───────────────────────────────────────────────────────

elif page == "Run History":
    st.title("Run History")

    state.init_db()
    runs = state.get_runs(limit=50)

    if not runs:
        st.info("No runs yet. Go to Configure and click 'Run newsletter now'.")
    else:
        import pandas as pd

        df = pd.DataFrame(runs)

        display = df[["run_id", "started_at", "status", "article_count", "cost_usd", "completed_at", "error_message"]].copy()
        display.columns = ["Run ID", "Started", "Status", "Articles", "Cost ($)", "Completed", "Error"]
        display["Cost ($)"] = display["Cost ($)"].apply(lambda x: f"${x:.4f}" if x else "—")
        display["Articles"] = display["Articles"].fillna("—")
        display["Error"] = display["Error"].fillna("")

        st.dataframe(display, use_container_width=True, hide_index=True)

        latest_success = next((r for r in runs if r["status"] == "success"), None)
        if latest_success:
            pdf_path = _ROOT / "data" / f"{latest_success['run_id']}.pdf"
            if pdf_path.exists():
                st.divider()
                st.subheader("Latest newsletter")
                with open(pdf_path, "rb") as f:
                    st.download_button(
                        f"Download {latest_success['run_id']}.pdf",
                        data=f.read(),
                        file_name=pdf_path.name,
                        mime="application/pdf",
                    )


# ── Page 3: Prompts & Memory ──────────────────────────────────────────────────

elif page == "Prompts & Memory":
    st.title("Prompts & Memory")

    tab1, tab2, tab3, tab4 = st.tabs([
        "Newsworthiness", "Writing Guidelines", "Editor Guidelines", "Agent Memory"
    ])

    def _prompt_editor(tab, filename: str, label: str) -> None:
        with tab:
            path = _PROMPTS_DIR / filename
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            edited = st.text_area(label, value=current, height=400, key=filename)
            if st.button("Save", key=f"save_{filename}"):
                path.write_text(edited, encoding="utf-8")
                st.success(f"Saved {filename}")

    _prompt_editor(tab1, "newsworthiness.md", "Newsworthiness filter prompt")
    _prompt_editor(tab2, "writing_guidelines.md", "Writing guidelines prompt")
    _prompt_editor(tab3, "editor_guidelines.md", "Editor guidelines prompt")

    with tab4:
        current = _MEMORY_FILE.read_text(encoding="utf-8") if _MEMORY_FILE.exists() else ""
        edited = st.text_area(
            "Agent memory (injected into research prompts at runtime)",
            value=current,
            height=500,
            key="memory",
        )
        if st.button("Save memory", key="save_memory"):
            _MEMORY_FILE.write_text(edited, encoding="utf-8")
            st.success("Saved memory/agent_memory.md")
