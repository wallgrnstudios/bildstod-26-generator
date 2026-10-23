"""Build a content-addressed Bildstöd 26 app release from approved image versions.

The input review snapshot is deliberately separate from the app release. Only
current versions with an explicit approved or pilot decision can enter the
catalog, and automatic term matching remains disabled until its fallback
mapping has been reviewed.
"""
import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
APP_ORIGIN = "https://wallgrn.com/bildstod/v1"
LICENSE = "Bildstöd 26 pilot – endast för intern utvärdering"
GRAMMAR = {"action": "verb", "object": "noun", "person": "noun", "body_part": "noun", "situation": "phrase"}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def approved_current(candidates, reviews):
    current = {item["concept_id"]: item for item in candidates}
    selected = []
    for review in reviews:
        candidate = current.get(review.get("concept_id"))
        if (review.get("decision") in {"approved", "keep_for_pilot"} and candidate
                and review.get("sha256") == candidate.get("sha256")):
            selected.append(candidate)
    return sorted({item["concept_id"]: item for item in selected}.values(), key=lambda item: item["concept_id"])


def entry_for(candidate, vocabulary):
    row = vocabulary.get(candidate["concept_id"], {})
    label = candidate["label_sv"]
    symbol_type = candidate.get("symbol_type", "object")
    digest = candidate["sha256"]
    return {
        "conceptID": candidate["concept_id"],
        "label": label,
        "category": row.get("category", "övrigt"),
        "grammar": GRAMMAR.get(symbol_type, "noun"),
        "searchTerms": [],
        "matching": {
            "enabled": False,
            "priority": 0,
            "preferred": False,
            "terms": [label],
            "requiresAny": [],
            "excludesAny": [],
        },
        "image": {
            "url": f"{APP_ORIGIN}/images/{digest}.png",
            "sha256": digest,
            "attribution": "Wallgrn Studios",
            "license": LICENSE,
        },
    }


def fetch_verified(candidate, images_dir):
    digest = candidate["sha256"]
    destination = images_dir / f"{digest}.png"
    if destination.exists():
        payload = destination.read_bytes()
    else:
        request = urllib.request.Request(candidate["source_url"], headers={"User-Agent": "Bildstod26-release-builder"})
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = response.read(4 * 1024 * 1024 + 1)
        if len(payload) > 4 * 1024 * 1024:
            raise ValueError("PNG exceeds app contract size: " + candidate["concept_id"])
        destination.write_bytes(payload)
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("PNG hash mismatch: " + candidate["concept_id"])
    with Image.open(destination) as image:
        if image.format != "PNG" or image.width > 4096 or image.height > 4096:
            raise ValueError("PNG format or dimensions violate app contract: " + candidate["concept_id"])


def build(candidates, reviews, vocabulary, destination, release_version):
    selected = approved_current(candidates, reviews)
    if not selected:
        raise ValueError("No current explicitly approved image versions")
    destination = Path(destination)
    images_dir = destination / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for candidate in selected:
        fetch_verified(candidate, images_dir)
    vocab = {item["id"]: item for item in vocabulary}
    catalog = {"schemaVersion": 1, "status": "published", "releaseVersion": release_version,
               "language": "sv", "entries": [entry_for(candidate, vocab) for candidate in selected]}
    if len(catalog["entries"]) > 10_000:
        raise ValueError("Catalog exceeds app contract limit")
    payload = json.dumps(catalog, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    if len(payload) > 4 * 1024 * 1024:
        raise ValueError("Catalog exceeds app contract size")
    temporary = destination / "catalog.json.tmp"
    temporary.write_bytes(payload)
    temporary.replace(destination / "catalog.json")
    return catalog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, default=ROOT.parent / "output/admin-diagnostic-public.json")
    parser.add_argument("--reviews", type=Path, default=ROOT.parent / "output/reviews-regeneration-private.json")
    parser.add_argument("--vocabulary", type=Path, default=ROOT / "catalog/school/vocabulary-2000.json")
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--release-version", required=True)
    args = parser.parse_args()
    candidate_data = load_json(args.candidates)
    catalog = build(candidate_data["candidates"], load_json(args.reviews), load_json(args.vocabulary),
                    args.destination, args.release_version)
    print(json.dumps({"releaseVersion": catalog["releaseVersion"], "entries": len(catalog["entries"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
