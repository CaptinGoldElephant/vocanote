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

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

stemmer = PorterStemmer()

# 어근 추출 도구 준비 
stemmer = PorterStemmer()
FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("Malgun",FONT_PATH))

    DB_FILE = "voca_db.csv"

#Deta Base
def load_data():
    if os.path.exists(DB_FILE):
        df = pd.read_csv(DB_FILE)
        # 'date' 컬럼이 없으면 새로 만들어줍니다.
        if 'date' not in df.columns:
            df['date'] = "2024-01-01" # 기존 데이터용 기본값
        return df
    else:
        return pd.DataFrame(columns=["word", "mean", "root", "count", "date"])
    
def save_data(df):
    df.to_csv(DB_FILE, index=False, encoding="utf-8-sig")


#화면 내용 시작
st.title("토익 단어장")

# 왼쪽 사이드바 메뉴 만들기
menu = st.sidebar.selectbox("메뉴를 선택하세요", ["단어 등록하기", "단어 목록 보기", "날짜별 단어 조회", "시험지 만들기"])

# 데이터를 불러옵니다
df = load_data()

# 단어 등록하기 화면
if menu == "단어 등록하기":
    st.header("➕ 새로운 단어 추가")
    # 입력창 만들기
    word = st.text_input("영어 단어를 입력하세요 ").strip().lower()
    mean = st.text_input("한글 뜻을 입력하세요 ").strip()
    
    if st.button("저장하기"):
        if word and mean:
            root = stemmer.stem(word)
            today = datetime.now().strftime("%Y-%m-%d") 

            if word in df['word'].values:
                st.warning("이미 등록된 단어입니다!")
            else:
                new_row = {"word": word, "mean": mean, "root": root, "count": 0, "date": today}
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(df)
                st.success(f"'{word}' 저장 완료! (등록일: {today})")
        else:
            st.error("단어와 뜻을 모두 입력해주세요.")

  
    st.divider() # 구분선
    st.subheader("📁 CSV 파일로 한꺼번에 등록하기")
    uploaded_file = st.file_uploader("CSV 파일을 선택하세요", type=["csv"])

    if uploaded_file is not None:
        try:
            # 1. 파일 읽기 시도
            try:
                user_csv = pd.read_csv(uploaded_file)
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                user_csv = pd.read_csv(uploaded_file, encoding='cp949') # 오타 수정

            # 2. 읽기에 성공한 후의 로직 (try/except 밖으로 빼야 함)
            st.write("불러온 파일 미리보기:")
            st.dataframe(user_csv.head())
            
            col_list = user_csv.columns.tolist()
            word_col = st.selectbox("단어(영어)가 들어있는 열을 선택하세요", col_list)
            mean_col = st.selectbox("뜻(한글)이 들어있는 열을 선택하세요", col_list)
            
            if st.button("내 단어장에 합치기"):
                temp_df = pd.DataFrame()
                temp_df['word'] = user_csv[word_col].astype(str).str.strip().str.lower()
                temp_df['mean'] = user_csv[mean_col].astype(str).str.strip()
                temp_df['root'] = temp_df['word'].apply(lambda x: stemmer.stem(str(x)))
                temp_df['count'] = 0
                temp_df['date'] = datetime.now().strftime("%Y-%m-%d")

                added_count = len(temp_df)
                
                # 기존 데이터 유지(keep='first')
                df = pd.concat([df, temp_df], ignore_index=True).drop_duplicates('word', keep='first')
                save_data(df)

                st.success(f"{added_count}개의 단어를 성공적으로 업로드했습니다!")
                st.toast(f'{added_count}개 단어 추가 완료!', icon='🚀')

                time.sleep(2) 
                st.rerun()
                
        except Exception as e:
            st.error(f"파일을 처리하는 중 오류가 발생했습니다: {e}")



