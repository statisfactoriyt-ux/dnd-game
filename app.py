import streamlit as st
import time
import os
import re
import random
from openai import OpenAI
from streamlit_server_state import server_state, server_state_lock

# === ПОДКЛЮЧЕНИЕ К ТВОЕМУ OLLAMA ЧЕРЕЗ NGROK ===
OLLAMA_URL = "https://cedar-giveaway-pamphlet.ngrok-free.dev/v1"

CLIENT = OpenAI(
    base_url=OLLAMA_URL,
    api_key="ollama"  # Любая строка
)

DEFAULT_MODEL = "llama3.2:3b"  # Или другая модель

# === ГЛОБАЛЬНОЕ СОСТОЯНИЕ (МУЛЬТИПЛЕЕР) ===
with server_state_lock["game_data"]:
    if "game_data" not in server_state:
        server_state.game_data = {
            "players": {},
            "online": set(),
            "history": [{"role": "system", "content": """
Ты — Мастер подземелий (DM). Ты ведёшь игру на РУССКОМ языке.

**СВЯЩЕННОЕ ПРАВИЛО (НЕ НАРУШАТЬ):**
- Ты НЕ изменяешь, НЕ дополняешь и НЕ переписываешь историю персонажа.
- Ты начинаешь игру ТОЧНО ТАМ, ГДЕ находится персонаж по его истории.
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
- Задавай вопрос: "Что вы делаете?"
"""}],
            "round_number": 1,
            "timer_start": None,
            "timer_duration": 60,
            "round_results": [],
            "game_phase": "waiting",
            "last_update": time.time()
        }

GAME = server_state.game_data


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def roll_dice(sides=20, description="🎲 Бросок"):
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


def parse_dice_rolls(response_text):
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


def parse_inventory_from_response(response_text, players):
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


