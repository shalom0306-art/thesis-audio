박사님, **'[클라우드 전용 전체 코드]'**란 박사님의 PC에서만 돌아가던 프로그램을 인터넷(Streamlit Cloud) 환경에서도 똑똑하게 작동하도록 수정한 최종 설계도를 말합니다.

가장 큰 차이점은 보안입니다. PC에서는 google_key.json 파일을 직접 불러왔지만, 인터넷에 이 파일을 그대로 올리면 해킹의 위험이 있습니다. 그래서 이 코드는 **'비밀 금고(Secrets)'**에 저장된 키 정보를 안전하게 꺼내 쓰도록 설계되어 있습니다.

아래 박스 안의 코드가 바로 그 전체 코드입니다. 이 내용을 통째로 복사해서 깃허브의 app.py 본문에 붙여넣으시면 됩니다.

📄 app.py에 붙여넣을 [클라우드 전용 전체 코드]
Python

from google.cloud import texttospeech
import fitz
import re
import os
import json

# --- 1. 구글 인증 설정 (클라우드/로컬 겸용) ---
# 스트림릿 클라우드의 'Secrets'에 키를 넣었을 때와 내 PC에서 돌릴 때를 모두 지원합니다.
if "google_creds" in st.secrets:
    # [클라우드 환경] Secrets에 저장된 정보를 임시 파일로 만들어 인증
    creds_dict = dict(st.secrets["google_creds"])
    with open("temp_key.json", "w") as f:
        json.dump(creds_dict, f)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"
else:
    # [로컬 PC 환경] 기존처럼 google_key.json 파일 사용
    current_dir = os.path.dirname(os.path.abspath(__file__))
    KEY_PATH = os.path.join(current_dir, "google_key.json")
    if os.path.exists(KEY_PATH):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEY_PATH

# --- 2. 음원 전용 필터링 (청각 최적화) ---
def clean_for_audio(text, is_chapter=False):
    # 영어 병기 및 인용/각주 생략
    text = re.sub(r'\([a-zA-Z\s,./-]+\)', '', text)
    text = re.sub(r'\([^)]*\d{4}[^)]*\)', '', text)
    text = re.sub(r'\[\d+[\d\s,]*\]', '', text)
    
    # '서론' 및 장 제목 뒤 휴지기(1.5초)
    text = text.replace("서론", "서론 <break time='1.5s'/>")
    if is_chapter:
        text = re.sub(r'^([^.!?\n]+)', r'\1 <break time="1.5s"/>', text)
    return text

# --- 3. 프리미엄 TTS 엔진 (1.1배속) ---
def google_premium_tts(raw_text, filename, is_chapter=False):
    if not raw_text.strip(): return None
    try:
        client = texttospeech.TextToSpeechClient()
        audio_text = clean_for_audio(raw_text, is_chapter)
        
        max_chunk = 1000 
        text_chunks = [audio_text[i:i+max_chunk] for i in range(0, len(audio_text), max_chunk)]
        
        combined_audio = b""
        for chunk in text_chunks:
            ssml_text = f"<speak><prosody rate='1.1' pitch='0.0st'>{chunk}</prosody></speak>"
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(ssml=ssml_text),
                voice=texttospeech.VoiceSelectionParams(
                    language_code="ko-KR", name="ko-KR-Neural2-B",
                    ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
                ),
                audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3, speaking_rate=1.1)
            )
            combined_audio += response.audio_content
        return combined_audio
    except Exception as e:
        st.error(f"⚠️ TTS 오류: {str(e)}")
        return None

# --- 4. 텍스트 정제 로직 ---
def narrative_word_healer(text):
    lines = text.split('\n')
    clean_lines = []
    meta_keywords = ['ISSN', 'DOI', 'http', 'Vol', 'No', 'Journal', '발행', 'pp.', 'ⓒ', 'Copyright']
    
    for line in lines:
        l = line.strip()
        if l.isdigit() and len(l) < 4: continue 
        if any(k.lower() in l.lower() for k in meta_keywords): continue
        clean_lines.append(l)
    
    text = " ".join(clean_lines)
    text = re.sub(r'([가-힣])\s?\n\s?([가-힣])', r'\1\2', text)
    text = re.sub(r'([은는이가을를의에로와과,.\)\]!\?])\s?\n', r'\1 ', text)
    return re.sub(r'\s+', ' ', text).strip()

