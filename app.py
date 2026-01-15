import streamlit as st
from google.cloud import texttospeech
import fitz
import re
import os
import json

# --- 1. 구글 인증 설정 (클라우드 비밀 금고 + 유령 문자 자동 세척) ---
if "google_creds" in st.secrets:
    creds_dict = dict(st.secrets["google_creds"])
    if "private_key" in creds_dict:
        pk = creds_dict["private_key"]
        header = "-----BEGIN PRIVATE KEY-----"
        footer = "-----END PRIVATE KEY-----"
        
        if header in pk and footer in pk:
            # [진단] 1625자 에러 및 유령 문자 'a'를 강제로 지웁니다.
            body = pk.split(header)[1].split(footer)[0]
            clean_body = "".join(body.replace("\\n", "").split())
            valid_len = (len(clean_body) // 4) * 4
            clean_body = clean_body[:valid_len]
            creds_dict["private_key"] = f"{header}\n{clean_body}\n{footer}\n"

    with open("temp_key.json", "w") as f:
        json.dump(creds_dict, f)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"
else:
    # 로컬 테스트용
    current_dir = os.path.dirname(os.path.abspath(__file__))
    KEY_PATH = os.path.join(current_dir, "google_key.json")
    if os.path.exists(KEY_PATH):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH

# --- 2. TTS 엔진 ---
def google_premium_tts(raw_text, filename, is_chapter=False):
    if not raw_text.strip(): return None
    try:
        client = texttospeech.TextToSpeechClient()
        # 불필요한 기호 제거
        clean_text = re.sub(r'\([가-힣a-zA-Z\s,·]+\)', '', raw_text)
        
        max_chunk = 1000 
        text_chunks = [clean_text[i:i+max_chunk] for i in range(0, len(clean_text), max_chunk)]
        
        combined_audio = b""
        for chunk in text_chunks:
            ssml_text = f"<speak><prosody rate='1.1'>{chunk}</prosody></speak>"
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(ssml=ssml_text),
                voice=texttospeech.VoiceSelectionParams(
                    language_code="ko-KR", name="ko-KR-Neural2-B"
                ),
                audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
            )
            combined_audio += response.audio_content
        return combined_audio
    except Exception as e:
        st.error(f"⚠️ TTS 오류: {str(e)}")
        return None

# --- 3. 텍스트 정제 및 추출 ---
def narrative_word_healer(text):
    text = re.sub(r'([가-힣])\s?\n\s?([가-힣])', r'\1\2', text)
    text = re.sub(r'([은는이가을를의에로와과,.\)\]!\?])\s?\n', r'\1 ', text)
    return re.sub(r'\s+', ' ', text).strip()

def extract_thesis(doc):
    pages_content = [page.get_text("text") for page in doc]
    full_text = narrative_word_healer("\n".join(pages_content))
    
    # 제목 추출
    first_page_lines = pages_content[0].split('\n')
    title = [l.strip() for l in first_page_lines if l.strip() and 'ISSN' not in l][:1][0]
    
    # 요약 및 본문
    main_body = full_text.split("참고문헌")[0].split("References")[0]
    abs_match = re.search(r'(요\s*약|국문요약)(.*?)(Abstract|Ⅰ\.)', main_body, re.S)
    summary = abs_match.group(2).strip() if abs_match else "요약을 찾을 수 없습니다."

    chapters = []
    ch_splits = re.split(r'(Ⅰ\.|Ⅱ\.|Ⅲ\.|Ⅳ\.|Ⅴ\.)', main_body)
    for i in range(1, len(ch_splits), 2):
        name, content = ch_splits[i], ch_splits[i+1].strip()
        if len(content) > 50:
            chapters.append({"name": name, "content": content})
    return title, summary, chapters

# --- 4. 메인 UI ---
st.set_page_config(page_title="논문 나레이터", layout="wide")
st.title("🎙️ 논문 나레이터 (Smart & Clean)")

uploaded_file = st.file_uploader("논문 PDF 업로드", type=["pdf"])

if uploaded_file:
    if 'thesis_data' not in st.session_state:
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        t, s, c = extract_thesis(doc)
        st.session_state.thesis_data = {'title': t, 'summary': s, 'chapters': c}

    data = st.session_state.thesis_data
    st.subheader("📌 1. 주제 및 요약")
    f_title = st.text_input("📄 논문 제목", data['title'])
    
    if st.button("🔊 제목 + 요약 음원 생성"):
        audio = google_premium_tts(f"{f_title}. {data['summary']}", "summary.mp3")
        if audio:
            st.audio(audio)
            st.download_button("📥 MP3 다운로드", audio, "summary.mp3")

    st.divider()
    st.subheader("📖 2. 본문")
    for idx, ch in enumerate(data['chapters']):
        with st.expander(f"🔹 {ch['name']}"):
            st.write(ch['content'][:1000] + "...")
            if st.button(f"🔊 {ch['name']} 변환", key=f"btn_{idx}"):
                audio = google_premium_tts(ch['content'], f"chapter_{idx+1}.mp3")
                if audio: st.audio(audio)

    st.divider()
    st.subheader("🚀 3. 전체 통합 변환")
    if st.button("🎙️ 논문 전체 통합 음원 생성", use_container_width=True):
        full_script = f"{f_title}. {data['summary']}. " + " ".join([ch['content'] for ch in data['chapters']])
        with st.spinner("전체 음원 합성 중... (수 분이 소요될 수 있습니다)"):
            audio = google_premium_tts(full_script, "full_thesis.mp3")
            if audio:
                st.success("✅ 전체 음원 생성 완료!")
                st.audio(audio)
