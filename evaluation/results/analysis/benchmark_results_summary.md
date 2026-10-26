# Benchmark Diagnostic Summary: benchmark_results

- Questions analyzed: **60**
- Type: **heuristic diagnostics only; not accuracy measurement**
- Existing manual grades and reviewer notes are preserved when the question and response are unchanged.

## Questions by difficulty

- edge_case: 20
- scenario: 20
- simple: 20

## Flags worth reviewing

- thinking_marker_present: 50/60
- no_numbered_citation: 9/60
- long_answer_over_2000_chars: 6/60
- placeholder_citation_present: 5/60
- possible_reasoning_leakage: 3/60
- repeated_placeholder_citations: 1/60

## Review notes

A numbered citation marker does not prove a correct citation. Lack of a numbered marker does not always mean no source is present. Verify correctness, groundedness, and policy currency manually or using a separately validated evaluator.
Reasoning-leakage and placeholder-citation flags are pattern-based and require manual review.
Fill `manual_grade` (correct / partial / incorrect) and `reviewer_notes` in the CSV after checking examples.
