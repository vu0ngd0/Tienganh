import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import os
import copy
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CẤU HÌNH ---
st.set_page_config(page_title="English Pro (Auto Sync)", page_icon="☁️", layout="wide")

# --- CSS ---
st.markdown("""
<style>
    div.stButton > button { height: 60px; font-size: 20px; font-weight: bold; border-radius: 12px; }
    .stToast { position: fixed; top: 50px; right: 10px; width: 300px; }
</style>
""", unsafe_allow_html=True)

# --- KẾT NỐI GOOGLE SHEETS (Đã sửa để đọc từ connections.gsheets) ---
@st.cache_resource
def connect_gsheet():
    try:
        # Cập nhật: Đọc từ mục [connections.gsheets]
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
            creds_dict = dict(st.secrets["connections"]["gsheets"])
        else:
            # Fallback cho trường hợp cũ
            creds_dict = dict(st.secrets["gcp_service_account"])

        # Xử lý lỗi dòng mới trong Private Key (quan trọng)
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        # st.error(f"Lỗi kết nối: {e}") 
        return None

def get_sheet_url():
    """Lấy URL từ secrets (ưu tiên spreadsheet hoặc sheet_url)"""
    url = ""
    # Kiểm tra trong connections.gsheets
    if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        secrets_gsheets = st.secrets["connections"]["gsheets"]
        if "spreadsheet" in secrets_gsheets:
            url = secrets_gsheets["spreadsheet"]
        elif "sheet_url" in secrets_gsheets:
            url = secrets_gsheets["sheet_url"]
    
    # Kiểm tra cấu hình cũ
    if not url and "sheet_url" in st.secrets:
        url = st.secrets["sheet_url"]
        
    return url

def save_to_gsheet(queue, mastered):
    sheet_url = get_sheet_url()
    if not sheet_url:
        st.error("Chưa tìm thấy Link Google Sheet trong secrets.toml")
        return

    client = connect_gsheet()
    if not client: return
    
    try:
        sh = client.open_by_url(sheet_url)
        
        # Lưu Queue
        try: ws_queue = sh.worksheet("Queue")
        except: ws_queue = sh.add_worksheet(title="Queue", rows=1000, cols=10)
        
        ws_queue.clear()
        if queue:
            headers = list(queue[0].keys())
            data = [headers] + [[str(d.get(k, '')) for k in headers] for d in queue]
            ws_queue.update(range_name='A1', values=data)
        else:
            ws_queue.update(range_name='A1', values=[["Empty"]])

        # Lưu Mastered
        try: ws_mastered = sh.worksheet("Mastered")
        except: ws_mastered = sh.add_worksheet(title="Mastered", rows=1000, cols=10)
        
        ws_mastered.clear()
        if mastered:
            headers = list(mastered[0].keys())
            data = [headers] + [[str(d.get(k, '')) for k in headers] for d in mastered]
            ws_mastered.update(range_name='A1', values=data)
        else:
            ws_mastered.update(range_name='A1', values=[["Empty"]])
            
    except Exception as e:
        st.error(f"Lỗi lưu data: {e}")

def load_from_gsheet():
    sheet_url = get_sheet_url()
    if not sheet_url: return None, None
    
    client = connect_gsheet()
    if not client: return None, None
    
    try:
        sh = client.open_by_url(sheet_url)
        
        def clean_records(records):
            cleaned = []
            for r in records:
                if len(r) == 1 and list(r.values())[0] == "Empty": continue
                if 'progress' in r:
                    try: r['progress'] = int(r['progress'])
                    except: r['progress'] = 0
                cleaned.append(r)
            return cleaned

        try:
            ws_queue = sh.worksheet("Queue")
            q_data = clean_records(ws_queue.get_all_records())
        except: q_data = []
        
        try:
            ws_mastered = sh.worksheet("Mastered")
            m_data = clean_records(ws_mastered.get_all_records())
        except: m_data = []
            
        return q_data, m_data

    except Exception as e:
        return None, None

