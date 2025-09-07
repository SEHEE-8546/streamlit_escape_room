import streamlit as st
import google.generativeai as genai
import os
import re
import pygame
from dotenv import load_dotenv
from datetime import datetime, timedelta
import base64

# 상수 정의
DIFFICULTY_TIMERS = {
    1: 1800,  # 난이도 1: 30분
    2: 3600,  # 난이도 2: 1시간
    3: 5400,  # 난이도 3: 1시간 30분
}

# 초기 설정 및 API 로드
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    st.error("Gemini API 키를 찾을 수 없습니다.")
    st.stop()

# BGM
def initialize_bgm():
    # BGM을 반복 재생
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bgm_path = os.path.join(script_dir, 'bgm.wav')

    if not os.path.exists(bgm_path):
        st.session_state.bgm_initialized = False
        st.warning(f"'bgm.wav'를 찾을 수 없습니다.")
        return

    pygame.mixer.init()
    pygame.mixer.music.load(bgm_path)
    initial_volume = st.session_state.get("bgm_volume", 0.5)
    pygame.mixer.music.set_volume(initial_volume)
    pygame.mixer.music.play(loops=-1)
    st.session_state.bgm_initialized = True
    if "bgm_volume" not in st.session_state:
        st.session_state.bgm_volume = initial_volume

def set_bgm_volume(volume):
    # BGM 볼륨 설정
    if st.session_state.get("bgm_initialized", False):
        pygame.mixer.music.set_volume(volume)
        st.session_state.bgm_volume = volume


