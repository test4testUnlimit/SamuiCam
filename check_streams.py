import urllib.request
import json
import re
from config import YOUTUBE_API_KEY

HTML_FILES = [
    "index.html",
    "180-2/360.html",
    "180-3/index.html",
]

def get_video_ids(filepath):
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    return re.findall(r'youtube\.com/embed/([A-Za-z0-9_-]{11})', content)

def check_videos(video_ids):
    ids_param = ",".join(set(video_ids))
    url = (
        f"https://www.googleapis.com/youtube/v3/videos"
        f"?part=status,snippet&id={ids_param}&key={YOUTUBE_API_KEY}"
    )
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())

    results = {}
    for item in data.get("items", []):
        vid_id = item["id"]
        embeddable = item["status"].get("embeddable", False)
        live = item["snippet"].get("liveBroadcastContent", "none")
        results[vid_id] = {"embeddable": embeddable, "live": live}

    # IDs not returned by API = deleted/private
    for vid_id in set(video_ids):
        if vid_id not in results:
            results[vid_id] = {"embeddable": False, "live": "gone"}

    return results

def main():
    all_ids = []
    file_ids = {}
    for filepath in HTML_FILES:
        ids = get_video_ids(filepath)
        file_ids[filepath] = ids
        all_ids.extend(ids)

    print("Проверяю стримы через YouTube API...\n")
    results = check_videos(all_ids)

    for filepath, ids in file_ids.items():
        print(f"=== {filepath} ===")
        for vid_id in ids:
            info = results.get(vid_id, {})
            live = info.get("live", "?")
            embeddable = info.get("embeddable", False)

            if live == "gone":
                status = "❌ УДАЛЁН / ПРИВАТНЫЙ"
            elif not embeddable:
                status = "⚠️  EMBED ЗАПРЕЩЁН (Error 153)"
            elif live == "live":
                status = "✅ LIVE + embed OK"
            elif live == "none":
                status = "⚠️  НЕ LIVE (запись или оффлайн)"
            else:
                status = f"⚠️  статус: {live}"

            print(f"  {vid_id}  {status}")
        print()

if __name__ == "__main__":
    main()
