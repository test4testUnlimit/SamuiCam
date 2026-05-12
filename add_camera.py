import urllib.request
import json
import re
import subprocess
import sys
from config import YOUTUBE_API_KEY

BUILDER_FILE = "builder/index.html"
VIEW_FILE    = "view/index.html"
CONFIG_FILE  = "streams_config.json"

# ── Location keyword → builder group label ──────────────────
LOCATION_TO_GROUP = {
    "thailand":    "🇹🇭 TH · Thailand",
    "samui":       "🇹🇭 TH · Thailand",
    "phangan":     "🇹🇭 TH · Thailand",
    "seychelles":  "🇸🇨 SC · Seychelles",
    "mahe":        "🇸🇨 SC · Seychelles",
    "mahé":        "🇸🇨 SC · Seychelles",
    "maldives":    "🇲🇻 MV · Maldives",
    "atoll":       "🇲🇻 MV · Maldives",
    "hawaii":      "🇺🇸 US · Hawaii",
    "oahu":        "🇺🇸 US · Hawaii",
    "maui":        "🇺🇸 US · Hawaii",
    "caribbean":   "🌴 Caribbean",
    "martin":      "🌴 Caribbean",
    "maarten":     "🌴 Caribbean",
    "barbados":    "🌴 Caribbean",
    "jamaica":     "🌴 Caribbean",
    "philippines": "🇵🇭 PH · Philippines",
    "switzerland": "🇨🇭 CH · Switzerland",
    "swiss":       "🇨🇭 CH · Switzerland",
    "alps":        "🇨🇭 CH · Switzerland",
    "space":       "🛸 Space",
    "iss":         "🛸 Space",
    "nasa":        "🛸 Space",
}

# ── Suffix hint shown to user ────────────────────────────────
SUFFIX_HINT = "Optional suffixes: Panoramic / 4K / Live / Rooftop / Underwater"