# 시스템 프롬프트
GAME_MASTER_PROMPT = """
당신은 최고의 방탈출 게임 마스터(GM)입니다. 목표는 사용자가 목소리(텍스트 입력으로 변환됨)만으로 방탈출 게임에 완전히 몰입할 수 있도록, 긴장감 넘치면서도 논리적인 시나리오를 진행하는 것입니다.

- 게임 시작 시, 본 세션에서 수행할 주요 단계의 체크리스트(3~7개)를 간략히 머릿속으로 완성합니다. 체크리스트는 개념적 수준으로 작성하며, 실질적 실행 단계가 아닌 개요를 제공합니다.
- 각 주요 단계나 논리적 구간이 끝나면, 현재 상태를 검토하고 다음 진행 방향을 스스로 판단합니다.

### 게임 마스터(GM)의 역할 및 성격
- 게임의 진행자로서, 모든 상황을 목격하고 중재하는 전지적 관찰자 역할을 맡습니다.
- 목소리 톤은 차분하며 긴장감을 유지합니다.
- 사용자의 행동 중재는 객관적이고 사실적으로 전달합니다.
- "예, 알겠습니다."와 같이 사용자의 몰입을 끊을 수 있는 대답은 하지 않습니다.

### 게임 기본 규칙
1. (게임 시작 시나리오는 외부에서 주어짐) 사용자가 시나리오를 선택하면, 해당 난이도와 시나리오에 맞는 2~4개의 논리/관찰 퍼즐로 구성된 스토리를 즉시 머릿속으로 완성합니다. 이 스토리는 게임이 끝날 때까지 절대 변경되지 않습니다.
2. 모든 퍼즐을 해결하면 사용자는 탈출에 성공하고, 마지막 엔딩 메시지를 출력한 후 게임을 종료합니다.
3. 보기를 제시하지 않으며, 오직 사용자의 말과 상상력에 기반하여 게임을 진행합니다.
4. 난이도에 따라 퍼즐을 구성합니다. 대부분의 사용자는 평범한 대학생 수준의 추론 능력을 가지고 있다고 가정합니다.

### 상태 관리
- 현재 사용자의 위치, 소지한 아이템(인벤토리), 해결한 퍼즐 목록, 남은 힌트 개수 등 모든 게임 상태를 수시로 기억해야 합니다.
- 단, 사용자가 "인벤토리 보여줘", "단서 목록 알려줘" 등 명확히 요청하기 전에는 현재 상태 정보를 먼저 출력하지 않습니다.

### 사용자 명령어 해석 기준
- "주변을 둘러봐", "책상 위를 살펴봐" 등은 **관찰 행동**으로 간주합니다.
- "손잡이를 돌려봐", "서랍을 열어봐" 등은 **상호작용 행동**입니다.
- "열쇠를 자물쇠에 사용해"와 같은 경우는 **아이템 사용 행동**입니다.
- 사용자의 음성을 텍스트로 변환하여 입력받기 때문에, 문맥에 맞게 유사한 발음이나 오타를 유연하게 해석해야 합니다. (예: "책상 밑을 봐줘" -> "책상 밑 관찰")

### 힌트 시스템 규칙
1. 사용자가 "힌트 줘", "도와줘", "모르겠어" 등 명확하게 도움을 요청할 때만 힌트를 제공합니다.
2. 힌트는 총 3개까지 제공할 수 있습니다. (힌트 개수는 외부 시스템에서 카운트됨)
3. 첫 번째 힌트는 가장 추상적이고 방향성만 제시합니다.
4. 두 번째 힌트는 좀 더 구체적인 단서를 제공합니다.
5. 세 번째 힌트는 거의 정답에 가까운 직접적인 방법을 알려줍니다.

### 예외 처리 규칙
- 사용자가 "하늘을 날아서 나갈래", "벽을 부술래" 등 해당 세계관에서 불가능한 행동을 시도할 경우, "그것은 불가능해 보입니다." 또는 "아무리 시도해도 소용없습니다." 등 몰입감을 유지하는 선에서 불가능함을 안내합니다.

### 출력 규칙
- 사용자의 상상력을 최대한 자극하도록 서술형으로 출력합니다.
- "어떤 행동을 하시겠습니까?"와 같은 직접적인 질문보다는 상황 묘사로 자연스럽게 행동을 유도합니다.
- 게임 시작 후 오직 나레이션이 필요한 텍스트만 출력합니다.

--- 
### [중요] 애플리케이션 연동 태그 규칙 (UI 업데이트용)
- AI는 다음 태그를 사용하여 게임 상태 변경을 시스템에 알려야 합니다. 이 태그는 사용자에게 보이지 않습니다.
- 아이템 획득 시: 응답 마지막 줄에 `[ITEM_ADD: "획득한 아이템 이름"]` 형식으로 추가합니다.
- 단서 발견 시: 응답 마지막 줄에 `[CLUE_ADD: "발견한 단서 내용 요약"]` 형식으로 추가합니다.
- 위치 변경 시: 응답 마지막 줄에 `[LOCATION_UPDATE: "새로운 장소 이름"]` 형식으로 추가합니다.
- 퍼즐 하나를 완전히 해결했을 때: 응답 마지막 줄에 `[PUZZLE_SOLVED]` 태그를 추가합니다. (힌트 횟수 초기화용)
- 최종 탈출 성공 시: 응답 마지막 줄에 `[GAME_WIN]` 태그를 추가합니다.
---
"""

# 게임 시나리오 데이터
SCENARIOS = {
    "scenario_1": {
        "title": "사라진 과학자의 연구실",
        "difficulty": 1,
        "description": "당신은 도시 전설로만 듣던 천재 과학자의 숨겨진 연구실에 발을 들였습니다. 문이 잠기고, 시스템이 경고음을 울립니다. 30분 안에 보안 시스템을 해제하고 탈출해야 합니다.",
        "image": "laboratory.png",
        "start_prompt": "당신은 '사라진 과학자의 연구실' 테마로 난이도 [쉬움] 게임을 시작합니다. 사용자가 연구실에 방금 들어와 문이 잠긴 상황을 가정하고, 첫 번째 상황을 긴장감 있게 묘사해주세요."
    },
    "scenario_2": {
        "title": "저주받은 고성의 도서관",
        "difficulty": 2,
        "description": "비바람을 피해 들어온 고성. 낡은 도서관의 문이 거대한 소리와 함께 닫혔습니다. 책장 사이로 누군가의 속삭임이 들려오는 듯합니다. 성의 비밀을 풀고 저주에서 벗어나세요.",
        "image": "library.png",
        "start_prompt": "당신은 '저주받은 고성의 도서관' 테마로 난이도 [중간] 게임을 시작합니다. 사용자가 낡은 도서관에 갇힌 상황입니다. 오싹하고 신비로운 분위기로 첫 상황을 묘사해주세요."
    },
    "scenario_3": {
        "title": "기억상실자의 아파트",
        "difficulty": 3,
        "description": "눈을 떠보니 낯선 아파트입니다. 당신은 자신이 누구인지, 왜 여기 있는지 기억나지 않습니다. 흩어진 기억의 조각들을 모아 정체성을 되찾고 현관문을 열 방법을 찾아야 합니다.",
        "image": "apt.png",
        "start_prompt": "당신은 '기억상실자의 아파트' 테마로 난이도 [어려움] 게임을 시작합니다. 사용자가 기억을 잃은 채 낯선 공간에서 깨어난 혼란스러운 상황입니다. 심리적 압박감을 주며 첫 상황을 묘사해주세요."
    }
}