def generate_starting_inventory(history, race, char_class):
    try:
        response = CLIENT.chat.completions.create(
            model=DEFAULT_MODEL,
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


# === НАСТРОЙКИ СТРАНИЦЫ ===
st.set_page_config(page_title="🎲 D&D с ИИ", page_icon="🎲", layout="wide")

# === CSS ===
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stApp { background-color: #0e1117; }
    h1, h2, h3, h4, h5, h6, .stMarkdown, p, label { color: #e0e0e0 !important; }
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
    .stSidebar { background-color: #161621 !important; }
    .stSidebar .stMarkdown, .stSidebar p, .stSidebar label { color: #e0e0e0 !important; }
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
""", unsafe_allow_html=True)

# === ИНИЦИАЛИЗАЦИЯ ===
if "player_name" not in st.session_state:
    st.session_state.player_name = None

if GAME["game_phase"] == "waiting":
    if st.session_state.player_name:
        if st.session_state.player_name not in GAME["players"]:
            st.session_state.player_name = None

col_title, col_online = st.columns([4, 1])
with col_title:
    st.title("🎲 D&D с ИИ")
with col_online:
    online_count = len(GAME["online"])
    st.markdown(f"""
    <div style="text-align: right; margin-top: 10px;">
        <span style="font-size: 18px; font-weight: bold; color: #00ff88;">🟢 {online_count} онлайн</span>
    </div>
    """, unsafe_allow_html=True)

if GAME["game_phase"] == "waiting":
    st.markdown("## 🎭 Ожидание игроков")

    if st.session_state.player_name:
        with server_state_lock["game_data"]:
            if st.session_state.player_name not in GAME["online"]:
                GAME["online"].add(st.session_state.player_name)

    st.markdown("### 👥 Игроки онлайн")
    if GAME["online"]:
        for name in GAME["online"]:
            if name in GAME["players"]:
                ready_status = "✅ Готов" if GAME["players"][name].get("ready", False) else "⏳ Ожидает"
                st.write(
                    f"- 🟢 {name} ({GAME['players'][name].get('race', '')} {GAME['players'][name].get('class', '')}) — {ready_status}")
            else:
                st.write(f"- 🟢 {name} (ожидает создания персонажа)")
    else:
        st.info("👤 Пока нет игроков онлайн")

    st.markdown("---")

    if st.session_state.player_name and st.session_state.player_name in GAME["players"]:
        st.success(f"✅ Вы уже создали персонажа: **{st.session_state.player_name}**")

        if st.button("🚪 Выйти из игры (удалить персонажа)", type="secondary"):
            with server_state_lock["game_data"]:
                if st.session_state.player_name in GAME["online"]:
                    GAME["online"].remove(st.session_state.player_name)
                if st.session_state.player_name in GAME["players"]:
                    del GAME["players"][st.session_state.player_name]
            st.session_state.player_name = None
            st.rerun()
    else:
        st.markdown("### 📝 Создать персонажа")
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Имя персонажа", placeholder="Введите имя")
            race = st.text_input("Раса", placeholder="Например: Ковбой, Эльф, Киборг")
            char_class = st.text_input("Класс", placeholder="Например: Стрелок, Маг, Хакер")
        with col2:
            history = st.text_area("История персонажа", placeholder="Опишите прошлое вашего героя", height=150)

        if st.button("➕ Добавить персонажа", type="primary"):
            if name and race and char_class and history:
                with server_state_lock["game_data"]:
                    if name not in GAME["players"]:
                        GAME["players"][name] = {
                            "action": "",
                            "ready": False,
                            "hp": 20,
                            "max_hp": 20,
                            "race": race,
                            "class": char_class,
                            "inventory": [],
                            "level": 1,
                            "exp": 0,
                            "history": history
                        }
                        st.session_state.player_name = name
                        st.rerun()
                    else:
                        st.error("Имя уже занято!")
            else:
                st.error("Заполните все поля!")

    st.markdown("---")

    if st.session_state.player_name and st.session_state.player_name in GAME["players"]:
        current_name = st.session_state.player_name

        with server_state_lock["game_data"]:
            is_ready = GAME["players"][current_name].get("ready", False)

        if not is_ready:
            if st.button("✅ Я готов!", type="primary", use_container_width=True):
                with server_state_lock["game_data"]:
                    GAME["players"][current_name]["ready"] = True
                st.rerun()
        else:
            st.success("✅ Вы готовы! Ожидаем остальных...")
            if st.button("❌ Отменить готовность"):
                with server_state_lock["game_data"]:
                    GAME["players"][current_name]["ready"] = False
                st.rerun()

        with server_state_lock["game_data"]:
            online_players = GAME["online"].copy()
            all_ready = all(
                name in GAME["players"] and GAME["players"][name].get("ready", False)
                for name in online_players
            )

        if online_players and all_ready and len(online_players) >= 1:
            st.success(f"🎉 Все {len(online_players)} игроков готовы!")
            if st.button("🚀 Начать игру!", type="primary", use_container_width=True):
                with st.spinner("🎲 Генерация мира..."):
                    with server_state_lock["game_data"]:
                        for name, data in GAME["players"].items():
                            if name in online_players and not data["inventory"]:
                                data["inventory"] = generate_starting_inventory(
                                    data.get("history", ""),
                                    data.get("race", ""),
                                    data.get("class", "")
                                )

                        players_info = []
                        for name, data in GAME["players"].items():
                            if name in online_players:
                                players_info.append(
                                    f"{name} ({data['race']}, {data['class']}): {data.get('history', '')}")

                        system_prompt = GAME["history"][0]["content"]

                    try:
                        prologue_response = CLIENT.chat.completions.create(
                            model=DEFAULT_MODEL,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": f"""
Создай пролог для игры. Учитывай следующие истории персонажей:

{chr(10).join(players_info)}

**ВАЖНЕЙШЕЕ ПРАВИЛО:**
- Начни игру ТАМ, ГДЕ находится каждый персонаж по его истории.
- НЕ изменяй историю персонажей. Ты только продолжаешь её.
- Объедини всех персонажей в одном месте и одной ситуации.

Напиши краткое вступление (3-4 предложения) и задай вопрос: "Что вы делаете?"
"""}
                            ]
                        )
                        prologue_text = prologue_response.choices[0].message.content

                        with server_state_lock["game_data"]:
                            GAME["round_results"].append(f"📜 **Пролог**\n\n{prologue_text}")
                            GAME["history"].append({"role": "assistant", "content": prologue_text})

                            for name in online_players:
                                if name in GAME["players"]:
                                    GAME["players"][name]["ready"] = False

                            GAME["game_phase"] = "playing"
                    except Exception as e:
                        st.error(f"Ошибка генерации пролога: {e}")
                        with server_state_lock["game_data"]:
                            GAME["round_results"].append(
                                "📜 **Пролог**\n\nВы стоите на перекрёстке судеб. Каждый из вас пришёл сюда со своей историей. Впереди вас ждёт неизведанный мир. Что вы делаете?"
                            )
                            GAME["game_phase"] = "playing"

                    st.rerun()

    time.sleep(3)
    st.rerun()
    st.stop()

st.title(f"🎲 Раунд {GAME['round_number']}")

with st.sidebar:
    players = GAME["players"]

    if st.session_state.player_name not in players:
        if players:
            st.session_state.player_name = list(players.keys())[0]
        else:
            st.session_state.player_name = None

    current_name = st.session_state.player_name

    if current_name and current_name in players:
        with server_state_lock["game_data"]:
            player_data = players[current_name]

        st.markdown("### 👤 Мой персонаж")
        st.markdown(f"**{current_name}**")
        st.markdown(f"*{player_data.get('race', 'Человек')} {player_data.get('class', 'Воин')}*")

        hp = player_data.get("hp", 20)
        max_hp = player_data.get("max_hp", 20)
        hp_percent = (hp / max_hp) * 100

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
        st.caption(f"Раунд {GAME['round_number']}")

        if st.button("🔄 Новая игра (сброс)", type="secondary"):
            with server_state_lock["game_data"]:
                GAME["players"] = {}
                GAME["online"] = set()
                GAME["round_number"] = 1
                GAME["round_results"] = []
                GAME["history"] = [GAME["history"][0]]
                GAME["game_phase"] = "waiting"
                GAME["timer_start"] = None
            st.session_state.player_name = None
            st.rerun()

    st.markdown("### 👥 Все игроки")
    for name, data in players.items():
        if name != current_name:
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
        with server_state_lock["game_data"]:
            for name in players:
                if not players[name]["ready"]:
                    players[name]["ready"] = True
        st.rerun()

for msg in GAME["round_results"]:
    with st.chat_message("assistant"):
        st.markdown(msg)

if GAME["game_phase"] == "playing":
    players = GAME["players"]

    if not players:
        st.warning("Нет игроков!")
        st.stop()

    if st.session_state.player_name not in players:
        st.session_state.player_name = list(players.keys())[0]

    with server_state_lock["game_data"]:
        current_player = players[st.session_state.player_name]

    if current_player["ready"]:
        st.info("✅ Вы уже отправили действие. Ждём остальных...")
    else:
        action = st.text_area(
            "Ваше действие:",
            value="",
            placeholder="Напишите, что делает ваш персонаж...",
            height=100,
            key=f"action_input_{GAME['round_number']}"
        )

        if st.button("📤 Отправить действие", type="primary"):
            if action.strip():
                with server_state_lock["game_data"]:
                    current_player["action"] = action
                    current_player["ready"] = True
                    GAME["timer_start"] = None
                st.rerun()
            else:
                st.error("Напишите действие!")

        with server_state_lock["game_data"]:
            ready_count = sum(1 for p in players.values() if p["ready"])
            total = len(players)

        if ready_count >= total * 0.5 and ready_count < total:
            with server_state_lock["game_data"]:
                if GAME["timer_start"] is None:
                    GAME["timer_start"] = time.time()

                elapsed = time.time() - GAME["timer_start"]
                remaining = max(0, GAME["timer_duration"] - elapsed)

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
                with server_state_lock["game_data"]:
                    if not current_player["ready"]:
                        if current_player["action"].strip():
                            current_player["ready"] = True
                        else:
                            current_player["action"] = "пропускает ход (замешкался)"
                            current_player["ready"] = True
                        GAME["timer_start"] = None
                st.rerun()

    with server_state_lock["game_data"]:
        all_ready = all(p["ready"] for p in players.values())
        has_actions = any(p["action"].strip() for p in players.values())

    if all_ready and has_actions:
        with st.spinner("🎲 Мастер обдумывает события..."):
            with server_state_lock["game_data"]:
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

Раунд {GAME['round_number']}.

Персонажи:
{chr(10).join(players_info)}

Действия игроков:
{actions_text}

Опиши результат. Обновляй здоровье в формате: ИМЯ: здоровье = X.
Используй только РУССКИЙ язык.
"""

            system_prompt = GAME["history"][0]["content"]

            messages_for_ai = [
                                  {"role": "system", "content": system_prompt}
                              ] + GAME["history"][1:] + [
                                  {"role": "user", "content": prompt}
                              ]

            try:
                status_placeholder = st.empty()
                status_placeholder.info("🎲 Мастер пишет...")

                response_placeholder = st.empty()
                full_response = ""

                # === СТРИМИНГ ЧЕРЕЗ OLLAMA ===
                stream = CLIENT.chat.completions.create(
                    model=DEFAULT_MODEL,
                    messages=messages_for_ai,
                    stream=True
                )

                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        full_response += chunk.choices[0].delta.content
                        response_placeholder.markdown(f"🎯 **Раунд {GAME['round_number']}**\n\n{full_response}▌")

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

                with server_state_lock["game_data"]:
                    for name in players:
                        pattern = rf"{name}: здоровье = (\d+)"
                        match = re.search(pattern, full_response, re.IGNORECASE)
                        if match:
                            new_hp = int(match.group(1))
                            players[name]["hp"] = max(0, min(new_hp, players[name]["max_hp"]))

                    added_items = parse_inventory_from_response(full_response, players)
                    for name, items in added_items.items():
                        if name in players:
                            for item in items:
                                if item not in players[name]["inventory"]:
                                    players[name]["inventory"].append(item)
                                    st.success(f"📦 {name} получил: {item}")

                response_placeholder.markdown(f"🎯 **Раунд {GAME['round_number']}**\n\n{full_response}")
                status_placeholder.empty()

                clean_response = re.sub(r'<[^>]+>', '', full_response)

                with server_state_lock["game_data"]:
                    GAME["round_results"].append(
                        f"🎯 **Раунд {GAME['round_number']}**\n\n{clean_response}"
                    )
                    GAME["history"].append({"role": "assistant", "content": clean_response})

                    for name in players:
                        players[name]["action"] = ""
                        players[name]["ready"] = False
                    GAME["round_number"] += 1
                    GAME["timer_start"] = None

                st.rerun()

            except Exception as e:
                st.error(f"Ошибка при обращении к ИИ: {e}")

    if not all_ready:
        with server_state_lock["game_data"]:
            ready_count = sum(1 for p in players.values() if p["ready"])
            total = len(players)

        if ready_count >= total * 0.5 and ready_count < total:
            pass
        elif ready_count > 0:
            st.info(f"⏳ {ready_count}/{total} игроков готовы. Ожидаем остальных...")
        else:
            st.info("📝 Напишите ваше действие в поле выше.")

    time.sleep(3)
    st.rerun()