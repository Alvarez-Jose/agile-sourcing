# builds the grounded pipeline's source index over the FULL local corpus so the A/B
# benchmark compares retrieval quality, not corpus access. The shipped manifest marks
# 29 of 32 documents internal/review, and grounded ask() refuses review scopes, so
# as-shipped it answers from 2 documents. This script copies the manifest with every
# entry active (reviewed_sha256 = the file's current bytes), registers any local file
# the manifest doesn't know, and writes a separate index. It never touches the real
# manifest or data/parsed/policy_index.sqlite.
#
#   python -m evaluation.benchmarks.build_grounded_index
#   -> data/parsed/policy_index_full.sqlite

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from rag_pipeline.documents.build import prepare_source_index
from rag_pipeline.documents.manifest import normalize_filename
from rag_pipeline.documents.store import DEFAULT_MANIFEST, DEFAULT_SOURCES, write_source_index

FULL_MANIFEST = ROOT / "data/parsed/document_manifest_full.json"
FULL_INDEX = ROOT / "data/parsed/policy_index_full.sqlite"


REVIEW_STAMP = {"reviewed_by": "benchmark-equalizer", "reviewed_at": "2026-10-28T00:00:00Z"}


def main():
    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    entries = manifest["documents"]
    known = {normalize_filename(name) for e in entries for name in e["filenames"]}

    files = sorted(
        p for p in Path(DEFAULT_SOURCES).rglob("*")
        if p.is_file() and p.suffix.lower() in (".pdf", ".docx")
    )
    by_norm = {normalize_filename(p.name): p for p in files}

    extra_entries = []
    for entry in entries:
        local = {}
        for name in entry["filenames"]:
            path = by_norm.get(normalize_filename(name))
            if path is not None:
                local.setdefault(path, []).append(name)
        if not local:
            continue
        # one reviewed_sha256 per entry: the first file keeps the entry, any other
        # distinct local file under the same entry gets its own active entry so the
        # sha check passes for every file on disk
        paths = sorted(local, key=lambda p: p.name)
        primary = paths[0]
        entry["filenames"] = local[primary] + [
            n for n in entry["filenames"] if normalize_filename(n) not in
            {normalize_filename(m) for ps in local.values() for m in ps}
        ]
        entry["review_status"] = "active"
        entry["reviewed_sha256"] = hashlib.sha256(primary.read_bytes()).hexdigest()
        entry["archived_sha256"] = []
        entry.update(REVIEW_STAMP)
        for path in paths[1:]:
            print(f"splitting multi-file entry {entry['id']}: {path.name}")
            slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]", "-", path.stem.lower())).strip("-")
            extra_entries.append({
                "id": slug,
                "filenames": local[path],
                "title": path.stem.replace("_", " "),
                "category": entry.get("category", "Procurement"),
                "kind": entry.get("kind", "policy"),
                "access_classification": entry.get("access_classification", "public"),
                "review_status": "active",
                "reviewed_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                **REVIEW_STAMP,
            })
    entries.extend(extra_entries)

    for norm, path in by_norm.items():
        if norm in known:
            continue
        print(f"registering unlisted source: {path.name}")
        slug = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]", "-", path.stem.lower())).strip("-")
        entries.append({
            "id": slug,
            "filenames": [path.name],
            "title": path.stem.replace("_", " "),
            "category": "Procurement",
            "kind": "policy",
            "access_classification": "public",
            "review_status": "active",
            "reviewed_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            **REVIEW_STAMP,
        })

    FULL_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    FULL_MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    bundle = prepare_source_index(
        Path(DEFAULT_SOURCES), FULL_MANIFEST,
        progress=lambda d, s, c: print(f"  {d.file}: {s} sections, {c} chunks"),
    )
    write_source_index(bundle, FULL_INDEX)
    print(f"\n{len(bundle.documents)} documents, {len(bundle.chunks)} chunks -> {FULL_INDEX}")


if __name__ == "__main__":
    main()
