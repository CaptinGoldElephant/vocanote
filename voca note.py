import streamlit as st
import pandas as pd
import random
import os
import time
import nltk
import io
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from nltk.stem import PorterStemmer

# --- 1. 배포 및 환경 준비 ---
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

stemmer = PorterStemmer()
DB_FILE = "voca_db.csv"

# 구글 시트 연동 설정
SHEET_ID = "1BYuQhbPLwnLxBHu4gjf-1H8fNoYvRRwIyg2TU1vfvw8"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

# 폰트 설정 (서버/로컬 대응)
FONT_PATH = "malgun.ttf" 
if not os.path.exists(FONT_PATH):
    FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("Malgun", FONT_PATH))

# --- 2. 데이터 관리 함수 ---
def load_data():
    try:
        # 1순위: 구글 시트 시도
        df_loaded = pd.read_csv(SHEET_URL)
        if 'date' not in df_loaded.columns:
            df_loaded['date'] = datetime.now().strftime("%Y-%m-%d")
        return df_loaded
    except:
        # 2순위: 로컬 파일 시도
        if os.path.exists(DB_FILE):
            return pd.read_csv(DB_FILE)
        return pd.DataFrame(columns=["word", "mean", "root", "count", "date"])

def save_data(dataframe):
    dataframe.to_csv(DB_FILE, index=False, encoding="utf-8-sig")

# --- 3. 앱 메인 로직 ---
st.set_page_config(page_title="스마트 토익 단어장", layout="wide")
st.title("📚 스마트 토익 단어장 (실시간 연동형)")

# [중요] 세션 상태에 데이터 고정 (오류 방지 핵심)
if 'df' not in st.session_state:
    st.session_state.df = load_data()

# 사이드바 백업 버튼
st.sidebar.header("💾 데이터 관리")
csv_backup = st.session_state.df.to_csv(index=False, encoding="utf-8-sig")
st.sidebar.download_button(
    label="내 컴퓨터로 전체 백업 (CSV)",
    data=csv_backup,
    file_name=f"voca_backup_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv"
)

menu = st.sidebar.selectbox("메뉴를 선택하세요", ["단어 등록하기", "단어 목록 보기", "날짜별 단어 조회", "시험지 만들기"])

# --- 메뉴 1: 단어 등록하기 ---
if menu == "단어 등록하기":
    st.header("📝 새 단어 등록")
    tab1, tab2 = st.tabs(["직접 입력", "CSV 파일 업로드"])
    
    with tab1:
        with st.form("word_form", clear_on_submit=True):
            word = st.text_input("영어 단어를 입력하세요").strip().lower()
            mean = st.text_input("한글 뜻을 입력하세요").strip()
            if st.form_submit_button("저장하기"):
                if word and mean:
                    root = stemmer.stem(word)
                    today = datetime.now().strftime("%Y-%m-%d")
                    new_row = {"word": word, "mean": mean, "root": root, "count": 0, "date": today}
                    st.session_state.df = pd.concat([st.session_state.df, pd.DataFrame([new_row])], ignore_index=True).drop_duplicates('word', keep='first')
                    save_data(st.session_state.df)
                    st.success(f"'{word}' 저장 완료!")
                    st.rerun()

    with tab2:
        uploaded_file = st.file_uploader("CSV 파일을 선택하세요", type=["csv"])
        if uploaded_file is not None:
            try:
                try: user_csv = pd.read_csv(uploaded_file)
                except:
                    uploaded_file.seek(0)
                    user_csv = pd.read_csv(uploaded_file, encoding='cp949')
                
                st.write("불러온 파일 미리보기:")
                st.dataframe(user_csv.head())
                cols = user_csv.columns.tolist()
                w_col = st.selectbox("단어 열 선택", cols)
                m_col = st.selectbox("뜻 열 선택", cols)
                
                if st.button("내 단어장에 합치기"):
                    temp_df = pd.DataFrame()
                    temp_df['word'] = user_csv[w_col].astype(str).str.strip().str.lower()
                    temp_df['mean'] = user_csv[m_col].astype(str).str.strip()
                    temp_df['root'] = temp_df['word'].apply(lambda x: stemmer.stem(str(x)))
                    temp_df['count'] = 0
                    temp_df['date'] = datetime.now().strftime("%Y-%m-%d")
                    
                    st.session_state.df = pd.concat([st.session_state.df, temp_df], ignore_index=True).drop_duplicates('word', keep='first')
                    save_data(st.session_state.df)
                    st.success("단어 합치기 완료!")
                    time.sleep(1); st.rerun()
            except Exception as e: st.error(f"오류: {e}")

 # --- 메뉴 2: 단어 목록 보기 (버튼 위치 조정 및 영어 수정 추가) ---
