AI Council V20 Secure
غرفة واحدة تجمع خمسة مقاعد أصلية: ChatGPT/OpenAI, Gemini/Google, Claude/Anthropic, Grok/xAI, Kimi/Moonshot. كل جولة تستخدم barrier: المقاعد الخمسة تقرأ نفس snapshot ثم تعمل بالتوازي، وبعد اكتمال الجولة تُضاف الردود إلى السياق المشترك.
تشغيل
pip install -r requirements.txt
streamlit run app.py
الاعتمادات
انسخ .streamlit/secrets.toml.example إلى .streamlit/secrets.toml وضع مفاتيح جديدة. لا تضع المفاتيح داخل Python ولا ترفع secrets.toml إلى GitHub.
الأمان
المفاتيح التي كُشفت في المحادثة يجب اعتبارها compromised وإلغاؤها/تدويرها لدى المزودين قبل الاستخدام. هذه النسخة لا تحتوي عليها.
Ollama
اختياري فقط. إذا فشل/غاب الاعتماد الرسمي، يمكن تفعيل Local Engine، ويُعرض بوضوح على أنه نموذج محلي وليس النموذج الأصلي.
ملاحظة الإصدارات
تم تصميم الموصلات وفق الواجهات الرسمية الحالية: OpenAI Responses API، Google GenAI SDK، Anthropic Messages API، وواجهة xAI المتوافقة مع OpenAI. معرفات النماذج قابلة للتعديل من Secrets لتجنب كسر التطبيق عند تغير الكتالوج.
