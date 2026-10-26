# CLAUDE.md

See @AGENTS.md for the project guidance: commands, architecture, and the policy-correctness
invariants (thresholds live in `rules/`, every threshold needs provenance with a document,
page, and quote, and policy documents stay out of the repo).

Notes specific to Claude Code:

- The tests CI runs are `python -m pytest rules tests/integration -q`. `rules/test_provenance.py`
  silently skips when `data/raw_policies/` is missing, so check the skip count after touching
  `rules/` rather than trusting a green run.
- Do not start the backend or the benchmark to "check" a rule change. Both load embeddings,
  a reranker, and a local Ollama model; use the rule engine's tests instead.
- `frontend/package.json` still says `wxt-react-starter`. Don't treat that as the source of
  the project description; this file and `AGENTS.md` are.
