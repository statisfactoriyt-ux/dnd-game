import streamlit as st
import time
import os
import re
import random
from openai import OpenAI

# === ПОЛУЧЕНИЕ API КЛЮЧА (для Cloud + локально) ===
try:
    # Пытаемся получить ключ из секретов Streamlit Cloud
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
except (FileNotFoundError, KeyError):
    # Если не получилось — пробуем загрузить из .env (для локальной разработки)
    from dotenv import load_dotenv

    load_dotenv()
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    st.error("❌ API ключ не найден! Добавьте OPENROUTER_API_KEY в Secrets (на Cloud) или в .env (локально).")
    st.stop()

# === ПОДКЛЮЧЕНИЕ К OPENROUTER ===
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    default_headers={
        "HTTP-Referer": "http://localhost:8501",
        "X-Title": "D&D Game"
    }
)


# === ФУНКЦИЯ БРОСКА КУБИКА ===
def roll_dice(sides=20, description="🎲 Бросок"):
    """Анимированный бросок кубика"""
    result = random.randint(1, sides)
    dice_html = f"""
    <div style="text-align: center; padding: 10px; background: rgba(255,107,107,0.1); border-radius: 10px; margin: 10px 0;">
        <div style="font-size: 64px; animation: roll 0.6s ease;">
            🎲
        </div>
        <div style="font-size: 28px; font-weight: bold; color: #ff6b6b;">
            {description}: {result}
        </div>
    </div>
    """
    return result, dice_html


# === ПАРСЕР БРОСКОВ КУБИКА ===
def parse_dice_rolls(response_text):
    """Ищет в ответе ИИ упоминания о бросках кубика"""
    dice_results = []
    patterns = [
        r'(?:бросок|кубик|d20)\s*[:]?\s*(\d{1,2})',
        r'(?:проверка|атака|спасение)\s*[:]?\s*(\d{1,2})',
        r'показал\s*(\d{1,2})',
        r'выпало\s*(\d{1,2})',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, response_text, re.IGNORECASE)
        for match in matches:
            value = int(match)
            if 1 <= value <= 20:
                dice_results.append(value)
    return dice_results


# === ПАРСЕР ИНВЕНТАРЯ ===
def parse_inventory_from_response(response_text, players):
    """Ищет в ответе ИИ упоминания о добавлении предметов"""
    added_items = {}
    patterns = [
        r'получаешь\s+([^,!\.]+)\s*[\(!\.]',
        r'находишь\s+([^,!\.]+)\s*[\(!\.]',
        r'кладёшь\s+([^,!\.]+)\s+в\s+рюкзак',
        r'добавлено\s+в\s+инвентарь\s*[:]?\s*([^,!\.]+)',
        r'получает\s+([^,!\.]+)\s*[\(!\.]',
    ]
    for name in players.keys():
        for pattern in patterns:
            full_pattern = rf'{name}\s+(?:{pattern})'
            matches = re.findall(full_pattern, response_text, re.IGNORECASE)
            for match in matches:
                item = match.strip()
                if item and len(item) < 30:
                    if name not in added_items:
                        added_items[name] = []
                    added_items[name].append(item)
            if not added_items.get(name):
                matches = re.findall(pattern, response_text, re.IGNORECASE)
                for match in matches:
                    item = match.strip()
                    if item and len(item) < 30:
                        if name not in added_items:
                            added_items[name] = []
                        added_items[name].append(item)
    return added_items


# === ГЕНЕРАЦИЯ НАЧАЛЬНОГО ИНВЕНТАРЯ ===
def generate_starting_inventory(history, race, char_class):
    """Генерирует начальный инвентарь на основе истории персонажа"""
    try:
        response = client.chat.completions.create(
            model="openrouter/free",
            messages=[
                {"role": "system",
                 "content": "Ты — Мастер D&D. На основе истории, расы и класса персонажа, сгенерируй начальный инвентарь. Ответь ТОЛЬКО списком предметов через запятую. Максимум 5 предметов."},
                {"role": "user", "content": f"""
Раса: {race}
Класс: {char_class}
История: {history}

Напиши начальный инвентарь (только список через запятую):
"""}
            ]
        )
        inventory_text = response.choices[0].message.content
        items = [item.strip() for item in inventory_text.split(",") if item.strip()]
        return items[:5]
    except Exception as e:
        print(f"Ошибка генерации инвентаря: {e}")
        return ["рюкзак", "тетрадь", "ручка"]


