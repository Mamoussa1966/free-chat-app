AI Council V9 — Provider Layer / Free-First
نسخة هجينة من الغرفة الخماسية. تعمل بدون أي API Key، وتضيف طبقة Provider رسمية اختيارية منفصلة.
المبدأ
لا يوجد مفتاح = لا توجد محاولة شبكة لذلك تعمل الغرفة محلياً.
يوجد اعتماد رسمي على الخادم = محاولة عبر API الرسمي للمزود.
فشل الاعتماد أو النموذج أو الشبكة = fallback محلي تلقائي لذلك لا تتوقف الغرفة.
لا توجد شاشة لإدخال المفاتيح.
لا تستخدم Cookies أو Session Scraping أو محاولة الدخول إلى جلسات ChatGPT/Gemini/Claude/Grok/Kimi الاستهلاكية.
النتيجة لا تسمى "أصلية" إلا عندما يكون مصدرها API رسمي مصادق عليه. المحرك المحلي لا ينتحل هوية النموذج التجاري.
الملفات
main.py — واجهة Streamlit والمنسق.
providers.py — طبقة Providers الرسمية الاختيارية.
local_engine.py — المحرك المحلي الذي يضمن استمرار الغرفة.
requirements.txt — الاعتمادات.
.streamlit_secrets.toml.example — مثال اختياري للأسرار على الخادم.
التشغيل
python -m pip install -r requirements.txt
streamlit run main.py
الاعتمادات الاختيارية
ضعها كـ Environment Variables أو Streamlit Secrets على الخادم، وليس في الواجهة:
OPENAI_API_KEY
GEMINI_API_KEY أو GOOGLE_API_KEY
ANTHROPIC_API_KEY
XAI_API_KEY
MOONSHOT_API_KEY
يمكن تخصيص النماذج عبر OPENAI_MODELS, GEMINI_MODELS, ANTHROPIC_MODELS, XAI_MODELS, KIMI_MODELS، مفصولة بفواصل. عند فشل نموذج ينتقل الـ Provider إلى النموذج التالي، ثم إلى المحلي.
الهوية
"ChatGPT" في واجهة الغرفة تعني عائلة OpenAI ومسارها الرسمي عندما يظهر نموذج أصلي عبر API رسمي. لا يعني ذلك تسجيل الدخول إلى تطبيق ChatGPT الاستهلاكي. المبدأ نفسه ينطبق على Gemini وClaude وGrok وKimi.
وجود API Key لا يعني أن الحساب مجاني أو أن الطلب سيقبل بلا رصيد/حصة؛ عند الرفض يعود التطبيق إلى المحلي.
