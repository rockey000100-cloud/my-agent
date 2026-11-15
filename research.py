"""Find viral videos in a niche, analyze why they work, find gaps, and refine our script."""
import datetime
import json
import os

from google import genai
from google.genai import types
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def _ask(prompt, max_tokens=2000, json_mode=False):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json" if json_mode else "text/plain"
    )
    return client.models.generate_content(model=MODEL, contents=prompt, config=cfg).text.strip()


def _json(text):
    text = text.strip().strip("`")
    if text.startswith("json"):
        text = text[4:]
    return json.loads(text)


def find_viral(topic, n=5):
    yt = build("youtube", "v3", developerKey=os.environ["YOUTUBE_API_KEY"])
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = [
        i["id"]["videoId"]
        for i in yt.search().list(
            q=topic, part="id", type="video", order="viewCount",
