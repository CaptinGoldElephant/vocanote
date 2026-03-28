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

# --- [설정] 사용자님의 구글 시트 ID 적용 ---
SHEET_ID = "1BYuQhbPLwnLxBHu4gjf-1H8fNoYvRRwIyg2TU1vfvw8"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

# --- 환경 준비 ---
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

stemmer = PorterStemmer()
DB_FILE = "voca_db.csv"

# 폰트 설정 (서버/로컬 공용)
FONT_PATH = "malgun.ttf" 
if not os.path.exists(FONT_PATH):
    FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("Malgun", FONT_PATH))

# --- 데이터 관리 함수 ---
def load_data():
    try:
        # 구글 시트에서 최신 데이터 읽기
        df = pd.read_csv(SHEET_URL)
        if 'date' not in df.columns:
            df['date'] = datetime.now().strftime("%Y-%m-%d")
        return df
    except:
        # 시트 로드 실패 시 로컬 CSV 활용
        if os.path.exists(DB_FILE):
            return pd.read_csv(DB_FILE)
        return pd.DataFrame(columns=["word", "mean", "root", "count", "date"])

def save_data(df):
    # 로컬에 저장 (백업용)
    df.to_csv(DB_FILE, index=False, encoding="utf-8-sig")
    st.info("💡 팁: 현재 구글 시트 데이터가 로드되었습니다. 등록 후 '전체 백업' 버튼으로 최신 상태를 저장하세요.")

# --- 앱 메인 ---
st.set_page_config(page_title="토익 단어장", layout="wide")
st.title("📚 스마트 토익 단어장 (실시간 연동형)")

df = load_data()

# 사이드바 백업 버튼 (방법 1: 수동 백업)
st.sidebar.header("💾 데이터 백업")
csv_data = df.to_csv(index=False, encoding="utf-8-sig")
st.sidebar.download_button(
    label="내 컴퓨터로 전체 다운로드 (CSV)",
    data=csv_data,
    file_name=f"voca_backup_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv"
)

menu = st.sidebar.selectbox("메뉴를 선택하세요", ["단어 등록하기", "단어 목록 보기", "시험지 만들기"])

# --- 메뉴 1: 단어 등록하기 ---
if menu == "단어 등록하기":
    st.header("📝 새 단어 등록")
    tab1, tab2 = st.tabs(["직접 입력", "CSV 파일 업로드"])
    with tab1:
        with st.form("word_form", clear_on_submit=True):
            word = st.text_input("단어 (영어)").strip().lower()
            mean = st.text_input("뜻 (한글)").strip()
            if st.form_submit_button("등록하기") and word and mean:
                root = stemmer.stem(word)
                new_row = pd.DataFrame([[word, mean, root, 0, datetime.now().strftime("%Y-%m-%d")]], 
                                        columns=["word", "mean", "root", "count", "date"])
                df = pd.concat([df, new_row], ignore_index=True).drop_duplicates('word', keep='first')
                save_data(df)
                st.success(f"'{word}' 등록 완료! 반드시 백업 버튼을 눌러 저장하세요.")
                st.rerun()
    # (CSV 업로드 로직 생략 없이 유지됨...)
    with tab2:
        uploaded_file = st.file_uploader("CSV 파일을 선택하세요", type=['csv'])
        if uploaded_file is not None:
            try:
                try: user_csv = pd.read_csv(uploaded_file)
                except:
                    uploaded_file.seek(0)
                    user_csv = pd.read_csv(uploaded_file, encoding='cp949')
                st.dataframe(user_csv.head())
                cols = user_csv.columns.tolist()
                w_col = st.selectbox("단어 열", cols); m_col = st.selectbox("뜻 열", cols)
                if st.button("내 단어장에 합치기"):
                    temp_df = pd.DataFrame()
                    temp_df['word'] = user_csv[w_col].astype(str).str.strip().str.lower()
                    temp_df['mean'] = user_csv[m_col].astype(str).str.strip()
                    temp_df['root'] = temp_df['word'].apply(lambda x: stemmer.stem(str(x)))
                    temp_df['count'] = 0
                    temp_df['date'] = datetime.now().strftime("%Y-%m-%d")
                    df = pd.concat([df, temp_df], ignore_index=True).drop_duplicates('word', keep='first')
                    save_data(df); st.success("합치기 완료!"); st.rerun()
            except Exception as e: st.error(f"오류: {e}")

