import streamlit as st
from google.cloud import texttospeech
from google.oauth2 import service_account  # 파일 없이 인증하기 위한 라이브러리
import fitz
import re
import json

# --- 1. 구글 인증 설정 (파일 생성 방식 탈피) ---
def get_google_credentials():
    if "google_creds" in st.secrets:
        try:
            creds_info = dict(st.secrets["google_creds"])
            # private_key 내의 줄바꿈 기호만 표준화
            if "private_key" in creds_info:
                creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
            
            # [핵심] 파일을 만들지 않고 딕셔너리에서 바로 인증 객체를 생성합니다.
            return service_account.Credentials.from_service_account_info(creds_info)
        except Exception as e:
            st.error(f"❌ 인증 설정 중 오류 발생: {e}")
            return None
    return None

# --- 2. TTS 엔진 ---
def google_premium_tts(raw_text):
    if not raw_text.strip(): return None
    creds = get_google_credentials()
    if not creds:
        st.error("🔑 구글 인증 정보(Secrets)를 확인해주세요.")
        return None

    try:
        client = texttospeech.TextToSpeechClient(credentials=creds)
        # 1.1배속 여성 음성 설정
        ssml_text = f"<speak><prosody rate='1.1'>{raw_text}</prosody></speak>"
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(ssml=ssml_text),
            voice=texttospeech.VoiceSelectionParams(language_code="ko-KR", name="ko-KR-Neural2-B"),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        )
        return response.audio_content
    except Exception as e:
        st.error(f"⚠️ TTS 오류 발생: {str(e)}")
        return None

# --- 3. 논문 분석 로직 ---
def extract_thesis(doc):
    full_text = "".join([page.get_text("text") for page in doc])
    first_page = doc[0].get_text("text").split('\n')
    title = [l.strip() for l in first_page if l.strip() and 'ISSN' not in l][:1][0]
    
    main_body = full_text.split("참고문헌")[0].split("References")[0]
    abs_match = re.search(r'(요\s*약|국문요약)(.*?)(Abstract|Ⅰ\.|1\.)', main_body, re.S)
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
st.title("🎙️ 논문 나레이터 (최종 수정본)")

uploaded_file = st.file_uploader("논문 PDF 업로드", type=["pdf"])

if uploaded_file:
    if 'thesis_data' not in st.session_state:
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        t, s, c = extract_thesis(doc)
        st.session_state.thesis_data = {'title': t, 'summary': s, 'chapters': c}

    data = st.session_state.thesis_data
    st.subheader(f"📄 제목: {data['title']}")
    
    # 1. 요약 섹션
    if st.button("🔊 제목 + 요약 듣기"):
        audio = google_premium_tts(f"{data['title']}. {data['summary']}")
        if audio: st.audio(audio)

    st.divider()
    
    # 2. 장별 섹션
    st.subheader("📖 장별 낭독")
    for idx, ch in enumerate(data['chapters']):
        with st.expander(f"🔹 {ch['name']}"):
            st.write(ch['content'][:1500] + "...")
            if st.button(f"🔊 {ch['name']} 낭독 시작", key=f"btn_{idx}"):
                audio = google_premium_tts(ch['content'])
                if audio: st.audio(audio)

    st.divider()

    # 3. 전체 통합 섹션
    if st.button("🎙️ 논문 전체 통합 음원 생성", use_container_width=True):
        full_script = f"{data['title']}. {data['summary']}. " + " ".join([ch['content'] for ch in data['chapters']])
        with st.spinner("전체 음성 합성 중... (수 분이 소요될 수 있습니다)"):
            audio = google_premium_tts(full_script)
            if audio:
                st.audio(audio)
                st.download_button("📥 전체 MP3 다운로드", audio, "full_thesis.mp3", use_container_width=True)
