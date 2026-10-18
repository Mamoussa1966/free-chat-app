# HOTFIX164.28 Final Closure Status

**Status: NOT_PROVEN — awaiting fresh deployed Run A and Run B evidence.**

This is deliberately not labelled live-confirmed. Package creation, an offline test pass, provider prose, a historic audit, and a read-only report PASS are not substitutes for a real successful handoff.

For each run, the deployed application must persist evidence tied to the same canonical Conversation → Message → Request → Round chain proving all of the following:

1. DeepSeek Seat 7 returned a successful official API response; that exact response is the only Bridge source value.
2. The app-owned Bridge transaction performed WRITE, VALIDATE, COMMIT and recorded a successful barrier-open event in order.
3. Gemini Seat 2 was dispatched only after the barrier opened and returned a successful official API response.
4. A post-response app-owned READ resolved the committed Bridge value; a constant-time or exact byte/string comparison proves exact source/read equality.
5. The real prepared HTTP body passed to `requests.post` has a SHA-256/byte-count attestation bound to the Gemini target's Request ID, canonical Round ID, selected model, target seat and successful response. The source Bridge value, Bridge control fields and internal IDs must not appear in the user message, provider prompt or Gemini HTTP payload.
6. Canonical-store evidence, runtime execution events, the Bridge ledger/projection and target request all agree. A missing phase, mismatch, stale report or incomplete payload attestation remains NOT_PROVEN.

The offline regression suite does not issue official API calls. To close the live gate, deploy this source, run A and B independently through the application's normal runtime with explicitly configured `*_FREE_MODELS`, then export the new application-owned evidence and run the read-only audit against those exact current canonical Request IDs. Do not reuse historical target IDs or overwrite a failed result with synthetic evidence.