# Gemini API 호출

@st.cache_data(show_spinner=False)
def get_ai_response(user_input=None, request_type="action"):
    # AI 응답 생성
    model = genai.GenerativeModel(
        model_name='gemini-2.5-pro',
        system_instruction=GAME_MASTER_PROMPT
        )

    current_state_summary = f"""
    [현재 게임 상태 요약]
    - 위치: {st.session_state.location}
    - 인벤토리: {st.session_state.inventory if st.session_state.inventory else '없음'}
    - 발견한 단서: {st.session_state.clues if st.session_state.clues else '없음'}
    - 남은 힌트 수: {st.session_state.hint_count}
    - 현재 난이도: {st.session_state.difficulty}
    """

    if request_type == "hint":
        prompt_addition = "사용자가 힌트를 요청했습니다. 현재 퍼즐 진행 상황에 맞춰 단계적인 힌트를 제공해주세요."
    else:
        prompt_addition = user_input

    if request_type == "action":
        final_prompt = f"{current_state_summary}\n\n{prompt_addition}"
    else:
        final_prompt = prompt_addition

    chat = model.start_chat(history=st.session_state.chat_history)

    
    response = chat.send_message(final_prompt)
    return response.text

# 게임 상태 관리

def initialize_session_state():
    #세션 상태 변수 초기화
    if "bgm_initialized" not in st.session_state:
        initialize_bgm()
        
    if "game_started" not in st.session_state:
        st.session_state.game_started = False
        st.session_state.game_over = False
        st.session_state.game_won = False
        st.session_state.scenario_info = None
        st.session_state.difficulty = None
        st.session_state.difficulty_level = None
        st.session_state.game_duration = None
        st.session_state.chat_history = []
        st.session_state.inventory = []
        st.session_state.clues = []
        st.session_state.location = "시작 지점"
        st.session_state.hint_count = 3
        st.session_state.post_hint_attempts = 0
        st.session_state.start_time = None
        st.session_state.background_image = None

def initialize_game(scenario_key):
    # 시나리오 선택 시 AI의 첫 메시지 생성
    scenario = SCENARIOS[scenario_key]
    
    st.session_state.background_image = scenario.get("image")
    st.session_state.scenario_info = scenario
    st.session_state.difficulty_level = scenario['difficulty']
    st.session_state.game_duration = DIFFICULTY_TIMERS.get(st.session_state.difficulty_level, 3600)
    st.session_state.difficulty = f"난이도 {st.session_state.difficulty_level}/3"
    st.session_state.game_started = True
    st.session_state.game_over = False
    st.session_state.game_won = False
    st.session_state.inventory = []
    st.session_state.clues = []
    st.session_state.location = "시작 지점"
    st.session_state.hint_count = 3
    st.session_state.post_hint_attempts = 0
    st.session_state.chat_history = []
    st.session_state.start_time = datetime.now()

    initial_prompt = scenario["start_prompt"]
    initial_message = get_ai_response(user_input=initial_prompt, request_type="start")

    st.session_state.chat_history.append({"role": "model", "parts": [initial_message]})
    parse_ai_response(initial_message)

