# Drift — Automated Hypnosis Content Pipeline

A fully automated pipeline that generates hypnosis/somatic relaxation sessions
and publishes them to YouTube. Each run produces a complete MP4 video:

```
topic selection → Claude script → ElevenLabs TTS → FFmpeg audio mix → gradient visual → YouTube upload
```

Use `--local` to generate the full video locally with LM Studio instead of Claude — no API costs, no upload.

---

## Stack

| Layer | Tool |
|---|---|
| Script generation | Anthropic Claude API (`claude-sonnet-4-6`) |
| Local script generation | LM Studio / Ollama (any OpenAI-compatible server) |
| Text-to-speech | ElevenLabs API (`eleven_v3`) |
| Audio mixing | FFmpeg |
| Video rendering | FFmpeg (lavfi gradient + geq per-pixel) |
| Upload | YouTube Data API v3 |
| Scheduler | APScheduler or system cron |
| Config | YAML + .env |
| Runtime | Python 3.11+ |

---

## Project Structure

```
drift/
├── README.md
├── requirements.txt
├── .env.example
├── config.yaml                  # Voice, schedule, topic, visual settings
├── run.py                       # Single pipeline entry point
├── scheduler.py                 # APScheduler cron wrapper
│
├── pipeline/
│   ├── __init__.py
│   ├── logger.py                # Structured logging (console + file)
│   ├── topics.py                # Topic rotation and session type logic
│   ├── script_gen.py            # Claude API + local LLM — script generation
│   ├── tts.py                   # ElevenLabs API — audio rendering
│   ├── audio_mix.py             # FFmpeg — voice + ambient layer
│   ├── video_render.py          # FFmpeg — gradient visual + audio → MP4
│   ├── thumbnail.py             # Pillow — auto-generate thumbnail
│   └── upload.py                # YouTube Data API v3 upload
│
├── skills/                      # Reference skill docs (ElevenLabs, etc.)
│
├── assets/
│   └── audio/                   # Ambient/binaural background tracks (.mp3/.wav)
│
├── output/                      # Per-run working directory (gitignored)
└── logs/                        # Run logs (gitignored)
```

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/yourname/drift.git
cd drift
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment variables

```bash
cp .env.example .env
```

Fill in `.env`:
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `ELEVENLABS_API_KEY` — from elevenlabs.io
- `YOUTUBE_CLIENT_SECRET_PATH` — path to OAuth2 credentials JSON

### 3. YouTube API setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable **YouTube Data API v3**
3. Create OAuth 2.0 credentials (Desktop app) → download `client_secret.json`
4. First run opens a browser for OAuth consent — token is cached after that

### 4. Assets

Place at least one ambient audio track in `assets/audio/`:
- Recommended: binaural beats (theta 4–7 Hz for relaxation, delta 1–3 Hz for sleep)
- Format: `.mp3` or `.wav`, minimum 60 min or loopable
- Free sources: mynoise.net exports, freesound.org (CC0)

---

## Usage

```bash
# Normal run — weighted random topic, Claude API, uploads to YouTube
python run.py

# Force a specific session type
python run.py --type deep_sleep

# Skip YouTube upload (generate video only)
python run.py --dry-run

# Local mode — use LM Studio instead of Claude, no upload
python run.py --local

# Local mode with forced session type
python run.py --local --type anxiety_release

# Custom config file
python run.py --config ./my_config.yaml
```

### Local mode (`--local`)

Routes script generation to a local OpenAI-compatible server instead of the Claude API.
Upload is automatically disabled.

**LM Studio setup:**
1. Open LM Studio → load a model (e.g. Llama 3.2, Mistral, Phi-4)
2. Start the local server (default: `http://localhost:1234/v1`)
3. Set `LOCAL_LLM_MODEL` in `.env` to the model name shown in LM Studio's selector
4. Run `python run.py --local`

Config in `config.yaml` under `local_llm:`, or override via env vars:
```
LOCAL_LLM_BASE_URL=http://localhost:1234/v1
LOCAL_LLM_MODEL=your-model-name
```

---

## Schedule

```bash
# System cron — daily at 3am
0 3 * * * /path/to/drift/venv/bin/python /path/to/drift/run.py >> /path/to/drift/logs/cron.log 2>&1

# Or use built-in APScheduler
python scheduler.py
```

---

## Configuration

See `config.yaml` for all parameters:

| Section | Key settings |
|---|---|
| `pipeline` | session duration, output dir, dry_run |
| `topics` | session types, weights, theme variants, YouTube metadata |
| `voice` | ElevenLabs voice ID, model, stability, speed |
| `script` | Claude model, max_tokens, induction style |
| `local_llm` | base_url, model, max_tokens |
| `audio` | ambient dir, volume levels, fade in/out |
| `video` | resolution, gradient colors, watermark |
| `youtube` | privacy, category, description template |

---

## Pipeline Flow

```
topics.py      → select topic + session type (weighted random or --type)
script_gen.py  → generate script via Claude API or local LLM (--local)
tts.py         → render script to audio via ElevenLabs eleven_v3
audio_mix.py   → layer ambient track under voice with FFmpeg
video_render.py → generate gradient visual + mux audio → MP4
thumbnail.py   → generate 1280x720 JPEG thumbnail with Pillow
upload.py      → upload to YouTube with metadata (skipped with --dry-run / --local)
```

Each stage writes output to `output/<run_id>/` and logs to `logs/drift.log`.
Failed runs are logged with full traceback and do not upload partial content.
