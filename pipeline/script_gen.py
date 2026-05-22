import os
import re
import anthropic
from pipeline.logger import get_logger
from pipeline.topics import Session

logger = get_logger(__name__)


def _strip_llm_artifacts(text: str) -> str:
    """
    Remove chain-of-thought / planning blocks that some local LLMs leak into output.

    Gemma models emit thinking blocks wrapped in <|channel>thought ... <channel|>.
    Other models may use <think>...</think> or similar.
    Everything before the first line of actual prose is removed.
    """
    # Gemma: <|channel>thought ... <channel|>
    text = re.sub(r"<\|channel\>thought.*?<channel\|>", "", text, flags=re.DOTALL)
    # Generic: <think>...</think>, <thinking>...</thinking>
    text = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # Any remaining <|...|> special tokens
    text = re.sub(r"<\|[^|>]*\|>", "", text)
    return text.strip()

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
    style    = config["script"]["induction_style"]
    pacing   = config["script"]["pacing_notes"]

    return f"""Write a {duration}-minute {style} hypnosis session for the following:

Session type: {session.session_type.replace("_", " ")}
Theme: {session.theme}
Title: {session.youtube_title}

Pacing guidance:
{pacing}

Begin the script now."""


# ── Public entry point ────────────────────────────────────────────────────────

def generate_script(session: Session, config: dict) -> str:
    """
    Generate a hypnosis script, with automatic quality checking and retry.

    Routes to local LLM when config["pipeline"]["use_local_llm"] is True.
    If the first response is too short (local LLMs often truncate long-form output),
    sends a continuation prompt and concatenates the result — up to max_retries times.
    Raises ValueError if the script is still below min_words after all retries.
    """
    use_local  = config["pipeline"].get("use_local_llm", False)
    user_prompt = build_user_prompt(session, config)

    # Messages list — Anthropic uses no system key here (passed separately in _call_anthropic)
    # Local LLM includes system as the first message
    if use_local:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ]
        call_fn = lambda msgs: _call_local(msgs, config)
        label   = "local"
    else:
        messages = [{"role": "user", "content": user_prompt}]
        call_fn  = lambda msgs: _call_anthropic(msgs, config)
        label    = "Claude"

    logger.info(f"Generating script ({label}) for: {session.youtube_title}")

    script     = _strip_llm_artifacts(call_fn(messages))
    word_count = len(script.split())
    logger.info(f"Script generated — {word_count} words")

    script = _quality_check(script, word_count, messages, call_fn, config)
    return script


# ── Quality guard ─────────────────────────────────────────────────────────────

def _quality_check(
    script: str,
    word_count: int,
    messages: list[dict],
    call_fn,
    config: dict,
) -> str:
    """
    If the script is below min_words, request a continuation and concatenate.
    Retries up to max_retries times, then raises ValueError.
    """
    quality_cfg = config["script"].get("quality", {})
    min_words   = quality_cfg.get("min_words", 1800)
    max_retries = quality_cfg.get("max_retries", 2)
    duration    = config["pipeline"]["session_duration_minutes"]
    target_words = duration * 130  # ~130 wpm average for slow hypnotic speech

    for attempt in range(1, max_retries + 1):
        if word_count >= min_words:
            break

        logger.warning(
            f"Script too short: {word_count} words "
            f"(minimum: {min_words}, target: ~{target_words}). "
            f"Requesting continuation — attempt {attempt}/{max_retries}."
        )

        continuation_prompt = (
            f"The script above is only {word_count} words — too short for a "
            f"{duration}-minute session (target: ~{target_words} words). "
            "Continue writing directly from where the script ends. "
            "Do not repeat, reintroduce, or summarise — just continue the "
            "flowing prose seamlessly as if there was no interruption."
        )

        # Append the short script as the assistant turn, then ask to continue
        messages = messages + [
            {"role": "assistant", "content": script},
            {"role": "user",      "content": continuation_prompt},
        ]

        continuation = _strip_llm_artifacts(call_fn(messages))
        script       = script.rstrip() + "\n\n" + continuation.lstrip()
        word_count   = len(script.split())
        logger.info(f"After continuation {attempt}: {word_count} words")

    if word_count < min_words:
        raise ValueError(
            f"Script quality check failed after {max_retries} retries: "
            f"{word_count} words (minimum: {min_words}). "
            "Try: increasing max_tokens, using a larger model, or lowering "
            "script.quality.min_words in config.yaml."
        )

    logger.info(f"Script quality OK — {word_count} words (minimum: {min_words})")
    return script


# ── Anthropic backend ─────────────────────────────────────────────────────────

def _call_anthropic(messages: list[dict], config: dict) -> str:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=config["script"]["model"],
        max_tokens=config["script"]["max_tokens"],
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    return message.content[0].text


# ── Local LLM backend (LM Studio / Ollama / any OpenAI-compatible server) ────

def _call_local(messages: list[dict], config: dict) -> str:
    """
    Calls a local OpenAI-compatible server.

    LM Studio defaults:  base_url = http://localhost:1234/v1
    Ollama defaults:      base_url = http://localhost:11434/v1

    Priority: env vars > config.yaml > built-in defaults (LM Studio)
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "openai package is required for local LLM mode. "
            "Run: pip install openai>=1.0.0"
        )

    local_cfg = config.get("local_llm", {})
    base_url  = os.getenv("LOCAL_LLM_BASE_URL", local_cfg.get("base_url", "http://localhost:1234/v1"))
    model     = os.getenv("LOCAL_LLM_MODEL",    local_cfg.get("model", "local-model"))
    max_tokens = local_cfg.get("max_tokens", config["script"].get("max_tokens", 6000))
    api_key   = os.getenv("LOCAL_LLM_API_KEY",  local_cfg.get("api_key", "lm-studio"))

    client = OpenAI(base_url=base_url, api_key=api_key)

    logger.info(f"Calling local LLM: {model} @ {base_url}")

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
    )
    return response.choices[0].message.content
