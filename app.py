import streamlit as st
from deep_translator import GoogleTranslator
import random
import requests
import re

# 1. إعداد الصفحة وتوفير واجهة متجاوبة للهواتف والكمبيوتر
st.set_page_config(
    page_title="غرفة المحادثة الخماسية الكبرى (النسخة الاحترافية)", 
    page_icon="🌟", 
    layout="wide"
)

# 2. حقن تصميم CSS مخصص لتحسين الواجهة على الموبايل
st.markdown("""
<style>
    /* تحسين شكل شاشة الدردشة وتقليل الفراغات للموبايل */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 1.5rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    /* جعل الخطوط أكثر وضوحاً وقراءة */
    html, body, [class*="css"] {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    /* تمييز الرسائل وتباعدها */
    .stChatMessage {
        border-radius: 12px;
        margin-bottom: 10px;
        padding: 10px;
    }
</style>
""", unsafe_allow_html=True)

# 3. واجهة المستخدم الرسومية واللوحة الجانبية
st.title("🌟 الغرفة الخماسية الكبرى - الإصدار الاحترافي المجاني")
st.caption("أقوى نقاش جماعي تفاعلي يضم 5 شخصيات ذكاء اصطناعي (مجاني 100% وبدون مفاتيح API)")

with st.sidebar:
    st.header("⚙️ تخصيص أسلوب الحوار")
    st.success("🤖 محرك توليد ذكي مجاني نشط")
    
    # ميزة جديدة: اختيار نبرة وأسلوب الردود
    chat_tone = st.selectbox(
        "اختر نبرة وأسلوب النقاش:",
        ("علمي وأكاديمي دقيق 📚", "ساخر ومرح ومضحك 🎭", "ودي، داعم وإيجابي 🤝", "مختصر، سريع ومباشر ⚡")
    )
    
    st.markdown("---")
    st.header("🎛️ التحكم في المتحدثين")
    talk_mode = st.radio(
        "نمط الإجابة والردود:",
        ("الجميع بالترتيب المتتابع", "متحدث واحد محدد فقط", "اختيار متحدث عشوائي")
    )
    
    selected_speaker = None
    if talk_mode == "متحدث واحد محدد فقط":
        selected_speaker = st.selectbox(
            "اختر المتحدث الحالي:",
            ("Gemini ♊", "ChatGPT 💬", "Claude 🧠", "Grok 🏴‍☠️", "Kimi 🥝")
        )
        
    st.markdown("---")
    
    # ميزة مسح المحادثة
    def reset_chat():
        st.session_state.chat_history = []
        st.toast("🧹 تم مسح المحادثة بنجاح!")

    st.button("🧹 مسح وإعادة تعيين", on_click=reset_chat, use_container_width=True)

# تهيئة الجلسة
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# 4. دالة معالجة النصوص وحذف الأسماء المتكررة من الردود
def clean_response(text, bot_name):
    # إزالة أي بدايات مكررة مثل "Gemini:" أو "(Gemini):" أو "أنا Gemini:"
    prefixes = [
        rf"^{bot_name}\s*[:：\-]", 
        rf"^\({bot_name}\)\s*[:：\-]", 
        rf"^أنا\s+{bot_name}\s*[:：\-]",
        rf"^\[{bot_name}\]\s*[:：\-]"
    ]
    for p in prefixes:
        text = re.sub(p, "", text, flags=re.IGNORECASE).strip()
    return text

# 5. دالة الترجمة الذكية والآمنة لتجنب الأخطاء
def safe_translate(text, target_lang='en'):
    if not text.strip():
        return ""
    try:
        translated = GoogleTranslator(source='auto', target=target_lang).translate(text)
        return translated
    except Exception:
        # إرجاع النص الأصلي في حال وجود مشكلة في الاتصال بالترجمة
        return text

# 6. بناء السياق وتوجيه النماذج بالأسلوب والنبرة المحددة
def build_prompt_with_tone(bot_name, user_query, tone):
    system_personas = {
        "Gemini": "أنت Gemini، نموذج تحليلي ذكي، تعشق البيانات المنظمة وتصيغ إجاباتك بطريقة ذكية وعميقة جداً.",
        "ChatGPT": "أنت ChatGPT، نموذج متزن، تشرح الأمور بوضوح وسلاسة، وتصيغ أفكارك بأسلوب متكامل ومفهوم.",
        "Claude": "أنت Claude، نموذج مفكر وفيلسوف، تركز على التفاصيل الدقيقة، وتجيب بحكمة ووعي وضمير.",
        "Grok": "أنت Grok، نموذج متمرد ومرح، وتستخدم خفة الظل والأسلوب المشوق والتحدي الفكري في الردود.",
        "Kimi": "أنت Kimi، نموذج سريع البديهة، ذو مهارة استدلالية عالية جداً، وتركز على تبسيط الفكرة الصعبة وسرعة إيصالها."
    }
    
    tone_directives = {
        "علمي وأكاديمي دقيق 📚": "اكتب بأسلوب علمي ومنهجي مستنداً إلى الحقائق والمنطق الرصين.",
        "ساخر ومرح ومضحك 🎭": "اكتب بأسلوب مضحك، ساخر، مليء بالمزاح والتعليقات الطريفة والذكية.",
        "ودي، داعم وإيجابي 🤝": "اكتب بأسلوب دافئ وودي للغاية، يشجع الآخرين ويعبر عن تفاؤلك وتأييدك.",
        "مختصر، سريع ومباشر ⚡": "اكتب في سطرين فقط وبطريقة رصاصية ومباشرة بدون مقدمات طويلاً."
    }
    
    base_prompt = f"{system_personas.get(bot_name, 'أنت مستشار ذكاء اصطناعي')}\n"
    base_prompt += f"توجيهات النبرة: {tone_directives.get(tone, '')}\n"
    base_prompt += "المطلوب: أجب باللغة العربية الفصحى وبشخصيتك المستقلة، ولا تكرر اسمك أو أسماء الآخرين في بداية إجابتك.\n\n"
    
    # تضمين آخر رسائل من السياق لضمان الترابط التام للنقاش
    history_context = ""
    for msg in st.session_state.chat_history[-5:]:
        history_context += f"{msg['sender']}: {msg['content_ar']}\n"
        
    full_prompt = f"{base_prompt}سجل النقاش السابق:\n{history_context}\nسؤال المستخدم الحالي: {user_query}\nأجب الآن كشخصية {bot_name} مباشرة:"
    return full_prompt

