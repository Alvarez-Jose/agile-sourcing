# Dependency audit — October 18, 2026

Inspected 79 tracked Python files across the backend, RAG, rules, source index,
training, evaluation, scripts, and tests. Parsed imports with Python 3.12's AST,
including imports inside functions and conditions, excluded standard-library/local
modules, and mapped import names to their actual distribution names. Checked for
explicit dynamic imports and optional training integrations as well.

## Missing declarations corrected

| Package | Pin | Direct use | Previous state |
| --- | --- | --- | --- |
| `trl` | `0.15.2` | `SFTTrainer` / `SFTConfig` in both fine-tuning scripts | Absent from requirements and the new venv |
| `numpy` | `2.5.4` | Intent classifier numerical operations | Installed indirectly |
| `starlette` | `1.9.0` | FastAPI optional warm-up threadpool helper | Installed indirectly |
| `lxml` | `6.1.3` | Source-index XML tests | Installed indirectly through python-docx |
| `pdfminer.six` | `20251230` | Source-index PDF helpers | Installed indirectly through pdfplumber |
| `google-api-core` | `2.42.0` | Firestore exceptions in authentication/tests | Installed indirectly through Firebase |
| `google-auth` | `2.62.0` | Authentication service exceptions | Installed indirectly through Google SDKs |

The six already-installed packages are pinned to their existing local versions;
this makes their direct use explicit without upgrading them. The PDF parser pin
matches the exact version required by pdfplumber 0.11.9.

TRL 0.15.2 supports the existing `max_seq_length` configuration and deprecated
`tokenizer` alias as well as `processing_class`. Verified against its
[configuration source](https://github.com/huggingface/trl/blob/v0.15.2/trl/trainer/sft_config.py)
and [trainer source](https://github.com/huggingface/trl/blob/v0.15.2/trl/trainer/sft_trainer.py).
Choosing a newer incompatible trainer API would require script changes, which this
audit avoids. No teammate RAG, rules, training, or evaluation source was edited.

The previous fix `datasets==4.0.0` is retained to satisfy `ragas==0.4.3`'s
`datasets>=4.0.0` requirement. No existing dependencies were removed. Declared
libraries without direct project imports are retained because some support library
features, command-line tools, or planned work.

## Verification

- Every detected third-party Python import now maps to an explicit requirements
  entry; native/standard-library modules such as `sqlite3` require no pip entry.
- Full dependency resolution succeeded for **195 distributions** using Python
  **3.12.15 on macOS arm64**, with `--dry-run --ignore-installed`.
- **211 Python tests passed, 2 skipped**. The skipped quote checks use external FAR
  sources; authentication tests mock Firebase.
- Existing embedding, cross-encoder, PEFT, and Transformers imports passed without
  loading models.
- Downloaded TRL into a temporary directory, leaving the project's venv unchanged.
  Both training modules imported successfully with it. Constructed their SFT
  configuration fields on CPU, verified trainer argument support, and ran
  `pip check` with that temporary package visible: no broken requirements.
- Frontend package-import roots are covered by `frontend/package.json`; JavaScript
  packages belong there rather than in Python requirements.

## Scope and remaining checks

This verifies declared imports, resolver compatibility, library imports, and the
existing CPU test suite. It does not prove full GPU fine-tuning, arbitrary model
behavior, production Firebase access, or cross-platform installation. Ollama's
server and Node/pnpm are external tools covered by the README.

The existing `transformers==4.57.0` release is
[marked yanked on PyPI](https://pypi.org/project/transformers/4.57.0/) for installation
issues. The pin remains unchanged here and its current imports passed locally;
coordinate any replacement with the RAG/training teammate.

To install the completed list in the actual project venv:

```sh
./venv/bin/python -m pip install -r requirements.txt && ./venv/bin/python -m pip check
```
