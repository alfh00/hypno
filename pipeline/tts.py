import re
import os
from pathlib import Path
from elevenlabs import ElevenLabs, VoiceSettings
from pipeline.logger import get_logger

logger = get_logger(__name__)


def preprocess_script(script: str) -> str:
    """
    Convert [pause] markers to SSML breaks and wrap in <speak> tags.
    ElevenLabs requires the full text inside <speak> for SSML to be processed.
    """
    processed = re.sub(r"\[pause\]", '<break time="2.5s"/>', script)
    return f"<speak>{processed}</speak>"


def render_tts(script: str, output_path: Path, config: dict) -> Path:
    """
    Send script to ElevenLabs and save the audio file.
    Uses client.text_to_speech.convert() (current API).
    Returns path to the rendered audio file.
    """
    client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
    voice_cfg = config["voice"]
    processed = preprocess_script(script)

    voice_id = voice_cfg["elevenlabs_voice_id"]
    model_id  = voice_cfg["model_id"]
    logger.info(f"Rendering TTS — voice: {voice_id}, model: {model_id}")

    # Build VoiceSettings — speed is optional (defaults to 1.0)
    voice_settings = VoiceSettings(
        stability=voice_cfg["stability"],
        similarity_boost=voice_cfg["similarity_boost"],
        style=voice_cfg["style"],
        speed=voice_cfg.get("speed", 1.0),       # <1.0 = slower, more hypnotic
        use_speaker_boost=voice_cfg["use_speaker_boost"],
    )

    # Use with_raw_response to log character usage for cost tracking
    response = client.text_to_speech.convert.with_raw_response(
        text=processed,
        voice_id=voice_id,
        model_id=model_id,
        voice_settings=voice_settings,
        output_format=voice_cfg["output_format"],
        language_code=config["script"].get("language"),   # e.g. "en" — enforces pronunciation
    )

    char_count = response.headers.get("x-character-count", "unknown")
    logger.info(f"TTS characters used: {char_count}")

    audio = response.parse()  # the actual audio iterator

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)

    size_mb = output_path.stat().st_size / 1_000_000
    logger.info(f"TTS audio saved: {output_path} ({size_mb:.1f} MB)")

    return output_path
