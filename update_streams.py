import urllib.request
import urllib.parse
import json
import re
import subprocess
import sys
from config import YOUTUBE_API_KEY

# ── Файлы проекта ────────────────────────────────────────
BUILDER_FILE = "builder/index.html"
VIEW_FILE    = "view/index.html"
CONFIG_FILE  = "streams_config.json"


# ══ CONFIG ═══════════════════════════════════════════════

def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ══ YOUTUBE API ══════════════════════════════════════════

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
            "live":       item["snippet"].get("liveBroadcastContent", "none"),
        }
    for vid_id in unique:
        if vid_id not in results:
            results[vid_id] = {"embeddable": False, "live": "gone"}
    return results

def is_ok(info):
    return info.get("embeddable", False) and info.get("live") in ("live", "upcoming")

def find_replacement(search_query, channel_id, exclude_ids):
    for use_channel in [True, False]:
        params = {
            "part":      "snippet",
            "q":         search_query,
            "eventType": "live",
            "type":      "video",
            "key":       YOUTUBE_API_KEY,
        }
        if use_channel:
            params["channelId"] = channel_id

        url  = "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(params)
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


# ══ BUILDER — читаем и обновляем ID ══════════════════════

def get_builder_ids():
    """Вытаскиваем все { id: "XXX" } из builder/index.html"""
    with open(BUILDER_FILE, encoding="utf-8") as f:
        content = f.read()
    return re.findall(r'\{\s*id:\s*"([^"]+)"', content)

def replace_id_in_builder(old_id, new_id):
    with open(BUILDER_FILE, encoding="utf-8") as f:
        content = f.read()
    new_content = content.replace(f'id: "{old_id}"', f'id: "{new_id}"')
    if new_content == content:
        return False
    with open(BUILDER_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


# ══ VIEW — таблица редиректов ═════════════════════════════

def load_redirects():
    """Читаем текущий CAM_REDIRECTS из view/index.html"""
    with open(VIEW_FILE, encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'const CAM_REDIRECTS = \{([^}]*)\}', content, re.DOTALL)
    if not m:
        return {}
    block = m.group(1)
    redirects = {}
    for match in re.finditer(r'"([^"]+)":\s*"([^"]+)"', block):
        redirects[match.group(1)] = match.group(2)
    return redirects

def save_redirects(redirects):
    """Записываем обновлённый CAM_REDIRECTS в view/index.html"""
    with open(VIEW_FILE, encoding="utf-8") as f:
        content = f.read()

    if not redirects:
        new_block = "const CAM_REDIRECTS = {};"
    else:
        lines = [f'            "{old}": "{new}"' for old, new in redirects.items()]
        new_block = "const CAM_REDIRECTS = {\n" + ",\n".join(lines) + "\n        };"

    new_content = re.sub(
        r'// ══ CAM_REDIRECTS.*?// ══ END CAM_REDIRECTS ══',
        f'// ══ CAM_REDIRECTS — old ID → new ID (auto-maintained by update_streams.py) ══\n        {new_block}\n        // ══ END CAM_REDIRECTS ══',
        content,
        flags=re.DOTALL
    )

    if new_content == content:
        print("  ⚠️  Не удалось записать редирект в view/index.html — проверь маркеры")
        return False

    with open(VIEW_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


# ══ GIT ══════════════════════════════════════════════════

def git_push(messages):
    msg = "auto-update streams: " + "; ".join(messages)
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-m", msg], check=True)
    subprocess.run(["git", "push"],              check=True)


# ══ MAIN ═════════════════════════════════════════════════

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("═══════════════════════════════════")
    print("  SamuiCam — stream updater v2")
    print("═══════════════════════════════════\n")

    config    = load_config()
    streams   = config["streams"]
    redirects = load_redirects()

    # Собираем все ID для проверки
    all_ids = []
    for s in streams.values():
        all_ids += [s["primary"], s["current"], s.get("fallback")]
    all_ids = [i for i in all_ids if i]

    print("Проверяю стримы через YouTube API...\n")
    statuses = check_videos(all_ids)

    git_messages  = []
    config_changed = False

    for key, s in streams.items():
        name       = s["name"]
        primary    = s["primary"]
        fallback   = s.get("fallback")
        current    = s["current"]
        channel_id = s["channel_id"]
        search_q   = s["search"]

        primary_ok = is_ok(statuses.get(primary, {}))
        current_ok = is_ok(statuses.get(current, {}))

        # Оригинал ожил — возвращаем
        if primary_ok and current != primary:
            print(f"🔄 [{name}] оригинал ожил! Возвращаю {primary} (был {current})")
            if replace_id_in_builder(current, primary):
                redirects[current] = primary          # старый URL → новый
                s["current"]       = primary
                config_changed     = True
                git_messages.append(f"restored {name}")
            continue

        # Всё ок
        if current_ok:
            print(f"✅ [{name}] {current} — OK")
            continue

        # Текущий сломан
        info   = statuses.get(current, {})
        reason = ("удалён"           if info.get("live") == "gone"
                  else "embed запрещён" if not info.get("embeddable")
                  else "оффлайн")
        print(f"❌ [{name}] {current} ({reason})")

        # Пробуем fallback
        new_id = None
        if fallback and fallback != current and is_ok(statuses.get(fallback, {})):
            new_id = fallback
            print(f"   ↩️  Переключаю на fallback: {fallback}")

        # Ищем замену
        if not new_id:
            print(f"   🔍 Ищу замену...")
            exclude = {primary, current, fallback} - {None}
            new_id  = find_replacement(search_q, channel_id, exclude)
            if new_id:
                print(f"   ✅ Нашёл замену: {new_id}")
            else:
                print(f"   ❌ Замену не нашёл, пропускаю")

        if new_id:
            if replace_id_in_builder(current, new_id):
                redirects[current] = new_id           # старый URL → новый стрим
                s["current"]       = new_id
                config_changed     = True
                git_messages.append(f"{name}: {current} → {new_id}")

    if not git_messages:
        print("\n✅ Всё в порядке, изменений нет.")
        return

    # Сохраняем
    if config_changed:
        save_config(config)
        save_redirects(redirects)

    print(f"\n📦 Изменения: {', '.join(git_messages)}")
    print("Пушу на GitHub...")
    git_push(git_messages)
    print("\n✅ Готово! Сайт обновится через ~30 секунд.")
    print("   Старые ссылки Wallpaper Engine заработают автоматически.")


if __name__ == "__main__":
    main()
