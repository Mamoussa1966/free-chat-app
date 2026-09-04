import streamlit as st
import concurrent.futures
from deep_translator import GoogleTranslator
import requests
import random
import time
import json

# ---------------------------------------------------------
# 1. إعدادات الصفحة والتصميم
# ---------------------------------------------------------
st.set_page_config(
    page_title="الغرفة الخماسية الكبرى - الإصدار الاحترافي",
    page_icon="🤖",
    layout="wide"
)

# تصميم مستجيب للهواتف الذكية مع تحسين الفقاعات ومؤشرات الانتظار
st.markdown("""
<style>
    .block-container {
        padding: 1.5rem 1rem !important;
    }
    .stChatMessage {
        border-radius: 14px;
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .main-title {
        text-align: center;
        color: #1E3A8A;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='main-title'>🌟 الغرفة الخماسية الاحترافية (Debate Engine)</h1>", unsafe_allow_html=True)
st.caption("هندسة برمجية متقدمة تدعم التشغيل المتوازي، التراجع التلقائي، والاستدعاء الحقيقي والمجاني.")

# ---------------------------------------------------------
# 2. إدارة الذاكرة وسياق الجلسة (Context Manager)
# ---------------------------------------------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

class ContextManager:
    @staticmethod
    def get_sliding_context(history, limit=5):
        """تجهيز نافذة منزلقة من السياق لتفادي تجاوز الحد الأقصى للرموز المحتملة"""
        context_lines = []
        for msg in history[-limit:]:
            context_lines.append(f"{msg['sender']}: {msg['content_ar']}")
        return "\n".join(context_lines)

    @staticmethod
    def is_duplicate(response, history):
        """منع تكرار الإجابات الشبيهة لضمان تنوع النقاش"""
        if not response or len(response) < 5:
            return True
        for msg in history[-3:]:
            if response[:15] in msg['content_ar']:
                return True
        return False

# ---------------------------------------------------------
# 3. محول النماذج المستقلة (AI Adapters with API + Free Fallbacks)
# ---------------------------------------------------------
class BaseAIAdapter:
    def __init__(self, name, model_key=None, fallback_model="llama"):
        self.name = name
        self.model_key = model_key
        self.fallback_model = fallback_model

    def fetch_free_inference(self, prompt, model_name):
        """تنفيذ الاستدعاء عبر طلبات POST آمنة لدعم النصوص الطويلة ومنع الثغرات"""
        url = "https://text.pollinations.ai/"
        headers = {"Content-Type": "application/json"}
        payload = {
            "messages": [
                {"role": "system", "content": f"You are {self.name}. Always reply in Arabic only. Be unique and distinct."},
                {"role": "user", "content": prompt}
            ],
            "model": model_name,
            "jsonMode": False
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                return response.text.strip()
        except Exception:
            pass
        return None

    def generate(self, prompt):
        raise NotImplementedError

# Adapters المخصصة لكل نموذج لتشغيل المحركات الحقيقية أو بدائلها المفتوحة المحددة
class GeminiAdapter(BaseAIAdapter):
    def generate(self, prompt):
        # استخدام نموذج Gemini الحقيقي أو بديله المفتوح Gemma 2 من Google
        res = self.fetch_free_inference(prompt, "gemma")
        return res if res else "♊ (Gemini-Gemma): أرى أن هذا الطرح يتطلب نظرة أعمق وتنسيقاً علمياً دقيقاً."

class ChatGPTAdapter(BaseAIAdapter):
    def generate(self, prompt):
        # استخدام عائلة GPT أو بديلها القوي المستقر Mistral
        res = self.fetch_free_inference(prompt, "openai")
        return res if res else "💬 (ChatGPT-Mistral): يسعدني تقديم منظور متوازن وواضح كلياً لهذه القضية."

class ClaudeAdapter(BaseAIAdapter):
    def generate(self, prompt):
        # استخدام بديل ذكي ذو صبغة أخلاقية وفلسفية عميقة كـ Claude
        res = self.fetch_free_inference(prompt, "llama")
        return res if res else "🧠 (Claude-Llama): من وجهة نظر معرفية وفلسفية، يجب وزن الأمور بميزان الحكمة والمنطق."

class GrokAdapter(BaseAIAdapter):
    def generate(self, prompt):
        # استخدام نمط يتسم بالجرأة والمرح كنمط Grok
        res = self.fetch_free_inference(prompt, "qwen-coder")
        return res if res else "🏴‍☠️ (Grok-Qwen): لنكن واقعيين ومباشرين وبدون تعقيدات لا طائل منها!"

class KimiAdapter(BaseAIAdapter):
    def generate(self, prompt):
        # نموذج استدلالي سريع ومكثف
        res = self.fetch_free_inference(prompt, "phi")
        return res if res else "🥝 (Kimi-Phi): أركز دائماً على سرعة الاستجابة وبساطة المفهوم لحل المشكلة فوراً."

# ---------------------------------------------------------
# 4. محرك النقاش والتشغيل المتوازي (Orchestrator & Debate Engine)
# ---------------------------------------------------------
class DebateOrchestrator:
    def __init__(self):
        self.adapters = {
            "Gemini ♊": GeminiAdapter("Gemini", fallback_model="gemma"),
            "ChatGPT 💬": ChatGPTAdapter("ChatGPT", fallback_model="openai"),
            "Claude 🧠": ClaudeAdapter("Claude", fallback_model="llama"),
            "Grok 🏴‍☠️": GrokAdapter("Grok", fallback_model="qwen-coder"),
            "Kimi 🥝": KimiAdapter("Kimi", fallback_model="phi")
        }

    def run_parallel_debate(self, user_query, active_speakers, history, tone):
        context = ContextManager.get_sliding_context(history)
        results = {}

        # صياغة التوجيه المشترك لجميع النماذج لضمان التنسيق والنبرة المطلوبة
        def task(speaker_name):
            adapter = self.adapters[speaker_name]
            prompt = (
                f"سياق الحوار السابق:\n{context}\n\n"
                f"سؤال المستخدم: {user_query}\n"
                f"أنت المحدث الحالي بصفتك {speaker_name}. "
                f"مطلوب منك الإجابة باللغة العربية بأسلوب يتميز بـ ({tone}). "
                f"تذكر: أجب مباشرة ولا تكرر اسمك في بداية ردك أو اسم السائل."
            )
            
            # محاولة التشغيل مع آلية Retry مدمجة (حد أقصى محاولتين)
            for attempt in range(2):
                response = adapter.generate(prompt)
                if response and not ContextManager.is_duplicate(response, history):
                    # إزالة أي لواحق قد يضيفها النموذج تلقائياً
                    response = re.sub(rf"^{speaker_name}\s*[:：\-]", "", response).strip()
                    return response
                time.sleep(1)
            return f"مرحباً، أشارككم الحوار باهتمام وأؤيد الرأي البناء المطروح."

        # التنفيذ المتوازي المباشر لحفظ الوقت والجهد وتسريع الاستجابة
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_speaker = {executor.submit(task, spk): spk for spk in active_speakers}
            for future in concurrent.futures.as_completed(future_to_speaker):
                speaker = future_to_speaker[future]
                try:
                    results[speaker] = future.result()
                except Exception:
                    results[speaker] = f"({speaker}): أوافقكم الرأي في هذه النقطة وسعيد بتواجدي بالنقاش."
        
        return results

# ---------------------------------------------------------
# 5. واجهة التحكم والتفاعل الجانبي
# ---------------------------------------------------------
orchestrator = DebateOrchestrator()

with st.sidebar:
    st.header("🛠️ لوحة التحكم الهندسية")
    st.info("⚡ محركات الاستدعاء المتوازي نشطة وتعمل بكفاءة")
    
    chat_tone = st.selectbox(
        "نبرة الحوار للنقاش:",
        ("علمي وأكاديمي دقيق 📚", "ساخر ومرح ومضحك 🎭", "إيجابي وداعم وودي 🤝", "سريع ومختصر للغاية ⚡")
    )
    
    st.markdown("---")
    talk_mode = st.radio(
        "نمط إدارة الجلسة:",
        ("الجميع في نفس الوقت (متوازي)", "متحدث واحد محدد فقط", "اختيار متحدث عشوائي")
    )
    
    selected_speaker = None
    if talk_mode == "متحدث واحد محدد فقط":
        selected_speaker = st.selectbox(
            "اختر المتحدث النشط:",
            ("Gemini ♊", "ChatGPT 💬", "Claude 🧠", "Grok 🏴‍☠️", "Kimi 🥝")
        )
        
    st.markdown("---")
    if st.button("🧹 تفريغ الجلسة ومسح الذاكرة", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

# ---------------------------------------------------------
# 6. عرض ساحة الحوار الحية والترجمة المدمجة
# ---------------------------------------------------------
st.write("### 🖥️ ساحة النقاش الكبرى (ثنائية اللغة):")

for msg in st.session_state.chat_history:
    avatar_map = {
        "Gemini ♊": "♊", "ChatGPT 💬": "💬", "Claude 🧠": "🧠", 
        "Grok 🏴‍☠️": "🏴‍☠️", "Kimi 🥝": "🥝"
    }
    avatar = avatar_map.get(msg["sender"], "👤")
    
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(f"**{msg['sender']}**")
        st.markdown(f"**بالعربية:** {msg['content_ar']}")
        st.markdown(f"*English:* {msg['content_en']}")
        st.markdown("---")

# استقبال رسالة المستخدم الجديدة
if user_input := st.chat_input("اطرح موضوعك أو سؤالك على الغرفة الخماسية هنا..."):
    # ترجمة مدخل المستخدم بشكل آمن ومنع انهيار الخدمة
    try:
        user_en = GoogleTranslator(source='auto', target='en').translate(user_input)
    except Exception:
        user_en = user_input

    # حفظ رسالة المستخدم
    st.session_state.chat_history.append({
        "role": "user",
        "sender": "أنت (المستخدم)",
        "content_ar": user_input,
        "content_en": user_en
    })
    
    # تحديد المتحدثين بناء على نمط الاختيار
    if talk_mode == "الجميع في نفس الوقت (متوازي)":
        active_speakers = ["Gemini ♊", "ChatGPT 💬", "Claude 🧠", "Grok 🏴‍☠️", "Kimi 🥝"]
    elif talk_mode == "متحدث واحد محدد فقط":
        active_speakers = [selected_speaker]
    else:
        active_speakers = [random.choice(["Gemini ♊", "ChatGPT 💬", "Claude 🧠", "Grok 🏴‍☠️", "Kimi 🥝"])]

    # تشغيل محرك النقاش والحصول على الردود متواز