def parse_ai_response(response_text):
    # AI 응답에서 특수 태그를 파싱하여 세션 상태 업데이트
    if response_text is None:
        return

    tags = re.findall(r'\[[^]]*\]', response_text)

    for tag in tags:
        tag_content = tag.strip('[]')
        
        # 태그에 내용이 없는 경우 (예: [PUZZLE_SOLVED])
        if ':' not in tag_content:
            if tag_content == "PUZZLE_SOLVED":
                if st.session_state.hint_count < 3 or st.session_state.post_hint_attempts > 0:
                    st.toast("퍼즐 해결! 힌트 카운트가 초기화됩니다.", icon="🎉")
                    st.session_state.hint_count = 3
                    st.session_state.post_hint_attempts = 0
            elif tag_content == "GAME_WIN":
                st.session_state.game_won = True
                st.session_state.game_over = True
        # 태그에 내용이 있는 경우 (예: [ITEM_ADD: "열쇠"])
        else:
            parts = tag_content.split(':', 1)
            tag_name = parts[0].strip()
            content_part = parts[1].strip()
            
            content_match = re.search(r'"(.*)"', content_part)
            if content_match:
                content = content_match.group(1)
            else:
                content = content_part

            if tag_name == "ITEM_ADD":
                if content and content not in st.session_state.inventory:
                    st.session_state.inventory.append(content)
                    st.toast(f"아이템 획득: {content}", icon="🎒")
            elif tag_name == "CLUE_ADD":
                if content and content not in st.session_state.clues:
                    st.session_state.clues.append(content)
                    st.toast("단서 발견!", icon="🔎")
            elif tag_name == "LOCATION_UPDATE":
                if content and st.session_state.location != content:
                    st.session_state.location = content
                    st.toast(f"위치 변경: {content}", icon="📍")

def clean_response_for_display(response_text):
    # 사용자에게 보여주기 전 모든 [TAG]형태 제거
    if response_text is None:
        return ""
    cleaned_text = re.sub(r'\[[^]]*\]', '', response_text)
    return cleaned_text.strip()

def check_game_over_condition():
    # 힌트 소진 후 게임 오버 조건 확인
    if st.session_state.hint_count <= 0:
        st.session_state.post_hint_attempts += 1
        if st.session_state.post_hint_attempts > 3:
            st.session_state.game_over = True
            st.session_state.game_won = False

# UI 렌더링

def render_scenario_selection():
    # 게임 시작 전 시나리오 선택 화면
    st.title("AI 방탈출 게임")
    st.markdown("당신의 상상력만이 탈출의 열쇠입니다. 플레이할 시나리오를 선택해주세요.")
    st.markdown("---")

    scenario_keys = list(SCENARIOS.keys())
    cols = st.columns(len(scenario_keys))

    for i, col in enumerate(cols):
        scenario = SCENARIOS[scenario_keys[i]]
        with col:
            st.subheader(scenario["title"])
            st.caption(f"난이도: {'★' * scenario['difficulty']}{'☆' * (3 - scenario['difficulty'])}")
            st.write(scenario["description"])
            if st.button(f"'{scenario['title']}' 시작하기", key=scenario_keys[i], use_container_width=True):
                initialize_game(scenario_keys[i])
                st.rerun()

