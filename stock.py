import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
import os
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor, as_completed

# 從子程式引入最新抓取函數
from scrapers import fetch_all_stock_data, get_robust_session

# -------------------------------------------------------------------------
# 1. 基礎設定與指定欄位 (包含 RWD 頁面設置)
# -------------------------------------------------------------------------
st.set_page_config(
    layout="wide", 
    page_title="股票數據監控面板",
    initial_sidebar_state="collapsed"  # 手機端開啟時預設收合側邊欄，釋放閱讀空間
)

# RWD / 手機與電腦端版型優化 CSS
st.markdown("""
    <style>
    /* 調整主要內容區塊內距，避免手機邊緣太擠 */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
    }
    
    /* 針對手機螢幕 (寬度小於 768px) 的自動彈性調整 */
    @media (max-width: 768px) {
        /* 按鈕在手機上自動滿版、易於手指點擊 */
        .stButton button {
            width: 100% !important;
            margin-top: 4px;
            margin-bottom: 4px;
        }
        /* 調整 Tab 標籤頁字體與間距，避免手機上太寬撐開 */
        .stTabs [data-baseweb="tab"] {
            font-size: 14px !important;
            padding-left: 6px !important;
            padding-right: 6px !important;
        }
        /* 調整多選下拉選單的高度與字體 */
        .stMultiSelect {
            font-size: 14px !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

COLUMNS = [
    "日期", "大盤指數", "台指期近一", "大盤成交量", "外資進出", 
    "法人進出(投信)", "自營商進出", 
    "融資增減", "融資餘額", "借券增減", "借券餘額", "券資比", 
    "外資未平倉", "自營商未平倉", "違約合計總金額", "違約相抵後金額"
]

STOCK_DB = {
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "0050": "元大台灣50",
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "TSLA": "Tesla"
}

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(CURRENT_DIR, "stock_history_cache.csv")

WEEK_DAYS = ["一", "二", "三", "四", "五", "六", "日"]

def get_unit_str(metric_name):
    if "指數" in metric_name or "台指期" in metric_name: return "點"
    elif "成交量" in metric_name or "金額" in metric_name or "進出" in metric_name or "增減" in metric_name or "餘額" in metric_name:
        if "違約" in metric_name: return "百萬"
        elif "成交量" in metric_name: return "張"
        else: return "億"
    elif "比" in metric_name: return "%"
    elif "口" in metric_name or "未平倉" in metric_name: return "口"
    else: return "張"

def format_cell(x):
    if pd.isna(x) or x == "" or x is None or str(x).strip() in ["", "-", "None"]:
        return "-"
    try:
        val_str = str(x).replace("億", "").replace("張", "").replace("%", "").replace("口", "").replace("百萬", "").replace(",", "").strip()
        val = float(val_str)
        return f"{val:.2f}"
    except:
        return str(x).strip()

def add_weekday_to_date_str(date_str):
    if "(" in date_str:  
        return date_str
    try:
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return f"{date_str}({WEEK_DAYS[dt.weekday()]})"
    except:
        return date_str

# -------------------------------------------------------------------------
# 2. 本地端讀寫
# -------------------------------------------------------------------------
def local_read_csv():
    if os.path.exists(CACHE_FILE):
        try:
            return pd.read_csv(CACHE_FILE, dtype=str)
        except Exception:
            return None
    return None

def local_write_csv(df):
    try:
        df.to_csv(CACHE_FILE, index=False, encoding="utf-8-sig")
        return True
    except Exception as e:
        st.error(f"本地檔案寫入失敗: {e}")
        return False

# -------------------------------------------------------------------------
# 3. 自動快取補抓與「僅保留交易日」（多執行緒優化版）
# -------------------------------------------------------------------------
def load_or_fetch_90_days_history(seed_name):
    df_cache = local_read_csv()
    
    cache_dict = {}
    if df_cache is not None and not df_cache.empty:
        df_cache["日期"] = df_cache["日期"].astype(str).str.strip()
        for _, row in df_cache.iterrows():
            pure_date = row["日期"].split("(")[0] 
            cache_dict[pure_date] = row.to_dict()

    potential_dates = []
    check_day = datetime.now()
    for _ in range(140):
        if check_day.weekday() < 5:
            potential_dates.append(check_day.strftime("%Y-%m-%d"))
        check_day -= timedelta(days=1)

    missing_dates = []
    final_valid_data = []

    for dt_str in potential_dates:
        if len(final_valid_data) >= 90:
            break

        if dt_str in cache_dict:
            row_vals = cache_dict[dt_str]
            idx_val = str(row_vals.get("大盤指數", "-")).strip()
            
            is_closed_day = any(kw in idx_val for kw in ["休市", "假日", "颱風"])
            
            if idx_val not in ["", "-", "None"] and not is_closed_day:
                has_empty_field = False
                for col in COLUMNS:
                    if col != "日期":
                        val_str = str(row_vals.get(col, "-")).strip()
                        if val_str in ["", "-", "None", "None 億", "None 張", "None 口"]:
                            has_empty_field = True
                            break
                
                if has_empty_field:
                    missing_dates.append(dt_str)
                else:
                    final_valid_data.append(row_vals)
                continue
        
        missing_dates.append(dt_str)

    if missing_dates and len(final_valid_data) < 90:
        needed_count = 90 - len(final_valid_data)
        dates_to_fetch = missing_dates[:min(len(missing_dates), int(needed_count * 1.5))]
        
        if dates_to_fetch:
            progress_bar = st.progress(0, text="⚡ 正在為您精確回補空缺/遺漏的欄位數據...")
            
            shared_session = get_robust_session()

            def thread_task(dt_str):
                date_param = dt_str.replace("-", "")
                real_data = fetch_all_stock_data(date_param, external_session=shared_session)
                
                if real_data is not None and real_data.get("大盤指數") is not None:
                    row_data = {"日期": add_weekday_to_date_str(dt_str)}
                    for col in COLUMNS:
                        if col != "日期":
                            new_val = real_data.get(col, "-")
                            if new_val in ["", "-", "None", None]:
                                old_val = cache_dict.get(dt_str, {}).get(col, "-")
                                row_data[col] = old_val
                            else:
                                row_data[col] = new_val
                    return dt_str, row_data
                return dt_str, None

            completed = 0
            fetched_results = {}
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_date = {executor.submit(thread_task, d): d for d in dates_to_fetch}
                for future in as_completed(future_to_date):
                    dt_str, result = future.result()
                    if result:
                        fetched_results[dt_str] = result
                    completed += 1
                    pct = min(completed / len(dates_to_fetch), 1.0)
                    progress_bar.progress(pct, text=f"⚡ 欄位補強中... 已處理：{completed}/{len(dates_to_fetch)} 日")

            progress_bar.empty()
            cache_dict.update(fetched_results)

    final_output = []
    check_day = datetime.now()
    loop_count = 0
    while len(final_output) < 90 and loop_count < 150:
        loop_count += 1
        dt_str = check_day.strftime("%Y-%m-%d")
        if check_day.weekday() < 5 and dt_str in cache_dict:
            row_vals = cache_dict[dt_str]
            idx_val = str(row_vals.get("大盤指數", "-")).strip()
            if idx_val not in ["", "-", "None"] and not any(kw in idx_val for kw in ["休市", "假日", "颱風"]):
                row_vals["日期"] = add_weekday_to_date_str(dt_str)
                final_output.append(row_vals)
        check_day -= timedelta(days=1)

    df_final = pd.DataFrame(final_output)
    
    if not df_final.empty:
        df_final["日期"] = df_final["日期"].apply(lambda x: add_weekday_to_date_str(x.split("(")[0]))
        
    local_write_csv(df_final)
    return df_final

def generate_today_metrics(last_row):
    today_dt = datetime.now()
    today_str = today_dt.strftime("%Y-%m-%d")
    date_param = today_dt.strftime("%Y%m%d")
    
    live_data = fetch_all_stock_data(date_param)
    if live_data is None or live_data.get("大盤指數") is None:
        return None
        
    row_data = {"日期": add_weekday_to_date_str(today_str)}
    for col in COLUMNS:
        if col != "日期":
            row_data[col] = live_data.get(col, "-")
    return row_data

# -------------------------------------------------------------------------
# 4. 全域狀態管理
# -------------------------------------------------------------------------
if "store" not in st.session_state:
    st.session_state.store = {
        "台股": {"INDEX": {"name": "大盤", "df": load_or_fetch_90_days_history("TW_INDEX")}},
        "美股": {"INDEX": {"name": "大盤", "df": load_or_fetch_90_days_history("US_INDEX")}}
    }

def update_and_trim_df(df, new_row_dict):
    if new_row_dict is None: return df
    
    today_with_week = add_weekday_to_date_str(datetime.now().strftime("%Y-%m-%d"))
    if not df.empty and df.iloc[0]["日期"] == today_with_week:
        df.iloc[0] = new_row_dict
    else:
        df = pd.concat([pd.DataFrame([new_row_dict]), df], ignore_index=True)
        
    if len(df) > 90: df = df.head(90)
    local_write_csv(df)
    return df

# -------------------------------------------------------------------------
# 5. 介面渲染
# -------------------------------------------------------------------------
st.sidebar.title("功能選單")
menu_option = st.sidebar.radio("選擇市場/清單", options=["美股市場 US", "台股市場 TW", "🔮 自訂個股名單"], index=1)
current_market = "美股" if "美股" in menu_option else "table" if "🔮" in menu_option else "台股"

st.sidebar.markdown("---")
if st.sidebar.button("💥 強制重構本地快取數據", use_container_width=True):
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    if "store" in st.session_state:
        del st.session_state["store"]
    st.rerun()

sub_tickets = list(st.session_state.store[current_market].keys())
sub_tab_labels = ["大盤" if t == "INDEX" else f"{t}-{st.session_state.store[current_market][t]['name']}" for t in sub_tickets]

add_col1, add_col2 = st.columns([3, 1])
with add_col2:
    with st.popover("＋ 新增個股分頁", use_container_width=True):
        new_code = st.text_input("輸入股票代碼:").strip().upper()
        if st.button("確認新增個股", use_container_width=True):
            if new_code and new_code not in st.session_state.store[current_market]:
                name = STOCK_DB.get(new_code, "自選股")
                new_df = load_or_fetch_90_days_history(f"{current_market}_{new_code}")
                st.session_state.store[current_market][new_code] = {"name": name, "df": new_df}
                st.rerun()

if sub_tickets:
    tabs = st.tabs(sub_tab_labels)
    for idx, tab in enumerate(tabs):
        ticket = sub_tickets[idx]
        page_info = st.session_state.store[current_market][ticket]
        df_data = page_info["df"]
        
        with tab:
            # 調整欄位比例，讓手機上按鈕不折行
            header_col, refresh_col = st.columns([3.5, 1.5])
            with header_col:
                title_name = "大盤指數" if ticket == "INDEX" else f"{ticket} - {page_info['name']}"
                st.subheader(f"📈 {title_name}")
            with refresh_col:
                if st.button("⚡ 即時更新", key=f"btn_ref_{current_market}_{ticket}", use_container_width=True):
                    new_row = generate_today_metrics(df_data.iloc[0])
                    if new_row is not None:
                        st.session_state.store[current_market][ticket]["df"] = update_and_trim_df(df_data, new_row)
                        st.rerun()
                    else:
                        st.toast("今日非交易日或尚無開盤數據！", icon="⚠️")
            
            st.write("📋 歷史數據明細（僅顯示交易日）：")
            
            df_ordered = df_data.reindex(columns=COLUMNS)
            formatted_df = df_ordered.copy()
            
            for col in formatted_df.columns:
                if col != "日期":
                    formatted_df[col] = formatted_df[col].apply(format_cell)

            # 表頭 MultiIndex 結構 (已完全移除公股銀行)
            multi_cols = pd.MultiIndex.from_tuples([
                ("基本", "日期"),
                ("大盤/期貨", "大盤指數"), ("大盤/期貨", "台指期近一"), ("大盤/期貨", "大盤成交量(張)"),
                ("三大法人進出量", "外資進出(億)"), ("三大法人進出量", "法人進出(投信)(億)"), 
                ("三大法人進出量", "自營商進出(億)"),
                ("融資/融券", "融資增減(億)"), ("融資/融券", "融資餘額(億)"), 
                ("融資/融券", "借券增減(億)"), ("融資/融券", "借券餘額(億)"), ("融資/融券", "券資比(%)"),
                ("未平倉口數", "外資未平倉(口)"), ("未平倉口數", "自營商未平倉(口)"),
                ("違約交割金額", "違約合計(百萬)"), ("違約交割金額", "違約相抵後(百萬)")
            ])
            formatted_df.columns = multi_cols
            formatted_df = formatted_df.set_index(("基本", "日期"))

            st.dataframe(formatted_df, use_container_width=True, height=400)
            
            st.markdown("---")
            available_metrics = [c for c in COLUMNS if c not in ["日期", "大盤指數"]]
            selected_charts = st.multiselect("請選擇要開啟的數據圖表：", options=available_metrics, max_selections=3, key=f"multi_{current_market}_{ticket}")
            
            all_plots_to_render = ["大盤指數"] + selected_charts
            num_plots = len(all_plots_to_render)
            
            subplot_titles = []
            for m in all_plots_to_render:
                u = get_unit_str(m)
                subplot_titles.append(f"📍 {m} <span style='font-size:12px; color:gray;'> ({u})</span>")
                
            fig = make_subplots(rows=num_plots, cols=1, shared_xaxes=True, vertical_spacing=0.08, subplot_titles=subplot_titles)
            chart_df = df_data.copy().iloc[::-1]
            
            for i, metric in enumerate(all_plots_to_render):
                row_idx = i + 1
                numeric_y = pd.to_numeric(chart_df[metric].astype(str).str.replace(r'[^\d.-]', '', regex=True), errors='coerce')
                
                fig.add_trace(
                    go.Scatter(
                        x=chart_df["日期"], y=numeric_y, mode='lines+markers', 
                        line=dict(color='#007bff', width=2), name=metric,
                        hovertemplate=f"<b>%{{x}}</b><br>{metric}: %{{y}} {get_unit_str(metric)}<extra></extra>"
                    ),
                    row=row_idx, col=1
                )
                
                fig.update_xaxes(
                    type='category', showgrid=True, 
                    tickangle=-45 if row_idx == num_plots else 0, 
                    showspikes=True, spikemode="across", spikesnap="cursor", 
                    spikethickness=1, spikecolor="#666666", spikedash="dash",
                    row=row_idx, col=1
                )
                fig.update_yaxes(showgrid=True, showspikes=False, row=row_idx, col=1)
            
            # 手機端圖表佈局與手勢優化
            fig.update_layout(
                height=160 * num_plots + 50, 
                margin=dict(l=10, r=10, t=30, b=20), 
                hovermode="x", 
                showlegend=False,
                dragmode=False  # 🔒 關閉拖曳縮放，確保手機網頁滑動順暢不卡住
            )
            fig.update_traces(xaxis=f"x{num_plots if num_plots > 1 else ''}")
            
            for annotation in fig['layout']['annotations']:
                annotation['x'] = 0
                annotation['xanchor'] = 'left'
                annotation['font'] = dict(size=13, color="#000000", family="Arial, sans-serif")
                
            # Streamlit 畫圖組件 (啟用 RWD 自適應與滾動手勢保護)
            st.plotly_chart(
                fig, 
                use_container_width=True, 
                config={
                    'displayModeBar': False, # 隱藏上方放大鏡工具列
                    'scrollZoom': False,     # 禁用滾輪/手勢縮放
                    'responsive': True       # 自動適應手機與電腦螢幕
                }
            )

            # -------------------------------------------------------------------------
            # 6. 外部數據來源超連結區塊
            # -------------------------------------------------------------------------
            st.markdown("---")
            st.markdown("### 🔗 外部數據來源與延伸參考連結")
            st.markdown(
                """
                - 🏛️ <a href="https://www.wantgoo.com/stock/public-bank/trend" target="_blank">公股銀行進出 trend - 玩股網</a>
                - 📈 <a href="https://www.pscnet.com.tw/pscnetStock/menuContent.do?main_id=386032846c000000ccd145898ac293b6&sub_id=38d642081a00000099f12672f4cf7d6e" target="_blank">整戶融資維持率 - 統一證券</a>
                - 📊 <a href="https://nstatdb.dgbas.gov.tw/dgbasAll/webMain.aspx?sys=100&funid=qryout&funid2=A018201010&outmode=8&ym=11001&ymt=11503&cycle=42&outkind=1&compmode=2.1&ratenm=%u7D71%u8A08%u503C%u53CA%u5E74%u589E%u7387&fldlst=111&codlst0=1111111111111111111&compmode=2.1&rr=q23704x&&rdm=R2632432" target="_blank">國民所得、儲蓄與投資統計 - 主計總處</a>
                """,
                unsafe_allow_html=True
            )