# === ИНИЦИАЛИЗАЦИЯ ТЕМЫ ===
if "theme" not in st.session_state:
    st.session_state.theme = "dark"

# === ИНИЦИАЛИЗАЦИЯ СОСТОЯНИЯ ИГРЫ ===
if "game_state" not in st.session_state:
    st.session_state.game_state = {
        "history": [{"role": "system", "content": """
Ты — Мастер подземелий (DM). Ты ведёшь игру на РУССКОМ языке.

**СВЯЩЕННОЕ ПРАВИЛО (НЕ НАРУШАТЬ):**
- Ты НЕ изменяешь, НЕ дополняешь и НЕ переписываешь историю персонажа.
- Ты начинаешь игру ТОЧНО ТАМ, ГДЕ находится персонаж по его истории.
- Если игрок написал: "Я ученик 8 класса в школе" — он в ШКОЛЕ. Не в лаборатории, не в лесу, не в подземелье.
- Ты НЕ добавляешь события, которых не было в истории.
- Ты НЕ переносишь персонажа в другое место без его согласия.

**БРОСКИ КУБИКА (d20):**
- Описывай броски в формате: "Бросок d20: [число]"

**ДОБАВЛЕНИЕ ПРЕДМЕТОВ:**
- Пиши: "Имя получает [предмет]! (добавлено в инвентарь)"

**ЗАПРЕЩЕНО:**
- Изменять историю персонажа.
- Переносить игрока без его согласия.
- Использовать английские слова.
- Создавать новых игроков.

**СТИЛЬ:**
- Кратко (2-3 абзаца).
- Задавай вопрос: "Что ты делаешь?"
"""}],
        "players": {},
        "round_number": 1,
        "timer_start": None,
        "timer_duration": 60,
        "round_results": [],
        "game_phase": "character_creation"
    }

if "player_name" not in st.session_state:
    st.session_state.player_name = None
if "player_history" not in st.session_state:
    st.session_state.player_history = ""
if "player_class" not in st.session_state:
    st.session_state.player_class = ""
if "player_race" not in st.session_state:
    st.session_state.player_race = ""
if "player_inventory" not in st.session_state:
    st.session_state.player_inventory = []

# === НАСТРОЙКА СТРАНИЦЫ ===
st.set_page_config(page_title="🎲 D&D с ИИ", page_icon="🎲", layout="wide")

