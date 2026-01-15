import streamlit as st
from google.cloud import texttospeech
from google.oauth2 import service_account
import fitz
import re
import os
import json

# --- 1. 구글 인증 설정 (유령 문자 'a'를 물리적으로 도려내는 버전) ---
def get_creds():
    if "google_creds" in st.secrets:
        info = dict(st.secrets["google_creds"])
        if "private_key" in info:
            pk = str(info["private_key"])
            header = "-----BEGIN PRIVATE KEY-----"
            footer = "-----END PRIVATE KEY-----"
            
            # [진단 해결] footer 뒤에 'a'가 있든 뭐가 있든 무시하고 footer까지만 칼같이 자릅니다.
            if header in pk and footer in pk:
                start_point = pk.find(header)
                end_point = pk.find(footer) + len(footer)
                # 추출된 키에서 불필요한 이스케이프 문자(\n)만 실제 줄바꿈으로 변경
                fixed_key = pk[start_point:end_point].replace("\\n", "\n")
                info["private_key"] = fixed_key
        
        try:
            return service_account.Credentials.from_service_account_info(info)
        except Exception as e:
            st.error(f"❌ 인증 최종 단계 오류: {e}")
            return None
    return None

# --- 2. TTS 및 텍스트 추출 로직 (장별 기능 복구) ---
def google_premium_tts(text):
    if not text or not text.strip(): return None
    creds = get_creds()
    try:
        client = texttospeech.TextToSpeechClient(credentials=creds)
        # 1.1배속 설정
        ssml = f"<speak><prosody rate='1.1'>{text}</prosody></speak>"
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(ssml=ssml),
            voice=texttospeech.VoiceSelectionParams(language_code="ko-KR", name="ko-KR-Neural2-B"),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        )
        return response.audio_content
    except Exception as e:
        st.error(f"⚠️ TTS 오류: {str(e)}")
        return None

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

# --- 3. UI 구성 (Full Version) ---
st.set_page_config(page_title="논문 나레이터 (교정 완료)", layout="wide")
st.title("🎙️ 논문 나레이터 (에러 해결 완료)")

uploaded_file = st.file_uploader("논문 PDF 업로드", type=["pdf"])
if uploaded_file:
    if 'thesis_data' not in st.session_state:
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        t, s, c = extract_thesis(doc)
        st.session_state.thesis_data = {'title': t, 'summary': s, 'chapters': c}
    
    data = st.session_state.thesis_data
    st.subheader(f"📄 제목: {data['title']}")
    if st.button("🔊 요약 듣기"):
        audio = google_premium_tts(data['summary'])
        if audio: st.audio(audio)
    
    st.divider()
    st.subheader("📖 장별 낭독")
    for idx, ch in enumerate(data['chapters']):
        with st.expander(f"🔹 {ch['name']} 내용 확인"):
            st.write(ch['content'][:1500] + "...")
            if st.button(f"🔊 {ch['name']} 낭독", key=f"btn_{idx}"):
                audio = google_premium_tts(ch['content'])
                if audio: st.audio(audio)

    st.divider()
    if st.button("🎙️ 논문 전체 통합 음원 생성", use_container_width=True):
        full_script = f"{data['title']}. {data['summary']}. " + " ".join([ch['content'] for ch in data['chapters']])
        with st.spinner("전체 음원 합성 중..."):
            audio = google_premium_tts(full_script)
            if audio:
                st.audio(audio)
                st.download_button("📥 전체 MP3 다운로드", audio, "full_thesis.mp3", use_container_width=True)
