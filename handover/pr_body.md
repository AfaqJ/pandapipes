## What

An optional add-on that helps new users understand why a pandapipes simulation failed. When a pandapipes call raises (e.g. `PipeflowNotConverged`, invalid values, topology or runtime errors), the normal traceback is printed as usual, followed by a short plain-English explanation from a **local** LLM: the likely cause, the evidence from the network, and a minimal fix.

Built in collaboration with Prof. Marten Klein (BTU Cottbus-Senftenberg) to make onboarding easier. It builds on the existing `pandapipes.diagnostic` checks.

## How to use it

One-time, install any model you like:

```bash
ollama pull llama3.1:8b
```

Then add two lines to your normal script:

```python
import pandapipes.explain
pandapipes.explain.enable()
```

(or scoped: `with pandapipes.explain.explain(): pp.pipeflow(net)`)

## Why it is safe to add

- **Opt-in:** nothing changes unless `enable()` is called.
- **Does not interfere:** the original exception and traceback are untouched; the explanation is printed after it.
- **Skips itself** if Ollama is not installed or not running.
- **No new required dependencies:** the `explain` extra is empty; Ollama is reached via `urllib`.
- **No network calls beyond localhost**, no telemetry, no API keys.

## Tests and docs

- New tests in `src/pandapipes/test/explain/` use a mocked LLM, so CI needs no Ollama. Real-model tests are opt-in (`PANDAPIPES_EXPLAIN_RUN_OLLAMA=1`).
- A test fails if a `pandapipes.diagnostic` check used here is renamed or removed.
- CI passes on my fork: Linux and Windows, Python 3.10-3.13, with and without numba, lint, docs and tutorials.
- Usage and maintainer notes are in `src/pandapipes/explain/README.md`; CHANGELOG entry added.

Happy to adjust scope or naming based on feedback.
