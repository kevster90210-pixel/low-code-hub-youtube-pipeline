#!/usr/bin/env python3
"""
The Low Code Hub — NotebookLM to YouTube Pipeline
RSS → NotebookLM (real podcast audio) → Video → Vizard → YouTube
Processes ONE article at a time to avoid wasting credits.
"""
import asyncio
import os
import json
import time
import subprocess
from pathlib import Path
import feedparser
import httpx

# ───────────────────────────────────────────
# CONFIG — all from environment variables
# ───────────────────────────────────────────
RSS_URL = os.environ["RSS_URL"]
VIZARD_API_KEY = os.environ["VIZARD_API_KEY"]
VIZARD_SOCIAL_ID = os.environ.get("VIZARD_SOCIAL_ID", "dml6YXJkLTEtMTc2Mzlx")
PROCESSED_FILE = "/data/processed.json"
NOTEBOOKLM_SESSION_FILE = "/root/.notebooklm/storage_state.json"

# Write session file from env var at startup
def setup_notebooklm_session():
    session_json = os.environ.get("NOTEBOOKLM_SESSION")
    if not session_json:
        raise Exception("NOTEBOOKLM_SESSION env var not set")
    # Validate it's proper JSON
    try:
        session_data = json.loads(session_json)
    except json.JSONDecodeError as e:
        raise Exception(f"NOTEBOOKLM_SESSION is not valid JSON: {e}")
    # Check session has cookies
    cookies = session_data.get("cookies", [])
    if not cookies:
        raise Exception("NOTEBOOKLM_SESSION has no cookies — session may be expired. Please refresh your session.")
    # Warn if cookies look expired
    import datetime
    now_ts = datetime.datetime.utcnow().timestamp()
    valid_cookies = [c for c in cookies if c.get("expires", now_ts + 1) > now_ts]
    if not valid_cookies:
        raise Exception("All cookies in NOTEBOOKLM_SESSION are expired. Please refresh your session and update the env var.")
    os.makedirs("/root/.notebooklm", exist_ok=True)
    with open(NOTEBOOKLM_SESSION_FILE, "w") as f:
        f.write(session_json)
    print(f"[NotebookLM] Session file written to {NOTEBOOKLM_SESSION_FILE} ✅ ({len(valid_cookies)} valid cookies)")

# ───────────────────────────────────────────
# STEP 1 — Get ONE new article from RSS
# ───────────────────────────────────────────
def get_one_new_article():
    print("[RSS] Fetching feed...")
    feed = feedparser.parse(RSS_URL)
    processed = []
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE) as f:
            processed = json.load(f)
    for entry in feed.entries:
        if entry.link not in processed:
            print(f"[RSS] Found new article: {entry.title}")
            return entry
    print("[RSS] No new articles found.")
    return None

def mark_processed(url):
    processed = []
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE) as f:
            processed = json.load(f)
    processed.append(url)
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    with open(PROCESSED_FILE, "w") as f:
        json.dump(processed, f)

# ───────────────────────────────────────────
# STEP 2 — Generate NotebookLM podcast
# ───────────────────────────────────────────
async def generate_podcast(article_url: str, title: str) -> str:
    print("[NotebookLM] Starting podcast generation...")
    from notebooklm import NotebookLMClient
    try:
        async with await NotebookLMClient.from_storage() as client:
            print("[NotebookLM] Creating notebook...")
            nb = await client.notebooks.create(title[:100])
            print(f"[NotebookLM] Adding source: {article_url}")
            await client.sources.add_url(nb.id, article_url, wait=True)
            print("[NotebookLM] Source added ✅")
            print("[NotebookLM] Generating audio overview (takes 5-10 mins)...")
            try:
                audio_overview = await client.artifacts.generate_audio(
                    nb.id,
                    instructions="Create an engaging, informative deep-dive podcast for tech professionals",
                    wait=True,
                    timeout=900
                )
                print("[NotebookLM] Audio generation complete ✅")
            except Exception as rpc_err:
                err_str = str(rpc_err)
                if "CREATE_ARTIFACT" in err_str or "RPC" in err_str:
                    raise Exception(
                        f"NotebookLM RPC error during audio generation: {rpc_err}\n"
                        "This usually means your NOTEBOOKLM_SESSION cookies have expired. "
                        "Please refresh your browser session on notebooklm.google.com, "
                        "export the new storage_state.json, and update the NOTEBOOKLM_SESSION env var."
                    )
                raise
            output_path = f"/tmp/podcast_{nb.id}.mp3"
            await client.artifacts.download_audio(nb.id, output_path)
            print(f"[NotebookLM] Downloaded to {output_path} ✅")
            await client.notebooks.delete(nb.id)
            return output_path
    except Exception as e:
        if "session" in str(e).lower() or "expired" in str(e).lower() or "auth" in str(e).lower():
            raise
        if "CREATE_ARTIFACT" in str(e) or "RPC" in str(e):
            raise Exception(
                f"NotebookLM RPC error: {e}\n"
                "This usually means your NOTEBOOKLM_SESSION cookies have expired. "
                "Please refresh your browser session on notebooklm.google.com, "
                "export the new storage_state.json, and update the NOTEBOOKLM_SESSION env var."
            )
        raise

