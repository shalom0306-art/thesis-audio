import streamlit as st
from google.cloud import texttospeech
import fitz
import re
import os
import json

# --- 1. 구글 인증 설정 (유령 문자 강제 소거 버전) ---
if "google_creds" in st.secrets:
    creds_dict = dict(st.secrets["google_creds"])
    if "private_key" in creds_dict:
        pk = creds_dict["private_key"]
        
        # [강력 세척 로직]
        # 1. 헤더와 푸터 분리
        header = "-----BEGIN PRIVATE KEY-----"
        footer = "-----END PRIVATE KEY-----"
        
        # 2. 본문만 추출해서 모든 공백, 줄바꿈, 특수기호(\n 등)를 완전히 제거
        body = pk.replace(header, "").replace(footer, "")
        body = body.replace("\\n", "").replace("\n", "").replace(" ", "").strip()
        
        # 3. 깨끗해진 본문을 다시 합쳐서 완벽한 키 생성
        cleaned_key = f"{header}\n{body}\n{footer}\n"
        creds_dict["private_key"] = cleaned_key

    with open("temp_key.json", "w") as f:
        json.dump(creds_dict, f)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"

# --- 2. TTS 및 기능 로직 (기존과 동일) ---
def google_premium_tts(raw_text):
    if not raw_text.strip(): return None
    try:
        client = texttospeech.TextToSpeechClient()
        ssml_text = f"<speak><prosody rate='1.1'>{raw_text}</prosody></speak>"
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
    summary = full_text.split("요약")[1].split("Abstract")[0] if "요약" in full_text else full_text[:1000]
    return title, summary

# --- 3. UI ---
st.set_page_config(page_title="논문 나레이터 (교정완료)")
st.title("🎙️ 논문 나레이터 (에러 해결 버전)")

uploaded_file = st.file_uploader("논문 PDF 업로드", type=["pdf"])
if uploaded_file:
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    t, s = extract_thesis(doc)
    st.write(f"📄 제목: {t}")
    if st.button("🔊 요약 듣기"):
        audio = google_premium_tts(s)
        if audio: st.audio(audio)
