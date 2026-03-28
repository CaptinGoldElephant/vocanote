import streamlit as st
import pandas as pd
import random
import os
import time
import nltk
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from nltk.stem import PorterStemmer

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

# --- 2. 데이터 관리 함수 ---
def load_data():
    if os.path.exists(DB_FILE):
        try:
            # utf-8-sig로 읽어보고 에러나면 cp949로 시도
            try:
                df = pd.read_csv(DB_FILE)
            except:
                df = pd.read_csv(DB_FILE, encoding='cp949')
            
            if 'date' not in df.columns:
                df['date'] = datetime.now().strftime("%Y-%m-%d")
            return df
        except:
            return pd.DataFrame(columns=["word", "mean", "root", "count", "date"])
    else:
        return pd.DataFrame(columns=["word", "mean", "root", "count", "date"])

def save_data(df):
    df.to_csv(DB_FILE, index=False, encoding="utf-8-sig")

# --- 3. 앱 메인 로직 ---
st.set_page_config(page_title="나만의 단어장", layout="wide")
st.title("📚 스마트 토익 단어장")

df = load_data()

menu = st.sidebar.selectbox("메뉴를 선택하세요", ["단어 등록하기", "단어 목록 보기", "시험지 만들기"])

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
                new_data = pd.DataFrame([[word, mean, root, 0, datetime.now().strftime("%Y-%m-%d")]], 
                                        columns=["word", "mean", "root", "count", "date"])
                
                # keep='first' 적용 (기존 단어 유지)
                df = pd.concat([df, new_data], ignore_index=True).drop_duplicates('word', keep='first')
                save_data(df)
                st.success(f"'{word}' 등록 완료!")
                st.rerun()

    with tab2:
        uploaded_file = st.file_uploader("CSV 파일을 선택하세요", type=['csv'])
        if uploaded_file is not None:
            try:
                try:
                    user_csv = pd.read_csv(uploaded_file)
                except UnicodeDecodeError:
                    uploaded_file.seek(0)
                    user_csv = pd.read_csv(uploaded_file, encoding='cp949')
                
                st.write("불러온 파일 미리보기:")
                st.dataframe(user_csv.head())
                
                col_list = user_csv.columns.tolist()
                word_col = st.selectbox("단어(영어) 열 선택", col_list)
                mean_col = st.selectbox("뜻(한글) 열 선택", col_list)
                
                if st.button("내 단어장에 합치기"):
                    temp_df = pd.DataFrame()
                    temp_df['word'] = user_csv[word_col].astype(str).str.strip().str.lower()
                    temp_df['mean'] = user_csv[mean_col].astype(str).str.strip()
                    temp_df['root'] = temp_df['word'].apply(lambda x: stemmer.stem(str(x)))
                    temp_df['count'] = 0
                    temp_df['date'] = datetime.now().strftime("%Y-%m-%d")
                    
                    added_count = len(temp_df)
                    df = pd.concat([df, temp_df], ignore_index=True).drop_duplicates('word', keep='first')
                    save_data(df)
                    st.success(f"{added_count}개의 단어 처리 완료! (중복 제외)")
                    time.sleep(1)
                    st.rerun()
            except Exception as e:
                st.error(f"파일 처리 오류: {e}")

