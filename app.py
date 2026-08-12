import json
import os
from datetime import datetime, date

import streamlit as st
import pandas as pd
from google import genai
from google.genai import types

# ============================================================
# 1) НАСТРОЙКА API-КЛЮЧА И КОНФИГУРАЦИИ
# ============================================================
if "GEMINI_API_KEY" in st.secrets:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
else:
    st.error("Критическая ошибка: API ключ не найден в Secrets хостинга!")
    st.stop()

MODEL_NAME = "gemini-3.6-flash"  
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "dish_name": {"type": "string"},
        "estimated_weight_g": {"type": "integer"},
        "calories": {"type": "integer"},
        "macros": {
            "type": "object",
            "properties": {
                "proteins": {"type": "integer"},
                "fats": {"type": "integer"},
                "carbs": {"type": "integer"},
            },
            "required": ["proteins", "fats", "carbs"],
        },
    },
    "required": ["dish_name", "estimated_weight_g", "calories", "macros"],
}

# Обновленный промпт с жесткими правилами калибровки веса фруктов/ягод
PROMPT_TEMPLATE = """Ты — строгий эксперт-нутрициолог. Посмотри на фото блюда и максимально реалистично
оцени его состав. Определи название блюда, примерный вес порции в граммах,
общую калорийность и БЖУ (белки, жиры, углеводы в граммах).

ВАЖНЫЕ ПРАВИЛА КАЛИБРОВКИ:
1. Будь консервативен в оценке веса. Если на фото тарелка с ягодами (черешня, ежевика) и небольшими плодами (персики/нектарины), 
   не завышай вес порции. Стандартная плоская тарелка таких фруктов весит примерно 350-500 грамм в сумме, а не 1-2 кг.
2. Внимательно считай калорийность: свежие ягоды и персики — это водянистые продукты с низкой плотностью калорий 
   (в среднем 40-50 ккал на 100г). Не присваивай им калорийность жирных или углеводных блюд.

{extra_context}
Отвечай СТРОГО в формате JSON, без каких-либо пояснений, комментариев или
markdown-разметки, только чистый JSON вида:
{{
  "dish_name": "Название блюда",
  "estimated_weight_g": 250,
  "calories": 380,
  "macros": {{"proteins": 15, "fats": 28, "carbs": 12}}
}}
"""

# ============================================================
# 2) ФУНКЦИИ ЛОГИКИ ПРИЛОЖЕНИЯ
# ============================================================
def analyze_image(image_bytes: bytes, mime_type: str, extra_details: str = "") -> dict:
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    extra_context = ""
    if extra_details.strip():
        extra_context = f"\nВАЖНОЕ УТОЧНЕНИЕ ОТ ПОЛЬЗОВАТЕЛЯ: {extra_details.strip()}\n"
    
    prompt = PROMPT_TEMPLATE.format(extra_context=extra_context)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[prompt, image_part],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            temperature=0.0,  # Делаем ответы ИИ стабильными, убирая случайный разброс
        ),
    )
    return json.loads(response.text)

def load_history() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

def save_history(history: list) -> None:
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def add_to_history(dish_name, weight, calories, proteins, fats, carbs, meal_type, extra_details) -> None:
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "dish_name": dish_name,
        "weight_g": weight,
        "calories": calories,
        "proteins": proteins,
        "fats": fats,
        "carbs": carbs,
        "meal_type": meal_type,
        "extra_details": extra_details.strip(),
    }
    history = load_history()
    history.append(entry)
    save_history(history)

# ============================================================
# 3) ИНТЕРФЕЙС STREAMLIT
# ============================================================
st.set_page_config(page_title="Калоризатор", page_icon="🍽️", layout="centered")

st.markdown("""
    <style>
    .stButton>button { width: 100%; padding: 10px; font-size: 16px; border-radius: 8px; }
    .stProgress > div > div > div > div { background-color: #4CAF50; }
    </style>
""", unsafe_allow_html=True)

st.title("🍽️ Мобильный Калоризатор")

history = load_history()
today_str = date.today().isoformat()
today_entries = [h for h in history if h["timestamp"].startswith(today_str)]

st.subheader("📊 Твой прогресс за сегодня")
daily_goal = st.number_input("Твоя цель калорий на день:", min_value=500, max_value=10000, value=2000, step=100)

total_cal = sum(e["calories"] for e in today_entries)
total_p = sum(e["proteins"] for e in today_entries)
total_f = sum(e["fats"] for e in today_entries)
total_c = sum(e["carbs"] for e in today_entries)

progress_ratio = min(total_cal / daily_goal, 1.0)
st.progress(progress_ratio)

c1, c2 = st.columns(2)
with c1:
    st.metric("Съедено", f"{total_cal} / {daily_goal} ккал")
