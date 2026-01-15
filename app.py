import streamlit as st
from google.cloud import texttospeech
import fitz
import re
import os
import json

# --- 1. 구글 인증 설정 (1625자 유령 에러 자동 세척 버전) ---
if "google_creds" in st.secrets:
    creds_dict = dict(st.secrets["google_creds"])
    if "private_key" in creds_dict:
        pk = creds_dict["private_key"]
        header = "-----BEGIN PRIVATE KEY-----"
        footer = "-----END PRIVATE KEY-----"
        
        if header in pk and footer in pk:
            # 본문만 추출해서 모든 공백과 줄바꿈 제거
            body = pk.split(header)[1].split(footer)[0]
            clean_body = "".join(body.replace("\\n", "").split())
            
            # [진단 해결] 4의 배수가 아니면(예: 1625자) 남는 글자를 강제로 잘라냄
            valid_len = (len(clean_body) // 4) * 4
            clean_body = clean_body[:valid_len]
            
            creds_dict["private_key"] = f"{header}\n{clean_body}\n{footer}\n"

    with open("temp_key.json", "w") as f:
        json.dump(creds_dict, f)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"

# --- 2. 기능 함수 (장별 추출 기능 복구) ---
def google_premium_tts(raw_text):
    if not raw_text.strip(): return None
    try:
        client = texttospeech.TextToSpeechClient()
        # 속도 1.1배, 여성 음성(B) 설정
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
    # 제목 추출
    first_page = doc[0].get_text("text").split('\n')
    title = [l.strip() for l in first_page if l.strip() and 'ISSN' not in l][:1][0]
    
    # 본문 영역 정의 (참고문헌 제외)
    main_body = full_text.split("참고문헌")[0].split("References")[0]
    
    # 요약 추출
    abs_match = re.search(r'(요\s*약|국문요약)(.*?)(Abstract|Ⅰ\.)', main_body, re.S)
    summary = abs_match.group(2).strip() if abs_match else "요약을 자동으로 찾지 못해 본문 상단 내용을 가져옵니다.\n" + main_body[:500]
    
    # 장별 추출 (Ⅰ., Ⅱ., Ⅲ. 등 기호 기준) - 이미지 5fa050.png 기준 복구
    chapters = []
    ch_splits = re.split(r'(Ⅰ\.|Ⅱ\.|Ⅲ\.|Ⅳ\.|Ⅴ\.)', main_body)
    for i in range(1, len(ch_splits), 2):
        name, content = ch_splits[i], ch_splits[i+1].strip()
        if len(content) > 50:
            chapters.append({"name": name, "content": content})
    return title, summary, chapters

# --- 3. UI 구성 ---
st.set_page_config(page_title="논문 나레이터 (교정완료)", layout="wide")
st.title("🎙️ 논문 나레이터 (Full Version)")

uploaded_file = st.file_uploader("논문 PDF 업로드", type=["pdf"])

if uploaded_file:
    if 'thesis_data' not in st.session_state:
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        t, s, c = extract_thesis(doc)
        st.session_state.thesis_data = {'title': t, 'summary': s, 'chapters': c}

    data = st.session_state.thesis_state = st.session_state.thesis_data
    st.subheader(f"📄 제목: {data['title']}")
    
    if st.button("🔊 요약 듣기"):
        audio = google_premium_tts(data['summary'])
        if audio: st.audio(audio)

    st.divider()
    # 장별 낭독 버튼들 다시 생성
    for idx, ch in enumerate(data['chapters']):
        with st.expander(f"🔹 {ch['name']} 내용 확인"):
            st.write(ch['content'][:1500] + "...")
            if st.button(f"🔊 {ch['name']} 낭독", key=f"btn_{idx}"):
                audio = google_premium_tts(ch['content'])
                if audio: st.audio(audio)