elif menu == "단어 목록 보기":
    st.header("📋 전체 단어 관리 및 검색")
    current_df = st.session_state.df
    
    if len(current_df) > 0:
        # 1. 안내 문구 (상단 고정)
        st.info("💡 위 표에서 수정하거나 삭제할 단어의 '선택' 칸을 체크해 주세요.")
        
        search = st.text_input("🔍 검색 (영어)").strip().lower()
        f_df = current_df[current_df['word'].str.contains(search, na=False)].sort_values(by="word")
        
        if not f_df.empty:
            d_df = f_df.copy(); d_df.insert(0, "선택", False)
            edited = st.data_editor(d_df, hide_index=True, use_container_width=True, key="v_editor")
            s_rows = edited[edited["선택"] == True]
            
            if not s_rows.empty:
                sel_w = s_rows.iloc[-1]["word"]
                idx = current_df[current_df['word'] == sel_w].index[0]
                
                st.divider()
                st.subheader(f"⚙️ 단어 수정 및 삭제")
                
                # 2. 수정 입력 칸 (영어 단어 포함 3열 배치)
                c1, c2, c3 = st.columns(3)
                with c1: n_w = st.text_input("영어 단어 수정", value=current_df.at[idx, 'word'], key=f"w_{idx}")
                with c2: n_m = st.text_input("한글 뜻 수정", value=current_df.at[idx, 'mean'], key=f"m_{idx}")
                with c3: n_r = st.text_input("어근 수정", value=current_df.at[idx, 'root'], key=f"r_{idx}")
                
                # 3. 버튼 배치 (수정 완료 옆에 바로 삭제 버튼 배치)
                btn_col = st.columns([1, 1, 4]) # 버튼 두 개를 왼쪽에 모으기 위해 컬럼 비율 조정
                with btn_col[0]:
                    if st.button("💾 수정 완료", use_container_width=True):
                        st.session_state.df.at[idx, 'word'] = n_w.strip().lower()
                        st.session_state.df.at[idx, 'mean'] = n_m.strip()
                        st.session_state.df.at[idx, 'root'] = n_r.strip()
                        save_data(st.session_state.df)
                        st.success("수정 완료!")
                        time.sleep(0.5)
                        st.rerun()
                with btn_col[1]:
                    if st.button("🗑️ 단어 삭제", use_container_width=True):
                        st.session_state.df = st.session_state.df.drop(idx)
                        save_data(st.session_state.df)
                        st.warning("삭제 완료!")
                        time.sleep(0.5)
                        st.rerun()
        else:
            st.warning("검색 결과가 없습니다.")
    else:
        st.info("저장된 단어가 없습니다.")


# --- 메뉴 3: 날짜별 단어 조회 ---
elif menu == "날짜별 단어 조회":
    st.header("📅 날짜별 등록 현황")
    current_df = st.session_state.df
    if len(current_df) > 0:
        all_dates = sorted(current_df['date'].unique(), reverse=True)
        target = st.selectbox("날짜 선택", all_dates)
        date_df = current_df[current_df['date'] == target]
        st.subheader(f"📍 {target} 등록 ({len(date_df)}개)")
        st.table(date_df[['word', 'mean']].sort_values(by="word"))
    else: st.info("저장된 단어가 없습니다.")

# --- 메뉴 4: 시험지 만들기 (사용자님 50개 레이아웃 보존) ---
elif menu == "시험지 만들기":
    st.header("🖨️ PDF 시험지 생성")
    current_df = st.session_state.df
    if len(current_df) < 5: st.error("단어가 부족합니다.")
    else:
        num = st.number_input("문제 개수", 5, len(current_df), min(50, len(current_df)))
        if st.button("랜덤 시험지 생성"):
            shuffled = current_df.sample(frac=1).reset_index(drop=True)
            sel_list, roots = [], set()
            for _, r in shuffled.iterrows():
                if len(sel_list) >= num: break
                if r['root'] not in roots: sel_list.append(r); roots.add(r['root'])
            
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=A4)
            width, height = A4
            
            def draw_layout(page_words, is_ans, p_num):
                c.setFont("Malgun", 22)
                c.drawString(50, height-50, "Vocabulary Test" if not is_ans else "Answer Key")
                c.setFont("Malgun", 11)
                c.drawRightString(width-50, height-48, f"Name: ________________  (Page {p_num})")
                c.line(45, height-62, width-45, height-62)
                for i, row in enumerate(page_words):
                    col_x = 50 if i < 25 else 310
                    row_y = (height-95) - ((i % 25) * 28.5)
                    txt = f"{i+1+(p_num-1)*50}. {row['word']} : "
                    c.setFillColorRGB(0,0,0); c.drawString(col_x, row_y, txt)
                    w_w = c.stringWidth(txt, "Malgun", 11)
                    if is_ans:
                        c.setFillColorRGB(0.8,0,0); m_txt = str(row['mean'])
                        c.setFont("Malgun", 8.5 if c.stringWidth(m_txt, "Malgun", 10) > 230 else 10)
                        c.drawString(col_x+w_w, row_y, m_txt); c.setFont("Malgun", 11)
                    else: c.drawString(col_x+w_w, row_y, "____________________")

            for p in range(0, len(sel_list), 50):
                draw_layout(sel_list[p:p+50], False, (p//50)+1); c.showPage()
            for p in range(0, len(sel_list), 50):
                draw_layout(sel_list[p:p+50], True, (p//50)+1); c.showPage()
            
            c.save()
            for r in sel_list: st.session_state.df.loc[st.session_state.df['word'] == r['word'], 'count'] += 1
            save_data(st.session_state.df)
            st.download_button("📥 시험지 다운로드", buf.getvalue(), file_name="test.pdf")
