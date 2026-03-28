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

SHEET_ID = "1BYuQhbPLwnLxBHu4gjf-1H8fNoYvRRwIyg2TU1vfvw8" 
SHEET_URL = f"https://docs.google.com/spreadsheets/d/1BYuQhbPLwnLxBHu4gjf-1H8fNoYvRRwIyg2TU1vfvw8/gviz/tq?tqx=out:csv"

# --- 1. 배포 및 실행 환경 준비 ---
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

stemmer = PorterStemmer()
DB_FILE = "voca_db.csv"

# 폰트 설정 (서버의 malgun.ttf 또는 로컬 윈도우 폰트 대응)
FONT_PATH = "malgun.ttf" 
if not os.path.exists(FONT_PATH):
    FONT_PATH = "C:/Windows/Fonts/malgun.ttf"

if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("Malgun", FONT_PATH))

def load_data():
    try:
        # 1순위: 구글 시트에서 읽어오기
        df = pd.read_csv(SHEET_URL)
        return df
    except:
        # 2순위: 구글 시트 실패 시 로컬 CSV 또는 빈 데이터
        if os.path.exists(DB_FILE):
            return pd.read_csv(DB_FILE)
        return pd.DataFrame(columns=["word", "mean", "root", "count", "date"])

def save_data(df):
    # 로컬 서버에 임시 저장 (백업용)
    df.to_csv(DB_FILE, index=False, encoding="utf-8-sig")
    st.info("💡 팁: 구글 시트 자동 저장은 현재 읽기 전용으로 설정되었습니다. 직접 시트에 입력하거나 아래 백업 버튼을 활용하세요.")

# --- 앱 메인 ---
st.set_page_config(page_title="토익 단어장", layout="wide")
st.title("토익 단어장")

df = load_data()

# 사이드바 메뉴 및 백업 버튼 (방법 1)
st.sidebar.header("💾 데이터 관리")
csv_data = df.to_csv(index=False, encoding="utf-8-sig")
st.sidebar.download_button(
    label="내 컴퓨터로 전체 백업 (CSV)",
    data=csv_data,
    file_name=f"voca_backup_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv"
)

menu = st.sidebar.selectbox("메뉴 선택", ["단어 등록하기", "단어 목록 보기", "시험지 만들기"])

# --- 메뉴 1: 단어 등록하기 ---
if menu == "단어 등록하기":
    st.header("📝 새 단어 등록")
    tab1, tab2 = st.tabs(["직접 입력", "CSV 파일 업로드"])
    
    with tab1:
        with st.form("word_form", clear_on_submit=True):
            word = st.text_input("단어 (영어)").strip().lower()
            mean = st.text_input("뜻 (한글)").strip()
            submitted = st.form_submit_button("등록하기")
            if submitted and word and mean:
                root = stemmer.stem(word)
                new_row = pd.DataFrame([[word, mean, root, 0, datetime.now().strftime("%Y-%m-%d")]], 
                                        columns=["word", "mean", "root", "count", "date"])
                df = pd.concat([df, new_row], ignore_index=True).drop_duplicates('word', keep='first')
                save_data(df)
                st.success(f"'{word}' 등록 완료!")
                st.rerun()

    with tab2:
        uploaded_file = st.file_uploader("CSV 파일을 선택하세요", type=['csv'])
        if uploaded_file is not None:
            try:
                try:
                    user_csv = pd.read_csv(uploaded_file)
                except:
                    uploaded_file.seek(0)
                    user_csv = pd.read_csv(uploaded_file, encoding='cp949')
                st.dataframe(user_csv.head())
                cols = user_csv.columns.tolist()
                w_col = st.selectbox("단어 열", cols)
                m_col = st.selectbox("뜻 열", cols)
                if st.button("내 단어장에 합치기"):
                    temp_df = pd.DataFrame()
                    temp_df['word'] = user_csv[w_col].astype(str).str.strip().str.lower()
                    temp_df['mean'] = user_csv[m_col].astype(str).str.strip()
                    temp_df['root'] = temp_df['word'].apply(lambda x: stemmer.stem(str(x)))
                    temp_df['count'] = 0
                    temp_df['date'] = datetime.now().strftime("%Y-%m-%d")
                    df = pd.concat([df, temp_df], ignore_index=True).drop_duplicates('word', keep='first')
                    save_data(df)
                    st.success("업로드 완료!")
                    st.rerun()
            except Exception as e:
                st.error(f"오류: {e}")

