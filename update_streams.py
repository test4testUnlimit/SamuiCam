import urllib.request
import urllib.parse
import json
import re
import subprocess
import sys
from config import YOUTUBE_API_KEY

CHANNEL_ID = "UCmYyJaUxYiF5IbLx-0jFXHQ"  # The Real Samui Webcam

HTML_FILES = [
    "index.html",
    "180-2/360.html",
    "180-3/index.html",
]

CONFIG_FILE = "streams_config.json"


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


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


def is_ok(info):
    return info.get("embeddable", False) and info.get("live") in ("live", "upcoming")


def find_replacement(search_query):
    # Сначала ищем на канале
    params = urllib.parse.urlencode({
        "part": "snippet",
        "q": search_query,
        "channelId": CHANNEL_ID,
        "eventType": "live",
        "type": "video",
        "key": YOUTUBE_API_KEY,
    })
    data = api_get(f"https://www.googleapis.com/youtube/v3/search?{params}")
    candidates = [item["id"]["videoId"] for item in data.get("items", [])]

    # Если на канале не нашли — ищем глобально
    if not candidates:
        params2 = urllib.parse.urlencode({
            "part": "snippet",
            "q": search_query,
            "eventType": "live",
            "type": "video",
            "key": YOUTUBE_API_KEY,
        })
        data2 = api_get(f"https://www.googleapis.com/youtube/v3/search?{params2}")
        candidates = [item["id"]["videoId"] for item in data2.get("items", [])]

    if not candidates:
        return None

    statuses = check_videos(candidates)
    for cid in candidates:
        if is_ok(statuses.get(cid, {})):
            return cid
    return None


def get_html_ids():
    all_ids = []
    for filepath in HTML_FILES:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        all_ids.extend(re.findall(r'youtube\.com/embed/([A-Za-z0-9_-]{11})', content))
    return all_ids


def update_html(old_id, new_id):
    changed = []
    for filepath in HTML_FILES:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        if f"youtube.com/embed/{old_id}" in content:
            content = content.replace(
                f"youtube.com/embed/{old_id}",
                f"youtube.com/embed/{new_id}"
            )
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            changed.append(filepath)
    return changed


def git_push(messages):
    msg = "Auto-update streams: " + "; ".join(messages)
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", msg], check=True)
    subprocess.run(["git", "push"], check=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== SamuiCam stream updater ===\n")

    config = load_config()
    preferred = config["preferred"]   # оригинальные ID — никогда не меняем
    current = config["current"]       # текущие ID в HTML

    # Все ID которые сейчас в HTML
    html_ids = get_html_ids()
    all_ids_to_check = list(set(html_ids) | set(preferred.keys()))

    print(f"Проверяю {len(all_ids_to_check)} стримов...\n")
    statuses = check_videos(all_ids_to_check)

    git_messages = []
    config_changed = False

    for pref_id, search_query in preferred.items():
        cur_id = current.get(pref_id, pref_id)
        pref_status = statuses.get(pref_id, {})
        cur_status = statuses.get(cur_id, {})

        # Предпочтительный ожил — возвращаемся к нему
        if is_ok(pref_status) and cur_id != pref_id:
            print(f"🔄 {pref_id} снова доступен! Возвращаю оригинал (заменяю {cur_id})")
            update_html(cur_id, pref_id)
            current[pref_id] = pref_id
            config_changed = True
            git_messages.append(f"restored {pref_id}")

        # Текущий сломан — ищем замену
        elif not is_ok(cur_status):
            reason = "удалён" if cur_status.get("live") == "gone" else "embed запрещён" if not cur_status.get("embeddable") else "оффлайн"
            print(f"❌ {cur_id} ({reason}) — ищу замену...")
            new_id = find_replacement(search_query)
            if new_id and new_id != cur_id:
                print(f"   ✅ Нашёл: {new_id}")
                update_html(cur_id, new_id)
                current[pref_id] = new_id
                config_changed = True
                git_messages.append(f"{cur_id} -> {new_id}")
            elif not new_id:
                print(f"   ❌ Замену не нашёл")
            else:
                print(f"   ✅ Уже стоит лучшая версия")

        else:
            print(f"✅ {cur_id} — OK")

    if not git_messages:
        print("\n✅ Всё в порядке, изменений нет.")
        return

    if config_changed:
        save_config(config)

    print("\nПушу изменения на GitHub...")
    git_push(git_messages)
    print("✅ Готово! Сайт обновится через ~30 секунд.")


if __name__ == "__main__":
    main()
