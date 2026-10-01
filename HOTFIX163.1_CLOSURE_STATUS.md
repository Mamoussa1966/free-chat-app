# HOTFIX163.1 Final Closure Status

## VERSION Contract Resolution

The release uses the canonical provider/runtime version contract:

`V22.1-HOTFIX123.2-SINGLE-REQUEST-DETERMINISM-LIVE-CASCADE`

HOTFIX117 is a historical regression layer. Its determinism test must validate the preserved HOTFIX116 request-determinism behavior under the current canonical release contract; it must not require the obsolete HOTFIX117 release string in `VERSION.txt`.

The HOTFIX117 regression test therefore validates:
- the canonical current VERSION contract;
- the HOTFIX116 request-fingerprint gate behavior;
- the HOTFIX117 bridge-value redaction boundary.

No production code path is selected from a historical VERSION string, and `VERSION.txt`, `providers.VERSION`, release notes, and the active release tests agree on the canonical `HOTFIX123.2` contract.

## Final Verification

- Full test suite: 579 passed, 0 failed.
- V26 missing-message identity regression: PASS.
- Gemini no-secret isolation: PASS.
- HOTFIX162 Gemini no-secret isolation: PASS.
- HOTFIX117 bridge boundary and determinism contract: PASS.
- Canonical counter source: `CANONICAL_IDENTITY_RECORDS`.
- Agent prose used as counter: NO.
- Agent prose used as identity: NO.
- Provider dispatch during audit/read/hydration verification: 0.
- New requests created by audit/read/hydration: 0.
- New rounds created by audit/read/hydration: 0.

## Release State

Status: CLOSED

Acceptance requires the same result after ZIP extraction. The release artifact is therefore re-extracted into a clean workspace and the complete test suite is executed again before publication.
