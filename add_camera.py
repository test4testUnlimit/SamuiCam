import urllib.request
import urllib.parse
import json
import re
import subprocess
import sys
from config import YOUTUBE_API_KEY

BUILDER_FILE = "builder/index.html"
VIEW_FILE    = "view/index.html"
CONFIG_FILE  = "streams_config.json"

def api_get(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())

def extract_video_id(url):
    patterns = [
        r'(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def get_video_info(video_id):
    url = (
        f"https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,status&id={video_id}&key={YOUTUBE_API_KEY}"
    )
    data = api_get(url)
    items = data.get("items", [])
    if not items:
        return None
    item = items[0]
    return {
        "video_id":   video_id,
        "title":      item["snippet"]["title"],
        "channel_id": item["snippet"]["channelId"],
        "channel":    item["snippet"]["channelTitle"],
        "live":       item["snippet"].get("liveBroadcastContent", "none"),
        "embeddable": item["status"].get("embeddable", False),
    }

def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def slug(name):
    s = name.lower()
    s = re.sub(r'[^a-z0-9]+', '_', s)
    return s.strip('_')

def add_to_builder(video_id, name):
    with open(BUILDER_FILE, encoding="utf-8") as f:
        content = f.read()
    if video_id in content:
        print(f"  ⚠️  {video_id} уже есть в builder/index.html")
        return
    # Ищем последний { id: "..." } и вставляем после него
    last = list(re.finditer(r'\{\s*id:\s*"[^"]+"\s*\}', content))
    if not last:
        print("  ❌ Не нашёл место для вставки в builder/index.html")
        return
    pos = last[-1].end()
    insert = f',\n                {{ id: "{video_id}" }}'
    content = content[:pos] + insert + content[pos:]
    with open(BUILDER_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✅ Добавлено в builder/index.html")

def add_to_view(video_id, name):
    with open(VIEW_FILE, encoding="utf-8") as f:
        content = f.read()
    if video_id in content:
        print(f"  ⚠️  {video_id} уже есть в view/index.html")
        return
    # Ищем последнюю запись в STREAMS и вставляем после неё
    last = list(re.finditer(r'"[A-Za-z0-9_-]{11}":\s*"[^"]+"', content))
    if not last:
        print("  ❌ Не нашёл место для вставки в view/index.html")
        return
    pos = last[-1].end()
    insert = f',\n            "{video_id}": "{name}"'
    content = content[:pos] + insert + content[pos:]
    with open(VIEW_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✅ Добавлено в view/index.html")

def add_to_config(config, video_id, name, channel_id, location):
    key = slug(name)
    # Если такой ключ уже есть — добавляем цифру
    base = key
    i = 2
    while key in config["streams"]:
        key = f"{base}_{i}"
        i += 1

    config["streams"][key] = {
        "name":       name,
        "primary":    video_id,
        "fallback":   None,
        "current":    video_id,
        "search":     name + " live webcam",
        "channel_id": channel_id,
        "location":   location
    }

    # Добавляем channel если новый
    if channel_id not in config["channels"]:
        config["channels"][channel_id] = "Unknown Channel"
        print(f"  ℹ️  Новый канал добавлен: {channel_id}")

    print(f"  ✅ Добавлено в streams_config.json как '{key}'")
    return config

def git_push(name):
    msg = f"add camera: {name}"
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", msg], check=True)
    subprocess.run(["git", "push"], check=True)

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("═══════════════════════════════════")
    print("  SamuiCam — add camera")
    print("═══════════════════════════════════\n")

    url = input("YouTube ссылка: ").strip()
    video_id = extract_video_id(url)
    if not video_id:
        print("❌ Не удалось извлечь Video ID из ссылки")
        return

    print(f"\n🔍 Проверяю {video_id}...")
    info = get_video_info(video_id)
    if not info:
        print("❌ Видео не найдено")
        return

    print(f"\n📺 Найдено:")
    print(f"   Канал:  {info['channel']}")
    print(f"   Тайтл: {info['title']}")
    print(f"   Live:  {info['live']}")
    print(f"   Embed: {'✅' if info['embeddable'] else '❌'}")

    if not info['embeddable']:
        print("\n⚠️  Embed запрещён — камера не будет работать на сайте!")
        go = input("Всё равно добавить? (y/N): ").strip().lower()
        if go != 'y':
            return

    if info['live'] == 'none':
        print("\n⚠️  Это не live стрим — это запись или оффлайн!")
        go = input("Всё равно добавить? (y/N): ").strip().lower()
        if go != 'y':
            return

    # Название
    print(f"\nНазвание для сайта:")
    print(f"  [{info['title']}]")
    custom = input("Enter = оставить, или введи своё: ").strip()
    name = custom if custom else info['title']

    # Локация
    location = input("Локация (напр. Koh Samui, Thailand): ").strip()
    if not location:
        location = "Unknown"

    print(f"\n📦 Добавляю...")
    config = load_config()
    config = add_to_config(config, video_id, name, info['channel_id'], location)
    save_config(config)
    add_to_builder(video_id, name)
    add_to_view(video_id, name)

    print(f"\n🚀 Пушу на GitHub...")
    git_push(name)

    print(f"\n✅ Готово! '{name}' появится на сайте через ~30 секунд.")

if __name__ == "__main__":
    main()