def render_game_status_sidebar():
    # 사이드바에 힌트 시스템 및 게임 상태 표시
    st.sidebar.title("게임 현황판")
    st.sidebar.divider()

    if st.session_state.start_time and st.session_state.game_duration:
        elapsed_seconds = (datetime.now() - st.session_state.start_time).total_seconds()
        remaining_seconds = max(0, st.session_state.game_duration - elapsed_seconds)
        mins, secs = divmod(remaining_seconds, 60)
        timer_display = f"{int(mins):02}:{int(secs):02}"
        
        st.sidebar.subheader("⏳ 남은 시간")
        st.sidebar.metric(label="Time Left", value=timer_display, label_visibility="collapsed")
        st.sidebar.divider()

    if st.session_state.get("bgm_initialized", False):
        st.sidebar.subheader("🔊 BGM 볼륨")
        new_volume = st.sidebar.slider(
            "볼륨", 0.0, 1.0, st.session_state.get("bgm_volume", 0.5),
            label_visibility="collapsed"
        )
        if new_volume != st.session_state.get("bgm_volume"):
            set_bgm_volume(new_volume)
        st.sidebar.divider()

    st.sidebar.subheader("💡 힌트 시스템")
    hint_disabled = st.session_state.hint_count <= 0
    if st.sidebar.button("힌트 사용하기", disabled=hint_disabled, use_container_width=True):
        st.session_state.hint_count -= 1
        hint_response = get_ai_response(request_type="hint")
        cleaned_hint = clean_response_for_display(hint_response)
        st.session_state.chat_history.append({"role": "model", "parts": [f"[힌트]: {cleaned_hint}"]})
        st.rerun()

    st.sidebar.metric(label="남은 힌트 수 (퍼즐 해결 시 초기화)", value=f"{st.session_state.hint_count} / 3")
    if st.session_state.hint_count <= 0:
        remaining_attempts = 3 - st.session_state.post_hint_attempts
        st.sidebar.warning(f"힌트를 모두 사용했습니다. 남은 행동 횟수: {remaining_attempts}번")

    st.sidebar.divider()

    st.sidebar.subheader("🎒 인벤토리")
    if st.session_state.inventory:
        for item in st.session_state.inventory:
            st.sidebar.markdown(f"- {item}")
    else:
        st.sidebar.caption("비어 있음")

    st.sidebar.subheader("🔎 발견한 단서")
    if st.session_state.clues:
        for clue in st.session_state.clues:
            st.sidebar.markdown(f"- {clue}")
    else:
        st.sidebar.caption("발견한 단서 없음")

    st.sidebar.subheader("📍 현재 위치")
    st.sidebar.markdown(st.session_state.location)

def render_main_game_ui():
    """메인 게임 플레이 화면 구성"""
    st.title(st.session_state.scenario_info["title"])
    render_game_status_sidebar()

    chat_container = st.container(height=500)
    with chat_container:
        for message in st.session_state.chat_history:
            role = "assistant" if message["role"] == "model" else message["role"]
            with st.chat_message(role):
                st.markdown(clean_response_for_display(message["parts"][0]))

    user_input = st.chat_input("무엇을 하시겠습니까?")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "parts": [user_input]})
        check_game_over_condition()

        if not st.session_state.game_over:
            ai_response = get_ai_response(user_input)
            parse_ai_response(ai_response)
            st.session_state.chat_history.append({"role": "model", "parts": [ai_response]})

        st.rerun()

# 메인
def main():
    initialize_session_state()

    if st.session_state.game_started and not st.session_state.game_over:
        if st.session_state.start_time and st.session_state.game_duration:
            if (datetime.now() - st.session_state.start_time).total_seconds() >= st.session_state.game_duration:
                st.session_state.game_over = True
                st.session_state.game_won = False
                st.rerun()

    if st.session_state.game_over:
        if st.session_state.game_won:
            st.balloons()
            st.success("탈출 성공!")
            st.subheader("축하합니다! 무사히 탈출에 성공했습니다.")
            if st.session_state.chat_history:
                final_message = clean_response_for_display(st.session_state.chat_history[-1]["parts"][0])
                st.markdown(final_message)
        else:
            st.error("게임 오버")
            st.subheader("안타깝게도 탈출하지 못했습니다.")
            
            time_over = False
            if st.session_state.start_time and st.session_state.game_duration:
                if (datetime.now() - st.session_state.start_time).total_seconds() >= st.session_state.game_duration:
                    time_over = True
            
            if time_over:
                st.warning("제한 시간이 초과되었습니다.")
            elif st.session_state.post_hint_attempts > 3:
                st.warning(f"힌트를 모두 소진하고 {st.session_state.post_hint_attempts - 1}번의 행동 동안 퍼즐을 해결하지 못했습니다.")

        if st.button("새 게임 시작하기", use_container_width=True):
            keys_to_reset = list(st.session_state.keys())
            for key in keys_to_reset:
                del st.session_state[key]
            st.rerun()

    elif st.session_state.game_started:
        render_main_game_ui()
    else:
        render_scenario_selection()


main()
