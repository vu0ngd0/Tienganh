import streamlit as st
import pandas as pd
from gtts import gTTS
import io
import os
import copy
import time

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="English Learning Pro (SRS)", page_icon="🧠", layout="wide")

# --- CSS TÙY CHỈNH (LÀM NÚT TO) ---
st.markdown("""
<style>
    /* Làm to tất cả các nút bấm trong ứng dụng để dễ thao tác */
    div.stButton > button {
        height: 60px;
        font-size: 20px;
        font-weight: bold;
        border-radius: 12px;
        transition: all 0.3s;
    }
    
    /* Hiệu ứng khi di chuột vào */
    div.stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }

    /* Tùy chỉnh riêng cho nút 'Nghe phát âm' để nó gọn hơn 1 chút nếu cần */
    div[data-testid="stHorizontalBlock"] button {
        /* Giữ nguyên style chung hoặc chỉnh sửa nếu muốn */
    }
</style>
""", unsafe_allow_html=True)

# --- HÀM TẢI DỮ LIỆU ---
@st.cache_data
def load_vocabulary(uploaded_file=None):
    df = None
    encodings_to_try = ['utf-8', 'utf-8-sig', 'cp1258', 'latin1', 'cp1252', 'utf-16']
    
    file_source = None
    if uploaded_file is not None:
        file_source = uploaded_file
    elif os.path.exists('vocabulary.csv'):
        file_source = 'vocabulary.csv'
    
    if file_source:
        for encoding in encodings_to_try:
            try:
                if hasattr(file_source, 'seek'): file_source.seek(0)
                df = pd.read_csv(file_source, encoding=encoding)
                if 'Word' in df.columns or 'English' in df.columns: break
            except: continue

    if df is None: return None

    # Xử lý dữ liệu
    df.columns = [c.strip() for c in df.columns]
    rename_map = {'English': 'Word', 'Tiếng Anh': 'Word', 'Vietnamese': 'Việt Note', 'Tiếng Việt': 'Việt Note', 'Cấp độ': 'Level'}
    df = df.rename(columns=rename_map)
    
    required_cols = {'Word', 'Việt Note'}
    if not required_cols.issubset(df.columns): return None

    df = df.dropna(subset=['Word', 'Việt Note'])
    if 'Level' not in df.columns: df['Level'] = 'Other'
    df['Level'] = df['Level'].fillna('Other')
    df['Phonetics'] = df['Phonetics'].fillna('') if 'Phonetics' in df.columns else ''
    df['Example'] = df['Example'].fillna('No example provided.') if 'Example' in df.columns else ''

    vocab_data = {}
    level_meta = {
        'A1': {'name': 'Cấp độ A1', 'icon': '🌱'}, 'A2': {'name': 'Cấp độ A2', 'icon': '🌿'},
        'B1': {'name': 'Cấp độ B1', 'icon': '🍂'}, 'B2': {'name': 'Cấp độ B2', 'icon': '🌳'},
        'C1': {'name': 'Cấp độ C1', 'icon': '🏔️'}, 'C2': {'name': 'Cấp độ C2', 'icon': '🚀'},
        'Other': {'name': 'Khác', 'icon': '📂'}
    }

    for level, group in df.groupby('Level'):
        level_key = str(level).strip()
        meta = level_meta.get(level_key, {'name': f'Level {level_key}', 'icon': '📘'})
        words_list = []
        for _, row in group.iterrows():
            words_list.append({
                "english": str(row['Word']).strip(),
                "vietnamese": str(row['Việt Note']).strip(),
                "pronunciation": str(row['Phonetics']).strip(),
                "example": str(row['Example']).strip(),
                "type": str(row['Type']).strip() if 'Type' in row else '',
                "progress": 0 
            })
        if words_list:
            vocab_data[level_key] = {"name": meta['name'], "icon": meta['icon'], "words": words_list}
            
    return vocab_data

# --- HÀM HỖ TRỢ ---
def text_to_speech(text):
    try:
        tts = gTTS(text=text, lang='en')
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        return audio_fp
    except: return None

def initialize_session(topic_data):
    st.session_state.learning_queue = copy.deepcopy(topic_data['words'])
    st.session_state.mastered_words = []
    st.session_state.show_meaning = False

# --- LOGIC XỬ LÝ NÚT BẤM ---
def handle_review(word, status):
    current_word = st.session_state.learning_queue.pop(0)
    
    if status == "forget":
        current_word['progress'] = 0
        insert_index = min(len(st.session_state.learning_queue), 10)
        st.session_state.learning_queue.insert(insert_index, current_word)
        # SỬA LỖI TẠI DÒNG DƯỚI ĐÂY (thay icon="study" thành icon="🔄")
        st.toast(f"Đã xếp lịch học lại '{current_word['english']}' sau 10 thẻ.", icon="🔄")
        
    elif status == "remember":
        current_word['progress'] += 1
        if current_word['progress'] >= 3:
            st.session_state.mastered_words.append(current_word)
            st.balloons()
            st.toast(f"🎉 Đã thuộc lòng '{current_word['english']}'", icon="✅")
        else:
            offset = 30 if current_word['progress'] == 1 else 50
            insert_index = min(len(st.session_state.learning_queue), offset)
            st.session_state.learning_queue.insert(insert_index, current_word)
            msg = "30 thẻ" if current_word['progress'] == 1 else "50 thẻ"
            st.toast(f"👍 Tốt! Gặp lại '{current_word['english']}' sau {msg}.", icon="⏰")
    
    st.session_state.show_meaning = False

# --- SETUP DỮ LIỆU ---
DEFAULT_DATA = {"demo": {"name": "Demo", "icon": "⚠️", "words": [{"english": "Hello", "vietnamese": "Xin chào", "pronunciation": "", "example": "", "progress": 0}]}}