with c2:
    left_cal = daily_goal - total_cal
    if left_cal >= 0:
        st.metric("Осталось", f"{left_cal} ккал")
    else:
        st.metric("Перебор на", f"{abs(left_cal)} ккал", delta_color="inverse")

b1, b2, b3 = st.columns(3)
b1.caption(f"🧬 Белки: {total_p} г")
b2.caption(f"🥑 Жиры: {total_f} г")
b3.caption(f"🍞 Угл: {total_c} г")

st.divider()

st.subheader("📸 Добавить приём пищи")
meal_type = st.selectbox("Тип приёма пищи:", ["Завтрак", "Обед", "Ужин", "Перекус"])
uploaded_file = st.file_uploader("Сделай фото или выбери из галереи", type=["jpg", "jpeg", "png", "webp"])

if uploaded_file is not None:
    st.image(uploaded_file, caption="Выбранное фото", use_container_width=True)
    extra_details = st.text_input("Уточнения (необязательно):", placeholder="Например: жарил без масла, соус сладкий")

    if "ai_result" not in st.session_state:
        st.session_state.ai_result = None
    if "last_uploaded" not in st.session_state or st.session_state.last_uploaded != uploaded_file.name:
        st.session_state.ai_result = None
        st.session_state.last_uploaded = uploaded_file.name

    if st.button("🔎 Распознать через ИИ", type="primary"):
        with st.spinner("ИИ изучает тарелку..."):
            try:
                image_bytes = uploaded_file.getvalue()
                mime_type = uploaded_file.type or "image/jpeg"
                st.session_state.ai_result = analyze_image(image_bytes, mime_type, extra_details)
                st.success("ИИ прислал оценку!")
            except Exception as e:
                st.error(f"Ошибка ИИ: {e}")

    if st.session_state.ai_result:
        st.markdown("### ✏️ Проверка и корректировка")
        edit_name = st.text_input("Название блюда:", value=st.session_state.ai_result["dish_name"])
        
        col_w, col_cal = st.columns(2)
        edit_weight = col_w.number_input("Вес порции (г):", value=int(st.session_state.ai_result["estimated_weight_g"]), step=10)
        edit_calories = col_cal.number_input("Калории (ккал):", value=int(st.session_state.ai_result["calories"]), step=5)
        
        st.markdown("**Редактировать БЖУ (г):**")
        col_p, col_f, col_c = st.columns(3)
        edit_p = col_p.number_input("Белки:", value=int(st.session_state.ai_result["macros"]["proteins"]), step=1)
        edit_f = col_f.number_input("Жиры:", value=int(st.session_state.ai_result["macros"]["fats"]), step=1)
        edit_c = col_c.number_input("Углеводы:", value=int(st.session_state.ai_result["macros"]["carbs"]), step=1)

        if st.button("💾 Сохранить в дневник", type="secondary"):
            add_to_history(edit_name, edit_weight, edit_calories, edit_p, edit_f, edit_c, meal_type, extra_details)
            st.success("Запись добавлена!")
            st.session_state.ai_result = None
            st.rerun()

st.divider()

with st.expander(f"📜 История и дневник питания ({len(history)})", expanded=False):
    if not history:
        st.write("Здесь будут появляться ваши приёмы пищи.")
    else:
        df = pd.DataFrame(history)
        
        for idx, entry in enumerate(reversed(history)):
            real_idx = len(history) - 1 - idx
            
            ts = entry["timestamp"].replace("T", " ")[5:16]
            m_type = entry.get("meal_type", "Перекус")
            meal_emoji = {"Завтрак": "🌅", "Обед": "☀️", "Ужин": "🌙", "Перекус": "🍏"}.get(m_type, "🍽️")
            
            col_text, col_del = st.columns([8, 2])
            
            with col_text:
                st.markdown(
                    f"**{ts} | {meal_emoji} {m_type}**\n"
                    f"**{entry['dish_name']}** ({entry['weight_g']}г) — **{entry['calories']} ккал**\n"
                    f"🧬 Б: {entry['proteins']}г | 🥑 Ж: {entry['fats']}г | 🍞 У: {entry['carbs']}г"
                )
                if entry.get("extra_details"):
                    st.caption(f"📝 *Уточнение: {entry['extra_details']}*")
            
            with col_del:
                if st.button("🗑️", key=f"del_{entry['timestamp']}_{real_idx}"):
                    updated_history = load_history()
                    if real_idx < len(updated_history):
                        updated_history.pop(real_idx)
                        save_history(updated_history)
                        st.success(f"Удалено!")
                        st.rerun()
            
            st.markdown("---")

        col_a, col_b = st.columns(2)
        with col_a:
            csv_data = df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Скачать CSV", data=csv_data, file_name="calories_history.csv", mime="text/csv")
        with col_b:
            if st.button("🗑️ Очистить всю историю"):
                save_history([])
                st.rerun()