# === CSS ДЛЯ ДВУХ ТЕМ ===
if st.session_state.theme == "dark":
    theme_css = """
    <style>
        .main { background-color: #0e1117; }
        .stApp { background-color: #0e1117; }
        .stApp, .stApp > header, .stApp > div { background-color: #0e1117; }
        h1, h2, h3, h4, h5, h6, .stMarkdown, p, label, .stTextInput label, .stSelectbox label, .stTextArea label {
            color: #e0e0e0 !important;
        }
        .stTextInput > div > div > input {
            background-color: #1e1e2e !important;
            color: #e0e0e0 !important;
            border: 1px solid #3d3d5c !important;
            border-radius: 8px !important;
        }
        .stTextArea > div > div > textarea {
            background-color: #1e1e2e !important;
            color: #e0e0e0 !important;
            border: 1px solid #3d3d5c !important;
            border-radius: 8px !important;
        }
        .stButton > button {
            background-color: #ff6b6b !important;
            color: white !important;
            border-radius: 10px !important;
            border: none !important;
            transition: all 0.3s !important;
        }
        .stButton > button:hover {
            background-color: #ff4757 !important;
            transform: scale(1.02) !important;
        }
        .player-card {
            background-color: #1e1e2e !important;
            padding: 15px !important;
            border-radius: 10px !important;
            margin: 5px 0 !important;
            border-left: 4px solid #ff6b6b !important;
            color: #e0e0e0 !important;
        }
        .inventory-item {
            background-color: #2d2d44 !important;
            padding: 5px 10px !important;
            border-radius: 5px !important;
            margin: 3px 0 !important;
            font-size: 14px !important;
            color: #e0e0e0 !important;
        }
        .stSidebar {
            background-color: #161621 !important;
        }
        .stSidebar .stMarkdown, .stSidebar p, .stSidebar label {
            color: #e0e0e0 !important;
        }
        .hp-bar {
            background-color: #2d2d44 !important;
            border-radius: 10px !important;
            height: 20px !important;
            overflow: hidden !important;
            margin: 5px 0 !important;
        }
        .hp-fill {
            background: linear-gradient(90deg, #ff6b6b, #ff4757) !important;
            height: 100% !important;
            transition: width 0.5s !important;
            border-radius: 10px !important;
        }
        .stChatMessage {
            background-color: #1a1a2e !important;
            border-radius: 10px !important;
            padding: 10px !important;
            margin: 5px 0 !important;
            color: #e0e0e0 !important;
        }
        .timer-circle {
            width: 80px !important;
            height: 80px !important;
            border-radius: 50% !important;
            border: 4px solid #ff6b6b !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            font-size: 24px !important;
            font-weight: bold !important;
            color: #e0e0e0 !important;
            margin: 0 auto !important;
        }
        .timer-warning {
            border-color: #ff4757 !important;
            animation: pulse 0.5s ease infinite !important;
        }
        @keyframes roll {
            0% { transform: rotate(0deg) scale(1); }
            25% { transform: rotate(90deg) scale(1.3); }
            50% { transform: rotate(180deg) scale(0.7); }
            75% { transform: rotate(270deg) scale(1.2); }
            100% { transform: rotate(360deg) scale(1); }
        }
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
    </style>
    """
else:
    theme_css = """
    <style>
        .main { background-color: #ffffff; }
        .stApp { background-color: #ffffff; }
        h1, h2, h3, h4, h5, h6, .stMarkdown, p, label {
            color: #1a1a2e !important;
        }
        .stTextInput > div > div > input {
            background-color: #f5f5f5 !important;
            color: #1a1a2e !important;
            border: 1px solid #d0d0d0 !important;
            border-radius: 8px !important;
        }
        .stTextArea > div > div > textarea {
            background-color: #f5f5f5 !important;
            color: #1a1a2e !important;
            border: 1px solid #d0d0d0 !important;
            border-radius: 8px !important;
        }
        .stButton > button {
            background-color: #ff6b6b !important;
            color: white !important;
            border-radius: 10px !important;
            border: none !important;
        }
        .stButton > button:hover {
            background-color: #ff4757 !important;
        }
        .player-card {
            background-color: #f5f5f5 !important;
            padding: 15px !important;
            border-radius: 10px !important;
            margin: 5px 0 !important;
            border-left: 4px solid #ff6b6b !important;
            color: #1a1a2e !important;
        }
        .inventory-item {
            background-color: #e8e8e8 !important;
            padding: 5px 10px !important;
            border-radius: 5px !important;
            margin: 3px 0 !important;
            font-size: 14px !important;
            color: #1a1a2e !important;
        }
        .stSidebar {
            background-color: #f0f0f5 !important;
        }
        .stSidebar .stMarkdown, .stSidebar p, .stSidebar label {
            color: #1a1a2e !important;
        }
        .hp-bar {
            background-color: #e0e0e0 !important;
            border-radius: 10px !important;
            height: 20px !important;
            overflow: hidden !important;
            margin: 5px 0 !important;
        }
        .hp-fill {
            background: linear-gradient(90deg, #ff6b6b, #ff4757) !important;
            height: 100% !important;
            transition: width 0.5s !important;
            border-radius: 10px !important;
        }
        .stChatMessage {
            background-color: #f5f5f5 !important;
            border-radius: 10px !important;
            padding: 10px !important;
            margin: 5px 0 !important;
            color: #1a1a2e !important;
        }
        .timer-circle {
            width: 80px !important;
            height: 80px !important;
            border-radius: 50% !important;
            border: 4px solid #ff6b6b !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            font-size: 24px !important;
            font-weight: bold !important;
            color: #1a1a2e !important;
            margin: 0 auto !important;
        }
        .timer-warning {
            border-color: #ff4757 !important;
            animation: pulse 0.5s ease infinite !important;
        }
    </style>
    """

