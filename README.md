AI Council V19.4 — Production Hardened Hybrid
العقد المعماري
تعمل الغرفة بدون أي API Key.
المقاعد الخمسة الأساسية تمثل عائلات ChatGPT/OpenAI وGemini/Google وClaude/Anthropic وGrok/xAI وKimi/Moonshot.
غياب المفتاح = local_direct ولا توجد أي محاولة شبكة لذلك المزود.
وجود مفتاح = محاولة API رسمي فقط.
نجاح API مصادق عليه = official_api وofficial_authenticated=true.
فشل المزود الرسمي بعد المحاولة = local_fallback لذلك المقعد فقط؛ بقية الغرفة تستمر.
المقاعد 6–15 محلية صراحةً.
المحرك المحلي ليس ChatGPT/Gemini/Claude/Grok/Kimi الأصلي ولا ينتحل هويتهم.
الأسرار لا تدخل الواجهة ولا تُخزن في سجل التدقيق؛ تُقرأ فقط من Streamlit Secrets أو Environment Variables.
تشغيل محلي
python -m pip install -r requirements.txt
streamlit run main.py
اختبارات
python -m py_compile main.py providers.py local_engine.py audit.py
python -m unittest discover -s tests -p 'test_*.py' -v
أسرار اختيارية
OPENAI_API_KEY
GEMINI_API_KEY أو GOOGLE_API_KEY
ANTHROPIC_API_KEY
XAI_API_KEY
MOONSHOT_API_KEY أو KIMI_API_KEY
نماذج قابلة للتخصيص عبر *_MODELS أو *_MODEL.
هوية النماذج
لا يُعرض أي مقعد على أنه النموذج الأصلي إلا عندما ينجح طلب API رسمي مصادق عليه ويُعاد نص فعلي. الأسماء في الواجهة هي أسماء المقاعد/عائلات المزودين، وليست دليلاً على اتصال رسمي.
النشر
Streamlit Cloud
ارفع الملفات إلى GitHub.
اختر main.py كنقطة تشغيل.
أضف الأسرار اختيارياً في إعدادات التطبيق؛ لا تضعها في Git.
بدون أسرار يجب أن تعمل الغرفة محلياً بالكامل داخل التطبيق.
Google Cloud
يمكن تشغيل المشروع داخل حاوية/خدمة تدعم Streamlit. ضع الأسرار في Secret Manager أو متغيرات البيئة، وليس داخل المستودع.
ملاحظة التكلفة
المسار المحلي لا يحتاج API ولا اعتماداً خارجياً. استخدام أي Provider رسمي قد يترتب عليه تكلفة بحسب حساب المزود، حتى لو كان التطبيق نفسه مستضافاً على طبقة مجانية.