# --- HÀM TẢI TỪ VỰNG GỐC ---
@st.cache_data
def load_vocabulary(uploaded_file=None):
    df = None
    encodings = ['utf-8', 'utf-8-sig', 'cp1258', 'latin1', 'cp1252']
    file_source = uploaded_file if uploaded_file else ('vocabulary.csv' if os.path.exists('vocabulary.csv') else None)
    
    if file_source:
        for enc in encodings:
            try:
                if hasattr(file_source, 'seek'): file_source.seek(0)
                df = pd.read_csv(file_source, encoding=enc)
                if 'Word' in df.columns or 'English' in df.columns: break
            except: continue

    if df is None: return None

    df.columns = [c.strip() for c in df.columns]
    rename = {'English': 'Word', 'Tiếng Anh': 'Word', 'Vietnamese': 'Việt Note', 'Tiếng Việt': 'Việt Note', 'Cấp độ': 'Level'}
    df = df.rename(columns=rename)
    
    df = df.dropna(subset=['Word', 'Việt Note'])
    if 'Level' not in df.columns: df['Level'] = 'Other'
    
    vocab_data = {}
    for level, group in df.groupby('Level'):
        level = str(level).strip()
        words = []
        for _, row in group.iterrows():
            words.append({
                "english": str(row['Word']).strip(),
                "vietnamese": str(row['Việt Note']).strip(),
                "pronunciation": str(row.get('Phonetics', '')).strip(),
                "example": str(row.get('Example', '')).strip(),
                "type": str(row.get('Type', '')).strip(),
                "progress": 0
            })
        vocab_data[level] = {"name": f"Level {level}", "words": words}
    return vocab_data

# --- HÀM LOGIC ---
def text_to_speech(text):
    try:
        tts = gTTS(text=text, lang='en')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        return fp
    except: return None

def handle_review(word, status):
    current = st.session_state.learning_queue.pop(0)
    
    if status == "forget":
        current['progress'] = 0
        st.session_state.learning_queue.insert(min(len(st.session_state.learning_queue), 10), current)
        st.toast(f"Học lại: {current['english']}", icon="🔄")
    elif status == "remember":
        current['progress'] += 1
        if current['progress'] >= 3:
            st.session_state.mastered_words.append(current)
            st.balloons()
        else:
            offset = 30 if current['progress'] == 1 else 50
            st.session_state.learning_queue.insert(min(len(st.session_state.learning_queue), offset), current)
            st.toast(f"Đã nhớ: {current['english']}", icon="✅")
            
    st.session_state.show_meaning = False
    
    # TỰ ĐỘNG LƯU
    save_to_gsheet(st.session_state.learning_queue, st.session_state.mastered_words)

# --- KHỞI TẠO DỮ LIỆU ---
DEFAULT_DATA = {"Demo": {"name": "Demo", "words": [{"english": "Hello", "vietnamese": "Xin chào", "progress": 0}]}}

with st.sidebar:
    st.title("⚙️ Cài đặt")
    uploaded_file = st.file_uploader("Upload CSV Từ vựng (nếu cần đổi)", type=['csv'])
    
    st.divider()
    if get_sheet_url():
        st.success("✅ Đã kết nối Google Sheet")
    else:
        st.error("⚠️ Chưa tìm thấy cấu hình Google Sheet")

# 1. Load từ vựng gốc
VOCABULARY_DATA = load_vocabulary(uploaded_file)
if not VOCABULARY_DATA: VOCABULARY_DATA = DEFAULT_DATA