st.markdown(theme_css, unsafe_allow_html=True)

# === ПЕРЕКЛЮЧАТЕЛЬ ТЕМЫ ===
col_theme1, col_theme2 = st.columns([6, 1])
with col_theme2:
    theme_label = "🌙" if st.session_state.theme == "dark" else "☀️"
    if st.button(theme_label, help="Переключить тему"):
        st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
        st.rerun()

# === ФАЗА 1: СОЗДАНИЕ ПЕРСОНАЖА ===
if st.session_state.game_state["game_phase"] == "character_creation":
    st.title("🎲 Создание персонажа")

    st.markdown("""
    <div style="background: rgba(255,107,107,0.1); padding: 15px; border-radius: 10px; margin-bottom: 20px;">
        <p style="color: #ff6b6b; margin: 0;">
            💡 Ты можешь создать <b>любого</b> персонажа! Ковбой, киборг, эльф-маг, мутант-сталкер, 
            ученик 8 класса — всё что угодно. Мир и правила подстроятся под твою историю.
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 👤 Основное")
        name = st.text_input("Имя персонажа", value=st.session_state.player_name or "")
        race = st.text_input(
            "Раса (любая)",
            value=st.session_state.player_race or "",
            placeholder="Например: Ковбой, Киборг, Эльф, Мутант, Человек"
        )
        char_class = st.text_input(
            "Класс (любой)",
            value=st.session_state.player_class or "",
            placeholder="Например: Стрелок, Хакер, Маг, Сталкер, Ученик"
        )

    with col2:
        st.markdown("### 📜 История персонажа")
        st.markdown("*Опиши прошлое своего героя. Это определит мир и сюжет.*")
        history = st.text_area(
            "История",
            value=st.session_state.player_history or "",
            placeholder="Пример: Я — ученик 8 класса в школе №43. Живу в Москве. У меня есть рюкзак, тетрадь и ручка.",
            height=150
        )

    if st.button("🚀 Начать приключение!", type="primary", use_container_width=True):
        if not name.strip():
            st.error("❌ Введите имя персонажа!")
        elif not race.strip():
            st.error("❌ Введите расу!")
        elif not char_class.strip():
            st.error("❌ Введите класс!")
        elif not history.strip():
            st.error("❌ Напишите историю персонажа!")
        else:
            st.session_state.player_name = name
            st.session_state.player_race = race
            st.session_state.player_class = char_class
            st.session_state.player_history = history

            st.session_state.game_state["players"][name] = {
                "action": "",
                "ready": False,
                "hp": 20,
                "max_hp": 20,
                "race": race,
                "class": char_class,
                "inventory": [],
                "level": 1,
                "exp": 0
            }

            st.session_state.game_state["game_phase"] = "prologue"
            st.rerun()

    st.stop()

# === ФАЗА 2: ПРОЛОГ + ГЕНЕРАЦИЯ ИНВЕНТАРЯ ===
if st.session_state.game_state["game_phase"] == "prologue":
    with st.spinner("🎲 Генерация мира и инвентаря..."):
        try:
            # Генерируем инвентарь для каждого игрока
            for name, data in st.session_state.game_state["players"].items():
                if "inventory" not in data or not data["inventory"]:
                    history = st.session_state.player_history if name == st.session_state.player_name else "Нет истории"
                    inv = generate_starting_inventory(history, data.get("race", ""), data.get("class", ""))
                    data["inventory"] = inv

            # Генерируем пролог
            players_info = []
            for name, data in st.session_state.game_state["players"].items():
                history = st.session_state.player_history if name == st.session_state.player_name else "Нет истории"
                players_info.append(f"{name} ({data['race']}, {data['class']}): {history}")

            system_prompt = st.session_state.game_state["history"][0]["content"]

            prologue_response = client.chat.completions.create(
                model="openrouter/free",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"""
Создай пролог для игры. Учитывай следующие истории персонажей:

{chr(10).join(players_info)}

**ВАЖНЕЙШЕЕ ПРАВИЛО:**
- Начни игру ТАМ, ГДЕ находится персонаж по его истории.
- НЕ изменяй историю персонажа. Ты только продолжаешь её.
- Если персонаж ученик в школе — он в ШКОЛЕ. Не придумывай лабораторию, подземелье или лес.
- Добавь ПРОСТОЕ событие в этом месте (например, странный звук за дверью, учитель входит в класс, звонок на урок).

Напиши краткое вступление (3-4 предложения) и задай вопрос: "Что ты делаешь?"
"""}
                ]
            )

            prologue_text = prologue_response.choices[0].message.content

            if prologue_text and prologue_text.strip():
                st.session_state.game_state["round_results"].append(f"📜 **Пролог**\n\n{prologue_text}")
                st.session_state.game_state["history"].append({"role": "assistant", "content": prologue_text})
                st.session_state.game_state["game_phase"] = "playing"
                st.rerun()
            else:
                raise ValueError("Пустой ответ от ИИ")

        except Exception as e:
            st.error(f"Ошибка генерации пролога: {e}")
            st.session_state.game_state["round_results"].append(
                "📜 **Пролог**\n\nТы сидишь на уроке. За окном обычный день. Что ты делаешь?"
            )
            st.session_state.game_state["game_phase"] = "playing"
            st.rerun()

    st.stop()

# === ОСНОВНАЯ ИГРА ===
st.title(f"🎲 Раунд {st.session_state.game_state['round_number']}")

# === ЛЕВАЯ ПАНЕЛЬ: Характеристики персонажа ===
with st.sidebar:
    st.markdown("### 👤 Мой персонаж")

    player_data = st.session_state.game_state["players"].get(st.session_state.player_name, {})

    if player_data:
        hp = player_data.get("hp", 20)
        max_hp = player_data.get("max_hp", 20)
        hp_percent = (hp / max_hp) * 100

        st.markdown(f"**{st.session_state.player_name}**")
        st.markdown(f"*{player_data.get('race', 'Человек')} {player_data.get('class', 'Воин')}*")

        st.markdown(f"**❤️ HP:** {hp}/{max_hp}")
        st.markdown(f"""
        <div class="hp-bar">
            <div class="hp-fill" style="width: {hp_percent}%;"></div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"**📈 Уровень:** {player_data.get('level', 1)}")
        st.markdown(f"**⭐ Опыт:** {player_data.get('exp', 0)}")

        st.markdown("### 🎒 Инвентарь")
        inventory = player_data.get("inventory", [])
        if inventory:
            for item in inventory:
                st.markdown(f"<div class='inventory-item'>• {item}</div>", unsafe_allow_html=True)
        else:
            st.caption("Инвентарь пуст")

        st.divider()
        st.caption(f"Раунд {st.session_state.game_state['round_number']}")

        # === КНОПКА НОВАЯ ИГРА ===
        if st.button("🔄 Новая игра (сброс)", type="secondary"):
            st.session_state.game_state["history"] = [st.session_state.game_state["history"][0]]
            st.session_state.game_state["round_results"] = []
            st.session_state.game_state["round_number"] = 1
            st.session_state.game_state["players"] = {}
            st.session_state.player_name = None
            st.session_state.game_state["game_phase"] = "character_creation"
            st.rerun()

