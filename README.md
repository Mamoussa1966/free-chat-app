AI Council V18.0 — Production Hybrid
نسخة إنتاجية هجينة: مزودات رسمية اختيارية + محرك محلي مستقل كـ failsafe.
العقد التشغيلي
تعمل الغرفة بدون أي API Key.
غياب المفتاح يعني لا توجد محاولة شبكة لذلك المزود.
عند وجود اعتماد رسمي يحاول المقعد الاتصال بالـ API الرسمي فقط.
نجاح API الرسمي فقط يجعل official_authenticated=true.
فشل API أو النموذج أو الشبكة أو الحصة يعيد المقعد إلى Local Fallback.
فشل مقعد واحد لا يوقف بقية المقاعد.
المقاعد 6–15 محلية صراحةً.
لا توجد خانات API Keys في الواجهة.
لا Cookies، ولا Session Scraping، ولا تسجيل دخول إلى تطبيقات المستهلك.
المحرك المحلي ليس ChatGPT/Gemini/Claude/Grok/Kimi الأصلي، ولا ينتحل هويتهم.
التشغيل
python -m pip install -r requirements.txt
streamlit run main.py
الاختبارات
python -m py_compile main.py providers.py local_engine.py
python -m unittest discover -s tests -p 'test_*.py' -v
الاعتمادات الرسمية الاختيارية
ضعها على الخادم فقط في Streamlit Secrets أو Environment Variables:
OPENAI_API_KEY
GEMINI_API_KEY أو GOOGLE_API_KEY
ANTHROPIC_API_KEY
XAI_API_KEY
MOONSHOT_API_KEY أو KIMI_API_KEY
يمكن تغيير النماذج بدون تعديل الكود عبر *_MODELS أو *_MODEL، بقيم مفصولة بفواصل.
النماذج الافتراضية
OpenAI: gpt-5.6-luna, ثم gpt-5.6-terra, ثم gpt-5.6-sol
Gemini: gemini-3.8-flash, ثم gemini-3.7-flash, ثم gemini-3.6-flash
Anthropic: claude-sonnet-5, ثم claude-sonnet-4-6
xAI: grok-4.6
Moonshot: kimi-k3
النماذج قابلة للتغيير من الخادم؛ لذلك لا تعتمد صحة المشروع على اسم نموذج ثابت.
Audit
كل نتيجة تحتوي على:
mode
source_mode
official_authenticated
fallback_used
model_used
audit.model_id
audit.local_engine
audit.success
audit.latency_seconds
وهذا يمنع الخلط بين الرد الرسمي والرد المحلي.
