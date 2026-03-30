import urllib.request
import urllib.parse
import json
import re
import subprocess
import sys
from config import YOUTUBE_API_KEY

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
    unique = [v for v in set(video_ids) if v]
    if not unique:
        return {}
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


def find_replacement(search_query, channel_id, exclude_ids):
    # Сначала ищем на родном канале
    for use_channel in [True, False]:
        params = {
            "part": "snippet",
            "q": search_query,
            "eventType": "live",
            "type": "video",
            "key": YOUTUBE_API_KEY,
        }
        if use_channel:
            params["channelId"] = channel_id

        url = "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(params)
        data = api_get(url)
        candidates = [
            item["id"]["videoId"] for item in data.get("items", [])
            if item["id"]["videoId"] not in exclude_ids
        ]
        if not candidates:
            continue

        statuses = check_videos(candidates)
        for cid in candidates:
            if is_ok(statuses.get(cid, {})):
                return cid

    return None


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
    streams = config["streams"]

    # Собираем все ID для проверки
    all_ids = []
    for s in streams.values():
        all_ids.append(s["primary"])
        all_ids.append(s["current"])
        if s.get("fallback"):
            all_ids.append(s["fallback"])

    print(f"Проверяю стримы через YouTube API...\n")
    statuses = check_videos(all_ids)

    git_messages = []
    config_changed = False

    for key, s in streams.items():
        name = s["name"]
        primary = s["primary"]
        fallback = s.get("fallback")
        current = s["current"]
        channel_id = s["channel_id"]
        search_query = s["search"]

        primary_ok = is_ok(statuses.get(primary, {}))
        current_ok = is_ok(statuses.get(current, {}))

        # Если primary ожил и сейчас стоит не primary — возвращаем
        if primary_ok and current != primary:
            print(f"🔄 [{name}] оригинал ожил! Возвращаю {primary} (был {current})")
            update_html(current, primary)
            s["current"] = primary
            config_changed = True
            git_messages.append(f"restored {primary}")
            continue

        # Если текущий OK — всё хорошо
        if current_ok:
            print(f"✅ [{name}] {current} — OK")
            continue

        # Текущий сломан
        reason = "удалён" if statuses.get(current, {}).get("live") == "gone" else "embed запрещён" if not statuses.get(current, {}).get("embeddable") else "оффлайн"
        print(f"❌ [{name}] {current} ({reason})")

        # Пробуем fallback если есть
        new_id = None
        if fallback and fallback != current:
            fallback_ok = is_ok(statuses.get(fallback, {}))
            if fallback_ok:
                new_id = fallback
                print(f"   ↩️  Переключаю на fallback: {fallback}")

        # Если fallback тоже не работает — ищем новый
        if not new_id:
            print(f"   🔍 Ищу замену...")
            exclude = {primary, current, fallback} - {None}
            new_id = find_replacement(search_query, channel_id, exclude)
            if new_id:
                print(f"   ✅ Нашёл замену: {new_id}")
            else:
                print(f"   ❌ Замену не нашёл")

        if new_id:
            update_html(current, new_id)
            s["current"] = new_id
            config_changed = True
            git_messages.append(f"{current} -> {new_id} ({name})")

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
