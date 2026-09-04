import streamlit as st
from deep_translator import GoogleTranslator
import random
import requests

# إعداد الصفحة لتناسب شاشات الموبايل والكمبيوتر
st.set_page_config(
    page_title="غرفة المحادثة الخماسية الكبرى (النسخة المجانية)", 
    page_icon="🌟", 
    layout="wide"
)

st.title("🌟 الغرفة الخماسية الكبرى - النسخة المجانية")
st.caption("نقاش جماعي يضم 5 شخصيات ذكاء اصطناعي بدون الحاجة لمفاتيح API أو أي تكاليف")

# إعدادات الشريط الجانبي
with st.sidebar:
    st.header("⚙️ خيارات التشغيل")
    st.success("✅ وضع التشغيل المجاني نشط (بدون API Keys)")
    
    st.markdown("---")
    st.header("🎛️ لوحة التحكم في المتحدثين")
    talk_mode = st.radio(
        "اختر نمط الإجابة والردود:",
        ("الجميع بالترتيب المتتابع", "متحدث واحد محدد فقط", "اختيار متحدث عشوائي")
    )
    
    selected_speaker = None
    if talk_mode == "متحدث واحد محدد فقط":
        selected_speaker = st.selectbox(
            "اختر المتحدث الحالي:",
            ("Gemini", "ChatGPT", "Claude", "Grok", "Kimi")
        )
        
    st.markdown("---")
    def reset_chat():
        st.session_state.chat_history = []
        st.toast("🧹 تم مسح المحادثة بالكامل!")

    st.button("🧹 مسح المحادثة وإعادة التعيين", on_click=reset_chat, use_container_width=True)

# تهيئة سجل المحادثة
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# بناء السياق وتوجيه الشخصية
def build_prompt(bot_name, user_query):
    system_personas = {
        "Gemini": "أنت Gemini، نموذج ذكي، تحليلي ومنظم جداً ومبدع من Google.",
        "ChatGPT": "أنت ChatGPT، نموذج متزن، واضح، ودود، ويقدم شروحات مفصلة من OpenAI.",
        "Claude": "أنت Claude، نموذج مفكر، دقيق، يركز على الأخلاقيات والعمق المعرفي من Anthropic.",
        "Grok": "أنت Grok، نموذج مرح، مباشر، يتمتع بروح الدعابة والذكاء من xAI.",
        "Kimi": "أنت Kimi، نموذج خبير في التحليل وسريع البديهة من Moonshot."
    }
    
    base_prompt = f"{system_personas.get(bot_name, 'أنت نموذج ذكاء اصطناعي')}\n"
    base_prompt += "المطلوب: أجب بإيجاز ووضوح باللغة العربية مع التركيز على وجهة نظرك الخاصة.\n\n"
    
    # إضافة آخر 3 رسائل للسياق لضمان ترابط النقاش
    history_context = ""
    for msg in st.session_state.chat_history[-4:]:
        history_context += f"{msg['sender']}: {msg['content_ar']}\n"
        
    full_prompt = f"{base_prompt}سياق المحادثة:\n{history_context}\nالمستخدم: {user_query}\n{bot_name}:"
    return full_prompt

# دالة توليد الردود المجانية عبر واجهة استدعاء مفتوحة وسريعة
def generate_free_response(bot_name, prompt):
    try:
        # استخدام Pollinations AI (واجهة مجانية وسريعة جداً بدون مفاتيح API)
        url = f"https://text.pollinations.ai/{requests.utils.quote(prompt)}?model=openai&seed={random.randint(1, 10000)}"
        response = requests.get(url, timeout=25)
        if response.status_code == 200:
            return response.text.strip()
        else:
            return f"مرحباً! أنا {bot_name}، مهتم جداً بهذا النقاش وأتطلع لمشاركة أفكاري معكم."
    except Exception:
        return f"({bot_name}): موضوع شيق للغاية، ومستعد لمواصلة الحوار معكم وطرح أفكار جديدة."

# عرض سجل الرسائل
st.write("### 🖥️ شاشة المحادثة النشطة (مترجمة ثنائياً):")
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(f"**{msg['sender']}**")
        st.markdown(f"**بالعربية:** {msg['content_ar']}")
        st.markdown(f"*English:* {msg['content_en']}")
        st.markdown("---")

# إدخال المستخدم
if user_input := st.chat_input("اكتب رسالتك بالعربية هنا لتظهر للجميع..."):
    try:
        user_en = GoogleTranslator(source='auto', target='en').translate(user_input)
    except Exception:
        user_en = user_input
        
    st.session_state.chat_history.append({
        "role": "user",
        "sender": "أنت (المستخدم)",
        "content_ar": user_input,
        "content_en": user_en
    })
    st.rerun()

# معالجة ردود النماذج
if len(st.session_state.chat_history) > 0 and st.session_state.chat_history[-1]["role"] == "user":
    last_user_query = st.session_state.chat_history[-1]["content_ar"]
    all_spks = ["Gemini", "ChatGPT", "Claude", "Grok", "Kimi"]
    speakers = []
    
    if talk_mode == "الجميع بالترتيب المتتابع":
        speakers = all_spks
    elif talk_mode == "متحدث واحد محدد فقط":
        speakers = [selected_speaker]
    elif talk_mode == "اختيار متحدث عشوائي":
        speakers = [random.choice(all_spks)]

    for spk in speakers:
        with st.spinner(f"[{spk}] يقرأ النقاش ويكتب رده الآن..."):
            prompt = build_prompt(spk, last_user_query)
            reply = generate_free_response(spk, prompt)
            
            # ترجمة الرد تلقائياً إلى الإنجليزية لتسهيل العرض الثنائي
            try:
                reply_en = GoogleTranslator(source='auto', target='en').translate(reply)
            except Exception:
                reply_en = reply
                
            st.session_state.chat_history.append({
                "role": "assistant",
                "sender": spk,
                "content_ar": reply,
                "content_en": reply_en
            })
    st.rerun()