# 2. Khởi tạo Session
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.session_state.show_meaning = False
    
    # Load từ Cloud
    with st.spinner("Đang đồng bộ dữ liệu từ Cloud..."):
        cloud_queue, cloud_mastered = load_from_gsheet()
    
    if cloud_queue is not None:
        st.session_state.learning_queue = cloud_queue
        st.session_state.mastered_words = cloud_mastered
        
        # Đoán topic
        found_topic = list(VOCABULARY_DATA.keys())[0]
        if cloud_queue:
            first_word = cloud_queue[0]['english']
            for topic, data in VOCABULARY_DATA.items():
                for w in data['words']:
                    if w['english'] == first_word:
                        found_topic = topic
                        break
        st.session_state.selected_topic = found_topic
        st.toast("📂 Đã tự động nạp tiến độ cũ!", icon="✅")
        
    else:
        first_topic = list(VOCABULARY_DATA.keys())[0]
        st.session_state.selected_topic = first_topic
        st.session_state.learning_queue = copy.deepcopy(VOCABULARY_DATA[first_topic]['words'])
        st.session_state.mastered_words = []

if 'previous_topic' not in st.session_state:
    st.session_state.previous_topic = st.session_state.selected_topic

# --- GIAO DIỆN CHÍNH ---
st.title("☁️ English Pro - Auto Sync")

topic_options = sorted(list(VOCABULARY_DATA.keys()))
topic_labels = [VOCABULARY_DATA[k]['name'] for k in topic_options]

col_select, col_stat = st.columns([2, 1])
with col_select:
    try: idx = topic_options.index(st.session_state.selected_topic)
    except: idx = 0
    selected_label = st.selectbox("Chọn cấp độ học:", options=topic_labels, index=idx)

new_topic = topic_options[topic_labels.index(selected_label)]
if new_topic != st.session_state.previous_topic:
    st.session_state.selected_topic = new_topic
    st.session_state.previous_topic = new_topic
    
    st.session_state.learning_queue = copy.deepcopy(VOCABULARY_DATA[new_topic]['words'])
    st.session_state.mastered_words = []
    st.session_state.show_meaning = False
    
    save_to_gsheet(st.session_state.learning_queue, st.session_state.mastered_words)
    st.rerun()

queue = st.session_state.learning_queue
mastered = st.session_state.mastered_words

with col_stat:
    st.metric("Hàng đợi", len(queue))
    st.metric("Đã thuộc", len(mastered))
st.progress(len(mastered) / (len(queue) + len(mastered)) if (len(queue) + len(mastered)) > 0 else 0)

st.divider()

if not queue:
    st.success("🎉 Bạn đã hoàn thành chủ đề này!")
    if st.button("Học lại từ đầu"):
        st.session_state.learning_queue = copy.deepcopy(VOCABULARY_DATA[st.session_state.selected_topic]['words'])
        st.session_state.mastered_words = []
        save_to_gsheet(st.session_state.learning_queue, [])
        st.rerun()
else:
    word = queue[0]
    with st.container(border=True):
        st.markdown(f"<h1 style='text-align: center; color: #0068C9'>{word['english']}</h1>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: center; color: gray'>{word.get('pronunciation', '')}</p>", unsafe_allow_html=True)
        
        col_audio, _ = st.columns([1,3])
        if 'trigger_audio' not in st.session_state: st.session_state.trigger_audio = False
        with col_audio:
             if st.button("🔊 NGHE", use_container_width=True):
                 st.session_state.trigger_audio = True
        
        if st.session_state.trigger_audio:
            audio = text_to_speech(word['english'])
            if audio: st.audio(audio, format='audio/mp3', autoplay=True)
            st.session_state.trigger_audio = False

        st.divider()
        
        if st.session_state.show_meaning:
            st.markdown(f"<h2 style='text-align: center; color: #FF4B4B'>{word['vietnamese']}</h2>", unsafe_allow_html=True)
            st.info(f"Ví dụ: {word.get('example', '')}")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("😖 HỌC LẠI", use_container_width=True):
                    handle_review(word, "forget")
                    st.rerun()
            with c2:
                if st.button("😎 ĐÃ NHỚ", type="primary", use_container_width=True):
                    handle_review(word, "remember")
                    st.rerun()
        else:
             if st.button("HIỆN NGHĨA", type="primary", use_container_width=True):
                 st.session_state.show_meaning = True
                 st.rerun()
