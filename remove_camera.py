import json
import re
import subprocess
import sys

BUILDER_FILE = "builder/index.html"
VIEW_FILE    = "view/index.html"
CONFIG_FILE  = "streams_config.json"


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def find_in_config(config, video_id):
    # Search by current or primary video ID
    for key, s in config["streams"].items():
        if s["primary"] == video_id or s["current"] == video_id:
            return key
    return None


def remove_from_config(config, key):
    name = config["streams"][key]["name"]
    del config["streams"][key]
    print(f"  ✅ Removed '{name}' from streams_config.json")
    return config, name


def remove_from_builder(video_id):
    with open(BUILDER_FILE, encoding="utf-8") as f:
        content = f.read()

    if video_id not in content:
        print(f"  ⚠️  {video_id} not found in builder/index.html")
        return

    # Remove the entire { id: "...", name: "..." }, line including comma and newline
    new_content = re.sub(
        r',?\s*\{\s*id:\s*"' + re.escape(video_id) + r'"[^}]*\},?',
        '',
        content
    )

    # Clean up double commas or trailing commas before ]
    new_content = re.sub(r',(\s*\])', r'\1', new_content)
    new_content = re.sub(r',\s*,', ',', new_content)

    with open(BUILDER_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  ✅ Removed {video_id} from builder/index.html")


def remove_from_view(video_id):
    with open(VIEW_FILE, encoding="utf-8") as f:
        content = f.read()

    if video_id not in content:
        print(f"  ⚠️  {video_id} not found in view/index.html")
        return

    # Remove the "VIDEO_ID": "Name", line
    new_content = re.sub(
        r',?\s*"' + re.escape(video_id) + r'":\s*"[^"]*"',
        '',
        new_content if False else content
    )

    with open(VIEW_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  ✅ Removed {video_id} from view/index.html")


def git_push(name):
    subprocess.run(["git", "add", "."],                         check=True)
    subprocess.run(["git", "commit", "-m", f"remove camera: {name}"], check=True)
    subprocess.run(["git", "push"],                             check=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    print("═══════════════════════════════════")
    print("  SamuiCam — Remove Camera")
    print("═══════════════════════════════════\n")

    config = load_config()

    # Show all cameras
    print("Current cameras:\n")
    cameras = []
    for i, (key, s) in enumerate(config["streams"].items(), 1):
        vid = s["current"]
        print(f"  {i:2}. [{vid}] {s['name']}")
        cameras.append((key, s, vid))

    print()
    choice = input("Enter number or Video ID to remove: ").strip()

    # Resolve choice
    key      = None
    video_id = None

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(cameras):
            key, s, video_id = cameras[idx]
    else:
        # Treat as video ID
        video_id = choice
        key = find_in_config(config, video_id)

    if not key:
        print("❌ Camera not found")
        return

    name     = config["streams"][key]["name"]
    video_id = config["streams"][key]["current"]

    print(f"\n⚠️  About to remove: '{name}' [{video_id}]")
    confirm = input("Confirm? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    print(f"\n📦 Removing...")
    config, name = remove_from_config(config, key)
    save_config(config)
    remove_from_builder(video_id)
    remove_from_view(video_id)

    print(f"\n🚀 Pushing to GitHub...")
    git_push(name)

    print(f"\n✅ Done! '{name}' removed from the site in ~30 seconds.")


if __name__ == "__main__":
    main()