def api_get(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def extract_video_id(url):
    m = re.search(r'(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})', url)
    return m.group(1) if m else None


def get_video_info(video_id):
    url = (
        f"https://www.googleapis.com/youtube/v3/videos"
        f"?part=snippet,status&id={video_id}&key={YOUTUBE_API_KEY}"
    )
    data  = api_get(url)
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

	
def sanitize_name(name):
    # Remove emojis and special characters that break JS syntax
    # Keep: letters, digits, spaces, commas, dashes, dots, apostrophes
    name = re.sub(r'[^\w\s,.\-\'—&()]', '', name)
    # Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name)
    # Remove quotes that would break JS string
    name = name.replace('"', '').replace("'", '')
    return name.strip()	

	
def detect_group(location):
    loc_lower = location.lower()
    for keyword, group in LOCATION_TO_GROUP.items():
        if keyword in loc_lower:
            return group
    return None


def add_to_config(config, video_id, name, channel_id, location):
    # Build unique key
    key  = slug(name)
    base = key
    i    = 2
    while key in config["streams"]:
        key = f"{base}_{i}"
        i  += 1

    config["streams"][key] = {
        "name":       name,
        "primary":    video_id,
        "fallback":   None,
        "current":    video_id,
        "search":     name + " live webcam",
        "channel_id": channel_id,
        "location":   location
    }

    # Register channel if new
    if channel_id not in config["channels"]:
        config["channels"][channel_id] = "Unknown Channel"
        print(f"  ℹ️  New channel registered: {channel_id}")

    print(f"  ✅ Added to streams_config.json as '{key}'")
    return config


def add_to_builder(video_id, name, location):
    with open(BUILDER_FILE, encoding="utf-8") as f:
        content = f.read()

    # Already exists?
    if f'id: "{video_id}"' in content:
        print(f"  ⚠️  {video_id} already exists in builder/index.html")
        return

    new_entry    = f'{{ id: "{video_id}", name: "{name}" }}'
    target_group = detect_group(location)

    if target_group:
        # Find the group block and append inside its cams array
        pattern = re.escape(target_group) + r'.*?cams:\s*\[(.*?)\]'
        m = re.search(pattern, content, re.DOTALL)
        if m:
            block      = m.group(1)
            last_brace = block.rfind('}')
            if last_brace >= 0:
                insert_pos = m.start(1) + last_brace + 1
                content    = (
                    content[:insert_pos]
                    + f',\n                {new_entry}'
                    + content[insert_pos:]
                )
                with open(BUILDER_FILE, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  ✅ Added to builder/index.html → group '{target_group}'")
                return

    # Group not found — create new group before closing ] of GROUPS array
    print(f"  ℹ️  Group for '{location}' not found — creating new group")
    new_group = (
        f',\n        {{\n'
        f'            label: "{location}",\n'
        f'            cams: [\n'
        f'                {new_entry},\n'
        f'            ]\n'
        f'        }}'
    )
    last_bracket = content.rfind('];')
    if last_bracket >= 0:
        content = content[:last_bracket] + new_group + '\n    ' + content[last_bracket:]
        with open(BUILDER_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  ✅ New group '{location}' created in builder/index.html")
    else:
        print(f"  ❌ Could not add to builder/index.html — check file structure")


def add_to_view(video_id, name):
    with open(VIEW_FILE, encoding="utf-8") as f:
        content = f.read()

    if f'"{video_id}"' in content:
        print(f"  ⚠️  {video_id} already exists in view/index.html")
        return

    # Find last STREAMS entry and append after it
    last = list(re.finditer(r'"[A-Za-z0-9_-]{11}":\s*"[^"]+"', content))
    if not last:
        print(f"  ❌ Could not find insertion point in view/index.html")
        return

    pos     = last[-1].end()
    content = content[:pos] + f',\n            "{video_id}": "{name}"' + content[pos:]
    with open(VIEW_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  ✅ Added to view/index.html")


def git_push(name):
    subprocess.run(["git", "add",    "."],                    check=True)
    subprocess.run(["git", "commit", "-m", f"add camera: {name}"], check=True)
    subprocess.run(["git", "push"],                           check=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    print("═══════════════════════════════════")
    print("  SamuiCam — Add Camera")
    print("═══════════════════════════════════\n")

    # ── Step 1: YouTube URL ──────────────────────────────────
    url      = input("YouTube URL: ").strip()
    video_id = extract_video_id(url)
    if not video_id:
        print("❌ Could not extract Video ID from URL")
        return

    # ── Step 2: Fetch video info ─────────────────────────────
    print(f"\n🔍 Checking {video_id}...")
    info = get_video_info(video_id)
    if not info:
        print("❌ Video not found")
        return

    print(f"\n📺 Found:")
    print(f"   Channel:    {info['channel']}")
    print(f"   Title:      {info['title']}")
    print(f"   Live:       {info['live']}")
    print(f"   Embeddable: {'✅' if info['embeddable'] else '❌'}")

    # ── Warnings ─────────────────────────────────────────────
    if not info['embeddable']:
        print("\n⚠️  Embed disabled — camera will NOT work on the site!")
        if input("Add anyway? (y/N): ").strip().lower() != 'y':
            return

    if info['live'] == 'none':
        print("\n⚠️  This is not a live stream — it may be offline or a recording!")
        if input("Add anyway? (y/N): ").strip().lower() != 'y':
            return

    # ── Step 3: Name ─────────────────────────────────────────
    print(f"\nCamera name for the site:")
    print(f"  [{info['title']}]")
    print(f"  Standard: [Place Name], [Area/City][ — Suffix]")
    print(f"  {SUFFIX_HINT}")
    custom = input("Enter = keep original, or type your own: ").strip()
    name   = custom if custom else info['title']

    # Sanitize — remove emojis and chars that break JS
    name_clean = sanitize_name(name)
    if name_clean != name:
        print(f"  ℹ️  Name sanitized: '{name}' → '{name_clean}'")
    name = name_clean

    if not name:
        print("❌ Name is empty after sanitization — please enter manually")
        name = input("Camera name: ").strip()

    # ── Step 4: Location ─────────────────────────────────────
    print(f"\nLocation (used to assign the correct group):")
    print(f"  Examples: Koh Samui, Thailand / Oahu, Hawaii, USA / Sint Maarten, Caribbean")
    location = input("Location: ").strip()
    if not location:
        location = "Unknown"

    # ── Step 5: Update all files ─────────────────────────────
    print(f"\n📦 Adding...")
    config = load_config()
    config = add_to_config(config, video_id, name, info['channel_id'], location)
    save_config(config)
    add_to_builder(video_id, name, location)
    add_to_view(video_id, name)

    # ── Step 6: Push ─────────────────────────────────────────
    print(f"\n🚀 Pushing to GitHub...")
    git_push(name)

    print(f"\n✅ Done! '{name}' will appear on the site in ~30 seconds.")


if __name__ == "__main__":
    main()