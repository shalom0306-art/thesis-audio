import streamlit as st
from google.cloud import texttospeech
from google.oauth2 import service_account
import fitz
import re
import json

# --- 1. 구글 인증 설정 (유령 문자 및 길이 에러 자동 치료) ---
def get_creds():
    if "GOOGLE_JSON_KEY" in st.secrets:
        try:
            info = json.loads(st.secrets["GOOGLE_JSON_KEY"])
            if "private_key" in info:
                pk = info["private_key"]
                # [진단 해결] Base64가 아닌 글자(유령 문자 'a' 등) 싹 제거
                clean_pk = "".join(re.findall(r'[A-Za-z0-9+/=\- \n]', pk))
                # 4의 배수가 아니면 강제로 잘라내어 길이 맞춤
                if "-----END PRIVATE KEY-----" in clean_pk:
                    header = "-----BEGIN PRIVATE KEY-----"
                    footer = "-----END PRIVATE KEY-----"
                    body = clean_pk.split(header)[1].split(footer)[0]
                    clean_body = "".join(body.split()) # 공백 제거
                    valid_len = (len(clean_body) // 4) * 4
                    info["private_key"] = f"{header}\n{clean_body[:valid_len]}\n{footer}\n"
            return service_account.Credentials.from_service_account_info(info)
        except Exception as e:
            st.error(f"❌ 인증 정보 해석 실패: {e}")
    return None

# --- 2. TTS 엔진 및 UI ---
def google_premium_tts(text):
    if not text or not text.strip(): return None
    try:
        creds = get_creds()
        client = texttospeech.TextToSpeechClient(credentials=creds)
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

# --- UI 실행 ---
st.set_page_config(page_title="논문 나레이터 (완성본)", layout="wide")
st.title("🎙️ 논문 나레이터 (완성본)")

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
    for idx, ch in enumerate(data['chapters']):
        with st.expander(f"🔹 {ch['name']} 내용 확인"):
            st.write(ch['content'][:1500] + "...")
            if st.button(f"🔊 {ch['name']} 낭독", key=f"btn_{idx}"):
                audio = google_premium_tts(ch['content'])
                if audio: st.audio(audio)