# --- 메뉴 2: 단어 목록 보기 (날짜 필터 추가) ---
elif menu == "단어 목록 보기":
    st.header("📋 전체 단어 관리 및 검색")
    if len(df) > 0:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            search_query = st.text_input("🔍 단어 검색 (영어)").strip().lower()
        with col_f2:
            # 날짜별 조회 기능 추가
            date_list = ["전체보기"] + sorted(df['date'].unique().tolist(), reverse=True)
            selected_date = st.selectbox("📅 날짜별 조회", date_list)

        # 필터링 적용
        filtered_df = df.copy()
        if search_query:
            filtered_df = filtered_df[filtered_df['word'].str.contains(search_query, na=False)]
        if selected_date != "전체보기":
            filtered_df = filtered_df[filtered_df['date'] == selected_date]
        
        filtered_df = filtered_df.sort_values(by="word")

        if not filtered_df.empty:
            display_df = filtered_df.copy()
            display_df.insert(0, "선택", False)
            edited_df = st.data_editor(
                display_df, hide_index=True, use_container_width=True,
                column_config={"선택": st.column_config.CheckboxColumn(required=True, width="small")},
                disabled=["word", "mean", "root", "count", "date"], key="editor_final"
            )
            
            selected_rows = edited_df[edited_df["선택"] == True]
            if not selected_rows.empty:
                sel_word = selected_rows.iloc[-1]["word"]
                st.divider()
                st.subheader(f"⚙️ '{sel_word}' 관리")
                idx = df[df['word'] == sel_word].index[0]
                
                c1, c2 = st.columns(2)
                with c1: new_m = st.text_input("뜻 수정", value=df.at[idx, 'mean'], key=f"m_{sel_word}")
                with c2: new_r = st.text_input("어근 수정", value=df.at[idx, 'root'], key=f"r_{sel_word}")
                
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("💾 수정 완료"):
                        df.at[idx, 'mean'], df.at[idx, 'root'] = new_m, new_r
                        save_data(df); st.success("수정됨!"); time.sleep(0.5); st.rerun()
                with b2:
                    if st.button("🗑️ 단어 삭제"):
                        df = df.drop(idx); save_data(df); st.warning("삭제됨!"); time.sleep(0.5); st.rerun()
        else:
            st.warning("결과가 없습니다.")
    else:
        st.info("단어를 먼저 등록해 주세요.")

# --- 메뉴 3: 시험지 만들기 ---
elif menu == "시험지 만들기":
    st.header("📄 PDF 시험지 생성")
    if len(df) < 5:
        st.error("단어가 부족합니다.")
    else:
        test_range = st.radio("범위", ["전체 랜덤", "오늘 등록한 단어만"])
        candidates = df[df['date'] == datetime.now().strftime("%Y-%m-%d")] if test_range == "오늘 등록한 단어만" else df
        
        if candidates.empty:
            st.warning("단어가 없습니다.")
        else:
            num = st.number_input("문제 수", 5, len(candidates), min(20, len(candidates)))
            if st.button("시험지 PDF 생성"):
                # 출제 로직: 가중치(count) + 어근 중복 방지
                candidates = candidates.sort_values('count')
                sel_list, roots = [], set()
                for _, r in candidates.iterrows():
                    if len(sel_list) >= num: break
                    if r['root'] not in roots:
                        sel_list.append(r); roots.add(r['root'])
                if len(sel_list) < num:
                    rem = candidates[~candidates['word'].isin([w['word'] for w in sel_list])]
                    for _, r in rem.head(num - len(sel_list)).iterrows(): sel_list.append(r)
                
                buf = io.BytesIO()
                c = canvas.Canvas(buf, pagesize=A4)
                def draw(words, ans):
                    c.setFont("Malgun", 16); c.drawCentredString(300, 800, "정답지" if ans else "시험지")
                    c.setFont("Malgun", 10); y = 750
                    for i, r in enumerate(words):
                        c.drawString(100, y, f"{i+1}. {r['word']} : {r['mean'] if ans else '__________'}")
                        y -= 25
                draw(sel_list, False); c.showPage(); draw(sel_list, True); c.save()
                for r in sel_list: df.loc[df['word'] == r['word'], 'count'] += 1
                save_data(df)
                st.download_button("PDF 다운로드", buf.getvalue(), "test.pdf", "application/pdf")
