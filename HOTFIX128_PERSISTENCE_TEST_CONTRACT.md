# HOTFIX128 — EXACT V26.3 PERSISTENCE TEST CONTRACT

## Scope
Test-contract correction only. No Provider Core, Free Cascade, Secrets, Model Lists, Bridge implementation, or canonical persistence engine behavior is changed by HOTFIX128.

## Exact test prompt to paste into the Council chat

نفّذ اختبار V26.3 Authoritative Conversation Persistence فقط.

الشروط:
- عدد الجولات في إعدادات المجلس = 1.
- نفّذ رسالتين مستقلتين في نفس المحادثة.
- لا تستخدم Bridge في هذا الاختبار.
- لا تعتمد على نص الوكلاء أو عناوين الواجهة لإثبات الهوية.
- مصدر إثبات الهوية يجب أن يكون Application-Owned Canonical Conversation Store فقط.

بعد الرسالة الأولى، يجب أن يثبت الـruntime:
1. MESSAGE_1 → REQUEST_1
2. REQUEST_1 → ROUND_1

بعد الرسالة الثانية، يجب أن يثبت الـruntime:
3. MESSAGE_2 → REQUEST_2
4. REQUEST_2 → ROUND_2

والاختبار السلبي الإلزامي:
5. REQUEST_2 → ROUND_1 = FALSE

ويجب أن تكون النتيجة النهائية PASS فقط إذا أثبت الـruntime من الـcanonical ledger نفسه:
- canonical_message_count = 2 (لرسالتَي المستخدم التاريخيتين في هذا الاختبار)
- canonical_request_count = 2
- canonical_round_count = 2
- Message 1 مربوط بالـRequest 1 بالضبط.
- Message 2 مربوط بالـRequest 2 بالضبط.
- Request 1 مربوط بالRound 1 بالضبط.
- Request 2 مربوط بالRound 2 بالضبط.
- لا يوجد أي canonical mapping صحيح لـRequest 2 → Round 1.
- Round 1 وRound 2 لكل منهما سجل Canonical واحد فقط.
- ترتيب الـrounds هو [1, 2] ومتصل ويبدأ من 1.
- round وround_id (:rN) وround_identity_contract متطابقة.
- agent prose = NOT_USED كدليل هوية.
- UI labels = NOT_USED كدليل هوية.
- latest-request projection = NOT_USED كبديل للتاريخ الكامل.

اختبار فساد إلزامي قبل إغلاق الإصدار:
- إذا تم تغيير السجل canonical الخاص بـRequest 2 عمدًا إلى Round 1، فيجب أن يفشل الاختبار:
  - request_2_round_2_mapping = FALSE
  - canonical_round_sequence_proven = FALSE
  - conversation_runtime_audit != PASS
  - overall_authoritative_status = NOT_PROVEN أو FAIL

لا تعتبر أي تسمية تاريخية تجعل REQUEST_2 → ROUND_1 إثباتًا إيجابيًا. الصيغة الوحيدة الصحيحة للإثبات الإيجابي هي REQUEST_2 → ROUND_2.

## Machine-readable active contract

MESSAGE_1 → REQUEST_1 → ROUND_1

MESSAGE_2 → REQUEST_2 → ROUND_2

REQUEST_2 → ROUND_1 = FALSE

## Expected authoritative chain

Message 1 → Request 1 → Round 1
Message 2 → Request 2 → Round 2
Negative control: Request 2 → Round 1 = FALSE

## Closure rule

لا يُغلق اختبار Persistence كـPASS إلا إذا كان كل الإثبات أعلاه موجودًا في Application-Owned Canonical Conversation Store، وكانت حالات الفشل/الفساد تُرفض Fail-Closed.
