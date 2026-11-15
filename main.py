"""YouTube Shorts automation: topic -> script -> voice -> footage -> edit -> upload.

Usage:  python main.py "5 amazing facts about space"
Env:    GEMINI_API_KEY, YOUTUBE_API_KEY, PEXELS_API_KEY
File:   client_secret.json (YouTube OAuth, Desktop app)
"""
import asyncio
import json
import os
import sys

import edge_tts
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from research import _ask, _json, get_viral_insights, refine_script
from moviepy.editor import AudioFileClip, VideoFileClip, concatenate_videoclips, vfx

W, H = 1080, 1920
VOICE = "hi-IN-MadhurNeural"  # English: "en-US-GuyNeural"
PRIVACY = "private"  # change to "public" after you check the video
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
os.makedirs("work", exist_ok=True)


def make_script(topic, insights=""):
    prompt = (
        f"Write a 45-second YouTube Short about: {topic}.\n"
        "Reply ONLY with JSON: {\"title\": str, \"description\": str, "
        "\"tags\": [str], \"scenes\": [{\"narration\": str, "
        "\"keyword\": str}]}. 6-8 scenes, keyword = English stock-video "
        "search term. Strong hook in scene 1.\n"
        f"Learn from these viral insights, but write fully ORIGINAL content:\n{insights}"
    )
    return _json(_ask(prompt, 2000, json_mode=True))


async def make_voice(text, path):
    await edge_tts.Communicate(text, VOICE).save(path)


def get_footage(keyword, path):
    r = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": os.environ["PEXELS_API_KEY"]},
        params={"query": keyword, "orientation": "portrait", "per_page": 5},
        timeout=30,
    )
    videos = r.json().get("videos", [])
    if not videos:
        raise RuntimeError(f"No footage for: {keyword}")
    files = sorted(videos[0]["video_files"], key=lambda f: f["width"])
    pick = next((f for f in files if f["width"] >= 720), files[-1])
    with open(path, "wb") as f:
        f.write(requests.get(pick["link"], timeout=120).content)


def build_scene(video_path, audio_path):
    audio = AudioFileClip(audio_path)
    clip = VideoFileClip(video_path).without_audio()
    clip = clip.resize(max(W / clip.w, H / clip.h))
    clip = vfx.crop(clip, width=W, height=H, x_center=clip.w / 2, y_center=clip.h / 2)
    if clip.duration < audio.duration:
        clip = clip.fx(vfx.loop, duration=audio.duration)
    else:
        clip = clip.subclip(0, audio.duration)
    return clip.set_audio(audio)


def youtube_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload(path, data):
    yt = youtube_service()
    body = {
        "snippet": {
            "title": data["title"][:100],
            "description": data["description"] + "\n\n#Shorts",
            "tags": data["tags"],
            "categoryId": "27",
        },
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(path, chunksize=-1, resumable=True)
    res = yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    print("Uploaded: https://youtube.com/shorts/" + res["id"])


def main():
    topic = " ".join(sys.argv[1:]) or "amazing facts about space"
    insights = get_viral_insights(topic)
    data = refine_script(make_script(topic, insights), insights)
    print("Script ready:", data["title"])

    clips = []
    for i, scene in enumerate(data["scenes"]):
        a, v = f"work/{i}.mp3", f"work/{i}.mp4"
        asyncio.run(make_voice(scene["narration"], a))
        get_footage(scene["keyword"], v)
        clips.append(build_scene(v, a))
        print(f"Scene {i + 1}/{len(data['scenes'])} done")

    out = "work/final.mp4"
    concatenate_videoclips(clips, method="compose").write_videofile(
        out, fps=30, codec="libx264", audio_codec="aac"
    )
    upload(out, data)


if __name__ == "__main__":
    main()
