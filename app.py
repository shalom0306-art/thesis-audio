import streamlit as st
from google.cloud import texttospeech
import fitz
import re
import os
import json

# --- 1. 구글 인증 설정 (유령 문자 'a' 및 모든 불순물 강제 제거 버전) ---
if "google_creds" in st.secrets:
    creds_dict = dict(st.secrets["google_creds"])
    if "private_key" in creds_dict:
        pk = creds_dict["private_key"]
        header = "-----BEGIN PRIVATE KEY-----"
        footer = "-----END PRIVATE KEY-----"
        
        if header in pk and footer in pk:
            # [강력 세척] footer 뒤에 붙은 'a'나 모든 유령 문자를 강제로 잘라냅니다.
            body = pk.split(header)[1].split(footer)[0]
            clean_body = "".join(body.replace("\\n", "").split())
            
            # Base64 규격(4의 배수) 강제 조정
            valid_len = (len(clean_body) // 4) * 4
            clean_body = clean_body[:valid_len]
            
            # 다시 합치기 (footer 뒤에는 아무것도 남기지 않음)
            creds_dict["private_key"] = f"{header}\n{clean_body}\n{footer}\n"

    with open("temp_key.json", "w") as f:
        json.dump(creds_dict, f)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"

# --- 2. TTS 및 텍스트 정제 (여성 음성 Neural2-B 적용) ---
def google_premium_tts(raw_text):
    if not raw_text.strip(): return None
    try:
        client = texttospeech.TextToSpeechClient()
        # 불필요한 기호(괄호 안의 한자, 인용구) 제거
        clean_text = re.sub(r'\([가-힣a-zA-Z\s,·]+\)', '', raw_text)
        ssml_text = f"<speak><prosody rate='1.1'>{clean_text}</prosody></speak>"
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(ssml=ssml_text),
            voice=texttospeech.VoiceSelectionParams(language_code="ko-KR", name="ko-KR-Neural2-B"),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        )
        return response.audio_content
    except Exception as e:
        st.error(f"⚠️ TTS 오류: {str(e)}")
        return None

# --- 3. 논문 구조 분석 (장별 낭독 기능 복구) ---
def extract_thesis(doc):
    full_text = "".join([page.get_text("text") for page in doc])
    first_page = doc[0].get_text("text").split('\n')
    title = [l.strip() for l in first_page if l.strip() and 'ISSN' not in l][:1][0]
    
    # 본문 추출 (참고문헌 앞까지만)
    main_body = full_text.split("참고문헌")[0].split("References")[0]
    
    # 요약 추출
    abs_match = re.search(r'(요\s*약|국문요약)(.*?)(Abstract|Ⅰ\.|1\.)', main_body, re.S)
    summary = abs_match.group(2).strip() if abs_match else main_body[:800]
    
    # 장별 추출 (Ⅰ., 1., 제 1장 등 다양한 형식 대응)
    chapters = []
    # Ⅰ. 또는 1. 또는 제1장 형태를 모두 찾아냅니다.
    ch_splits = re.split(r'([ⅠⅡⅢⅣⅤ]\.|\d+\.\s+[가-힣]|제\s*\d+\s*장)', main_body)
    for i in range(1, len(ch_splits), 2):
        name, content = ch_splits[i], ch_splits[i+1].strip()
        if len(content) > 100:
            chapters.append({"name": name, "content": content})
    
    return title, summary, chapters

# --- 4. UI 구성 (Full Version) ---
st.set_page_config(page_title="논문 나레이터 (완성본)", layout="wide")
st.title("🎙️ 논문 나레이터 (장별 낭독 복구 완료)")

uploaded_file = st.file_uploader("논문 PDF 업로드", type=["pdf"])

if uploaded_file:
    if 'thesis_data' not in st.session_state:
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        t, s, c = extract_thesis(doc)
        st.session_state.thesis_data = {'title': t, 'summary': s, 'chapters': c}

    data = st.session_state.thesis_data
    st.subheader(f"📄 제목: {data['title']}")
    
    if st.button("🔊 요약 전체 듣기"):
        with st.spinner("요약 음성 생성 중..."):
            audio = google_premium_tts(data['summary'])
            if audio: st.audio(audio)

    st.divider()
    # 장별 낭독 버튼 (이미지 5fa050.png 형태 복구)
    st.info("💡 각 장의 제목을 클릭하면 상세 내용을 확인하고 낭독할 수 있습니다.")
    for idx, ch in enumerate(data['chapters']):
        with st.expander(f"🔹 {ch['name']} 내용 보기"):
            st.write(ch['content'][:1500] + "...")
            if st.button(f"🔊 {ch['name']} 낭독 시작", key=f"btn_{idx}"):
                with st.spinner(f"{ch['name']} 음성 생성 중..."):
                    audio = google_premium_tts(ch['content'])
                    if audio: st.audio(audio)
