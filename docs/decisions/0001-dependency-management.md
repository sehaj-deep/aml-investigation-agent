# 0001 Dependency management

Status: accepted (Sprint 0)

Decision: a plain venv (`.venv`, Python 3.12) with pip-tools. `requirements.in` and `requirements-dev.in` list direct dependencies; `requirements.txt` and `requirements-dev.txt` are compiled with `pip-compile --generate-hashes` and installed with `--require-hashes` in CI.

Why: pinned, hash-checked installs (PRD section 6, reproducibility) with standard tools. Chosen by the project owner over uv.

Update a pin: edit the `.in` file, re-run `pip-compile --generate-hashes --strip-extras`, commit both files.
