import urllib.request
import urllib.parse
import json
import re
import subprocess
import sys
from config import YOUTUBE_API_KEY

# Конфиг: video_id -> поисковый запрос для замены
STREAMS = {
    "3N3ZwIB_X4Y": "Crystal Bay Yacht Club Lamai Koh Samui Beach Webcam",
    "Tpj0cmMVOd0": "Baobab Cam Lamai Koh Samui Live Beach Webcam",
    "Fw9hgttWzIg": "Crystal Bay Beach Resort Lamai Koh Samui Live Beach Webcam",
    "NTTtqzL5OWI": "Crystal Bay Beach Resort Panoramic Lamai Koh Samui",
    "LGNYKz4yziE": "Crystal Bay Yacht Club Lamai Koh Samui Beach Panoramic Webcam",
}

CHANNEL_ID = "UCmYyJaUxYiF5IbLx-0jFXHQ"  # The Real Samui Webcam

HTML_FILES = [
    "index.html",
    "180-2/360.html",
    "180-3/index.html",
]


def api_get(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def check_videos(video_ids):
    unique = list(set(video_ids))
    url = (
        "https://www.googleapis.com/youtube/v3/videos"
        f"?part=status,snippet&id={','.join(unique)}&key={YOUTUBE_API_KEY}"
    )
    data = api_get(url)
    results = {}
    for item in data.get("items", []):
        vid_id = item["id"]
        results[vid_id] = {
            "embeddable": item["status"].get("embeddable", False),
            "live": item["snippet"].get("liveBroadcastContent", "none"),
        }
    for vid_id in unique:
        if vid_id not in results:
            results[vid_id] = {"embeddable": False, "live": "gone"}
    return results


def is_broken(info):
    return not info["embeddable"] or info["live"] not in ("live", "upcoming")


def find_replacement(broken_id):
    query = STREAMS.get(broken_id, "Koh Samui live webcam")
    params = urllib.parse.urlencode({
        "part": "snippet",
        "q": query,
        "channelId": CHANNEL_ID,
        "eventType": "live",
        "type": "video",
        "key": YOUTUBE_API_KEY,
    })
    data = api_get(f"https://www.googleapis.com/youtube/v3/search?{params}")
    candidates = [item["id"]["videoId"] for item in data.get("items", [])]

    if not candidates:
        # Попробуем без фильтра по каналу
        params2 = urllib.parse.urlencode({
            "part": "snippet",
            "q": query,
            "eventType": "live",
            "type": "video",
            "key": YOUTUBE_API_KEY,
        })
        data2 = api_get(f"https://www.googleapis.com/youtube/v3/search?{params2}")
        candidates = [item["id"]["videoId"] for item in data2.get("items", [])]

    if not candidates:
        return None

    # Проверяем embeddable
    check = check_videos(candidates)
    for cid in candidates:
        if not is_broken(check.get(cid, {})):
            return cid

    return None


def update_html_files(replacements):
    if not replacements:
        return []
    changed = []
    for filepath in HTML_FILES:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        original = content
        for old_id, new_id in replacements.items():
            content = content.replace(
                f"youtube.com/embed/{old_id}",
                f"youtube.com/embed/{new_id}"
            )
        if content != original:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            changed.append(filepath)
    return changed


def git_push(replacements):
    msg_parts = [f"{old} -> {new}" for old, new in replacements.items()]
    msg = "Auto-update broken streams: " + ", ".join(msg_parts)
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", msg], check=True)
    subprocess.run(["git", "push"], check=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== SamuiCam stream updater ===\n")

    # Собираем все video ID из HTML
    all_ids = []
    for filepath in HTML_FILES:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        ids = re.findall(r'youtube\.com/embed/([A-Za-z0-9_-]{11})', content)
        all_ids.extend(ids)

    print(f"Найдено {len(set(all_ids))} уникальных стримов. Проверяю...\n")
    statuses = check_videos(all_ids)

    broken = {}
    for vid_id, info in statuses.items():
        if is_broken(info):
            reason = "удалён" if info["live"] == "gone" else (
                "embed запрещён" if not info["embeddable"] else "не в эфире"
            )
            broken[vid_id] = reason

    if not broken:
        print("✅ Все стримы живые и работают. Ничего менять не нужно.")
        return

    print(f"⚠️  Сломанных стримов: {len(broken)}\n")
    replacements = {}

    for vid_id, reason in broken.items():
        print(f"❌ {vid_id} ({reason}) — ищу замену...")
        new_id = find_replacement(vid_id)
        if new_id:
            print(f"   ✅ Нашёл замену: {new_id}")
            replacements[vid_id] = new_id
        else:
            print(f"   ❌ Замену не нашёл, пропускаю")

    if not replacements:
        print("\nНичего заменить не удалось.")
        return

    print(f"\nОбновляю HTML файлы...")
    changed = update_html_files(replacements)
    print(f"Изменено файлов: {len(changed)}")

    print("Пушу на GitHub...")
    git_push(replacements)
    print("\n✅ Готово! Сайт обновится через ~30 секунд.")


if __name__ == "__main__":
    main()
