import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from pipeline.logger import get_logger
from pipeline.topics import Session

logger = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# 10 MB chunks — safe for VPS instances with limited RAM
_CHUNK_SIZE = 10 * 1024 * 1024


def get_youtube_client():
    token_path  = os.getenv("YOUTUBE_TOKEN_PATH", "./youtube_token.json")
    secret_path = os.getenv("YOUTUBE_CLIENT_SECRET_PATH", "./client_secret.json")

    creds = None
    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow  = InstalledAppFlow.from_client_secrets_file(secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def build_description(session: Session, config: dict) -> str:
    template = config["youtube"]["description_template"]
    return template.format(session_title=session.youtube_title)


def upload_to_youtube(
    video_path: Path,
    thumbnail_path: Path,
    session: Session,
    config: dict,
) -> str:
    """
    Upload video to YouTube. Returns the video ID.
    Skipped entirely in dry-run mode.
    """
    if config["pipeline"].get("dry_run") or os.getenv("DRY_RUN", "false").lower() == "true":
        logger.info(f"[DRY RUN] Would upload: {video_path}")
        return "dry_run_video_id"

    youtube = get_youtube_client()
    yt_cfg  = config["youtube"]

    body = {
        "snippet": {
            "title":           session.youtube_title,
            "description":     build_description(session, config),
            "tags":            session.tags,
            "categoryId":      yt_cfg["category_id"],
            "defaultLanguage": yt_cfg.get("default_language", "en"),
        },
        "status": {
            "privacyStatus":          yt_cfg["privacy_status"],
            "selfDeclaredMadeForKids": False,
        },
    }

    # Use chunked upload to avoid loading the full video into RAM
    media = MediaFileUpload(str(video_path), chunksize=_CHUNK_SIZE, resumable=True)

    logger.info(f"Uploading to YouTube: {session.youtube_title}")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    logger.info(f"Uploaded — https://youtube.com/watch?v={video_id}")

    if thumbnail_path.exists():
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumbnail_path)),
        ).execute()
        logger.info("Thumbnail set.")

    return video_id