# --- 메뉴 2: 단어 목록 보기 (수정/삭제 포함) ---
elif menu == "단어 목록 보기":
    st.header("📋 전체 단어 관리 및 검색")
    
    if df is None or len(df) == 0:
        st.info("등록된 단어가 없습니다. 먼저 단어를 추가해 주세요.")
    else:
        search_query = st.text_input("🔍 찾으실 단어를 입력하세요 (영어)").strip().lower()
        filtered_df = df[df['word'].str.contains(search_query, na=False)].sort_values(by="word")

        if not filtered_df.empty:
            display_df = filtered_df.copy()
            display_df.insert(0, "선택", False)
            
            edited_df = st.data_editor(
                display_df,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "선택": st.column_config.CheckboxColumn(required=True, width="small"),
                    "word": "단어", "mean": "뜻", "root": "어근", "count": "출제수", "date": "등록일"
                },
                disabled=["word", "mean", "root", "count", "date"],
                key="voca_editor"
            )

            selected_rows = edited_df[edited_df["선택"] == True]
            
            if not selected_rows.empty:
                selected_word = selected_rows.iloc[-1]["word"]
                st.divider()
                st.subheader(f"⚙️ '{selected_word}' 관리")
                
                word_idx = df[df['word'] == selected_word].index[0]
                c_mean = df.at[word_idx, 'mean']
                c_root = df.at[word_idx, 'root']
                
                col1, col2 = st.columns(2)
                with col1:
                    new_mean = st.text_input("뜻 수정", value=c_mean, key=f"m_{selected_word}")
                with col2:
                    new_root = st.text_input("어근 수정", value=c_root, key=f"r_{selected_word}")
                
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("💾 수정 완료"):
                        df.at[word_idx, 'mean'] = new_mean
                        df.at[word_idx, 'root'] = new_root
                        save_data(df)
                        st.success("수정 완료!")
                        time.sleep(1)
                        st.rerun()
                with b2:
                    if st.button("🗑️ 단어 삭제"):
                        df = df.drop(word_idx)
                        save_data(df)
                        st.warning("삭제 완료!")
                        time.sleep(1)
                        st.rerun()
            else:
                st.info("💡 표에서 수정할 단어의 '선택' 칸을 체크해 주세요.")
        else:
            st.warning("검색 결과가 없습니다.")

# --- 메뉴 3: 시험지 만들기 ---
elif menu == "시험지 만들기":
    st.header("📄 PDF 시험지 생성")
    
    if len(df) < 5:
        st.error("단어가 최소 5개 이상 필요합니다.")
    else:
        test_type = st.radio("시험 범위 선택", ["전체 랜덤", "오늘 등록한 단어만"])
        
        if test_type == "오늘 등록한 단어만":
            today_str = datetime.now().strftime("%Y-%m-%d")
            candidates = df[df['date'] == today_str]
        else:
            candidates = df

        if candidates.empty:
            st.warning("해당하는 단어가 없습니다.")
        else:
            num_words = st.number_input("문제 수", min_value=5, max_value=len(candidates), value=min(20, len(candidates)))
            
            if st.button("시험지 PDF 생성"):
                # 1. 단어 선택 로직 (출제 횟수 적은 순 가중치 + 어근 중복 방지)
                candidates = candidates.sort_values(by='count')
                selected_words = []
                used_roots = set()
                
                for _, row in candidates.iterrows():
                    if len(selected_words) >= num_words: break
                    if row['root'] not in used_roots:
                        selected_words.append(row)
                        used_roots.add(row['root'])
                
                # 부족하면 어근 상관없이 추가
                if len(selected_words) < num_words:
                    remaining = candidates[~candidates['word'].isin([w['word'] for w in selected_words])]
                    for _, row in remaining.head(num_words - len(selected_words)).iterrows():
                        selected_words.append(row)

                # PDF 생성
                import io
                buf = io.BytesIO()
                c = canvas.Canvas(buf, pagesize=A4)
                
                def draw_page(word_list, is_answer):
                    c.setFont("Malgun", 16)
                    title = "영단어 정답지" if is_answer else "영단어 시험지"
                    c.drawCentredString(300, 800, title)
                    c.setFont("Malgun", 10)
                    y = 750
                    for i, row in enumerate(word_list):
                        text = f"{i+1}. {row['word']} : {row['mean'] if is_answer else '__________'}"
                        c.drawString(100, y, text)
                        y -= 25
                        if y < 50: break

                draw_page(selected_words, False)
                c.showPage()
                draw_page(selected_words, True)
                c.save()
                
                # 출제 횟수 업데이트
                for row in selected_words:
                    df.loc[df['word'] == row['word'], 'count'] += 1
                save_data(df)
                
                st.download_button("PDF 다운로드", buf.getvalue(), "voca_test.pdf", "application/pdf")
                st.success("시험지가 생성되었습니다!")
