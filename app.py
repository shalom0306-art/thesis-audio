import streamlit as st
from google.cloud import texttospeech
import fitz
import re
import os
import json

# --- 1. 구글 인증 설정 (글자 수 자동 교정 강화 버전) ---
if "google_creds" in st.secrets:
    creds_dict = dict(st.secrets["google_creds"])
    if "private_key" in creds_dict:
        # [핵심] 65자 에러를 잡기 위해 모든 공백과 잘못된 기호를 강제로 제거합니다.
        raw_key = creds_dict["private_key"]
        # 1. 역슬래시 n(\n) 문자를 실제 줄바꿈으로 변경
        cleaned_key = raw_key.replace("\\n", "\n")
        # 2. 앞뒤의 모든 공백, 탭, 줄바꿈 제거 (이게 65자 에러의 주범입니다)
        cleaned_key = cleaned_key.strip()
        # 3. 마지막에 줄바꿈 하나만 깔끔하게 추가
        if not cleaned_key.endswith("\n"): cleaned_key += "\n"
        creds_dict["private_key"] = cleaned_key

    with open("temp_key.json", "w") as f:
        json.dump(creds_dict, f)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"

# --- 2. TTS 및 텍스트 추출 함수 (기능 복구) ---
def clean_for_audio(text, is_chapter=False):
    text = re.sub(r'\([a-zA-Z\s,./-]+\)', '', text)
    text = re.sub(r'\([^)]*\d{4}[^)]*\)', '', text)
    text = re.sub(r'\[\d+[\d\s,]*\]', '', text)
    if is_chapter:
        text = re.sub(r'^([^.!?\n]+)', r'\1 <break time="1.5s"/>', text)
    return text

def google_premium_tts(raw_text):
    if not raw_text.strip(): return None
    try:
        client = texttospeech.TextToSpeechClient()
        audio_text = clean_for_audio(raw_text, True)
        ssml_text = f"<speak><prosody rate='1.1' pitch='0.0st'>{audio_text}</prosody></speak>"
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(ssml=ssml_text),
            voice=texttospeech.VoiceSelectionParams(
                language_code="ko-KR", name="ko-KR-Neural2-B",
                ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
            ),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=1.1)
        )
        return response.audio_content
    except Exception as e:
        st.error(f"⚠️ TTS 오류: {str(e)}")
        return None

def extract_thesis(doc):
    full_text = "".join([page.get_text("text") for page in doc])
    first_page = doc[0].get_text("text").split('\n')
    title = [l.strip() for l in first_page if l.strip() and 'ISSN' not in l][:1][0]
    main_body = full_text.split("참고문헌")[0].split("References")[0]
    
    # 요약 추출
    abs_match = re.search(r'(요\s*약|국문요약)(.*?)(Abstract|Ⅰ\.)', main_body, re.S)
    summary = abs_match.group(2).strip() if abs_match else "요약을 찾을 수 없습니다."
    
    # 장별 추출 (I, II, III...)
    chapters = []
    ch_splits = re.split(r'(Ⅰ\.|Ⅱ\.|Ⅲ\.|Ⅳ\.|Ⅴ\.)', main_body)
    for i in range(1, len(ch_splits), 2):
        name, content = ch_splits[i], ch_splits[i+1].strip()
        if len(content) > 50: chapters.append({"name": name, "content": content})
    return title, summary, chapters

# --- 3. UI ---
st.set_page_config(page_title="논문 나레이터 (Final)", layout="wide")
st.title("🎙️ 논문 나레이터 (Cloud 버전)")

uploaded_file = st.file_uploader("논문 PDF 업로드", type=["pdf"])

if uploaded_file:
    if 'thesis_data' not in st.session_state:
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        t, s, c = extract_thesis(doc)
        st.session_state.thesis_data = {'title': t, 'summary': s, 'chapters': c}

    data = st.session_state.thesis_data
    st.subheader(f"📄 제목: {data['title']}")
    
    with st.expander("📝 요약 내용 확인"):
        st.write(data['summary'])
    
    if st.button("🔊 요약 듣기"):
        with st.spinner("음성 생성 중..."):
            audio = google_premium_tts(data['summary'])
            if audio: st.audio(audio)

    st.divider()
    for idx, ch in enumerate(data['chapters']):
        with st.expander(f"🔹 {ch['name']}"):
            st.write(ch['content'][:1000] + "...")
            if st.button(f"🔊 {ch['name']} 낭독", key=f"btn_{idx}"):
                with st.spinner(f"{ch['name']} 생성 중..."):
                    audio = google_premium_tts(ch['content'])
                    if audio: st.audio(audio)