# 2. 단어 목록 보기 및 관리
elif menu == "단어 목록 보기":
    st.header("📋 전체 단어 관리 및 검색")
    
    if len(df) > 0:
        search_query = st.text_input("🔍 찾으실 단어를 입력하세요 (영어)").strip().lower()
        filtered_df = df[df['word'].str.contains(search_query, na=False)].sort_values(by="word")

        if not filtered_df.empty:
            # 선택용 데이터프레임 구성
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
                key="word_editor_final"
            )

            # 체크된 단어들 추출
            selected_rows = edited_df[edited_df["선택"] == True]
            
            # --- 🚨 오류 방지 핵심 로직 ---
            selected_word = None
            if not selected_rows.empty:
                # 체크가 되었을 때만 indexer를 사용함
                selected_word = selected_rows.iloc[-1]["word"]

            if selected_word:
                st.divider()
                st.subheader(f"⚙️ '{selected_word}' 관리")
                
                word_idx = df[df['word'] == selected_word].index[0]
                current_mean = df.at[word_idx, 'mean']
                current_root = df.at[word_idx, 'root']
                
                col_edit1, col_edit2 = st.columns(2)
                with col_edit1:
                    new_mean = st.text_input("뜻 수정", value=current_mean, key=f"edit_mean_{selected_word}")
                with col_edit2:
                    new_root = st.text_input("어근 수정", value=current_root, key=f"edit_root_{selected_word}")
                
                btn_col1, btn_col2 = st.columns(2)
                # (수정/삭제 버튼 로직은 기존과 동일)
                with btn_col1:
                    if st.button("💾 수정 완료"):
                        st.session_state.confirm_update = True
                    if st.session_state.get('confirm_update'):
                        st.warning("정말 수정을 완료하시겠습니까?")
                        c_col1, c_col2 = st.columns(2)
                        if c_col1.button("예 (수정)"):
                            df.at[word_idx, 'mean'] = new_mean
                            df.at[word_idx, 'root'] = new_root
                            save_data(df)
                            st.success("✅ 수정 완료!")
                            st.session_state.pop('confirm_update', None)
                            time.sleep(1)
                            st.rerun()
                        if c_col2.button("아니오 (수정취소)"):
                            st.session_state.pop('confirm_update', None)
                            st.rerun()

                with btn_col2:
                    if st.button("🗑️ 단어 삭제"):
                        st.session_state.confirm_delete = True
                    if st.session_state.get('confirm_delete'):
                        st.error("🚨 정말 삭제하시겠습니까?")
                        d_col1, d_col2 = st.columns(2)
                        if d_col1.button("예 (삭제)"):
                            df = df.drop(word_idx)
                            save_data(df)
                            st.warning("🗑️ 삭제 완료!")
                            st.session_state.pop('confirm_delete', None)
                            time.sleep(1)
                            st.rerun()
                        if d_col2.button("아니오 (삭제취소)"):
                            st.session_state.pop('confirm_delete', None)
                            st.rerun()
            else:
                st.info("💡 위 표에서 수정하거나 삭제할 단어의 '선택' 칸을 체크해 주세요.")
        else:
            st.warning("🔍 검색 결과가 없습니다.")
    else:
        st.info("📥 저장된 단어가 없습니다. [단어 등록하기] 메뉴에서 먼저 단어를 추가해 주세요.")


