import random
from dataclasses import dataclass
from typing import Optional
from pipeline.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Session:
    session_type: str
    theme: str
    youtube_title: str
    tags: list[str]
    description_hint: str


def pick_session(config: dict, force_type: Optional[str] = None) -> Session:
    """
    Select a session type and theme variant using weighted random sampling.
    Pass force_type to override (useful for testing a specific session type).
    """
    sessions = config["topics"]["sessions"]

    if force_type:
        candidates = [s for s in sessions if s["name"] == force_type]
        if not candidates:
            raise ValueError(f"Session type '{force_type}' not found in config.")
        chosen = candidates[0]
    else:
        weights = [s["weight"] for s in sessions]
        chosen = random.choices(sessions, weights=weights, k=1)[0]

    theme = random.choice(chosen["theme_variants"])
    title = chosen["youtube_title_template"].format(theme=theme.title())

    logger.info(f"Selected session: {chosen['name']} / theme: '{theme}'")

    return Session(
        session_type=chosen["name"],
        theme=theme,
        youtube_title=title,
        tags=chosen["tags"],
        description_hint=theme,
    )