with st.sidebar:
    st.header("⚙️ Cài đặt")
    uploaded_file = st.file_uploader("Tải lên file từ vựng (CSV)", type=['csv'])

VOCABULARY_DATA = load_vocabulary(uploaded_file)
if VOCABULARY_DATA is None: VOCABULARY_DATA = DEFAULT_DATA

# --- SESSION STATE ---
if 'selected_topic' not in st.session_state:
    st.session_state.selected_topic = list(VOCABULARY_DATA.keys())[0]
    initialize_session(VOCABULARY_DATA[st.session_state.selected_topic])

if 'previous_topic' not in st.session_state:
    st.session_state.previous_topic = st.session_state.selected_topic

# --- GIAO DIỆN CHÍNH ---
st.title("🧠 English SRS - Học lặp lại ngắt quãng")

topic_options = sorted(list(VOCABULARY_DATA.keys()))
topic_labels = [VOCABULARY_DATA[k]['name'] for k in topic_options]

col_select, col_stat = st.columns([2, 1])
with col_select:
    selected_label = st.selectbox("Chọn cấp độ học:", options=topic_labels, index=topic_options.index(st.session_state.selected_topic) if st.session_state.selected_topic in topic_options else 0)

new_topic = topic_options[topic_labels.index(selected_label)]
if new_topic != st.session_state.previous_topic:
    st.session_state.selected_topic = new_topic
    st.session_state.previous_topic = new_topic
    initialize_session(VOCABULARY_DATA[new_topic])
    st.rerun()

queue = st.session_state.learning_queue
mastered = st.session_state.mastered_words

with col_stat:
    st.metric("Còn lại", f"{len(queue)} từ")
    st.metric("Đã thuộc", f"{len(mastered)} từ")

total_words = len(queue) + len(mastered)
st.progress(len(mastered) / total_words if total_words > 0 else 0)

st.divider()

if len(queue) == 0:
    st.success("🎉 CHÚC MỪNG! Bạn đã học hết tất cả các từ trong danh sách này!")
    if st.button("Học lại từ đầu"):
        initialize_session(VOCABULARY_DATA[st.session_state.selected_topic])
        st.rerun()
else:
    word = queue[0]
    
    card_container = st.container(border=True)
    with card_container:
        c1, c2 = st.columns([4, 1])
        with c1:
            st.markdown(f"<h1 style='text-align: center; color: #2563EB; font-size: 3em; margin-bottom: 0;'>{word['english']}</h1>", unsafe_allow_html=True)
        with c2:
            st.caption(f"Cấp độ nhớ: {'🟢' * word['progress'] + '⚪' * (3-word['progress'])}")
        
        st.markdown(f"<p style='text-align: center; font-size: 1.5em; color: #666;'>{word['pronunciation']}</p>", unsafe_allow_html=True)
        
        # Audio Button & Logic Autoplay
        col_audio_btn, col_audio_player = st.columns([1, 1])
        
        # Biến để kiểm tra xem có vừa bấm nút nghe không
        if 'trigger_audio' not in st.session_state:
            st.session_state.trigger_audio = False
            
        with col_audio_btn:
            # Tạo một container nhỏ căn giữa cho nút nghe
            if st.button("🔊 NGHE PHÁT ÂM", use_container_width=True):
                st.session_state.trigger_audio = True
        
        # Xử lý phát âm thanh (Ẩn trình phát nhưng bật Autoplay)
        if st.session_state.trigger_audio:
            audio_fp = text_to_speech(word['english'])
            if audio_fp:
                # autoplay=True giúp phát ngay lập tức
                st.audio(audio_fp, format='audio/mp3', autoplay=True)
                st.session_state.trigger_audio = False # Reset lại sau khi phát

        st.markdown("---")
        
        if st.session_state.show_meaning:
            st.markdown(f"<h2 style='text-align: center; color: #DC2626;'>{word['vietnamese']}</h2>", unsafe_allow_html=True)
            if word['type']:
                st.markdown(f"<p style='text-align: center;'><strong>Loại từ:</strong> {word['type']}</p>", unsafe_allow_html=True)
            st.info(f"💡 Ví dụ: {word['example']}")
        else:
            st.markdown("<div style='height: 150px; display: flex; align-items: center; justify-content: center; color: #aaa;'><em>(Nhấn 'Hiện nghĩa' để xem đáp án)</em></div>", unsafe_allow_html=True)

    st.write("") 
    
    # --- CÁC NÚT ĐIỀU KHIỂN (ĐÃ ĐƯỢC CSS LÀM TO) ---
    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
    
    if not st.session_state.show_meaning:
        with col_btn2:
            if st.button("👆 HIỆN NGHĨA", type="primary", use_container_width=True):
                st.session_state.show_meaning = True
                st.rerun()
    else:
        with col_btn1:
            # Nút Học lại
            if st.button("😖 HỌC LẠI\n(10 thẻ)", use_container_width=True):
                handle_review(word, "forget")
                st.rerun()
        
        with col_btn3:
            # Nút Đã nhớ
            next_step = "30 thẻ" if word['progress'] == 0 else "50 thẻ" if word['progress'] == 1 else "Xong"
            # Dùng type="primary" để nút này nổi bật hơn (màu đỏ/cam mặc định của theme)
            if st.button(f"😎 ĐÃ NHỚ\n({next_step})", type="primary", use_container_width=True):
                handle_review(word, "remember")
                st.rerun()

with st.expander("Debug: Xem hàng đợi"):
    st.write(f"Queue: {len(queue)}")
    if len(queue) > 0:
        st.dataframe(pd.DataFrame(queue)[['english', 'vietnamese', 'progress']].head(5))