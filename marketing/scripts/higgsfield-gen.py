#!/usr/bin/env python3
"""
FQ — Higgsfield asset generator.

Bridges Higgsfield Cloud (cinematic B-roll / product shots / AI backgrounds) into
this repo's pipeline: it generates from content/higgsfield-prompts.json and
downloads the results straight into the folders Remotion/carousels already read:
  - video  -> public/footage/    (usable as a clip `src` in the EDL)
  - images -> products/social/assets/ (overlays, banners, carousel backgrounds)

The brand / captions / legal / audio layer stays in this repo. Higgsfield only
makes the raw footage.

Usage:
  pip install higgsfield-client
  export HF_KEY="your-api-key:your-api-secret"     # from cloud.higgsfield.ai/api-keys
  python3 scripts/higgsfield-gen.py                # generate everything in the prompts file
  python3 scripts/higgsfield-gen.py desk-broll     # just one asset by id
  python3 scripts/higgsfield-gen.py --dry          # print calls, generate nothing

Compliance: keep prompts free of on-screen performance numbers / profit claims —
we add the compliant copy in Remotion, not in the AI footage.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "content" / "higgsfield-prompts.json"


def download(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    # urllib honors HTTPS_PROXY from the environment automatically.
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        f.write(r.read())
    print(f"  saved -> {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KB)")


def urls_from(result: dict):
    """Pull asset URLs from a Higgsfield result, tolerant of shape (image/video)."""
    out = []
    for key in ("videos", "images"):
        for item in result.get(key, []) or []:
            if isinstance(item, dict) and item.get("url"):
                out.append(item["url"])
    for key in ("video", "image"):
        node = result.get(key)
        if isinstance(node, dict) and node.get("url"):
            out.append(node["url"])
    return out


def main():
    args = [a for a in sys.argv[1:]]
    dry = "--dry" in args or not (os.getenv("HF_KEY") or os.getenv("HF_API_KEY"))
    wanted = [a for a in args if not a.startswith("--")]

    assets = json.loads(PROMPTS.read_text(encoding="utf-8"))["assets"]
    if wanted:
        assets = [a for a in assets if a["id"] in wanted]
        if not assets:
            sys.exit(f"No asset id in {wanted}. Available: "
                     f"{[a['id'] for a in json.loads(PROMPTS.read_text())['assets']]}")

    if dry:
        why = "--dry" if "--dry" in args else "no HF_KEY set"
        print(f"[{why}] would generate {len(assets)} asset(s):")
        for a in assets:
            print(f"  {a['id']}: {a['model']} -> {a['out']}")
            print(f"    {a['arguments'].get('prompt','')[:100]}")
        return

    import higgsfield_client
    for a in assets:
        print(f"generating {a['id']} via {a['model']} ...")
        result = higgsfield_client.subscribe(a["model"], arguments=a["arguments"])
        urls = urls_from(result)
        if not urls:
            print(f"  WARN: no asset url in result keys={list(result.keys())}")
            continue
        dest = ROOT / a["out"]
        download(urls[0], dest)


if __name__ == "__main__":
    main()
