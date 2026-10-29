"""Bounded graph inspection; conditions are not evaluated as procurement decisions."""

from collections import deque

from rag_pipeline.documents.store import PolicyIndex


def traverse(
    index: PolicyIndex, start_id: str, max_hops: int = 2, max_nodes: int = 100
):
    if not 0 <= max_hops <= 10 or not 1 <= max_nodes <= 1000:
        raise ValueError("Traversal limits are outside the permitted bounds")
    nodes = {node.id: node for node in index.nodes()}
    if start_id not in nodes:
        return {"nodes": [], "edges": []}
    adjacency = {}
    for edge in index.edges():
        if edge.relation == "overrides":
            # Traversal cannot treat a conditional override as applicable without
            # an explicit condition evaluator and purchase context (a later phase).
            continue
        adjacency.setdefault(edge.source_id, []).append(edge)
    visited, queue, selected = {start_id}, deque([(start_id, 0)]), {}
    while queue:
        identifier, depth = queue.popleft()
        if depth >= max_hops:
            continue
        for edge in adjacency.get(identifier, []):
            if edge.target_id not in visited and len(visited) >= max_nodes:
                continue
            selected[edge.id] = edge
            if edge.target_id not in visited:
                visited.add(edge.target_id)
                queue.append((edge.target_id, depth + 1))
    return {
        "nodes": [nodes[key] for key in sorted(visited)],
        "edges": list(selected.values()),
    }
