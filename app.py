import streamlit as st
from google.cloud import texttospeech
import fitz
import re
import os
import json

# --- 1. 구글 인증 설정 (클라우드/로컬 겸용 & 키 자동 교정 기능 추가) ---
if "google_creds" in st.secrets:
    creds_dict = dict(st.secrets["google_creds"])
    # [핵심 수정] private_key에 섞인 줄바꿈 기호와 공백을 강제로 청소합니다.
    if "private_key" in creds_dict:
        raw_key = creds_dict["private_key"]
        # 실제 줄바꿈 문자로 변환하고 앞뒤 공백 제거
        cleaned_key = raw_key.replace("\\n", "\n").strip()
        creds_dict["private_key"] = cleaned_key

    with open("temp_key.json", "w") as f:
        json.dump(creds_dict, f)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    KEY_PATH = os.path.join(current_dir, "google_key.json")
    if os.path.exists(KEY_PATH):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH

# --- 2. 음원 전용 필터링 및 TTS 엔진 ---
def clean_for_audio(text, is_chapter=False):
    text = re.sub(r'\([a-zA-Z\s,./-]+\)', '', text)
    text = re.sub(r'\([^)]*\d{4}[^)]*\)', '', text)
    text = re.sub(r'\[\d+[\d\s,]*\]', '', text)
    text = text.replace("서론", "서론 <break time='1.5s'/>")
    if is_chapter:
        text = re.sub(r'^([^.!?\n]+)', r'\1 <break time="1.5s"/>', text)
    return text

def google_premium_tts(raw_text, filename, is_chapter=False):
    if not raw_text.strip(): return None
    try:
        client = texttospeech.TextToSpeechClient()
        audio_text = clean_for_audio(raw_text, is_chapter)
        max_chunk = 1000 
        text_chunks = [audio_text[i:i+max_chunk] for i in range(0, len(audio_text), max_chunk)]
        combined_audio = b""
        for chunk in text_chunks:
            ssml_text = f"<speak><prosody rate='1.1' pitch='0.0st'>{chunk}</prosody></speak>"
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(ssml=ssml_text),
                voice=texttospeech.VoiceSelectionParams(
                    language_code="ko-KR", name="ko-KR-Neural2-B",
                    ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
                ),
                audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=1.1)
            )
            combined_audio += response.audio_content
        return combined_audio
    except Exception as e:
        st.error(f"⚠️ TTS 오류: {str(e)}")
        return None

# --- 3. 텍스트 추출 로직 ---
def narrative_word_healer(text):
    text = re.sub(r'([가-힣])\s?\n\s?([가-힣])', r'\1\2', text)
    text = re.sub(r'([은는이가을를의에로와과,.\)\]!\?])\s?\n', r'\1 ', text)
    return re.sub(r'\s+', ' ', text).strip()

def extract_thesis(doc):
    full_text_raw = "".join([page.get_text("text") for page in doc])
    first_page_lines = doc[0].get_text("text").split('\n')
    title_parts = [l.strip() for l in first_page_lines if l.strip() and not any(k in l for k in ['ISSN', 'DOI'])][:2]
    title = re.sub(r'\s*\d+$', '', " ".join(title_parts)).strip()

    full_text = narrative_word_healer(full_text_raw)
    main_body = full_text.split("참고문헌")[0].split("References")[0]
    abs_match = re.search(r'(국\s*문\s*요\s*약|요\s*약)(.*?)(Abstract|주\s*제\s*어|Ⅰ\.)', main_body, re.S)
    summary = narrative_word_healer(abs_match.group(2)) if abs_match else "요약을 찾을 수 없습니다."
    
    chapters = []
    ch_splits = re.split(r'(제\s*[1-5]\s*장|Ⅰ\.|Ⅱ\.|Ⅲ\.|Ⅳ\.|Ⅴ\.)', main_body)
    for i in range(1, len(ch_splits), 2):
        name, content = ch_splits[i].strip(), ch_splits[i+1].strip()
        if len(content) > 50: chapters.append({"name": name, "content": f"{name}. {content}"})
    return title, summary, chapters

# --- 4. 메인 UI ---
st.set_page_config(page_title="논문 나레이터 Cloud", layout="wide")
st.title("🎙️ 논문 나레이터 (Cloud 버전)")

uploaded_file = st.file_uploader("논문 PDF 업로드", type=["pdf"])

if uploaded_file:
    if 'thesis_data' not in st.session_state:
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        t, s, c = extract_thesis(doc)
        st.session_state.thesis_data = {'title': t, 'summary': s, 'chapters': c}

    data = st.session_state.thesis_data
    f_title = st.text_input("📄 제목", data['title'])
    
    if st.button("🔊 주제 + 요약 음원 생성"):
        audio = google_premium_tts(f"{f_title}. {data['summary']}", "summary.mp3", is_chapter=True)
        if audio:
            st.audio(audio)
            st.download_button("📥 다운로드 (summary.mp3)", audio, "summary.mp3", "audio/mp3")

    st.divider()
    for idx, ch in enumerate(data['chapters']):
        with st.expander(f"🔹 {ch['name']}"):
            st.write(ch['content'])
            if st.button(f"🔊 {ch['name']} 낭독", key=f"btn_{idx}"):
                audio = google_premium_tts(ch['content'], f"chapter_{idx+1}.mp3", is_chapter=True)
                if audio:
                    st.audio(audio)
                    st.download_button(f"📥 다운로드 (chapter_{idx+1}.mp3)", audio, f"chapter_{idx+1}.mp3", "audio/mp3")
