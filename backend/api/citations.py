"""Translate the team's unchanged RAG source fields for the existing extension.

This is a transport adapter: it does not change answers, rankings, citations, or
refusal decisions. Legacy chunk text has no authoritative section offsets.
"""


def frontend_sources(sources):
    result = []
    for position, source in enumerate(sources, 1):
        evidence = source.get("evidence", [])
        if not evidence and source.get("text"):
            evidence = [{"quote": source["text"]}]
        result.append(
            {
                **source,
                "citation_id": source.get("ref", position),
                "source_url": source.get("source_url", source.get("url")),
                "evidence": evidence,
            }
        )
    return result