# 7. دالة توليد الردود المجانية عبر واجهة مستقرة (Pollinations)
def generate_free_response(bot_name, prompt):
    try:
        # استخدام Pollinations AI مع تفعيل بذور عشوائية لضمان تنوع وتعدد الردود
        seed = random.randint(1, 99999)
        url = f"https://text.pollinations.ai/{requests.utils.quote(prompt)}?model=openai&seed={seed}"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            raw_text = response.text.strip()
            return clean_response(raw_text, bot_name)
        else:
            return f"مرحباً بك! كشخصية {bot_name}، أرى أن هذا الموضوع يفتح آفاقاً رائعة للنقاش المستقبلي."
    except Exception:
        return f"كشخصية {bot_name}، أود أن أضيف أن زاوية النظر لهذه المسألة تبدأ من الفهم السليم للأساسيات وتطوير الحوار."

# 8. عرض شاشة المحادثة التفاعلية
st.write("### 🖥️ شاشة المحادثة النشطة (مترجمة ثنائياً):")
for msg in st.session_state.chat_history:
    # تخصيص لون الأيقونة والاسم بناء على المتحدث
    avatar_emoji = "👤"
    if "Gemini" in msg["sender"]: avatar_emoji = "♊"
    elif "ChatGPT" in msg["sender"]: avatar_emoji = "💬"
    elif "Claude" in msg["sender"]: avatar_emoji = "🧠"
    elif "Grok" in msg["sender"]: avatar_emoji = "🏴‍☠️"
    elif "Kimi" in msg["sender"]: avatar_emoji = "🥝"
    
    with st.chat_message(msg["role"], avatar=avatar_emoji):
        st.markdown(f"**{msg['sender']}**")
        st.markdown(f"**بالعربية:** {msg['content_ar']}")
        st.markdown(f"*English:* {msg['content_en']}")
        st.markdown("---")

# 9. حقل إدخال الرسائل من المستخدم
if user_input := st.chat_input("اكتب رسالتك بالعربية هنا لتظهر للجميع..."):
    # ترجمة رسالة المستخدم تلقائياً
    user_en = safe_translate(user_input, 'en')
        
    st.session_state.chat_history.append({
        "role": "user",
        "sender": "أنت (المستخدم)",
        "content_ar": user_input,
        "content_en": user_en
    })
    st.rerun()

# 10. تشغيل ردود النماذج بعد استلام رسالة جديدة
if len(st.session_state.chat_history) > 0 and st.session_state.chat_history[-1]["role"] == "user":
    last_user_query = st.session_state.chat_history[-1]["content_ar"]
    
    # تحديد المتحدثين المطلوبين
    all_spks = ["Gemini", "ChatGPT", "Claude", "Grok", "Kimi"]
    speakers = []
    
    if talk_mode == "الجميع بالترتيب المتتابع":
        speakers = all_spks
    elif talk_mode == "متحدث واحد محدد فقط":
        # تنظيف الاسم من الإيموجي المضاف للتصميم
        clean_name = selected_speaker.split(" ")[0]
        speakers = [clean_name]
    elif talk_mode == "اختيار متحدث عشوائي":
        speakers = [random.choice(all_spks)]

    # تكرار التوليد لكل نموذج
    for spk in speakers:
        with st.spinner(f"[{spk}] يقرأ الحوار ويكتب رده بنبرة ({chat_tone})..."):
            # بناء التوجيه بالنبرة المختارة
            prompt = build_prompt_with_tone(spk, last_user_query, chat_tone)
            # استدعاء النموذج
            reply = generate_free_response(spk, prompt)
            # ترجمة الرد
            reply_en = safe_translate(reply, 'en')
                
            st.session_state.chat_history.append({
                "role": "assistant",
                "sender": f"{spk}",
                "content_ar": reply,
                "content_en": reply_en
            })
    st.rerun()

# 11. ميزة تصدير وتحميل الدردشة في الشريط الجانبي في حال وجود محادثات
if len(st.session_state.chat_history) > 0:
    st.sidebar.markdown("---")
    st.sidebar.header("📥 حفظ وتصدير النقاش")
    
    # إنشاء نص المحادثة المنسق
    chat_export_text = "=== سجل الغرفة الخماسية الكبرى ===\n\n"
    for msg in st.session_state.chat_history:
        chat_export_text += f"[{msg['sender']}]:\n"
        chat_export_text += f"بالعربية: {msg['content_ar']}\n"
        chat_export_text += f"English: {msg['content_en']}\n"
        chat_export_text += "----------------------------------------\n"
        
    st.sidebar.download_button(
        label="📥 تحميل كامل المحادثة كملف نصي",
        data=chat_export_text,
        file_name="big5_chat_session.txt",
        mime="text/plain",
        use_container_width=True
    )
