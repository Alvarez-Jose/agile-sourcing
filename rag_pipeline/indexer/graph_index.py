"""Public facade for the SQLite-backed, source-provenanced policy graph."""

from rag_pipeline.documents.models import AccessScope
from rag_pipeline.documents.store import DEFAULT_INDEX, PolicyIndex
from rag_pipeline.graph.traversal import traverse


class PolicyGraphIndex:
    def __init__(self, path=DEFAULT_INDEX, scope: AccessScope | None = None):
        self.sources = PolicyIndex(path, scope)

    def expand(self, node_id: str, max_hops: int = 2, max_nodes: int = 100):
        return traverse(self.sources, node_id, max_hops, max_nodes)

    def parent_section(self, chunk_id: str):
        return self.sources.parent_section(chunk_id)
