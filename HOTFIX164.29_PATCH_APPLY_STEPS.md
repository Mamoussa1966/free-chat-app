# HOTFIX164.29 patch application

This replacement archive is a source patch, not a ZIP to upload as a single project file. Extract it over the repository root while preserving its relative paths. It replaces `main.py`, `providers.py`, `build_release.py`, and two existing test modules, and adds the independent gate, manifest, workflow, status/notes, and new tests.

After extraction, verify that `main.py`, `providers.py`, and `VERSION.txt` are directly in the repository root. Do **not** change `VERSION.txt`: its required contents remain `V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`.

Run:

```bash
python -m py_compile main.py providers.py HOTFIX164.29_INDEPENDENT_CLOSURE_GATE.py
pytest -q
python build_release.py --output dist/HOTFIX164.29_FULL_RELEASE_CANDIDATE.zip
```

The full release builder compiles the project, runs the complete tests in an isolated workspace, builds the ZIP with files at the archive root, extracts it to a fresh directory, and runs the suite again. The verified local result for this package revision is 660 passed, 0 failed, 0 errors across 173 test files.

## Live release closure

A test-suite pass is not proof of live closure. Deploy HOTFIX164.29, perform fresh normal-runtime Run A and Run B using configured official Free models, then export `HOTFIX164.29_BRIDGE_EVIDENCE_FORENSICS.json` from the same active conversation. Put the file at `evidence/HOTFIX164.29_BRIDGE_EVIDENCE_FORENSICS.json` in the repository and run the workflow **HOTFIX164.29 Independent Live Closure Gate**. The workflow deliberately returns `NOT_PROVEN` if the report is from HOTFIX164.28, older than 24 hours, missing any request-bound HTTP attestation, mismatched against the candidate archive, or otherwise incomplete. Only a passing run generates `HOTFIX164.29_VERIFIED_RELEASE_MANIFEST.json`, a detached closure statement binding the report hash to the exact release ZIP hash. It is not embedded in the ZIP, avoiding a self-referential checksum.

Do not mark the release final or publish a final-release tag until the independent workflow itself ends successfully with `HOTFIX164.29_INDEPENDENT_FINAL_CLOSURE=PASS` and provides the verified manifest.
