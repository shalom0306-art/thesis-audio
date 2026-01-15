import streamlit as st
from google.cloud import texttospeech
import fitz
import re
import os
import json

# --- 1. 구글 인증 설정 (에러 자동 교정 버전) ---
if "google_creds" in st.secrets:
    creds_dict = dict(st.secrets["google_creds"])
    # [핵심] 키에 포함된 줄바꿈 문자(\n)와 공백을 강제로 올바르게 교정합니다.
    if "private_key" in creds_dict:
        k = creds_dict["private_key"]
        cleaned_key = k.replace("\\n", "\n").strip()
        if not cleaned_key.endswith("\n"): cleaned_key += "\n"
        creds_dict["private_key"] = cleaned_key

    with open("temp_key.json", "w") as f:
        json.dump(creds_dict, f)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"

# --- 2. TTS 및 텍스트 추출 함수 ---
def clean_for_audio(text, is_chapter=False):
    text = re.sub(r'\([a-zA-Z\s,./-]+\)', '', text)
    text = re.sub(r'\([^)]*\d{4}[^)]*\)', '', text)
    text = re.sub(r'\[\d+[\d\s,]*\]', '', text)
    if is_chapter: text = re.sub(r'^([^.!?\n]+)', r'\1 <break time="1.5s"/>', text)
    return text

def google_premium_tts(raw_text):
    try:
        client = texttospeech.TextToSpeechClient()
        audio_text = clean_for_audio(raw_text, True)
        ssml_text = f"<speak><prosody rate='1.1'>{audio_text}</prosody></speak>"
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(ssml=ssml_text),
            voice=texttospeech.VoiceSelectionParams(language_code="ko-KR", name="ko-KR-Neural2-B"),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        )
        return response.audio_content
    except Exception as e:
        st.error(f"⚠️ TTS 오류: {str(e)}")
        return None

def extract_thesis(doc):
    full_text = "".join([page.get_text("text") for page in doc])
    title = doc[0].get_text("text").split('\n')[0].strip()
    summary = full_text.split("요약")[1].split("Abstract")[0] if "요약" in full_text else "요약 없음"
    chapters = []
    ch_splits = re.split(r'(제\s*[1-5]\s*장|Ⅰ\.|Ⅱ\.)', full_text)
    for i in range(1, len(ch_splits), 2):
        chapters.append({"name": ch_splits[i], "content": ch_splits[i+1][:2000]})
    return title, summary, chapters

# --- 3. UI ---
st.title("🎙️ 논문 나레이터 (Final)")
uploaded_file = st.file_uploader("논문 PDF 업로드", type=["pdf"])

if uploaded_file:
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    t, s, c = extract_thesis(doc)
    st.write(f"📄 제목: {t}")
    if st.button("🔊 요약 듣기"):
        audio = google_premium_tts(s)
        if audio: st.audio(audio)
