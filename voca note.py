import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import random
import os
import time
import math
import nltk
import io
import json
from datetime import datetime, timedelta, timezone
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from nltk.stem import PorterStemmer

# 1. 환경 및 시간설정
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

stemmer = PorterStemmer()

def get_today_kst():
    kst = timezone(timedelta(hours=9))
    return datetime.now(kst).strftime("%Y-%m-%d")

FONT_PATH = "malgun.ttf" 
if not os.path.exists(FONT_PATH):
    FONT_PATH = "C:/Windows/Fonts/malgun.ttf"
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("Malgun", FONT_PATH))

# --- 2. 구글 시트 연결 및 데이터 로직 ---
def get_gspread_client():
    key_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    creds = Credentials.from_service_account_info(
        key_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

def sync_data():
    try:
        client = get_gspread_client()
        sh = client.open_by_key("1BYuQhbPLwnLxBHu4gjf-1H8fNoYvRRwIyg2TU1vfvw8")
        worksheet = sh.get_worksheet(0)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        for col in ["word", "mean", "root", "count", "wrong_count", "date"]:
            if col not in df.columns: 
                df[col] = 0 if col in ["count", "wrong_count"] else ""
        return worksheet, df
    except Exception as e:
        st.error(f"연결 실패: {e}")
        return None, pd.DataFrame(columns=["word", "mean", "root", "count", "wrong_count", "date"])

def select_test_words(df, num):
    try:
        # --- [1단계] 유예 로직 (어제오늘 오답은 추출 대상에서 아예 제외) ---
        client = get_gspread_client()
        sh = client.open_by_key("1BYuQhbPLwnLxBHu4gjf-1H8fNoYvRRwIyg2TU1vfvw8")
        history_ws = sh.worksheet("Last_Test")
        history_data = history_ws.get_all_records()
        
        excluded_words = set()
        now = datetime.now(timezone(timedelta(hours=9)))
        
        for record in history_data:
            w_val = str(record.get('wrong_words', '')).strip()
            if w_val and w_val != "None" and w_val != "0":
                # 날짜 파싱 (yyyy-mm-dd)
                test_date_str = record['date'].split(' ')[0]
                test_date = datetime.strptime(test_date_str, "%Y-%m-%d").replace(tzinfo=timezone(timedelta(hours=9)))
                
                # 오늘(0)과 어제(1) 기록된 오답 제외
                diff = (now - test_date).days
                if 0 <= diff <= 1:
                    words_to_exclude = [w.strip() for w in w_val.split(",") if w.strip()]
                    excluded_words.update(words_to_exclude)
        
        # 유예 기간 단어들을 필터링한 데이터프레임 생성
        df_filtered = df[~df['word'].isin(excluded_words)].copy()

        # --- [2단계] 가중치(확률) 계산 함수 정의 ---
        def calculate_weight(row):
            cnt = int(row['count'])
            wrg = int(row['wrong_count'])
            
            # 1순위: 새 단어 (기준 가중치 100)
            if cnt == 0:
                return 100.0
            
            # 2순위: 오답 단어 (많이 틀릴수록 가중치가 완만하게 상승하여 100에 근접)
            # 로그 함수를 사용하여 지수 함수처럼 너무 튀지 않게 조절함
            if wrg > 0:
                # 1번 틀림: 약 50점 / 3번 틀림: 약 80점 / 7번 틀림: 약 110점(새 단어 추월 시작)
                return 20.0 + (30.0 * math.log2(wrg + 1))
            
            # 3순위: 이미 아는 단어 (최하위 가중치 1)
            return 1.0

        df_filtered['weight'] = df_filtered.apply(calculate_weight, axis=1)

        # --- [3단계] 가중치 기반 비복원 추출 (중복 없이 뽑기) ---
        candidates = df_filtered.to_dict('records')
        selected_list = []
        used_roots = set()

        # 뽑을 개수만큼 반복하거나 후보가 떨어질 때까지 반복
        while len(selected_list) < num and candidates:
            # 현재 후보들의 가중치 리스트 추출
            weights = [c['weight'] for c in candidates]
            
            # 가중치에 따라 1개 무작위 추첨
            picked = random.choices(candidates, weights=weights, k=1)[0]
            
            # 어근 중복 방지 로직
            root = str(picked.get('root', ''))
            if root not in used_roots:
                selected_list.append(picked)
                used_roots.add(root)
            
            # 뽑힌 단어는 성공 여부와 상관없이 후보에서 제거 (무한 루프 방지)
            candidates.remove(picked)

        # 자리가 남을 경우(어근 중복 등으로 인해) 부족한 만큼 아무나 추가 채우기
        if len(selected_list) < num:
            current_words = [w['word'] for w in selected_list]
            remaining = [c for c in df_filtered.to_dict('records') if c['word'] not in current_words]
            needed = num - len(selected_list)
            selected_list.extend(random.sample(remaining, min(needed, len(remaining))))

        # 최종 시험지는 다시 한번 셔플하여 순서 랜덤화
        random.shuffle(selected_list)
        return selected_list

    except Exception as e:
        # 오류 발생 시 안전하게 기본 샘플링으로 대체
        import streamlit as st
        st.error(f"알고리즘 오류 발생: {e}")
        return df.sample(n=min(num, len(df))).to_dict('records')



def generate_pdf(selected_words, title_prefix, test_id):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    
    def draw_layout(words, is_ans, p_num):
        c.setFont("Malgun", 16)
        c.drawCentredString(300, 800, f"{title_prefix} {'정답지' if is_ans else '시험지'} (P.{p_num})")
        c.setFont("Malgun", 8)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawString(500, 20, f"ID: {test_id}")
        
        c.setFont("Malgun", 10)
        for i, r in enumerate(words):
            col = i // 25; row_i = i % 25
            x = 70 + (col * 250); y = 740 - (row_i * 27)
            num_txt = f"{i+1+(p_num-1)*50}. "
            word_txt = f"{r['word']} : "
            
            c.setFillColorRGB(0, 0, 0)
            c.drawString(x, y, num_txt)
            word_x = x + c.stringWidth(num_txt, "Malgun", 10)
            c.drawString(word_x, y, word_txt)
            mean_x = word_x + c.stringWidth(word_txt, "Malgun", 10)
            
            if is_ans:
                c.setFillColorRGB(0.8, 0, 0) 
                c.drawString(mean_x, y, str(r['mean']))
            else:
                c.drawString(mean_x, y, "____________________")

    for p in range(0, len(selected_words), 50):
        draw_layout(selected_words[p:p+50], False, (p//50)+1); c.showPage()
    for p in range(0, len(selected_words), 50):
        draw_layout(selected_words[p:p+50], True, (p//50)+1); c.showPage()
    c.save()
    return buf

def save_test_history(selected_words, test_id):
    try:
        client = get_gspread_client()
        sh = client.open_by_key("1BYuQhbPLwnLxBHu4gjf-1H8fNoYvRRwIyg2TU1vfvw8")
        history_ws = sh.worksheet("Last_Test") 
        words_str = ",".join([w['word'] for w in selected_words])
        now_str = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
        history_ws.insert_row([test_id, now_str, words_str], 2)
    except Exception as e:
        st.error(f"히스토리 저장 실패: {e}")

# --- 4. 메인 로직 ---
st.set_page_config(page_title="스마트 토익 단어장", layout="wide")
st.title("📚 실시간 자동 동기화 단어장")

if 'worksheet' not in st.session_state or 'df' not in st.session_state or st.sidebar.button("🔄 데이터 새로고침"):
    ws, df = sync_data()
    st.session_state.worksheet = ws
    st.session_state.df = df

worksheet = st.session_state.worksheet
df_main = st.session_state.df

menu = st.sidebar.selectbox("메뉴 선택", ["단어 등록하기", "단어 목록 보기", "날짜별 단어 조회", "시험지 만들기", "오답 체크하기", "날짜별 오답 조회", "지옥의 오답 노트"])

if menu == "단어 등록하기":
    st.header("📝 새 단어 등록")
    tab1, tab2 = st.tabs(["직접 입력", "CSV 파일 업로드"])
    with tab1:
        with st.form("single_add", clear_on_submit=True):
            word = st.text_input("영어 단어").strip().lower()
            mean = st.text_input("한글 뜻").strip()
            if st.form_submit_button("시트에 저장"):
                if word and mean:
                    if word in df_main['word'].astype(str).tolist():
                        st.error(f"⚠️ '{word}'는 이미 등록된 단어입니다!")
                    else:
                        root = stemmer.stem(word)
                        today = get_today_kst()
                        worksheet.append_row([word, mean, root, 0, 0, today])
                        st.success(f"✅ '{word}' 저장 완료!")
                        time.sleep(1); st.rerun()

    with tab2:
        uploaded_file = st.file_uploader("CSV 선택", type=["csv"])
        if uploaded_file and st.button("🚀 구글 시트로 일괄 전송"):
            try:
                try: user_csv = pd.read_csv(uploaded_file)
                except:
                    uploaded_file.seek(0)
                    user_csv = pd.read_csv(uploaded_file, encoding='cp949')
                today = get_today_kst()
                exist = df_main['word'].astype(str).tolist()
                new_rows = []
                for _, row in user_csv.iterrows():
                    w = str(row.iloc[0]).strip().lower()
                    m = str(row.iloc[1]).strip()
                    if w not in exist:
                        r = stemmer.stem(w); new_rows.append([w, m, r, 0, 0, today]); exist.append(w)
                if new_rows:
                    worksheet.append_rows(new_rows)
                    st.success(f"✅ {len(new_rows)}개 저장 완료!"); time.sleep(1); st.rerun()
                else: st.warning("추가할 단어가 없습니다.")
            except Exception as e: st.error(f"오류: {e}")

elif menu == "단어 목록 보기":
    st.header("📋 전체 단어 관리 및 검색")
    if not df_main.empty:
        search = st.text_input("🔍 검색 (영어)").strip().lower()
        f_df = df_main[df_main['word'].astype(str).str.contains(search, na=False, case=False)].sort_values("word")
        d_df = f_df.copy(); d_df.insert(0, "선택", False)
        edited = st.data_editor(d_df, hide_index=True, use_container_width=True, key="v_editor")
        s_rows = edited[edited["선택"] == True]
        if not s_rows.empty:
            sel_w = s_rows.iloc[-1]["word"]
            try:
                cell = worksheet.find(sel_w); row_idx = cell.row
                st.divider(); st.subheader("⚙️ 단어 수정 및 삭제")
                c1, c2, c3 = st.columns(3)
                with c1: n_w = st.text_input("영어 수정", value=sel_w)
                with c2: n_m = st.text_input("한글 수정", value=f_df.loc[f_df['word']==sel_w, 'mean'].values[0])
                with c3: n_r = st.text_input("어근 수정", value=f_df.loc[f_df['word']==sel_w, 'root'].values[0])
                b_col1, b_col2, b_col3 = st.columns([1, 4, 1])
                with b_col1:
                    if st.button("💾 시트에 반영"):
                        worksheet.update_cell(row_idx, 1, n_w.strip().lower())
                        worksheet.update_cell(row_idx, 2, n_m.strip())
                        worksheet.update_cell(row_idx, 3, n_r.strip())
                        st.success("수정 완료!"); time.sleep(0.5); st.rerun()
                with b_col3:
                    if st.button("🗑️ 시트에서 삭제"):
                        worksheet.delete_rows(row_idx)
                        st.warning("삭제 완료!"); time.sleep(0.5); st.rerun()
            except: st.error("동기화 오류. 새로고침을 눌러주세요.")

elif menu == "날짜별 단어 조회":
    st.header("📅 날짜별 등록 현황")
    if not df_main.empty:
        target = st.selectbox("날짜 선택", sorted(df_main['date'].astype(str).unique(), reverse=True))
        date_df = df_main[df_main['date'].astype(str) == target].copy()
        
        if st.button(f"📄 {target} 시험지 생성"):
            shuffled_df = date_df.sample(frac=1).reset_index(drop=True)
            now = datetime.now(timezone(timedelta(hours=9)))
            test_id = f"{now.strftime('%y%m%d')}-{target.replace('-', '')}"
            selected_dicts = shuffled_df.to_dict('records')
            pdf_buf = generate_pdf(selected_dicts, target, test_id)
            save_test_history(selected_dicts, test_id)
            st.download_button(label="📥 PDF 다운로드", data=pdf_buf.getvalue(), file_name=f"voca_{target}.pdf", mime="application/pdf")
        st.table(date_df.sort_values("word")[['word', 'mean']])

elif menu == "시험지 만들기":
    st.header("🖨️ 랜덤 시험지 생성")
    if len(df_main) < 5: st.error("단어가 부족합니다.")
    else:
        num = st.number_input("문제 수", 5, len(df_main), 20)
        if st.button("시험지 생성 및 카운트 업데이트"):
            selected = select_test_words(df_main, num)
            now = datetime.now(timezone(timedelta(hours=9)))
            test_id = now.strftime("%y%m%d-%H%M") 
            pdf_buf = generate_pdf(selected, "랜덤", test_id)
            save_test_history(selected, test_id)
            
            with st.spinner("카운트 업데이트 중..."):
                all_data = worksheet.get_all_values()
                header = all_data[0]; rows = all_data[1:]
                word_idx = header.index("word"); count_idx = header.index("count")
                sel_words = [item['word'] for item in selected]
                for row in rows:
                    if row[word_idx] in sel_words:
                        row[count_idx] = int(row[count_idx] or 0) + 1
                worksheet.update(range_name="A2", values=rows)
            st.success("✅ 카운트 반영 완료!")
            st.download_button("📥 PDF 다운로드", pdf_buf.getvalue(), f"test_{test_id}.pdf")

elif menu == "오답 체크하기":
    st.header("📝 시험지 오답 체크")
    try:
        client = get_gspread_client()
        sh = client.open_by_key("1BYuQhbPLwnLxBHu4gjf-1H8fNoYvRRwIyg2TU1vfvw8")
        history_ws = sh.worksheet("Last_Test")
        
        # [수정] 시트 자체가 최신순이므로 역순 뒤집기([::-1]) 제거
        history_data = history_ws.get_all_records()
        
        if not history_data:
            st.warning("기록된 시험지가 없습니다.")
        else:
            # 1. 이미 최신순이므로 그대로 상위 10개 표시
            test_options = [f"{r['test_id']} ({r['date']})" for r in history_data[:10]]
            selected_option = st.selectbox("채점할 시험지 ID 선택", test_options)
            
            # 2. 선택된 ID와 일치하는 데이터 찾기 (문자열 변환 비교)
            test_id_selected = str(selected_option.split(" ")[0])
            selected_test = next((r for r in history_data if str(r['test_id']) == test_id_selected), None)
            
            if selected_test:
                # 단어 목록 파싱 (공백 제거)
                test_words = [w.strip() for w in str(selected_test['words']).split(",") if w.strip()]
                
                st.info(f"💡 시트에 기록된 최신 순서대로 표시됩니다. 틀린 것만 체크하세요.")
                
                wrong_words = []
                cols = st.columns(2)
                for i, word in enumerate(test_words):
                    with cols[i % 2]:
                        if st.checkbox(f"{i+1}. {word}", key=f"chk_{test_id_selected}_{i}"):
                            wrong_words.append(word)

                if st.button("🔴 오답 데이터 시트에 반영"):
                    if not wrong_words:
                        st.success("🎉 만점입니다! 따로 반영할 오답이 없네요.")
                    else:
                        try:
                            # --- 1. 단어장(Sheet1) 누적 업데이트 ---
                            with st.spinner("단어장(Sheet1) 업데이트 중..."):
                                main_ws = sh.get_worksheet(0)
                                all_data = main_ws.get_all_values()
                                header = all_data[0]
                                rows = all_data[1:]
                                
                                w_idx = header.index("word")
                                wc_idx = header.index("wrong_count")
                                
                                updated_rows = []
                                for row in rows:
                                    if row[w_idx] in wrong_words:
                                        curr = str(row[wc_idx]).strip()
                                        row[wc_idx] = int(curr) + 1 if curr.isdigit() else 1
                                    updated_rows.append(row)
                                
                                # 데이터가 있을 때만 한 번에 업데이트
                                main_ws.update("A2", updated_rows)

                            # --- 2. Last_Test 시트에 오답 기록 합치기 ---
                            with st.spinner("Last_Test 오답 누적 기록 중..."):
                                existing_wrong = str(selected_test.get('wrong_words', '')).strip()
                                if existing_wrong and existing_wrong not in ["None", "0", ""]:
                                    existing_list = [w.strip() for w in existing_wrong.split(",") if w.strip()]
                                    # 기존 오답 + 새로 체크한 오답 (중복 제거)
                                    final_list = list(set(existing_list + wrong_words))
                                    final_val = ",".join(final_list)
                                else:
                                    final_val = ",".join(wrong_words)
                                
                                # 행 위치 찾아서 업데이트
                                cell = history_ws.find(test_id_selected)
                                if cell:
                                    history_ws.update_cell(cell.row, 4, final_val)

                            st.success(f"✅ 오답 기록이 성공적으로 반영되었습니다!")
                            time.sleep(1)
                            st.rerun()
                            
                        except Exception as e:
                            if "429" in str(e):
                                st.error("⚠️ 요청이 너무 많습니다. 1분 뒤에 다시 시도해주세요.")
                            else:
                                st.error(f"반영 중 오류 발생: {e}")
            else:
                st.error("시험지 데이터를 찾을 수 없습니다. 시트를 확인해주세요.")

    except Exception as e:
        st.error(f"데이터 로딩 중 오류: {e}")


elif menu == "날짜별 오답 조회":
    st.header("📅 날짜별 오답 모아보기 (채점 기록 기준)")
    st.write("사용자가 실제로 '오답 반영' 버튼을 눌렀던 기록만 표시합니다.")

    try:
        client = get_gspread_client()
        sh = client.open_by_key("1BYuQhbPLwnLxBHu4gjf-1H8fNoYvRRwIyg2TU1vfvw8")
        history_ws = sh.worksheet("Last_Test")
        history_data = history_ws.get_all_records()

        if not history_data:
            st.warning("기록된 시험 히스토리가 없습니다.")
        else:
            history_df = pd.DataFrame(history_data)
            history_df['only_date'] = history_df['date'].str.split(' ').str[0]
            available_dates = sorted(history_df['only_date'].unique(), reverse=True)

            target_date = st.selectbox("조회할 날짜 선택", available_dates)

            # 해당 날짜의 시험들 필터링
            daily_tests = history_df[history_df['only_date'] == target_date]
            
            # 진짜로 틀렸다고 기록된 단어들만 수집
            real_wrong_list = []
            for _, row in daily_tests.iterrows():
                # D열(wrong_words) 값이 있고, "None"이 아닐 때만 파싱
                w_val = str(row.get('wrong_words', '')).strip()
                if w_val and w_val != "None" and w_val != "0":
                    real_wrong_list.extend(w_val.split(","))

            # 중복 제거 및 빈값 정리
            real_wrong_list = list(set([w.strip() for w in real_wrong_list if w.strip()]))

            if not real_wrong_list:
                st.info(f"ℹ️ {target_date}에는 채점(오답 반영)을 한 기록이 없거나 모두 맞으셨습니다.")
            else:
                st.success(f"📍 {target_date}에 실제로 틀렸던 단어: {len(real_wrong_list)}개")
                
                # 메인 시트에서 해당 단어 정보 가져오기
                wrong_display_df = df_main[df_main['word'].isin(real_wrong_list)].copy()
                st.table(wrong_display_df[['word', 'mean', 'wrong_count']])

                st.divider()
                
                if st.button(f"📄 {target_date} 실제 오답들로만 시험지 생성"):
                    shuffled_review = wrong_display_df.sample(frac=1).reset_index(drop=True)
                    sel_dicts = shuffled_review.to_dict('records')
                    
                    now = datetime.now(timezone(timedelta(hours=9)))
                    test_id = f"REV-{target_date.replace('-', '')}-{now.strftime('%H%M')}"
                    
                    pdf_buf = generate_pdf(sel_dicts, f"{target_date} 오답복습", test_id)
                    save_test_history(sel_dicts, test_id)
                    
                    st.download_button("📥 복습 시험지 다운로드", pdf_buf.getvalue(), f"review_{test_id}.pdf")

    except Exception as e:
        st.error(f"오류 발생: {e}")


elif menu == "지옥의 오답 노트":
    st.header("🔥 지옥의 오답 노트")
    threshold = st.number_input("최소 오답 횟수", min_value=1, value=3, step=1)
    wrong_df = df_main[df_main['wrong_count'].astype(int) >= threshold].copy()
    if wrong_df.empty: st.warning("해당하는 단어가 없습니다.")
    else:
        st.success(f"해당 단어: {len(wrong_df)}개")
        if st.button("📄 오답 노트 생성"):
            shuffled = wrong_df.sample(frac=1).reset_index(drop=True)
            selected_dicts = shuffled.to_dict('records')
            now = datetime.now(timezone(timedelta(hours=9)))
            test_id = f"WRONG-{threshold}-{now.strftime('%y%m%d')}"
            pdf_buf = generate_pdf(selected_dicts, f"오답({threshold}회↑)", test_id)
            save_test_history(selected_dicts, test_id)
            st.download_button("📥 PDF 다운로드", pdf_buf.getvalue(), f"wrong_note_{test_id}.pdf")
        st.table(wrong_df.sort_values("wrong_count", ascending=False)[['word', 'mean', 'wrong_count']])
