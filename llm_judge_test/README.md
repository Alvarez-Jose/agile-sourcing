# Three-judge RAG experiment

Run the corrected 60-question benchmark once, then give the **same frozen answers**
to `qwen3:8b`, `gemma4:12b`, and `llama3:8b`. Each judge grades every answer **three
independent times**, for 540 judgments. The existing chat/retrieval code is unchanged.

## Run

Use your activated project environment and the project's existing policy index.
Ollama must be running. Install the exact local models once:

```sh
ollama pull qwen3:8b
ollama pull gemma4:12b
ollama pull llama3:8b
```

The verified library tags are [Qwen](https://ollama.com/library/qwen3:8b),
[Gemma](https://ollama.com/library/gemma4:12b), and
[Llama](https://ollama.com/library/llama3:8b). Gemma may need a newer Ollama version;
installing a cloud tag is not a substitute. Missing models produce instructions,
not automatic downloads or substitutions.

From the repository root:

```sh
python -m llm_judge_test.run_experiment --check
python -m llm_judge_test.run_experiment
```

For a quick trial, use `--limit 2`. This creates a separate experiment, not a full
60-question result. The full benchmark can take a long time on a laptop.

The script first runs the existing **retrieval-only evaluation** (expected-document
recall@1, recall@5 and candidate-pool recall). Then it generates the RAG answers,
including retrieved sources/citations, and runs each judge sequentially to limit
memory pressure. Rule-engine answers can bypass retrieval during answer generation;
the separate retrieval test bypasses that shortcut and tests retrieval for every
question. Its expected-document mapping accepts alternative supporting documents;
a hit does not prove the passage contains everything needed to answer.

Both scripts also support direct execution, e.g. `python llm_judge_test/run_experiment.py`.
No API server or browser sign-in is required for this offline evaluation.

## Results and comparisons

Each experiment lives in **`llm_judge_test/results/<timestamp>/`**, ignored by Git.
The terminal prints the exact directory. All outputs for that experiment stay there:

| File | Contents |
| --- | --- |
| `retrieval.json` | Per-question expected-document hits, ranks and retrieved document names. |
| `responses.json` | Frozen RAG answers, reference answers, sources, citations, errors and latency. |
| `experiment.json` | Full checkpoint, all nine judgments per question, raw judge replies, settings, model digests and rubric. |
| `judgments.csv` | One row per judgment: question, reference, RAG answer, model, run, grade, short explanation, errors and latency. |
| `results.csv` | Compact view: question, reference answer, RAG answer, each model's majority grade/score, and panel verdict. |
| `comparison.csv` | Every question with all nine grades, within-model consistency and cross-model agreement. |
| `disagreements.csv` | Questions with differing model majority grades, sorted by number of distinct grades then score spread. |
| `comparison_summary.json` | Per-model consistency/verdict counts, pairwise agreement rates and question IDs for agreement/disagreement. |
| `model.log` | Model-loading and answer-generation logs. |

Regenerate the comparisons independently, without running models:

```sh
python -m llm_judge_test.compare_results llm_judge_test/results/<timestamp>
```

`model1`, `model2`, `model3` follow the model order above; the summary records their
exact tag mapping. Scores encode **Correct = 2, Partial = 1, Incorrect = 0**. The
categories are ordered labels; the numeric spacing is only a display convention.
These are reference-agreement judgments, not expert-validated policy accuracy.

For each model, at least two of its three grades must match for a majority. Three
different grades mean `NO_CONSENSUS`; missing/failed calls mean `INCOMPLETE` and
are excluded from agreement denominators. Across models, the panel verdict uses
the three model majorities, giving each model equal weight. A question is unresolved
if any model lacks a valid majority. The summary lists unanimously correct,
partial and incorrect questions separately: agreement does not imply a good answer.

The terminal reports consistency, changed question IDs, each model's verdict
distribution, pairwise agreement and questions with the strongest disagreement.
Failed/missing judgments are reported separately and produce a nonzero exit code.

## Settings and interruption

Defaults: temperature **0**, seed **42** on every call, context **8,192** tokens,
maximum judge output **512** tokens and timeout **120 seconds**. Each call has a
fresh single-message conversation and never sees other votes or model identities.
Thinking is disabled for models advertising that capability and for Qwen3.
JSON-schema output is validated strictly; malformed/truncated output is an error,
not an inferred grade. Full question/reference/answer text is sent without deliberate
truncation; context saturation is flagged as an error.

At temperature zero with the same seed, repeated judgments may be identical.
That measures repeatability under these settings, not fairness or truth. Different
model sizes, training and quantization also affect the comparison. This experiment
uses the existing substantive rubric with structured grades and short explanations;
its prompt differs from the older one-word judge, so historical scores are not a
controlled comparison. The reference key itself is AI-generated and partly corrected.

Completed answers and judgments are saved after every call. To resume after Ctrl+C:

```sh
python -m llm_judge_test.run_experiment --resume llm_judge_test/results/<timestamp>
```

Use the original `--limit`, model order, seed, temperature and timeout settings.
Resume rejects changed judge digests, settings, rubric or reference questions and
never regrades completed calls, including recorded failures. To rerun failures as
part of a fresh experiment using exactly the same saved answers:

```sh
python -m llm_judge_test.run_experiment --responses llm_judge_test/results/<timestamp>/responses.json
```

Include `--limit N` if the saved answers came from a limited trial. `--models`
accepts three explicit local tags; `--output-dir` selects a new output folder.
Use the default `results/` location to keep generated data ignored.

## Paper connection

[Replacing Judges with Juries](https://arxiv.org/abs/2404.18796) motivates comparing
diverse judge panels. This is a small procurement-specific experiment, not a
replication of that paper. A Procurement-reviewed subset would be needed to measure
which judge or panel is actually more accurate, rather than simply more consistent.
