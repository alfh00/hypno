import math
import os
import wave
import array
from pathlib import Path
from elevenlabs import ElevenLabs, VoiceSettings
from pipeline.logger import get_logger

logger = get_logger(__name__)

_TTS_WORDS_PER_MINUTE = 130
_PAUSE_SECONDS = 2.5
_MOCK_SAMPLE_RATE = 44100
_MOCK_FREQ_HZ = 220.0


def render_tts(script: str, output_path: Path, config: dict) -> Path:
    """Send script to ElevenLabs, save MP3. Returns the output path."""

    if config["pipeline"].get("mock_tts"):
        return _render_mock(script, output_path)

    client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
    voice_cfg = config["voice"]

    # [pause] → inline SSML break — ElevenLabs accepts <break> without a <speak> wrapper
    text = script.replace("[pause]", '<break time="2.5s"/>')

    logger.info(f"Rendering TTS — voice: {voice_cfg['elevenlabs_voice_id']}, model: {voice_cfg['model_id']}")

    audio = client.text_to_speech.convert(
        text=text,
        voice_id=voice_cfg["elevenlabs_voice_id"],
        model_id=voice_cfg["model_id"],
        voice_settings=VoiceSettings(
            stability=voice_cfg["stability"],
            similarity_boost=voice_cfg["similarity_boost"],
            style=voice_cfg["style"],
            speed=voice_cfg.get("speed", 1.0),
            use_speaker_boost=voice_cfg["use_speaker_boost"],
        ),
        output_format=voice_cfg["output_format"],
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)

    size_mb = output_path.stat().st_size / 1_000_000
    logger.info(f"TTS audio saved: {output_path} ({size_mb:.1f} MB)")
    return output_path


# ── Mock TTS (--mock-tts flag) ────────────────────────────────────────────────

def _estimate_duration(script: str) -> float:
    words = len(script.split())
    pauses = script.count("[pause]")
    return (words / _TTS_WORDS_PER_MINUTE) * 60 + pauses * _PAUSE_SECONDS


def _render_mock(script: str, output_path: Path) -> Path:
    """Generate an audible 220 Hz sine wave WAV — no ElevenLabs call."""
    duration = _estimate_duration(script)
    n_samples = int(_MOCK_SAMPLE_RATE * duration)
    samples = array.array("h")
    for i in range(n_samples):
        t = i / _MOCK_SAMPLE_RATE
        val = int(0.30 * 32767 * math.sin(2 * math.pi * _MOCK_FREQ_HZ * t))
        samples.append(val)
        samples.append(val)

    wav_path = output_path.with_suffix(".wav")
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(_MOCK_SAMPLE_RATE)
        wf.writeframes(samples.tobytes())

    size_mb = wav_path.stat().st_size / 1_000_000
    logger.info(f"[MOCK TTS] {wav_path} — {duration:.0f}s, {size_mb:.1f} MB")
    return wav_path
