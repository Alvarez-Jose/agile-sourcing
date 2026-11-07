"""Restore the exact publicly verified starter bytes; never auto-approve replacements."""

from http.cookiejar import CookieJar
import hashlib
import os
from urllib.request import build_opener, HTTPCookieProcessor, Request
import uuid

from rag_pipeline.documents.manifest import DocumentManifest
from rag_pipeline.documents.store import DEFAULT_MANIFEST, DEFAULT_SOURCES

SOURCES = {
    "bus-43": (
        "https://policy.ucop.edu/doc/3220485/BFB-BUS-43",
        "BUS-43_Interim_2026-01-26.pdf",
    ),
    "sspr-form": (
        "https://financial.ucsc.edu/Financial_Affairs_Forms/Source_Selection_Justification_Form.pdf",
        "SSPR_Official_UCSC_2025-12.pdf",
    ),
}


def main():
    entries = {e.id: e for e in DocumentManifest.load(DEFAULT_MANIFEST).entries}
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    DEFAULT_SOURCES.mkdir(parents=True, exist_ok=True)
    for identifier, (url, filename) in SOURCES.items():
        entry = entries[identifier]
        if (
            entry.review_status != "active"
            or entry.source_url != url
            or filename not in entry.filenames
        ):
            raise ValueError(
                "Starter manifest review no longer matches downloader; review before downloading"
            )
        path = DEFAULT_SOURCES / filename
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry.reviewed_sha256:
                raise ValueError(
                    f"{identifier}: local source bytes changed; preserve them for review before restoring the verified source"
                )
            print(f"{identifier}: exact reviewed bytes already present")
            continue
        with opener.open(
            Request(url, headers={"User-Agent": "Agile-Sourcing source verification"}),
            timeout=30,
        ) as response:
            payload = response.read(30_000_001)
        if len(payload) > 30_000_000 or not payload.startswith(b"%PDF-"):
            raise ValueError("Expected a PDF, not an error/login page")
        if hashlib.sha256(payload).hexdigest() != entry.reviewed_sha256:
            raise ValueError(
                f"{identifier}: official bytes changed; retained previous source. Review the new release before activating it."
            )
        temporary = path.with_name(path.name + ".download-" + uuid.uuid4().hex)
        try:
            with os.fdopen(
                os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb"
            ) as stream:
                stream.write(payload)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        print(f"{identifier}: downloaded and hash-verified")


if __name__ == "__main__":
    main()
