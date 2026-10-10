import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
CLIENT_FILE = ROOT / "client_secret.json"
DB_FILE = ROOT / "upload_history.sqlite3"
LOG_DIR = ROOT / "logs"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
SERVICE = "RandomWordYouTubePipeline"
USERNAME = "youtube-oauth-token"

LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "upload.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

def get_credentials():
    saved = keyring.get_password(SERVICE, USERNAME)
    creds = None

    if saved:
        try:
            creds = Credentials.from_authorized_user_info(
                json.loads(saved), SCOPES
            )
        except (ValueError, KeyError):
            logging.warning("Saved credentials invalid; reauthorizing.")

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not CLIENT_FILE.exists():
            raise FileNotFoundError(
                f"Missing {CLIENT_FILE.name}. Put your downloaded "
                "Desktop OAuth JSON beside upload_video.py."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_FILE), SCOPES
        )
        creds = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent",
        )

    keyring.set_password(SERVICE, USERNAME, creds.to_json())
    return creds


def connect_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            sha256 TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            video_id TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    videos = sorted(
        OUTPUT.glob("*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not videos:
        raise FileNotFoundError(
            "No MP4 found in output/. Run py main.py first."
        )

    video = videos[0]
    digest = sha256_file(video)

    conn = connect_db()
    try:
        existing = conn.execute(
            "SELECT status, video_id FROM uploads WHERE sha256 = ?",
            (digest,),
        ).fetchone()

        if existing and existing[0] == "uploaded":
            print("This exact video was already uploaded.")
            print("Video ID:", existing[1])
            print("No duplicate upload performed.")
            return

        conn.execute("""
            INSERT INTO uploads
                (sha256, filename, status, created_at)
            VALUES (?, ?, 'uploading', ?)
            ON CONFLICT(sha256) DO UPDATE SET
                status='uploading',
                filename=excluded.filename
        """, (
            digest,
            video.name,
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()

        try:
            youtube = build(
                "youtube", "v3",
                credentials=get_credentials(),
                cache_discovery=False,
            )

            request = youtube.videos().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": f"Random Word: {video.stem}"[:100],
                        "description": (
                            f"A random word: {video.stem}\n"
                            "#Shorts #RandomWord"
                        ),
                        "tags": ["random word", "vocabulary", "shorts"],
                        "categoryId": "27",
                    },
                    "status": {
                        "privacyStatus": "private",
                    },
                },
                media_body=MediaFileUpload(
                    str(video),
                    mimetype="video/mp4",
                    resumable=True,
                ),
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"Upload progress: {status.progress():.0%}")

            video_id = response["id"]
            conn.execute("""
                UPDATE uploads
                SET status='uploaded', video_id=?
                WHERE sha256=?
            """, (video_id, digest))
            conn.commit()

            logging.info("Uploaded %s as %s", video.name, video_id)
            print("\nUpload successful!")
            print("Title:", f"Random Word: {video.stem}")
            print("Privacy: Private")
            print("YouTube URL:", f"https://www.youtube.com/watch?v={video_id}")

        except Exception as exc:
            conn.execute("""
                UPDATE uploads SET status='failed'
                WHERE sha256=?
            """, (digest,))
            conn.commit()
            logging.exception("Upload failed for %s", video.name)
            print("Upload failed:", exc)
            print("Check logs/upload.log and YouTube Studio before retrying.")
            raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()