V19.4 Deployment Gate
قبل النشر
python -m py_compile main.py providers.py local_engine.py audit.py
python -m unittest discover -s tests -p 'test_*.py' -v
تأكد أن .streamlit/secrets.toml غير موجود في Git.
شغّل التطبيق بدون أي مفاتيح.
اختبر 5 ثم 10 ثم 15 مقعداً.
اختبر مفتاحاً رسمياً واحداً فقط، ثم افصل المزود عمداً للتأكد من local_fallback.
راجع JSON Audit وتأكد من عدم وجود API key أو Authorization header.
معايير القبول
صفر مفاتيح: التطبيق يبدأ وتعمل الجولة.
صفر مفاتيح: لا توجد مكالمة Provider.
API ناجح: المقعد المعني فقط يصبح official_api.
API فاشل: المقعد نفسه فقط يصبح local_fallback.
مقاعد 6–15 تبقى محلية دائماً.
لا توجد حقول لإدخال API Keys في الواجهة.
JSON Audit لا يحتوي الأسرار.
Streamlit rerun لا يكرر النتائج السابقة.
