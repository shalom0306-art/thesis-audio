import streamlit as st
from google.cloud import texttospeech
from google.oauth2 import service_account
import fitz
import re
import json

# --- 1. 구글 인증 설정 (모든 형식 에러 원천 차단 버전) ---
def get_creds():
    # Secrets에 [google_creds] 섹션이 있는지 확인
    if "google_creds" in st.secrets:
        info = dict(st.secrets["google_creds"])
        
        # [핵심 로직] private_key 내부의 불순물을 '나노 단위'가 아니라 '원자 단위'로 제거합니다.
        if "private_key" in info:
            pk = str(info["private_key"])
            # 1. 헤더와 푸터 사이의 진짜 데이터만 추출
            header = "-----BEGIN PRIVATE KEY-----"
            footer = "-----END PRIVATE KEY-----"
            
            if header in pk and footer in pk:
                body = pk.split(header)[1].split(footer)[0]
                # 2. Base64에 쓰이는 문자(A-Z, a-z, 0-9, +, /, =)만 남기고 싹 지움 (\n, 공백, 'a' 등 모두 제거)
                clean_body = "".join(re.findall(r'[A-Za-z0-9+/=]', body))
                # 3. 4의 배수가 아니면 남는 찌꺼기 강제 삭제 (1625자 에러 등 방지)
                clean_body = clean_body[:(len(clean_body) // 4) * 4]
                # 4. 구글이 원하는 완벽한 형식으로 재조립
                info["private_key"] = f"{header}\n{clean_body}\n{footer}\n"
        
        try:
            return service_account.Credentials.from_service_account_info(info)
        except Exception as e:
            st.error(f"❌ 인증 최종 단계 오류: {e}")
    return None

# --- 2. TTS 엔진 ---
def google_premium_tts(text):
    if not text or not text.strip(): return None
    creds = get_creds()
    if not creds: return None
    try:
        client = texttospeech.TextToSpeechClient(credentials=creds)
        # 1.1배속 여성 음성 적용
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

# --- 3. 논문 구조 분석 (장별 버튼 기능 완벽 복구) ---
def extract_thesis(doc):
    full_text = "".join([p.get_text("text") for p in doc])
    # 제목 추출 (첫 페이지 첫 줄)
    title = doc[0].get_text("text").split('\n')[0].strip()
    # 본문 추출 (참고문헌 제외)
    main_body = full_text.split("참고문헌")[0].split("References")[0]
    # 요약 추출
    abs_match = re.search(r'(요\s*약|국문요약)(.*?)(Abstract|Ⅰ\.)', main_body, re.S)
    summary = abs_match.group(2).strip() if abs_match else main_body[:800]
    
    # 장별 추출 (Ⅰ., Ⅱ., Ⅲ. 등 기호 기준)
    chapters = []
    ch_splits = re.split(r'(Ⅰ\.|Ⅱ\.|Ⅲ\.|Ⅳ\.|Ⅴ\.)', main_body)
    for i in range(1, len(ch_splits), 2):
        name, content = ch_splits[i], ch_splits[i+1].strip()
        if len(content) > 100: chapters.append({"name": name, "content": content})
    return title, summary, chapters

# --- 4. UI ---
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
        with st.expander(f"🔹 {ch['name']}"):
            st.write(ch['content'][:1500] + "...")
            if st.button(f"🔊 {ch['name']} 낭독", key=f"btn_{idx}"):
                audio = google_premium_tts(ch['content'])
                if audio: st.audio(audio)
