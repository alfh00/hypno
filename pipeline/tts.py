import re
import os
import math
import wave
import array
from pathlib import Path
from elevenlabs import ElevenLabs, VoiceSettings
from pipeline.logger import get_logger

logger = get_logger(__name__)

_TTS_WORDS_PER_MINUTE = 130   # slow hypnotic pacing — used to estimate mock duration
_PAUSE_SECONDS        = 2.5   # duration added per [pause] marker in mock mode
_MOCK_SAMPLE_RATE     = 44100
_MOCK_FREQ_HZ         = 220.0  # A3 — clearly audible on any speaker, obviously not a voice


def preprocess_script(script: str) -> str:
    """
    Convert [pause] markers to SSML breaks and wrap in <speak> tags.
    ElevenLabs requires the full text inside <speak> for SSML to be processed.
    """
    processed = re.sub(r"\[pause\]", '<break time="2.5s"/>', script)
    return f"<speak>{processed}</speak>"


def _estimate_duration(script: str) -> float:
    """Estimate spoken duration in seconds from raw script text."""
    word_count  = len(script.split())
    pause_count = script.count("[pause]")
    speech_secs = (word_count / _TTS_WORDS_PER_MINUTE) * 60
    pause_secs  = pause_count * _PAUSE_SECONDS
    return speech_secs + pause_secs


def _render_mock(script: str, output_path: Path) -> Path:
    """
    Generate a synthetic placeholder WAV instead of calling ElevenLabs.
    Duration is estimated from word count + pause markers.
    Saves a stereo 44.1 kHz sine wave at 60 Hz — clearly not a real voice.
    """
    duration   = _estimate_duration(script)
    n_samples  = int(_MOCK_SAMPLE_RATE * duration)
    amplitude  = 0.30   # clearly audible test tone
    samples    = array.array("h")

    for i in range(n_samples):
        t   = i / _MOCK_SAMPLE_RATE
        val = int(amplitude * 32767 * math.sin(2 * math.pi * _MOCK_FREQ_HZ * t))
        samples.append(val)   # L
        samples.append(val)   # R

    # Always save as .wav regardless of output_path extension —
    # the caller should pass a .wav path when mock_tts is active (see run.py)
    wav_path = output_path.with_suffix(".wav")
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(_MOCK_SAMPLE_RATE)
        wf.writeframes(samples.tobytes())

    size_mb = wav_path.stat().st_size / 1_000_000
    logger.info(
        f"[MOCK TTS] Placeholder audio: {wav_path} "
        f"({duration:.0f}s estimated, {size_mb:.1f} MB) — 220 Hz tone, audible on any speaker"
    )
    return wav_path


def render_tts(script: str, output_path: Path, config: dict) -> Path:
    """
    Render script to audio.

    Routes to _render_mock() when config["pipeline"]["mock_tts"] is True —
    no ElevenLabs call, no cost, full pipeline still exercises audio_mix and
    video_render stages correctly.

    Otherwise calls ElevenLabs text_to_speech.convert() with voice settings
    from config["voice"].
    """
    if config["pipeline"].get("mock_tts"):
        return _render_mock(script, output_path)

    client    = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
    voice_cfg = config["voice"]
    processed = preprocess_script(script)

    voice_id = voice_cfg["elevenlabs_voice_id"]
    model_id = voice_cfg["model_id"]
    logger.info(f"Rendering TTS — voice: {voice_id}, model: {model_id}")

    voice_settings = VoiceSettings(
        stability=voice_cfg["stability"],
        similarity_boost=voice_cfg["similarity_boost"],
        style=voice_cfg["style"],
        speed=voice_cfg.get("speed", 1.0),
        use_speaker_boost=voice_cfg["use_speaker_boost"],
    )

    audio = client.text_to_speech.convert(
        text=processed,
        voice_id=voice_id,
        model_id=model_id,
        voice_settings=voice_settings,
        output_format=voice_cfg["output_format"],
        language_code=config["script"].get("language"),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)

    size_mb = output_path.stat().st_size / 1_000_000
    logger.info(f"TTS audio saved: {output_path} ({size_mb:.1f} MB)")
    return output_path
