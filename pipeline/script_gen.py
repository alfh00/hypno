import os
import anthropic
from pipeline.logger import get_logger
from pipeline.topics import Session

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an expert hypnotherapist and somatic experiencing practitioner.
You write deeply therapeutic hypnosis scripts for guided audio sessions.

Your scripts follow this structure:
1. INDUCTION (3-4 min): gentle sensory grounding, breath awareness, eye closure invitation
2. DEEPENING (4-5 min): progressive relaxation, counting down, heaviness and warmth metaphors
3. THERAPEUTIC CORE (12-15 min): the main session work — titrated, pendulating between
   activation and resourcing. Use the control room metaphor, inner landscape imagery,
   parts work, or somatic body awareness depending on the session type.
4. FUTURE PACING (2-3 min): anchoring a new state, rehearsing the felt sense forward
5. REORIENTATION (2 min): gentle return, counting up, grounded re-entry

Style rules:
- Ericksonian indirect language: "you might notice...", "perhaps you find...", "as you allow..."
- Short rhythmic sentences in deepening and core phases
- Rich sensory language: weight, warmth, breath, gravity, texture, colour
- Mark natural pauses with [pause] — use generously
- Never use clinical or instructional tone
- Write as if whispering beside the listener
- Total output: approximately 2500-3500 words of flowing prose
- NO headers, NO bullet points, NO stage directions in brackets except [pause]
- Output the script only — no preamble, no meta-commentary"""


def build_user_prompt(session: Session, config: dict) -> str:
    duration = config["pipeline"]["session_duration_minutes"]
    style = config["script"]["induction_style"]
    pacing = config["script"]["pacing_notes"]

    return f"""Write a {duration}-minute {style} hypnosis session for the following:

Session type: {session.session_type.replace("_", " ")}
Theme: {session.theme}
Title: {session.youtube_title}

Pacing guidance:
{pacing}

Begin the script now."""


def generate_script(session: Session, config: dict) -> str:
    """
    Generate a hypnosis script.
    Routes to the local LLM backend when config["pipeline"]["use_local_llm"] is True,
    otherwise uses the Anthropic Claude API.
    """
    if config["pipeline"].get("use_local_llm"):
        return _generate_local(session, config)
    return _generate_anthropic(session, config)


# ── Anthropic backend ─────────────────────────────────────────────────────────

def _generate_anthropic(session: Session, config: dict) -> str:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    logger.info(f"Generating script (Claude) for: {session.youtube_title}")

    message = client.messages.create(
        model=config["script"]["model"],
        max_tokens=config["script"]["max_tokens"],
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": build_user_prompt(session, config)}
        ],
    )

    script = message.content[0].text
    logger.info(f"Script generated — {len(script.split())} words")
    return script


# ── Local LLM backend (LM Studio / Ollama / any OpenAI-compatible server) ────

def _generate_local(session: Session, config: dict) -> str:
    """
    Uses the openai library pointed at a local OpenAI-compatible server.

    LM Studio defaults:  base_url = http://localhost:1234/v1
    Ollama defaults:      base_url = http://localhost:11434/v1

    Priority order for settings:
      1. Environment variables  (LOCAL_LLM_BASE_URL, LOCAL_LLM_MODEL)
      2. config.yaml local_llm section
      3. Built-in defaults (LM Studio)
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "openai package is required for local LLM mode. "
            "Run: pip install openai>=1.0.0"
        )

    local_cfg = config.get("local_llm", {})
    base_url = os.getenv(
        "LOCAL_LLM_BASE_URL",
        local_cfg.get("base_url", "http://localhost:1234/v1"),  # LM Studio default
    )
    model = os.getenv(
        "LOCAL_LLM_MODEL",
        local_cfg.get("model", "local-model"),
    )
    max_tokens = local_cfg.get("max_tokens", config["script"].get("max_tokens", 6000))
    api_key = os.getenv("LOCAL_LLM_API_KEY", local_cfg.get("api_key", "lm-studio"))

    client = OpenAI(base_url=base_url, api_key=api_key)

    logger.info(f"Generating script (local: {model} @ {base_url}) for: {session.youtube_title}")

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(session, config)},
        ],
    )

    script = response.choices[0].message.content
    logger.info(f"Local script generated — {len(script.split())} words")
    return script
