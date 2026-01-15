import streamlit as st
from google.cloud import texttospeech
from google.oauth2 import service_account
import fitz
import re
import json

# --- 1. 구글 인증 설정 (통째로 읽기 방식) ---
def get_creds():
    if "GOOGLE_JSON_KEY" in st.secrets:
        try:
            # Secrets에서 'GOOGLE_JSON_KEY'를 가져옵니다.
            raw_json = st.secrets["GOOGLE_JSON_KEY"]
            
            # [진단 해결] 혹시 모를 유령 문자 'a'나 앞뒤 공백을 물리적으로 제거합니다.
            raw_json = raw_json.strip()
            if raw_json.endswith('a'):
                raw_json = raw_json[:-1]
                
            info = json.loads(raw_json)
            return service_account.Credentials.from_service_account_info(info)
        except Exception as e:
            st.error(f"❌ 구글 인증 정보 해석 실패: {e}")
    return None

# --- 2. TTS 엔진 ---
def google_premium_tts(text):
    if not text or not text.strip(): return None
    creds = get_creds()
    if not creds:
        st.error("🔑 Secrets에 GOOGLE_JSON_KEY를 설정해주세요.")
        return None
    try:
        client = texttospeech.TextToSpeechClient(credentials=creds)
        ssml = f"<speak><prosody rate='1.1'>{text}</prosody></speak>"
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(ssml=ssml),
            voice=texttospeech.VoiceSelectionParams(language_code="ko-KR", name="ko-KR-Neural2-B"),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        )
        return response.audio_content
    except Exception as e:
        st.error(f"⚠️ TTS 합성 실패: {str(e)}")
        return None

# --- 3. 논문 분석 로직 (기능 복구) ---
def extract_thesis(doc):
    full_text = "".join([p.get_text("text") for p in doc])
    title = doc[0].get_text("text").split('\n')[0].strip()
    main_body = full_text.split("참고문헌")[0].split("References")[0]
    abs_match = re.search(r'(요\s*약|국문요약)(.*?)(Abstract|Ⅰ\.)', main_body, re.S)
    summary = abs_match.group(2).strip() if abs_match else main_body[:800]
    chapters = []
    ch_splits = re.split(r'(Ⅰ\.|Ⅱ\.|Ⅲ\.|Ⅳ\.|Ⅴ\.)', main_body)
    for i in range(1, len(ch_splits), 2):
        name, content = ch_splits[i], ch_splits[i+1].strip()
        if len(content) > 100:
            chapters.append({"name": name, "content": content})
    return title, summary, chapters

# --- 4. 메인 UI ---
st.set_page_config(page_title="논문 나레이터", layout="wide")
st.title("🎙️ 논문 나레이터 (Smart Clean)")

uploaded_file = st.file_uploader("논문 PDF 업로드", type=["pdf"])
if uploaded_file:
    if 'thesis_data' not in st.session_state:
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        t, s, c = extract_thesis(doc)
        st.session_state.thesis_data = {'title': t, 'summary': s, 'chapters': c}

    data = st.session_state.thesis_data
    st.subheader(f"📄 제목: {data['title']}")
    
    if st.button("🔊 제목 + 요약 듣기"):
        audio = google_premium_tts(f"{data['title']}. {data['summary']}")
        if audio: st.audio(audio)

    st.divider()
    for idx, ch in enumerate(data['chapters']):
        with st.expander(f"🔹 {ch['name']} 낭독"):
            st.write(ch['content'][:1500] + "...")
            if st.button(f"🔊 {ch['name']} 시작", key=f"btn_{idx}"):
                audio = google_premium_tts(ch['content'])
                if audio: st.audio(audio)