# ───────────────────────────────────────────
# STEP 3 — Convert MP3 to MP4 video
# ───────────────────────────────────────────
def create_video(audio_path: str, title: str) -> str:
    print("[FFmpeg] Creating video...")
    output_path = audio_path.replace(".mp3", ".mp4")
    safe_title = title.replace("'", "\\'").replace(":", "\\:")[:80]
    cmd = [
        "ffmpeg", "-y",
        "-i", audio_path,
        "-f", "lavfi",
        "-i", "color=c=black:size=1280x720:rate=30",
        "-vf", (
            f"drawtext=text='{safe_title}':"
            "fontcolor=white:fontsize=36:"
            "x=(w-text_w)/2:y=(h-text_h)/2-60:line_spacing=10,"
            "drawtext=text='The Low Code Hub':"
            "fontcolor=#FF6B35:fontsize=28:"
            "x=(w-text_w)/2:y=(h-text_h)/2+60"
        ),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        "-pix_fmt", "yuv420p",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"FFmpeg failed: {result.stderr}")
    print(f"[FFmpeg] Video created ✅")
    return output_path

# ───────────────────────────────────────────
# STEP 4 — Upload & Publish via Vizard
# ───────────────────────────────────────────
def publish_via_vizard(video_path: str, title: str, description: str) -> str:
    headers = {"VIZARDAI_API_KEY": VIZARD_API_KEY}
    base_url = "https://elb-api.vizard.ai/hvizard-server-front/open-api/v1"
    print("[Vizard] Submitting video...")
    with open(video_path, "rb") as f:
        submit_resp = httpx.post(
            f"{base_url}/project/create",
            headers=headers,
            files={"video": ("video.mp4", f, "video/mp4")},
            data={"title": title[:100]},
            timeout=300
        )
    if submit_resp.status_code not in (200, 201):
        raise Exception(f"Vizard submit failed: {submit_resp.text}")
    project_id = submit_resp.json()["projectId"]
    print(f"[Vizard] Project created: {project_id}")
    print("[Vizard] Waiting for processing...")
    for attempt in range(60):
        time.sleep(10)
        poll_resp = httpx.get(
            f"{base_url}/project/query/{project_id}",
            headers=headers,
            timeout=30
        )
        data = poll_resp.json()
        status = data.get("status")
        print(f"[Vizard] Status: {status} (attempt {attempt + 1})")
        if status == "completed":
            videos = data.get("videos", [])
            if not videos:
                raise Exception("Vizard returned no videos")
            final_video_id = videos[0]["id"]
            print(f"[Vizard] Processing complete ✅ finalVideoId: {final_video_id}")
            break
        elif status in ("failed", "error"):
            raise Exception(f"Vizard processing failed: {data}")
    else:
        raise Exception("Vizard timed out after 10 minutes")
    print("[Vizard] Publishing to YouTube...")
    publish_resp = httpx.post(
        f"{base_url}/project/publish-video",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "finalVideoId": final_video_id,
            "socialAccountId": VIZARD_SOCIAL_ID,
            "platform": "youtube",
            "title": title[:100],
            "description": description,
            "privacyStatus": "public"
        },
        timeout=60
    )
    if publish_resp.status_code not in (200, 201):
        raise Exception(f"Vizard publish failed: {publish_resp.text}")
    print("[Vizard] Published to YouTube ✅")
    return final_video_id

# ───────────────────────────────────────────
# MAIN
# ───────────────────────────────────────────
async def main():
    setup_notebooklm_session()
    print("\n🚀 Starting NotebookLM → YouTube Pipeline")
    print("=" * 50)
    article = get_one_new_article()
    if not article:
        print("✅ Nothing to process. Done!")
        return
    title = article.title
    url = article.link
    description = (
        f"AI-generated podcast overview of: {title}\n\n"
        f"Source: {url}\n\n"
        f"Generated by The Low Code Hub automated pipeline."
    )
    print(f"\n📰 Processing: {title}")
    print(f"🔗 URL: {url}")
    audio_path = None
    video_path = None
    try:
        audio_path = await generate_podcast(url, title)
        video_path = create_video(audio_path, title)
        publish_via_vizard(video_path, title, description)
        mark_processed(url)
        print(f"\n🎉 SUCCESS! Video published to The Low Code Hub YouTube channel.")
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        raise
    finally:
        for f in [audio_path, video_path]:
            if f and os.path.exists(f):
                os.remove(f)

if __name__ == "__main__":
    asyncio.run(main())