# 날짜별 단어 조회 화면
elif menu == "날짜별 단어 조회":
    st.header("📅 날짜별 등록 현황")
    
    if len(df) > 0:
        # 등록된 날짜 목록 (최신순)
        all_dates = sorted(df['date'].unique(), reverse=True)
        target_date = st.selectbox("조회할 날짜를 선택하세요", all_dates)
        
        date_df = df[df['date'] == target_date]
        
        # 상단 레이아웃: 단어 개수와 공부하기 버튼 배치
        col_info, col_btn = st.columns([2, 1])
        
        with col_info:
            st.subheader(f"📍 {target_date} 등록 단어 ({len(date_df)}개)")
            
        with col_btn:
            # --- 오늘(선택된 날짜) 단어 공부하기 버튼 ---
            if st.button(f"오늘 등록한 단어 시험지"):
                if len(date_df) > 0:
                    # 해당 날짜 단어들로 PDF 생성 시작
                    test_words = date_df.sample(frac=1).to_dict('records') # 해당 날짜 단어 랜덤 섞기
                    
                    file_name = f"voca_test_{target_date}.pdf"
                    c = canvas.Canvas(file_name, pagesize=A4)
                    width, height = A4

                    # 기존에 만든 최적화된 레이아웃 함수 재사용 (필요시 내부 정의)
                    def draw_instant_page(page_words, is_answer_key=False, page_num=1):
                        c.setFont("Malgun", 22)
                        title = f"Test: {target_date}" if not is_answer_key else f"Answer: {target_date}"
                        c.drawString(50, height - 50, title)
                        c.setFont("Malgun", 11)
                        c.drawRightString(width - 50, height - 48, f"Name: ________________  (Page {page_num})")
                        c.line(45, height - 62, width - 45, height - 62)

                        x_left, x_right = 50, 310
                        y_start, y_gap = height - 95, 28.5

                        for i, row in enumerate(page_words):
                            col_x = x_left if i < 25 else x_right
                            row_y = y_start - ((i % 25) * y_gap)
                            
                            c.setFillColorRGB(0, 0, 0)
                            word_text = f"{i + 1}. {row['word']} : "
                            c.drawString(col_x, row_y, word_text)
                            word_width = c.stringWidth(word_text, "Malgun", 11)
                            
                            if is_answer_key:
                                c.setFillColorRGB(0.8, 0, 0) # 빨간색 정답
                                mean_text = str(row['mean'])
                                if c.stringWidth(mean_text, "Malgun", 10) > 230:
                                    c.setFont("Malgun", 8.5)
                                else:
                                    c.setFont("Malgun", 10)
                                c.drawString(col_x + word_width, row_y, mean_text)
                                c.setFont("Malgun", 11) # 폰트 복구
                            else:
                                c.setFillColorRGB(0, 0, 0)
                                c.drawString(col_x + word_width, row_y, "____________________")

                    # 페이지 생성 (50개 단위)
                    for p in range(0, len(test_words), 50):
                        draw_instant_page(test_words[p:p+50], False, (p//50)+1)
                        c.showPage()
                    for p in range(0, len(test_words), 50):
                        draw_instant_page(test_words[p:p+50], True, (p//50)+1)
                        c.showPage()
                    
                    c.save()
                    
                    # 다운로드 버튼 표시
                    with open(file_name, "rb") as f:
                        st.download_button(f"📥 {target_date} 시험지 다운로드", f, file_name=file_name)
                    st.success(f"오늘 배운 {len(test_words)}개의 단어로 시험지를 만들었습니다!")
                else:
                    st.error("해당 날짜에 등록된 단어가 없습니다.")
        
        st.divider()
        st.table(date_df[['word', 'mean']].sort_values(by="word"))
    else:
        st.info("저장된 단어가 없습니다.")



# 시험지 만들기 화면
elif menu == "시험지 만들기":
    st.header("🖨️ PDF 시험지 생성 ")
    
    if len(df) < 1:
        st.write("시험을 보려면 먼저 단어를 등록해 주세요.")
    else:
        test_count = st.number_input("문제 개수 설정", min_value=1, max_value=len(df), value=min(50, len(df)))
        
        if st.button("랜덤 시험지 생성"):
            selected_words = []
            selected_roots = set()
            
            # 가중치 기반 랜덤 선택
            temp_df = df.copy()
            
            # 1. 가중치(Weight) 계산: 출제 횟수가 적을수록 뽑힐 확률이 높아집니다.
            # (count + 1)로 나누어 count가 0인 단어가 가장 높은 가중치를 갖게 합니다.
            temp_df['weight'] = 1 / (temp_df['count'] + 1)
            
            # 2. 전체 단어를 가중치에 따라 무작위로 섞습니다. (복원 추출 X)
            # weights 매개변수를 쓰면 가중치가 높은 행이 위로 올라올 확률이 큽니다.
            shuffled_df = temp_df.sample(frac=1, weights='weight').reset_index(drop=True)

            selected_words = []
            selected_roots = set()

            # 3. 섞인 순서대로 어근 중복을 피하며 필요한 개수만큼 뽑습니다.
            for _, row in shuffled_df.iterrows():
                if len(selected_words) >= test_count:
                    break
                if row['root'] not in selected_roots:
                    selected_words.append(row)
                    selected_roots.add(row['root'])
            
            # 4. 최종 선택된 리스트를 다시 한번 랜덤하게 섞어 순서를 흩트립니다.
            random.shuffle(selected_words)
            
            file_name = "voca_test.pdf"
            c = canvas.Canvas(file_name, pagesize=A4)
            width, height = A4

            def draw_page_layout(page_words, is_answer_key=False, page_num=1):
                # 제목 및 이름 칸 (최상단 배치)
                c.setFont("Malgun", 22)
                title = "Vocabulary Test" if not is_answer_key else "Answer Key"
                c.drawString(50, height - 50, title)
                
                c.setFont("Malgun", 11)
                c.drawRightString(width - 50, height - 48, f"Name: ________________  (Page {page_num})")
                c.line(45, height - 62, width - 45, height - 62)

                # 레이아웃 설정 (여백 최소화 및 줄 간격 확대)
                x_left = 50
                x_right = 310 # 오른쪽 열 시작 위치
                y_start = height - 95
                y_gap = 28.5  # 하단 여백을 줄이기 위해 간격을 더 넓힘 (26 -> 28.5)

                for i, row in enumerate(page_words):
                    col_x = x_left if i < 25 else x_right
                    row_y = y_start - ((i % 25) * y_gap)
                    global_idx = (page_num - 1) * 50 + i + 1
                    
                    # 1. 문제 번호와 영어 단어 (검정색)
                    c.setFillColorRGB(0, 0, 0)
                    word_text = f"{global_idx}. {row['word']} : "
                    c.drawString(col_x, row_y, word_text)
                    
                    # 단어 텍스트 길이 계산 (뜻이 시작될 위치)
                    word_width = c.stringWidth(word_text, "Malgun", 11)
                    
                    if is_answer_key:
                        # 2. 한국어 뜻 (빨간색)
                        c.setFillColorRGB(0.8, 0, 0) # 진한 빨강
                        mean_text = str(row['mean'])
                        
                        # 뜻이 너무 길어 옆 칸을 침범하는지 체크 (최대 너비 제한)
                        max_mean_width = 230 # 한 열의 최대 허용 너비
                        actual_width = c.stringWidth(mean_text, "Malgun", 10)
                        
                        if actual_width > max_mean_width:
                            # 뜻이 길면 글자 크기를 줄여서 한 줄에 맞춤
                            c.setFont("Malgun", 8.5)
                        else:
                            c.setFont("Malgun", 10)
                            
                        c.drawString(col_x + word_width, row_y, mean_text)
                    else:
                        # 시험지용 밑줄
                        c.drawString(col_x + word_width, row_y, "____________________")

            # 시험지 및 정답지 생성 (50개 단위)
            for p in range(0, len(selected_words), 50):
                draw_page_layout(selected_words[p:p+50], False, (p//50)+1)
                c.showPage()
            for p in range(0, len(selected_words), 50):
                draw_page_layout(selected_words[p:p+50], True, (p//50)+1)
                c.showPage()
            
            c.save()
            
            # DB 업데이트 및 다운로드 버튼 (기존 코드와 동일)
            for row in selected_words:
                df.loc[df['word'] == row['word'], 'count'] += 1
            save_data(df)
            
            with open(file_name, "rb") as f:
                st.download_button("📥 최적화된 시험지 다운로드", f, file_name=file_name)