def extract_thesis(doc):
    pages_content = [page.get_text("text") for page in doc]
    
    # 제목 추출 (쪽번호 제거 포함)
    first_page_lines = pages_content[0].split('\n')
    title_parts = []
    for line in first_page_lines:
        l = line.strip()
        if not l or any(k in l for k in ['ISSN', 'DOI', 'http']): continue
        if '*' in l or '요약' in l or 'Abstract' in l or 'Ⅰ.' in l: break
        title_parts.append(l)
    title = re.sub(r'\s*\d+$', '', " ".join(title_parts)).strip()

    # 본문 및 요약 추출
    full_text = narrative_word_healer("\n".join(pages_content))
    main_body = full_text.split("참고문헌")[0].split("References")[0]
    
    abs_match = re.search(r'(국\s*문\s*요\s*약|요\s*약)(.*?)(Abstract|주\s*제\s*어|Ⅰ\.|1\.)', main_body, re.S)
    summary = narrative_word_healer(abs_match.group(2)) if abs_match else "요약을 찾을 수 없습니다."

    chapters = []
    ch_splits = re.split(r'(제\s*[1-5]\s*장|Ⅰ\.|Ⅱ\.|Ⅲ\.|Ⅳ\.|Ⅴ\.)', main_body)
    for i in range(1, len(ch_splits), 2):
        name = ch_splits[i].strip()
        content = ch_splits[i+1].strip()
        if len(content) > 50:
            chapters.append({"name": name, "content": f"{name}. {content}"})

    return title, summary, chapters

# --- 5. 메인 UI ---
st.set_page_config(page_title="논문 나레이터 Cloud", layout="wide")
st.title("🎙️ 논문 나레이터 (Cloud 버전)")

uploaded_file = st.file_uploader("논문 PDF 업로드", type=["pdf"])

if uploaded_file:
    if 'thesis_data' not in st.session_state:
        with st.spinner("논문을 분석 중입니다..."):
            doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
            t, s, c = extract_thesis(doc)
            st.session_state.thesis_data = {'title': t, 'summary': s, 'chapters': c}

    data = st.session_state.thesis_data
    f_title = st.text_input("📄 논문 제목 (수정 가능)", data['title'])
    
    if st.button("🔊 주제 + 요약 음원 생성"):
        audio = google_premium_tts(f"{f_title}. {data['summary']}", "summary.mp3", is_chapter=True)
        if audio:
            st.audio(audio)
            st.download_button("📥 MP3 다운로드 (summary.mp3)", audio, "summary.mp3", "audio/mp3")

    st.divider()
    for idx, ch in enumerate(data['chapters']):
        with st.expander(f"🔹 {ch['name']}"):
            st.write(ch['content'])
            if st.button(f"🔊 {ch['name']} 낭독", key=f"btn_{idx}"):
                fname = f"chapter_{idx+1}.mp3"
                audio = google_premium_tts(ch['content'], fname, is_chapter=True)
                if audio:
                    st.audio(audio)
                    st.download_button(f"📥 다운로드 ({fname})", audio, fname, "audio/mp3")

    st.divider()
    if st.button("🚀 논문 전체 통합 음원 생성", use_container_width=True):
        full_script = f"{f_title}. {data['summary']}. " + " ".join([ch['content'] for ch in data['chapters']])
        with st.spinner("전체 음원 합성 중..."):
            audio = google_premium_tts(full_script, "original.mp3", is_chapter=True)
            if audio:
                st.audio(audio)
                st.download_button("📥 전체 논문 다운로드 (original.mp3)", audio, "original.mp3", "audio/mp3", use_container_width=True)
