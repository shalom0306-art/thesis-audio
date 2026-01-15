import streamlit as st
from google.cloud import texttospeech
from google.oauth2 import service_account
import fitz
import re
import json
import os

# --- 1. 구글 인증 설정 (어떤 오타도 스스로 치료하는 버전) ---
def get_creds():
    if "google_creds" in st.secrets:
        info = dict(st.secrets["google_creds"])
        if "private_key" in info:
            pk = info["private_key"]
            header = "-----BEGIN PRIVATE KEY-----"
            footer = "-----END PRIVATE KEY-----"
            
            # [진단 해결] 키 주변에 붙은 'a'나 공백을 무시하고 정답만 추출합니다.
            if header in pk and footer in pk:
                try:
                    start_idx = pk.find(header)
                    end_idx = pk.find(footer) + len(footer)
                    # 정확히 푸터까지만 잘라내고 내부 줄바꿈만 정리
                    clean_pk = pk[start_idx:end_idx].replace("\\n", "\n")
                    info["private_key"] = clean_pk
                except:
                    pass
        return service_account.Credentials.from_service_account_info(info)
    return None

# --- 2. TTS 엔진 ---
def google_premium_tts(text):
    if not text or not text.strip(): return None
    creds = get_creds()
    try:
        client = texttospeech.TextToSpeechClient(credentials=creds)
        chunks = [text[i:i+1500] for i in range(0, len(text), 1500)]
        combined_audio = b""
        for chunk in chunks:
            ssml = f"<speak><prosody rate='1.1'>{chunk}</prosody></speak>"
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(ssml=ssml),
                voice=texttospeech.VoiceSelectionParams(language_code="ko-KR", name="ko-KR-Neural2-B"),
                audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
            )
            combined_audio += response.audio_content
        return combined_audio
    except Exception as e:
        st.error(f"⚠️ 구글 인증 오류 (Secrets를 확인하세요): {str(e)}")
        return None

# --- 3. 논문 분석 로직 (장별 버튼 기능 복구) ---
def extract_thesis(doc):
    full_text = "".join([page.get_text("text") for page in doc])
    first_page = doc[0].get_text("text").split('\n')
    title = [l.strip() for l in first_page if l.strip() and 'ISSN' not in l][:1][0]
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

# --- 4. UI 구성 ---
st.set_page_config(page_title="논문 나레이터 (완성)", layout="wide")
st.title("🎙️ 논문 나레이터 (Smart & Clean)")

uploaded_file = st.file_uploader("논문 PDF 업로드", type=["pdf"])

if uploaded_file:
    if 'thesis_data' not in st.session_state:
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        t, s, c = extract_thesis(doc)
        st.session_state.thesis_data = {'title': t, 'summary': s, 'chapters': c}

    data = st.session_state.thesis_data
    st.subheader(f"📄 제목: {data['title']}")
    
    if st.button("🔊 제목+요약 듣기"):
        audio = google_premium_tts(f"{data['title']}. {data['summary']}")
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
        with st.spinner("전체 합성 중..."):
            audio = google_premium_tts(full_script)
            if audio:
                st.audio(audio)
                st.download_button("📥 전체 MP3 다운로드", audio, "full.mp3", use_container_width=True)