# === ПРАВАЯ ПАНЕЛЬ: Все игроки ===
with st.sidebar:
    st.markdown("### 👥 Все игроки")
    for name, data in st.session_state.game_state["players"].items():
        if name != st.session_state.player_name:
            hp = data.get("hp", 20)
            max_hp = data.get("max_hp", 20)
            status = "✅ Готов" if data.get("ready", False) else "✏️ Пишет..."
            st.markdown(f"""
            <div class='player-card'>
                <b>{name}</b> ({data.get('race', '')} {data.get('class', '')})<br>
                ❤️ {hp}/{max_hp} HP — {status}
            </div>
            """, unsafe_allow_html=True)

    if st.button("⚔️ Завершить раунд (админ)"):
        for name in st.session_state.game_state["players"]:
            if not st.session_state.game_state["players"][name]["ready"]:
                st.session_state.game_state["players"][name]["ready"] = True
        st.rerun()

# === ОТОБРАЖЕНИЕ ИСТОРИИ ===
for msg in st.session_state.game_state["round_results"]:
    with st.chat_message("assistant"):
        st.markdown(msg)

# === ВВОД ДЕЙСТВИЯ ===
if st.session_state.game_state["game_phase"] == "playing":
    current_player = st.session_state.game_state["players"][st.session_state.player_name]
    players = st.session_state.game_state["players"]

    if current_player["ready"]:
        st.info("✅ Вы уже отправили действие. Ждём остальных...")
    else:
        action = st.text_area(
            "Ваше действие:",
            value="",
            placeholder="Напишите, что делает ваш персонаж...",
            height=100,
            key=f"action_input_{st.session_state.game_state['round_number']}"
        )

        if st.button("📤 Отправить действие", type="primary"):
            if action.strip():
                current_player["action"] = action
                current_player["ready"] = True
                st.session_state.game_state["timer_start"] = None
                st.rerun()
            else:
                st.error("Напишите действие!")

        ready_count = sum(1 for p in players.values() if p["ready"])
        total = len(players)

        if ready_count >= total * 0.5 and ready_count < total:
            if st.session_state.game_state["timer_start"] is None:
                st.session_state.game_state["timer_start"] = time.time()

            elapsed = time.time() - st.session_state.game_state["timer_start"]
            remaining = max(0, st.session_state.game_state["timer_duration"] - elapsed)

            color = "green" if remaining > 20 else "orange" if remaining > 10 else "red"

            st.markdown(f"""
            <div style="text-align: center; margin: 10px 0;">
                <div class="timer-circle {'timer-warning' if remaining < 10 else ''}" 
                     style="border-color: {color};">
                    {int(remaining)}с
                </div>
                <p style="color: {color}; margin-top: 5px;">
                    ⚡ {ready_count}/{total} игроков готовы! Торопитесь!
                </p>
            </div>
            """, unsafe_allow_html=True)

            if remaining <= 0:
                if not current_player["ready"]:
                    if current_player["action"].strip():
                        current_player["ready"] = True
                    else:
                        current_player["action"] = "пропускает ход (замешкался)"
                        current_player["ready"] = True
                    st.session_state.game_state["timer_start"] = None
                    st.rerun()

    all_ready = all(p["ready"] for p in players.values())
    has_actions = any(p["action"].strip() for p in players.values())

    if all_ready and has_actions:
        with st.spinner("🎲 Мастер обдумывает события..."):
            actions_list = []
            for name, data in players.items():
                if data["action"].strip() and not data["action"] == "пропускает ход (замешкался)":
                    actions_list.append(f"{name}: {data['action']}")
                elif data["action"] == "пропускает ход (замешкался)":
                    actions_list.append(f"{name}: замешкался и пропустил ход")

            actions_text = "\n".join(actions_list) if actions_list else "Все игроки замешкались."

            players_info = []
            for name, data in players.items():
                players_info.append(
                    f"{name} (здоровье: {data['hp']}/{data['max_hp']}, инвентарь: {', '.join(data.get('inventory', []))})")

            prompt = f"""
ПОМНИ: ты НЕ изменяешь историю персонажа. Ты продолжаешь её.

Раунд {st.session_state.game_state['round_number']}.

Персонажи:
{chr(10).join(players_info)}

Действия игроков:
{actions_text}

ВАЖНЫЕ ПРАВИЛА ПО ИНВЕНТАРЮ:
1. Игроки могут использовать ТОЛЬКО те предметы, которые есть в их инвентаре.
2. Если игрок пытается использовать предмет, которого у него нет — скажи, что его нет.
3. Ты можешь ДОБАВЛЯТЬ предметы в инвентарь по сюжету.
4. Когда добавляешь предмет — напиши в формате: "Имя получает [предмет]! (добавлено в инвентарь)"

Опиши результат. Обновляй здоровье в формате: ИМЯ: здоровье = X.
Используй только РУССКИЙ язык.
"""

            system_prompt = st.session_state.game_state["history"][0]["content"]

            messages_for_ai = [
                                  {"role": "system", "content": system_prompt}
                              ] + st.session_state.game_state["history"][1:] + [
                                  {"role": "user", "content": prompt}
                              ]

            try:
                status_placeholder = st.empty()
                status_placeholder.info("🎲 Мастер пишет...")

                response_placeholder = st.empty()
                full_response = ""

                stream = client.chat.completions.create(
                    model="openrouter/free",
                    messages=messages_for_ai,
                    stream=True
                )

                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        full_response += chunk.choices[0].delta.content
                        response_placeholder.markdown(
                            f"🎯 **Раунд {st.session_state.game_state['round_number']}**\n\n{full_response}▌")

                # === ПАРСИНГ БРОСКОВ КУБИКА ===
                dice_results = parse_dice_rolls(full_response)
                if dice_results:
                    dice_html = ""
                    for result in dice_results:
                        dice_html += f"""
                        <div style="text-align: center; padding: 10px; background: rgba(255,107,107,0.1); border-radius: 10px; margin: 10px 0;">
                            <div style="font-size: 64px; animation: roll 0.6s ease;">
                                🎲
                            </div>
                            <div style="font-size: 28px; font-weight: bold; color: #ff6b6b;">
                                Бросок d20: {result}
                            </div>
                        </div>
                        """
                    full_response = dice_html + "\n\n" + full_response

                # === ПАРСИНГ HP ===
                for name in players:
                    pattern = rf"{name}: здоровье = (\d+)"
                    match = re.search(pattern, full_response, re.IGNORECASE)
                    if match:
                        new_hp = int(match.group(1))
                        players[name]["hp"] = max(0, min(new_hp, players[name]["max_hp"]))

                # === ПАРСИНГ ИНВЕНТАРЯ ===
                added_items = parse_inventory_from_response(full_response, players)
                for name, items in added_items.items():
                    if name in players:
                        for item in items:
                            if item not in players[name]["inventory"]:
                                players[name]["inventory"].append(item)
                                st.success(f"📦 {name} получил: {item}")

                # Отображаем финальный ответ
                response_placeholder.markdown(
                    f"🎯 **Раунд {st.session_state.game_state['round_number']}**\n\n{full_response}")
                status_placeholder.empty()

                # Сохраняем в историю (убираем HTML-теги)
                clean_response = re.sub(r'<[^>]+>', '', full_response)
                st.session_state.game_state["round_results"].append(
                    f"🎯 **Раунд {st.session_state.game_state['round_number']}**\n\n{clean_response}"
                )
                st.session_state.game_state["history"].append({"role": "assistant", "content": clean_response})

                for name in players:
                    players[name]["action"] = ""
                    players[name]["ready"] = False
                st.session_state.game_state["round_number"] += 1
                st.session_state.game_state["timer_start"] = None

                st.rerun()

            except Exception as e:
                st.error(f"Ошибка при обращении к ИИ: {e}")

    if not all_ready:
        ready_count = sum(1 for p in players.values() if p["ready"])
        total = len(players)

        if ready_count >= total * 0.5 and ready_count < total:
            pass
        elif ready_count > 0:
            st.info(f"⏳ {ready_count}/{total} игроков готовы. Ожидаем остальных...")
        else:
            st.info("📝 Напишите ваше действие в поле выше.")