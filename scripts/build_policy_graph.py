"""Build/inspect the source index and explicit graph without embeddings or an LLM.

python -m scripts.build_policy_graph build --preview
python -m scripts.build_policy_graph build
python -m scripts.build_policy_graph search SSPR --local-review
"""

import argparse
import json
import os
from pathlib import Path
import uuid

from rag_pipeline.documents.build import prepare_source_index
from rag_pipeline.documents.models import AccessScope, LOCAL_REVIEW_SCOPE
from rag_pipeline.documents.store import (
    DEFAULT_INDEX,
    DEFAULT_MANIFEST,
    DEFAULT_SOURCES,
    PolicyIndex,
    write_source_index,
)
from rag_pipeline.graph.traversal import traverse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRAPH = ROOT / "data/graphs/policy_index/graph.json"


def export_graph(bundle, path=DEFAULT_GRAPH):
    """Local inspection artifact; source quotes make this a private build output."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".build-{uuid.uuid4().hex}")
    data = {
        "schema_version": 1,
        "summary": bundle.summary(),
        "nodes": [node.model_dump(mode="json") for node in bundle.nodes],
        "edges": [edge.model_dump(mode="json") for edge in bundle.edges],
    }
    try:
        with os.fdopen(
            os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w"
        ) as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def progress(document, sections, chunks):
    print(
        f"{document.file}: {sections} sections, {chunks} chunks; "
        f"{document.access_classification}/{document.review_status}",
        flush=True,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser(
        "build", help="Extract all sources and build their graph"
    )
    build.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCES)
    build.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    build.add_argument("--db", type=Path, default=DEFAULT_INDEX)
    build.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    build.add_argument(
        "--preview",
        action="store_true",
        help="Validate/extract without writing outputs",
    )
    build.add_argument("--max-tokens", type=int, default=240)
    build.add_argument("--overlap-tokens", type=int, default=40)
    search = commands.add_parser(
        "search", help="Search source chunks and inspect their parents"
    )
    search.add_argument("query")
    search.add_argument("--db", type=Path, default=DEFAULT_INDEX)
    search.add_argument(
        "--local-review",
        action="store_true",
        help="Explicitly inspect internal/restricted, unreviewed and archived local sources",
    )
    graph = commands.add_parser(
        "traverse", help="Inspect bounded, scoped graph relationships"
    )
    graph.add_argument("node_id")
    graph.add_argument("--db", type=Path, default=DEFAULT_INDEX)
    graph.add_argument("--local-review", action="store_true")
    graph.add_argument("--hops", type=int, default=2)
    listing = commands.add_parser(
        "documents", help="Inspect source versions, dates, and review metadata"
    )
    listing.add_argument("--db", type=Path, default=DEFAULT_INDEX)
    listing.add_argument("--local-review", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            bundle = prepare_source_index(
                args.source_dir,
                args.manifest,
                progress=progress,
                max_tokens=args.max_tokens,
                overlap_tokens=args.overlap_tokens,
            )
            if not args.preview:
                bundle = write_source_index(bundle, args.db)
                export_graph(bundle, args.graph)
                print(f"Source index: {args.db}\nGraph: {args.graph}")
            print(json.dumps(bundle.summary(), indent=2))
            return
        scope = LOCAL_REVIEW_SCOPE if args.local_review else AccessScope()
        index = PolicyIndex(args.db, scope)
        if args.command == "documents":
            print(
                json.dumps(
                    [
                        {
                            "document_id": doc.id,
                            "version_id": doc.version_id,
                            "sha256": doc.sha256,
                            "title": doc.title,
                            "file": doc.file,
                            "access_classification": doc.access_classification,
                            "review_status": doc.review_status,
                            "dates": [item.model_dump() for item in doc.dates],
                            "review_notes": doc.review_notes,
                        }
                        for doc in index.documents()
                    ],
                    indent=2,
                )
            )
        elif args.command == "search":
            results = []
            for chunk in index.search(args.query, limit=5):
                parent = index.parent_section(chunk.id)
                document = index.document(chunk.document_version_id)
                results.append(
                    {
                        "chunk_id": chunk.id,
                        "parent_section_id": chunk.parent_section_id,
                        "document": document.title,
                        "section": parent.title,
                        "locations": [item.model_dump() for item in chunk.locations],
                        "excerpt": chunk.text[:400],
                        "full_parent_characters": len(parent.text),
                    }
                )
            print(json.dumps(results, indent=2))
        else:
            result = traverse(index, args.node_id, max_hops=args.hops)
            print(
                json.dumps(
                    {
                        key: [item.model_dump(mode="json") for item in value]
                        for key, value in result.items()
                    },
                    indent=2,
                )
            )
    except Exception as error:
        parser.exit(1, f"Index operation failed: {error}\n")


if __name__ == "__main__":
    main()
