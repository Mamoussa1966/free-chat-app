# HOTFIX129 — TWO-REAL-TURN PERSISTENCE EXECUTION GATE

## Purpose
HOTFIX129 closes the execution gap exposed after HOTFIX128. It does **not** weaken or reinterpret the persistence contract. The runtime must reach the two-message historical state through **two actual user submissions in the same conversation**.

The key rule is:

`one user submission = one MessageRecord = one RequestRecord = one RoundRecord`

A single user message that contains instructions for "Message 1" and "Message 2" is still **one** runtime submission and must create only one Request and one Round. The application must never fabricate Request 2 / Round 2 from prose, UI labels, or message text.

## Required positive chain

`MESSAGE_1 → REQUEST_1 → ROUND_1`

`MESSAGE_2 → REQUEST_2 → ROUND_2`

## Required negative control

`REQUEST_2 → ROUND_1 = FALSE`

## Runtime behavior

1. Before a new user submission, restore the complete committed canonical ConversationRecord.
2. Allocate a fresh runtime Request ID and Message ID for that submission.
3. Persist MessageRecord and RequestRecord before provider execution.
4. Allocate the next conversation-scoped Round ordinal from the canonical store, not from UI state or the current request projection.
5. Commit the RoundRecord before provider dispatch.
6. After a Streamlit rerun/narrowing event, hydrate the complete canonical history before the next submission.
7. Never synthesize a missing Request or Round merely because a second user-facing message exists.
8. If the canonical chain is incomplete, ambiguous, contradictory, or corrupted, return `NOT_PROVEN`/`FAIL` rather than infer identity.

## What the test must actually do

The tester must send **two separate chat messages**, one after the other, without putting both test messages into one submission.

### Message 1 — send this first

```text
V26.3 PERSISTENCE TURN 1
هذه رسالة المستخدم الأولى المستقلة فقط.
نفّذها كطلب واحد مستقل.
لا تستخدم Bridge.
المطلوب من Runtime فقط: إنشاء Message 1 ثم Request 1 ثم Round 1، وحفظها في Application-Owned Canonical Conversation Store.
لا تعتمد على Agent Prose أو UI labels لإثبات الهوية.
بعد التنفيذ اعرض الـAuthoritative Runtime Audit فقط.
```

### Message 2 — send this as a NEW chat submission in the SAME conversation

```text
V26.3 PERSISTENCE TURN 2
هذه رسالة المستخدم الثانية المستقلة والجديدة داخل نفس المحادثة.
لا تعِد تنفيذ الرسالة الأولى ولا تنشئ Request بديلًا لها.
لا تستخدم Bridge.
المطلوب من Runtime فقط: إنشاء Message 2 ثم Request 2 ثم Round 2، مع الحفاظ على التاريخ canonical السابق.
الإثبات الإيجابي الوحيد المقبول: REQUEST_2 → ROUND_2.
الإثبات السلبي الإلزامي: REQUEST_2 → ROUND_1 = FALSE.
لا تعتمد على Agent Prose أو UI labels أو latest-request projection.
إذا لم يكن السجل canonical يثبت السلسلة كاملة، أرجع NOT_PROVEN ولا تخمّن.
بعد التنفيذ اعرض الـAuthoritative Runtime Audit فقط.
```

## PASS closure

PASS requires all of the following from the canonical store itself:

- `canonical_message_count = 2`
- `canonical_request_count = 2`
- `canonical_round_count = 2`
- exact `MESSAGE_1 → REQUEST_1`
- exact `MESSAGE_2 → REQUEST_2`
- exact `REQUEST_1 → ROUND_1`
- exact `REQUEST_2 → ROUND_2`
- `REQUEST_2 → ROUND_1 = FALSE`
- exactly one canonical RoundRecord for Round 1
- exactly one canonical RoundRecord for Round 2
- canonical round sequence `[1, 2]`, contiguous, base 1
- `round`, `round_id (:rN)`, and `round_identity_contract` agree
- `agent_prose_used_as_identity = NO`
- `agent_prose_used_as_counter = NO`
- UI labels are not an authority
- latest-request projection is not an authority
- no previous Request was re-executed

## Fail-closed requirement

A single submission must **not** pass the two-message contract. In that case the correct result is `NOT_PROVEN`, not PASS.

An intentionally corrupted canonical Request 2 → Round 1 record must produce:

- `request_2_round_2_mapping = FALSE`
- `canonical_round_sequence_proven = FALSE`
- `conversation_runtime_audit != PASS`
- `overall_authoritative_status ∈ {NOT_PROVEN, FAIL}`

HOTFIX129 therefore tests the actual lifecycle, not merely the wording of the test contract.