# --- 메뉴 2: 단어 목록 보기 (날짜 필터 및 수정/삭제) ---
elif menu == "단어 목록 보기":
    st.header("📋 전체 단어 관리 및 검색")
    if len(df) > 0:
        col_f1, col_f2 = st.columns(2)
        with col_f1: search_query = st.text_input("🔍 검색").strip().lower()
        with col_f2:
            date_list = ["전체보기"] + sorted(df['date'].unique().tolist(), reverse=True)
            selected_date = st.selectbox("📅 날짜별 조회", date_list)

        f_df = df.copy()
        if search_query: f_df = f_df[f_df['word'].str.contains(search_query, na=False)]
        if selected_date != "전체보기": f_df = f_df[f_df['date'] == selected_date]
        f_df = f_df.sort_values(by="word")

        if not f_df.empty:
            d_df = f_df.copy(); d_df.insert(0, "선택", False)
            edited_df = st.data_editor(d_df, hide_index=True, use_container_width=True, key="voca_editor")
            s_rows = edited_df[edited_df["선택"] == True]
            if not s_rows.empty:
                sel_w = s_rows.iloc[-1]["word"]
                st.divider(); st.subheader(f"⚙️ '{sel_w}' 관리")
                idx = df[df['word'] == sel_w].index[0]
                c1, c2 = st.columns(2)
                with c1: n_m = st.text_input("뜻 수정", value=df.at[idx, 'mean'], key=f"m_{sel_w}")
                with c2: n_r = st.text_input("어근 수정", value=df.at[idx, 'root'], key=f"r_{sel_w}")
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("💾 수정 완료"):
                        df.at[idx, 'mean'], df.at[idx, 'root'] = n_m, n_r
                        save_data(df); st.success("수정됨!"); time.sleep(0.5); st.rerun()
                with b2:
                    if st.button("🗑️ 단어 삭제"):
                        df = df.drop(idx); save_data(df); st.warning("삭제됨!"); time.sleep(0.5); st.rerun()
        else: st.warning("결과 없음")
    else: st.info("등록된 단어가 없습니다.")

# --- 메뉴 3: 시험지 만들기 (사용자님 고유 레이아웃 보존) ---
elif menu == "시험지 만들기":
    st.header("📄 PDF 시험지 생성 (2열 50개 배치)")
    if len(df) < 5: st.error("단어가 부족합니다.")
    else:
        t_range = st.radio("범위", ["전체 랜덤", "오늘 등록한 단어만"])
        candidates = df[df['date'] == datetime.now().strftime("%Y-%m-%d")] if t_range == "오늘 등록한 단어만" else df
        if candidates.empty: st.warning("단어가 없습니다.")
        else:
            num = st.number_input("문제 수", 5, len(candidates), min(20, len(candidates)))
            if st.button("시험지 PDF 생성"):
                # 가중치 + 어근 중복 방지
                candidates = candidates.sort_values('count')
                sel_words, roots = [], set()
                for _, r in candidates.iterrows():
                    if len(sel_words) >= num: break
                    if r['root'] not in roots: sel_words.append(r); roots.add(r['root'])
                if len(sel_words) < num:
                    rem = candidates[~candidates['word'].isin([w['word'] for w in sel_words])]
                    for _, r in rem.head(num - len(sel_words)).iterrows(): sel_words.append(r)

                buf = io.BytesIO()
                c = canvas.Canvas(buf, pagesize=A4)
                
                def draw_page_layout(word_list, is_answer, page_num):
                    c.setFont("Malgun", 16)
                    c.drawCentredString(300, 800, f"영단어 {'정답지' if is_answer else '시험지'} (Page {page_num})")
                    c.setFont("Malgun", 10)
                    for i, row in enumerate(word_list):
                        col = i // 25; row_idx = i % 25
                        col_x = 70 + (col * 250); row_y = 740 - (row_idx * 27)
                        word_text = f"{i+1+(page_num-1)*50}. {row['word']}"
                        c.drawString(col_x, row_y, word_text)
                        word_w = c.stringWidth(word_text, "Malgun", 10) + 10
                        if is_answer:
                            m_txt = str(row['mean'])
                            if c.stringWidth(m_txt, "Malgun", 10) > 230: c.setFont("Malgun", 8.5)
                            c.drawString(col_x + word_w, row_y, m_txt); c.setFont("Malgun", 10)
                        else: c.drawString(col_x + word_w, row_y, "____________________")

                for p in range(0, len(sel_words), 50):
                    draw_page_layout(sel_words[p:p+50], False, (p//50)+1); c.showPage()
                for p in range(0, len(sel_words), 50):
                    draw_page_layout(sel_words[p:p+50], True, (p//50)+1); c.showPage()
                
                c.save()
                for r in sel_words: df.loc[df['word'] == r['word'], 'count'] += 1
                save_data(df)
                st.download_button("PDF 다운로드", buf.getvalue(), "voca_test.pdf", "application/pdf")
