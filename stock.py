import streamlit as st
import pandas as pd
import numpy as np
import requests
import os
import time
import random
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. 引入爬蟲 (已包含 fetch_stock_name)
from scrapers import fetch_all_stock_data, get_robust_session
from scrapers_ind import fetch_merged_stock_data

# 2. 引入個股模組子程式
from individual import render_individual_tab, load_or_fetch_ind_90_days

# -------------------------------------------------------------------------
# 基礎頁面設定與 CSS
# -------------------------------------------------------------------------
st.set_page_config(
    layout="wide", 
    page_title="股票數據監控面板",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    .block-container {
        padding-top: 3.8rem !important;
        padding-bottom: 2rem !important;
        padding-left: 0.8rem !important;
        padding-right: 0.8rem !important;
    }
    
    /* 強制確保自訂表格容器與基本設定 */
    .custom-table-container {
        width: 100% !important;
        overflow-x: auto !important;
        max-height: 450px !important;
        overflow-y: auto !important;
        border: 1px solid #dcdcdc !important;
        border-radius: 4px !important;
        margin-bottom: 0.8rem !important;
        position: relative !important;
    }
    .custom-table {
        width: 100% !important;
        border-collapse: separate !important;
        border-spacing: 0 !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        font-size: 14px !important;
        white-space: nowrap !important;
    }
    
    .custom-table th {
        position: sticky !important;
        top: 0 !important;
        background-color: #f0f0f0 !important;
        color: #111111 !important;
        font-weight: bold !important;
        border: 1px solid #dcdcdc !important;
        padding: 8px 10px !important;
        text-align: center !important;
        z-index: 2 !important;
    }
    .custom-table tr:nth-child(2) th {
        top: 35px !important;
        border-bottom: 2.5px solid #333333 !important;
    }
    
    .custom-table th.sticky-corner {
        position: sticky !important;
        top: 0 !important;
        left: 0 !important;
        z-index: 3 !important;
        background-color: #e5e5e5 !important;
        border-right: 2.5px solid #333333 !important;
    }

    .custom-table td.date-cell {
        position: sticky !important;
        left: 0 !important;
        background-color: #f5f5f5 !important;
        color: #000000 !important;
        font-weight: bold !important;
        border: 1px solid #e0e0e0 !important;
        border-right: 2.5px solid #333333 !important;
        padding: 8px 10px !important;
        z-index: 1 !important;
        text-align: center !important;
    }

    .custom-table td.value-cell {
        font-weight: bold !important;
        border: 1px solid #eeeeee !important;
        padding: 8px 10px !important;
        text-align: right !important;
        color: #111111 !important;
    }

    /* 強制紅綠色顯色（避免雲端平台被 Streamlit 預設覆蓋） */
    .custom-table td.value-cell.pos-val,
    .custom-table td.pos-val {
        color: #d32f2f !important;
    }

    .custom-table td.value-cell.neg-val,
    .custom-table td.neg-val {
        color: #2e7d32 !important;
    }

    .custom-table td.nodata-cell {
        color: #9e9e9e !important;
        font-weight: normal !important;
        border: 1px solid #eeeeee !important;
        padding: 8px 10px !important;
        text-align: center !important;
    }
    
    .custom-table tr:hover td {
        background-color: #f7f7f7 !important;
    }

    /* 強制底色呈現 */
    .custom-table td.bg-pink, 
    tr td.bg-pink { 
        background-color: #f8d7da !important; 
        color: #842029 !important;
    }
    .custom-table td.bg-light-green, 
    tr td.bg-light-green { 
        background-color: #d4edda !important; 
        color: #0f5132 !important;
    }
    </style>
""", unsafe_allow_html=True) 

# -------------------------------------------------------------------------
# 統一欄位名稱定義與常數
# -------------------------------------------------------------------------
def fetch_stock_name(stock_id):
    try:
        url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{stock_id}.tw|otc_{stock_id}.tw"
        res = requests.get(url, timeout=3).json()
        if "msgArray" in res and len(res["msgArray"]) > 0:
            name = res["msgArray"][0].get("n")
            if name: return name
    except:
        pass
    return "股票"

ALL_METRICS = [
    "訊號燈", "大盤指數", "大盤改變率", "融資VS大盤", "融資大盤倍數", "台指期近一", 
    "成交量金額(億)", "成交量倍數", "成交量(千股)", "外資進出(億)", "外資買賣力度", "外資累積", 
    "投信進出(億)", "自營商進出(億)", "三大法人(億)", "三大法人累積", 
    "融資餘額", "融資增減", "融資改變率", 
    "融券餘額", "融券增減", "券資比(%)", 
    "外資未平倉(口)", "外資未平倉維持率", "投信未平倉(口)", "自營商未平倉(口)", 
    "違約合計(百萬)", "違約相抵後(百萬)", 
    "券賣餘額(千股)", "券賣出量(千股)", "券賣還券(千股)", "借券賣出變動比"
]

DEFAULT_VISIBLE_METRICS = [
    "訊號燈", "大盤指數", "大盤改變率", "融資VS大盤", "融資大盤倍數", "台指期近一", 
    "成交量金額(億)", "成交量倍數", "成交量(千股)", "外資進出(億)","外資買賣力度", 
    "融資餘額", "融資增減", "融資改變率", 
    "外資未平倉(口)","外資未平倉維持率", 
    "券賣餘額(千股)", "券賣出量(千股)", "券賣還券(千股)", "借券賣出變動比"
]

COL_GROUP_MAPPING = {
    "訊號燈": ("g_ind", "大盤/期貨資訊", "訊號燈"),
    "大盤指數": ("g_ind", "大盤/期貨資訊", "大盤指數"),
    "大盤改變率": ("g_ind", "大盤/期貨資訊", "大盤改變率"),
    "融資VS大盤": ("g_ind", "大盤/期貨資訊", "融資VS大盤"),
    "融資大盤倍數": ("g_ind", "大盤/期貨資訊", "融資大盤倍數"),
    "台指期近一": ("g_ind", "大盤/期貨資訊", "台指期近一"),
    "成交量金額(億)": ("g_ind", "大盤/期貨資訊", "成交量金額(億)"),
    "成交量倍數": ("g_ind", "大盤/期貨資訊", "成交量倍數"),
    "成交量(千股)": ("g_ind", "大盤/期貨資訊", "成交量(千股)"),
    
    "外資進出(億)": ("g_three", "三大法人進出", "外資進出(億)"),
    "外資買賣力度": ("g_three", "三大法人進出", "外資買賣力度"),
    "外資累積": ("g_three", "三大法人進出", "外資累積"),
    "投信進出(億)": ("g_three", "三大法人進出", "投信進出(億)"),
    "自營商進出(億)": ("g_three", "三大法人進出", "自營商進出(億)"),
    "三大法人(億)": ("g_three", "三大法人進出", "三大法人(億)"),
    "三大法人累積": ("g_three", "三大法人進出", "三大法人累積"),
    
    "融資餘額": ("g_margin", "融資/融券", "融資餘額"),
    "融資增減": ("g_margin", "融資/融券", "融資增減"),
    "融資改變率": ("g_margin", "融資/融券", "融資改變率"),
    "融券餘額": ("g_margin", "融資/融券", "融券餘額"),
    "融券增減": ("g_margin", "融資/融券", "融券增減"),
    "券資比(%)": ("g_margin", "融資/融券", "券資比(%)"),
    
    "外資未平倉(口)": ("g_oi", "未平倉", "外資未平倉(口)"),
    "外資未平倉維持率": ("g_oi", "未平倉", "外資未平倉維持率"),
    "投信未平倉(口)": ("g_oi", "未平倉", "投信未平倉(口)"),
    "自營商未平倉(口)": ("g_oi", "未平倉", "自營商未平倉(口)"),
    
    "違約合計(百萬)": ("g_default", "違約交割", "違約合計(百萬)"),
    "違約相抵後(百萬)": ("g_default", "違約交割", "違約相抵後(百萬)"),
    
    "券賣餘額(千股)": ("g_short", "借券賣出", "券賣餘額(千股)"),
    "券賣出量(千股)": ("g_short", "借券賣出", "券賣出量(千股)"),
    "券賣還券(千股)": ("g_short", "借券賣出", "券賣還券(千股)"),
    "借券賣出變動比": ("g_short", "借券賣出", "借券賣出變動比")
}

GROUP_ORDER_IDS = ["g_ind", "g_three", "g_margin", "g_oi", "g_default", "g_short"]

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(CURRENT_DIR, "stock_history_cache.csv")
WEEK_DAYS = ["一", "二", "三", "四", "五", "六", "日"]

def get_unit_str(metric_name):
    if "率" in metric_name or "力度" in metric_name or "比" in metric_name: return "%"
    elif "倍數" in metric_name or "VS" in metric_name or "訊號燈" in metric_name: return ""
    elif "指數" in metric_name or "台指期" in metric_name: return "點"
    elif "成交量(千股)" in metric_name: return "張"
    elif "違約" in metric_name: return "百萬"
    elif "億" in metric_name: return "億"
    elif "口" in metric_name or "未平倉" in metric_name: return "口"
    elif "千股" in metric_name: return "千股"
    else: return ""

def parse_num_safe(val):
    if pd.isna(val) or val is None: return None
    val_str = str(val).replace("億", "").replace("張", "").replace("%", "").replace("口", "").replace("百萬", "").replace("千股", "").replace(",", "").strip()
    if val_str in ["", "-", "None", "nan", "NaN", "無交易數據", "休市", "假日", "颱風", "股市未開盤"]:
        return None
    try: return float(val_str)
    except: return None

def clean_unit_text(val_str):
    if pd.isna(val_str) or val_str is None:
        return "-"
    s = str(val_str).strip()
    for unit in ["億", "張", "口", "百萬", "千股"]:
        s = s.replace(unit, "")
    return s.strip()

def add_weekday_to_date_str(date_str):
    if "(" in date_str: return date_str
    try:
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return f"{date_str}({WEEK_DAYS[dt.weekday()]} )"
    except:
        return date_str

def local_read_csv():
    if os.path.exists(CACHE_FILE):
        try: return pd.read_csv(CACHE_FILE, dtype=str)
        except Exception: return None
    return None

def local_write_csv(df):
    try:
        df.to_csv(CACHE_FILE, index=False, encoding="utf-8-sig")
        return True
    except Exception as e:
        st.error(f"本地檔案寫入失敗: {e}")
        return False

def calculate_derived_metrics(df):
    if df is None or df.empty: return df
    df_calc = df.copy()
    
    if "日期" in df_calc.columns:
        df_calc['pure_date'] = df_calc['日期'].apply(lambda x: str(x).split("(")[0])
        df_calc = df_calc.sort_values(by="pure_date", ascending=True).reset_index(drop=True)

    n = len(df_calc)
    
    idx_change_rate = ["-"] * n
    margin_change_rate = ["-"] * n
    margin_vs_index = ["-"] * n
    margin_index_ratio = ["-"] * n
    foreign_power = ["-"] * n
    foreign_oi_maint = ["-"] * n
    signal_light = ["-"] * n
    
    margin_change_raw = [None] * n
    is_bottom_10_percent = [False] * n

    volume_ratio_arr = ["-"] * n
    foreign_cum_arr = ["-"] * n
    three_cum_arr = ["-"] * n
    total_io_arr_str = ["-"] * n
    short_change_ratio_arr = ["-"] * n

    def get_last_valid_idx(curr_i, col_name):
        for k in range(curr_i - 1, -1, -1):
            if col_name in df_calc.columns:
                val = parse_num_safe(df_calc.loc[k, col_name])
                if val is not None:
                    return k, val
        return None, None

    vol_amount_window = []
    vol_shares_window = []
    foreign_window = []
    three_window = []

    for i in range(n):
        idx_val = parse_num_safe(df_calc.loc[i, "大盤指數"])
        if idx_val is None:
            continue

        prev_idx_i, prev_idx_val = get_last_valid_idx(i, "大盤指數")
        if prev_idx_val is not None and prev_idx_val != 0:
            rate = ((idx_val - prev_idx_val) / prev_idx_val) * 100
            idx_change_rate[i] = f"{rate:.2f}%"
            curr_idx_rate_num = rate
        else:
            idx_change_rate[i] = "0.00%"
            curr_idx_rate_num = 0.0

        margin_diff = parse_num_safe(df_calc.loc[i, "融資增減"])
        _, prev_margin_bal = get_last_valid_idx(i, "融資餘額")
        
        curr_margin_rate_num = None
        if margin_diff is not None and prev_margin_bal is not None and prev_margin_bal != 0:
            m_rate = (margin_diff / prev_margin_bal) * 100
            margin_change_rate[i] = f"{m_rate:.2f}%"
            margin_change_raw[i] = m_rate
            curr_margin_rate_num = m_rate

        if curr_margin_rate_num is not None and curr_idx_rate_num is not None:
            margin_vs_index[i] = "大" if curr_margin_rate_num > curr_idx_rate_num else "小"
            if curr_idx_rate_num != 0:
                ratio = curr_margin_rate_num / curr_idx_rate_num
                margin_index_ratio[i] = f"{ratio:.2f}"
            else:
                margin_index_ratio[i] = "0.00"

        v_amt = parse_num_safe(df_calc.loc[i, "成交量金額(億)"])
        if v_amt is not None:
            vol_amount_window.append(v_amt)
            if len(vol_amount_window) > 20:
                vol_amount_window.pop(0)
            avg_20_amt = sum(vol_amount_window) / len(vol_amount_window)
            if avg_20_amt != 0:
                v_mult = v_amt / avg_20_amt
                volume_ratio_arr[i] = f"{v_mult:.2f}"

        v_shares = parse_num_safe(df_calc.loc[i, "成交量(千股)"])
        if v_shares is not None:
            vol_shares_window.append(v_shares)
            if len(vol_shares_window) > 20:
                vol_shares_window.pop(0)
        
        s_out = parse_num_safe(df_calc.loc[i, "券賣出量(千股)"])
        s_ret = parse_num_safe(df_calc.loc[i, "券賣還券(千股)"])
        short_ratio = None
        if s_out is not None and s_ret is not None and len(vol_shares_window) > 0:
            avg_20_shares = sum(vol_shares_window) / len(vol_shares_window)
            if avg_20_shares != 0:
                net_short_shares = (s_out - s_ret)
                short_ratio = (net_short_shares / avg_20_shares) * 100
                short_change_ratio_arr[i] = f"{short_ratio:.2f}%"

        f_io = parse_num_safe(df_calc.loc[i, "外資進出(億)"])
        if f_io is not None and v_amt is not None and v_amt != 0:
            f_power = (f_io / v_amt) * 100
            foreign_power[i] = f"{f_power:.2f}%"

        if f_io is not None:
            foreign_window.append(f_io)
            if len(foreign_window) > 30:
                foreign_window.pop(0)
            foreign_cum_arr[i] = f"{sum(foreign_window):.2f}"

        t_io = parse_num_safe(df_calc.loc[i, "投信進出(億)"])
        d_io = parse_num_safe(df_calc.loc[i, "自營商進出(億)"])

        tot_day = (f_io or 0.0) + (t_io or 0.0) + (d_io or 0.0)
        if any(v is not None for v in [f_io, t_io, d_io]):
            total_io_arr_str[i] = f"{tot_day:.2f}"
            three_window.append(tot_day)
            if len(three_window) > 30:
                three_window.pop(0)
            three_cum_arr[i] = f"{sum(three_window):.2f}"

        f_oi = parse_num_safe(df_calc.loc[i, "外資未平倉(口)"])
        _, prev_f_oi = get_last_valid_idx(i, "外資未平倉(口)")
        if f_oi is not None and prev_f_oi is not None and prev_f_oi != 0:
            maint = (f_oi / prev_f_oi) * 100
            foreign_oi_maint[i] = f"{maint:.2f}%"

        s_ratio_val = short_ratio if short_ratio is not None else 0.0
        v_mult_val = parse_num_safe(volume_ratio_arr[i]) if volume_ratio_arr[i] != "-" else 1.0
        d_rate_val = curr_idx_rate_num

        if s_ratio_val >= 3.0 and v_mult_val >= 1.5 and d_rate_val <= -2.0:
            signal_light[i] = "空頭"
        elif s_ratio_val <= -3.0 and v_mult_val >= 1.5 and d_rate_val >= 2.0:
            signal_light[i] = "強勢軋空"
        elif s_ratio_val <= -1.0 and v_mult_val <= 0.7 and -1.5 <= d_rate_val <= 1.5:
            signal_light[i] = "籌碼沉澱"
        elif s_ratio_val >= 1.0 and v_mult_val <= 1.5 and -1.5 <= d_rate_val <= 1.5:
            signal_light[i] = "高位壓盤"

    for i in range(n):
        f_oi = parse_num_safe(df_calc.loc[i, "外資未平倉(口)"])
        if f_oi is not None and f_oi < 0:
            valid_window = []
            for k in range(i, -1, -1):
                val = parse_num_safe(df_calc.loc[k, "外資未平倉(口)"])
                if val is not None:
                    valid_window.append(val)
                if len(valid_window) >= 66:
                    break
            if valid_window:
                threshold_10p = np.percentile(valid_window, 10)
                if f_oi <= threshold_10p:
                    is_bottom_10_percent[i] = True

    is_3day_big_green = [False] * n
    consecutive_cnt = 0
    for i in range(n):
        m_raw = margin_change_raw[i]
        if margin_vs_index[i] == "大" and m_raw is not None and m_raw > 0:
            consecutive_cnt += 1
        else:
            consecutive_cnt = 0
        
        if consecutive_cnt >= 3:
            for back in range(consecutive_cnt):
                is_3day_big_green[i - back] = True

    df_calc["大盤改變率"] = idx_change_rate
    df_calc["融資改變率"] = margin_change_rate
    df_calc["融資VS大盤"] = margin_vs_index
    df_calc["融資大盤倍數"] = margin_index_ratio
    df_calc["外資買賣力度"] = foreign_power
    df_calc["外資未平倉維持率"] = foreign_oi_maint
    df_calc["成交量倍數"] = volume_ratio_arr
    df_calc["外資累積"] = foreign_cum_arr
    df_calc["三大法人(億)"] = total_io_arr_str
    df_calc["三大法人累積"] = three_cum_arr
    df_calc["借券賣出變動比"] = short_change_ratio_arr
    df_calc["訊號燈"] = signal_light
    df_calc["_is_bottom_10p"] = is_bottom_10_percent
    df_calc["_margin_change_raw"] = margin_change_raw
    df_calc["_is_3day_big_green"] = is_3day_big_green

    for i in range(n):
        idx_val_str = str(df_calc.loc[i, "大盤指數"]).strip()
        if parse_num_safe(idx_val_str) is None:
            df_calc.loc[i, "大盤指數"] = "股市未開盤"
            for col in ALL_METRICS:
                if col != "大盤指數" and col in df_calc.columns:
                    df_calc.loc[i, col] = "-"

    df_calc = df_calc.sort_values(by="pure_date", ascending=False).drop(columns=['pure_date']).reset_index(drop=True)
    return df_calc

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
    for _ in range(160):
        if check_day.weekday() < 5:
            potential_dates.append(check_day.strftime("%Y-%m-%d"))
        check_day -= timedelta(days=1)

    dates_to_process_set = set()
    for dt_str in potential_dates:
        if dt_str not in cache_dict:
            dates_to_process_set.add(dt_str)
        else:
            row_vals = cache_dict[dt_str]
            idx_val = str(row_vals.get("大盤指數", "-")).strip()
            
            if idx_val == "股市未開盤":
                continue
            elif idx_val in ["", "-", "None", "nan", "NaN"]:
                dates_to_process_set.add(dt_str)
            else:
                has_empty_field = False
                core_check_cols = ["大盤指數", "成交量金額(億)", "融資餘額", "三大法人(億)"]
                for col in core_check_cols:
                    if col in ALL_METRICS:
                        val_str = str(row_vals.get(col, "-")).strip()
                        if val_str in ["", "-", "None", "nan", "NaN"]:
                            has_empty_field = True
                            break
                if has_empty_field:
                    dates_to_process_set.add(dt_str)

    missing_dates = list(dates_to_process_set)

    if missing_dates:
        total_missing = len(missing_dates)
        progress_bar = st.progress(0, text=f"⚡ 正在智慧補齊現有日期的缺漏資料 (共 {total_missing} 筆)...")
        
        # 【修正重點 1】：降低同時發動的執行緒數（改為 3），避免瞬間大量請求觸發伺服器防火牆封鎖
        max_workers = 3
        batch_size = 6  # 每批處理 6 筆後強制暫停
        completed_count = 0

        # 將 missing_dates 切成小批次
        batches = [missing_dates[i:i + batch_size] for i in range(0, len(missing_dates), batch_size)]

        for b_idx, batch in enumerate(batches):
            # 【修正重點 2】：每一批次強制重建一個全新的 Session 與隨機延遲，防止 Session 汙染或遭 IP 標記
            shared_session = get_robust_session()
            
            def thread_task(dt_str):
                date_param = dt_str.replace("-", "")
                existing_row = cache_dict.get(dt_str, {})
                
                # 【修正重點 3】：加入防爬蟲隨機緩衝時間 (0.3 ~ 0.8秒)
                time.sleep(random.uniform(0.3, 0.8))
                
                real_data = None
                try:
                    real_data = fetch_all_stock_data(date_param, external_session=shared_session)
                except Exception:
                    real_data = None
                
                if real_data is None or real_data.get("大盤指數") is None:
                    old_idx = str(existing_row.get("大盤指數", "-")).strip()
                    if old_idx not in ["", "-", "None", "nan", "NaN", "股市未開盤"]:
                        return dt_str, existing_row
                    
                    row_data = {"日期": add_weekday_to_date_str(dt_str)}
                    row_data["大盤指數"] = "股市未開盤"
                    for col in ALL_METRICS:
                        if col != "大盤指數":
                            row_data[col] = "-"
                    return dt_str, row_data
                else:
                    row_data = {"日期": add_weekday_to_date_str(dt_str)}
                    for col in ALL_METRICS:
                        if col in ["成交量倍數", "外資累積", "三大法人累積", "借券賣出變動比", "訊號燈"]:
                            row_data[col] = "-"
                            continue
                        
                        new_val = real_data.get(col, "-")
                        old_val = existing_row.get(col, "-")
                        
                        if old_val not in ["", "-", "None", None, "nan", "NaN", "股市未開盤"]:
                            row_data[col] = new_val if new_val not in [None, "-", ""] else old_val
                        else:
                            row_data[col] = new_val if new_val not in [None, ""] else "-"
                    return dt_str, row_data

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_date = {executor.submit(thread_task, dt): dt for dt in batch}
                for future in as_completed(future_to_date):
                    try:
                        dt_str, row_data = future.result()
                        cache_dict[dt_str] = row_data
                    except Exception:
                        pass
                    completed_count += 1
                    progress_bar.progress(
                        min(completed_count / total_missing, 1.0),
                        text=f"⚡ 正在批次補齊缺漏資料 ({completed_count}/{total_missing})..."
                    )
            
            # 【修正重點 4】：每批之間休息 0.8 ~ 1.2 秒，讓伺服器不會覺得遭受惡意攻擊
            if b_idx < len(batches) - 1:
                time.sleep(random.uniform(0.8, 1.2))

        progress_bar.empty()

    final_output = []
    check_day = datetime.now()
    loop_count = 0
    
    while len(final_output) < 90 and loop_count < 180:
        loop_count += 1
        dt_str = check_day.strftime("%Y-%m-%d")
        if check_day.weekday() < 5:
            if dt_str in cache_dict:
                row_vals = cache_dict[dt_str]
            else:
                row_vals = {"日期": add_weekday_to_date_str(dt_str)}
                row_vals["大盤指數"] = "股市未開盤"
                for col in ALL_METRICS:
                    if col != "大盤指數":
                        row_vals[col] = "-"
                cache_dict[dt_str] = row_vals
            
            row_vals["日期"] = add_weekday_to_date_str(dt_str)
            final_output.append(row_vals)
            
        check_day -= timedelta(days=1)

    df_final = pd.DataFrame(final_output)
    if not df_final.empty:
        df_final["日期"] = df_final["日期"].apply(lambda x: add_weekday_to_date_str(x.split("(")[0]))
        df_final = calculate_derived_metrics(df_final)
    
    local_write_csv(df_final)
    return df_final

def generate_today_metrics(last_row):
    today_dt = datetime.now()
    today_str = today_dt.strftime("%Y-%m-%d")
    try:
        live_data = fetch_all_stock_data(today_dt.strftime("%Y%m%d"))
    except Exception:
        live_data = None
        
    if live_data is None or live_data.get("大盤指數") is None: return None
    row_data = {"日期": add_weekday_to_date_str(today_str)}
    
    for col in ALL_METRICS:
        if col not in ["成交量倍數", "外資累積", "三大法人累積", "借券賣出變動比", "訊號燈"]:
            row_data[col] = live_data.get(col, "-")
    return row_data

def render_custom_html_table(df, visible_metrics):
    html = ['<div class="custom-table-container"><table class="custom-table">']
    
    sorted_visible_metrics = [m for m in ALL_METRICS if m in visible_metrics]
    
    group_counts = {}
    group_titles = {
        "g_ind": "大盤/期貨資訊",
        "g_three": "三大法人進出",
        "g_margin": "融資/融券",
        "g_oi": "未平倉",
        "g_default": "違約交割",
        "g_short": "借券賣出"
    }
    
    for col in sorted_visible_metrics:
        if col in COL_GROUP_MAPPING:
            grp_id, _, _ = COL_GROUP_MAPPING[col]
            group_counts[grp_id] = group_counts.get(grp_id, 0) + 1

    html.append('<thead><tr><th rowspan="2" class="sticky-corner">基本<br>日期</th>')
    for grp_id in GROUP_ORDER_IDS:
        cnt = group_counts.get(grp_id, 0)
        if cnt > 0:
            html.append(f'<th colspan="{cnt}">{group_titles[grp_id]}</th>')
    html.append('</tr><tr>')

    for col in sorted_visible_metrics:
        if col in COL_GROUP_MAPPING:
            _, _, col_label = COL_GROUP_MAPPING[col]
            html.append(f'<th>{col_label}</th>')
    html.append('</tr></thead><tbody>')

    red_green_metrics = [
        "大盤改變率", "融資改變率", "外資買賣力度", 
        "三大法人(億)", "融資增減", "借券賣出變動比", 
        "融券增減"
    ]

    for _, row in df.iterrows():
        html.append('<tr>')
        html.append(f'<td class="date-cell">{row.get("日期", "-")}</td>')
        for col in sorted_visible_metrics:
            raw_val = str(row.get(col, "-")).strip()
            val_str = clean_unit_text(raw_val)
            
            if raw_val == "股市未開盤":
                if col == "大盤指數":
                    html.append('<td class="nodata-cell">股市未開盤</td>')
                else:
                    html.append('<td class="nodata-cell">-</td>')
                continue

            if val_str in ["-", "無交易數據", "", "None", "nan", "NaN", "休市", "假日", "颱風"]:
                html.append(f'<td class="nodata-cell">{val_str}</td>')
                continue

            cell_class = "value-cell"
            color_style_class = ""
            bg_style_class = ""

            if col in red_green_metrics:
                num_val = parse_num_safe(val_str)
                if num_val is not None:
                    if num_val > 0:
                        color_style_class = "pos-val"
                    elif num_val < 0:
                        color_style_class = "neg-val"

            if col == "融資VS大盤" and row.get("_is_3day_big_green", False):
                bg_style_class = "bg-light-green"
            elif col == "融資大盤倍數":
                ratio_val = parse_num_safe(val_str)
                m_change_val = row.get("_margin_change_raw")
                if ratio_val is not None and m_change_val is not None and ratio_val >= 2.0 and m_change_val < 0:
                    bg_style_class = "bg-pink"
            elif col == "外資買賣力度":
                power_val = parse_num_safe(val_str)
                if power_val is not None:
                    if power_val > 5.0: bg_style_class = "bg-pink"
                    elif power_val < -5.0: bg_style_class = "bg-light-green"
            elif col == "外資未平倉維持率":
                maint_val = parse_num_safe(val_str)
                if maint_val is not None and maint_val <= 90.0:
                    bg_style_class = "bg-pink"
            elif col == "外資未平倉(口)":
                oi_val = parse_num_safe(val_str)
                if oi_val is not None and oi_val < 0 and row.get("_is_bottom_10p", False):
                    bg_style_class = "bg-light-green"
            elif col == "借券賣出變動比":
                s_val = parse_num_safe(val_str)
                if s_val is not None:
                    if s_val >= 3.0: bg_style_class = "bg-pink"
                    elif s_val <= -3.0: bg_style_class = "bg-light-green"
            elif col == "成交量倍數":
                v_val = parse_num_safe(val_str)
                if v_val is not None:
                    if v_val >= 1.5: bg_style_class = "bg-pink"
                    elif v_val <= 0.7: bg_style_class = "bg-light-green"
            elif col == "大盤改變率":
                d_val = parse_num_safe(val_str)
                if d_val is not None:
                    if d_val >= 2.0: bg_style_class = "bg-pink"
                    elif d_val <= -2.0: bg_style_class = "bg-light-green"
            elif col == "訊號燈":
                if val_str == "強勢軋空":
                    bg_style_class = "bg-pink"
                elif val_str == "空頭":
                    bg_style_class = "bg-light-green"

            combined_class = f"{cell_class} {color_style_class} {bg_style_class}".strip()
            html.append(f'<td class="{combined_class}">{val_str}</td>')

        html.append('</tr>')

    html.append('</tbody></table></div>')
    return "".join(html)

# -------------------------------------------------------------------------
# 全域狀態初始化
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
    df = calculate_derived_metrics(df)
    if len(df) > 90: df = df.head(90)
    local_write_csv(df)
    return df

# -------------------------------------------------------------------------
# 主介面渲染
# -------------------------------------------------------------------------
st.sidebar.title("功能選單")
menu_option = st.sidebar.radio("選擇市場/清單", options=["美股市場 US", "台股市場 TW", "🔮 自訂個股名單"], index=1)
current_market = "美股" if "美股" in menu_option else "table" if "🔮" in menu_option else "台股"

sub_tickets = list(st.session_state.store[current_market].keys())
sub_tab_labels = ["大盤" if t == "INDEX" else f"{t}-{st.session_state.store[current_market][t]['name']}" for t in sub_tickets]

add_col1, add_col2 = st.columns([3, 1])
with add_col2:
    with st.popover("＋ 新增個股分頁", use_container_width=True):
        new_code = st.text_input("輸入股票代碼 (例: 2330):").strip().upper()
        if st.button("確認新增個股", use_container_width=True):
            if new_code and new_code not in st.session_state.store[current_market]:
                with st.spinner(f"正在查詢 {new_code} 名稱與 90 天數據..."):
                    stock_real_name = fetch_stock_name(new_code)
                    new_df = load_or_fetch_ind_90_days(new_code)
                st.session_state.store[current_market][new_code] = {"name": stock_real_name, "df": new_df}
                st.rerun()

if sub_tickets:
    tabs = st.tabs(sub_tab_labels)
    for idx, tab in enumerate(tabs):
        ticket = sub_tickets[idx]
        page_info = st.session_state.store[current_market][ticket]
        
        with tab:
            if ticket == "INDEX":
                df_data = page_info["df"]
                header_col, refresh_col = st.columns([3.5, 1.5])
                with header_col:
                    st.subheader("📈 大盤指數")
                with refresh_col:
                    if st.button("⚡ 即時更新", key=f"btn_ref_{current_market}_{ticket}", use_container_width=True):
                        with st.spinner("⚡ 正在執行即時更新與缺漏數據智慧批次補齊..."):
                             updated_df = load_or_fetch_90_days_history("TW_INDEX" if current_market == "台股" else "US_INDEX")
                             st.session_state.store[current_market][ticket]["df"] = updated_df
                             st.toast("即時更新與數據補齊完成！", icon="✅")
                             st.rerun()
                
                st.markdown(
                    """
                    🔗 延伸數據：
                    <a href="https://www.wantgoo.com/stock/public-bank/trend" target="_blank">🏛️ 公股銀行進出</a>｜
                    <a href="https://www.pscnet.com.tw/pscnetStock/menuContent.do?main_id=386032846c000000ccd145898ac293b6&sub_id=38d642081a00000099f12672f4cf7d6e" target="_blank">📈 整戶融資維持率</a>｜
                    <a href="https://nstatdb.dgbas.gov.tw/dgbasAll/webMain.aspx?sys=100&funid=qryout&funid2=A018201010&outmode=8&ym=11001&ymt=11503&cycle=42&outkind=1&compmode=2.1&ratenm=%u7D71%u8A08%u503C%u53CA%u5E74%u589E%u7387&fldlst=111&codlst0=1111111111111111111&compmode=2.1&rr=q23704x&&rdm=R2632432" target="_blank">📊 國民所得/儲蓄/投資統計</a>
                    """,
                    unsafe_allow_html=True
                )

                st.markdown("""
                    <div style="background-color: #f8f9fa; border-left: 4px solid #0047AB; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 13px; color: #333333; line-height: 1.5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                    <div style="margin-bottom: 3px;">
                    📌 <span style="font-weight: bold; color: #296873;">計算公式與欄位提示說明 (Note) :</span>
                    </div>
                         • <span style="font-weight: bold; color: #296873;">大盤改變率</span> = 100% * (今日大盤指數增減 / 昨日大盤指數)。 <span style="background-color: #f8d7da; color: #842029; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&ge; 2%</span> : 大漲 | -1.5% ~ 1.5% : 盤整 | <span style="background-color: #d1e7dd; color: #0f5132; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&le; -2%</span> : 大跌。<br>
                         • <span style="font-weight: bold; color: #296873;">融資改變率</span> = 100% * (今日融資增減 / 昨日融資餘額)<br>
                         • <span style="font-weight: bold; color: #296873;">融資VS大盤</span>：當「融資改變率」&gt;「大盤改變率」時顯示「大」，反之為「小」。若 <span style="background-color: #d1e7dd; color: #0f5132; padding: 1px 5px; border-radius: 3px; font-size: 12px;">連續三天(或以上)為「大」且融資改變率皆為正數</span> : 準備到高點可以賣。<br>
                         • <span style="font-weight: bold; color: #296873;">融資大盤倍數</span> = 融資改變率是大盤改變率的幾倍。當 <span style="background-color: #f8d7da; color: #842029; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&ge; 2 且融資改變率為負數</span> : 準備到低點可以買。<br>
                         • <span style="font-weight: bold; color: #296873;">成交量倍數</span> = 成交量金額 / 近20日平均成交量金額。 <span style="background-color: #f8d7da; color: #842029; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&ge; 1.5</span> : 成交爆量 | &lt; 1.5 : 量能不足 | <span style="background-color: #d1e7dd; color: #0f5132; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&lt; 0.7</span> : 成交縮量。<br>
                         • <span style="font-weight: bold; color: #296873;">外資買賣力度</span> = 100% * (外資進出量 / 大盤成交量金額)。 <span style="background-color: #f8d7da; color: #842029; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&gt; 5%</span> : 外資做多；<span style="background-color: #d1e7dd; color: #0f5132; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&lt; -5%</span> : 外資做空。<br>
                         • <span style="font-weight: bold; color: #296873;">外資未平倉維持率</span> = 100% * (今日外資未平倉量 / 昨日外資未平倉量)。 <span style="background-color: #f8d7da; color: #842029; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&le; 90%</span> : 外資準備反手做多。<br>
                         • <span style="font-weight: bold; color: #296873;">外資未平倉</span>：抓 66 交易日的外資未平倉量由小到大排序，外資未平倉量為 <span style="background-color: #d1e7dd; color: #0f5132; padding: 1px 5px; border-radius: 3px; font-size: 12px;">負數且是前 10% 的小</span> : 不要買股票且即將要有波段震盪。<br>
                         • <span style="font-weight: bold; color: #296873;">借券賣出變動比</span> = 100 * (券賣出量 - 券賣還券) / 近20日平均成交量(千股)。 <span style="background-color: #f8d7da; color: #842029; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&ge; 3%</span> : 大量賣出 | <span style="background-color: #d1e7dd; color: #0f5132; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&le; -3%</span> : 大量還券 | &ge; 1% : 中量賣出 | &le; -1% : 中量還券。<br>
                         • <span style="font-weight: bold; color: #296873;">訊號燈觸發條件</span>（需所有條件同時成立）：<br>
                         &nbsp;&nbsp;- <span style="background-color: #d1e7dd; color: #0f5132; padding: 1px 5px; border-radius: 3px; font-weight: bold; font-size: 12px;">空頭</span>：大量賣出 + 成交爆量 + 大跌 （代表開始走空，避免做多）<br>
                         &nbsp;&nbsp;- <span style="background-color: #f8d7da; color: #842029; padding: 1px 5px; border-radius: 3px; font-weight: bold; font-size: 12px;">強勢軋空</span>：大量還券 + 成交爆量 + 大漲 （代表開始走多，避免借券）<br>
                         &nbsp;&nbsp;- <span style="font-weight: bold;">籌碼沉澱</span>：中量還券 + 成交縮量 + 盤整 （代表等待突破，未來不明）<br>
                         &nbsp;&nbsp;- <span style="font-weight: bold;">高位壓盤</span>：中量賣出 + 量能不足 + 盤整 （代表向上動能不足，觀望不動作）<br>
                         • <span style="font-weight: bold; color: #296873;">公股買賣力度</span>: 100*(公股銀行進出/大盤成交量) > 1.5% >> 表示機會(準備低點，國發基金開始護盤)
                    </div>
                    """, unsafe_allow_html=True)
                
                col_key = f"col_select_{current_market}_{ticket}"
                if col_key not in st.session_state:
                    st.session_state[col_key] = DEFAULT_VISIBLE_METRICS

                df_data = calculate_derived_metrics(df_data)

                selected_visible_columns = [c for c in st.session_state[col_key] if c in ALL_METRICS]
                
                table_html = render_custom_html_table(df_data, selected_visible_columns)
                st.markdown(table_html, unsafe_allow_html=True)

                st.multiselect(
                    "⚙️ 調整表格顯示欄位（點擊可切換隱藏 / 顯示）：",
                    options=ALL_METRICS,
                    default=selected_visible_columns,
                    key=col_key
                )
                
                st.markdown("---")
                
                excluded_from_options = [
                    "大盤指數", "台指期近一", "成交量(千股)", "成交量金額(億)", 
                    "大盤改變率", "融資改變率", 
                    "融資VS大盤", "融資大盤倍數", "訊號燈"
                ]
                available_metrics = [c for c in ALL_METRICS if c not in excluded_from_options]
                
                selected_charts = st.multiselect(
                    "請選擇要額外開啟的數據圖表：", 
                    options=available_metrics, 
                    max_selections=3, 
                    key=f"multi_{current_market}_{ticket}"
                )
                
                chart_df = df_data.copy().iloc[::-1].reset_index(drop=True)
                x_vals = chart_df["日期"]
                
                num_plots = 2 + len(selected_charts)
                
                subplot_titles = [
                    "📍 大盤 / 台指期 / 成交量金額(億)",
                    "📍 大盤改變率 vs 融資改變率 (%)"
                ] + [f"📍 {m} ({get_unit_str(m)})" for m in selected_charts]

                specs = [[{"secondary_y": True}]] + [[{"secondary_y": False}]] * (num_plots - 1)

                fig = make_subplots(
                    rows=num_plots, 
                    cols=1, 
                    shared_xaxes=True, 
                    vertical_spacing=0.08, 
                    subplot_titles=subplot_titles,
                    specs=specs
                )

                y_idx = chart_df["大盤指數"].apply(parse_num_safe)
                y_fut = chart_df["台指期近一"].apply(parse_num_safe)
                y_vol_amt = chart_df["成交量金額(億)"].apply(parse_num_safe)

                fig.add_trace(go.Scatter(
                    x=x_vals, y=y_idx, mode='lines', name='大盤指數',
                    line=dict(color='#1f77b4', width=2), connectgaps=True,
                    hovertemplate="<b>%{x}</b><br>大盤指數: %{y:,.2f} 點<extra></extra>"
                ), row=1, col=1, secondary_y=False)

                fig.add_trace(go.Scatter(
                    x=x_vals, y=y_fut, mode='lines', name='台指期近一',
                    line=dict(color='#ff7f0e', width=1.8, dash='dot'), connectgaps=True,
                    hovertemplate="<b>%{x}</b><br>台指期近一: %{y:,.2f} 點<extra></extra>"
                ), row=1, col=1, secondary_y=False)

                fig.add_trace(go.Bar(
                    x=x_vals, y=y_vol_amt, name='成交量金額(億)',
                    marker_color='rgba(100, 110, 120, 0.3)',
                    hovertemplate="<b>%{x}</b><br>成交量金額(億): %{y:,.2f} 億<extra></extra>"
                ), row=1, col=1, secondary_y=True)

                fig.update_yaxes(title_text="指數 (點)", row=1, col=1, secondary_y=False, showgrid=True)
                fig.update_yaxes(title_text="成交量金額(億)", row=1, col=1, secondary_y=True, showgrid=False)

                y_idx_change = chart_df["大盤改變率"].apply(parse_num_safe)
                y_margin_change = chart_df["融資改變率"].apply(parse_num_safe)
                ratios = chart_df["融資大盤倍數"].apply(lambda x: str(x) if x is not None else "-")

                hover_text_idx = [f"<b>{x}</b><br>大盤改變率: {c:.2f}%" if c is not None else f"<b>{x}</b><br>大盤改變率: - " for x, c in zip(x_vals, y_idx_change)]
                hover_text_margin = [
                    f"<b>{x}</b><br>融資改變率: {m:.2f}%<br>融資大盤倍數: {r}" if m is not None else f"<b>{x}</b><br>融資改變率: -<br>融資大盤倍數: {r}" 
                    for x, m, r in zip(x_vals, y_margin_change, ratios)
                ]

                fig.add_trace(go.Scatter(
                    x=x_vals, y=y_idx_change, mode='lines', name='大盤改變率',
                    line=dict(color='#2ca02c', width=2), connectgaps=True,
                    hovertext=hover_text_idx, hoverinfo="text"
                ), row=2, col=1)

                fig.add_trace(go.Scatter(
                    x=x_vals, y=y_margin_change, mode='lines', name='融資改變率',
                    line=dict(color='#d62728', width=2), connectgaps=True,
                    hovertext=hover_text_margin, hoverinfo="text"
                ), row=2, col=1)

                for i, metric in enumerate(selected_charts):
                    row_idx = i + 3
                    numeric_y = chart_df[metric].apply(parse_num_safe)
                    
                    valid_y = pd.Series([v for v in numeric_y if v is not None])
                    if not valid_y.empty and valid_y.min() < 0 and valid_y.max() > 0:
                        y_pos = [v if (v is not None and v >= 0) else (0 if v is not None else np.nan) for v in numeric_y]
                        y_neg = [v if (v is not None and v <= 0) else (0 if v is not None else np.nan) for v in numeric_y]
                        fig.add_trace(go.Scatter(x=x_vals, y=y_pos, mode='lines', fill='tozeroy', fillcolor='rgba(255, 77, 79, 0.25)', line=dict(width=0), connectgaps=True, showlegend=False, hoverinfo='skip'), row=row_idx, col=1)
                        fig.add_trace(go.Scatter(x=x_vals, y=y_neg, mode='lines', fill='tozeroy', fillcolor='rgba(82, 196, 26, 0.25)', line=dict(width=0), connectgaps=True, showlegend=False, hoverinfo='skip'), row=row_idx, col=1)

                    fig.add_trace(go.Scatter(
                        x=x_vals, y=numeric_y, mode='lines', line=dict(color='#007bff', width=2), 
                        name=metric, connectgaps=True, 
                        hovertemplate=f"<b>%{{x}}</b><br>{metric}: %{{y:,.2f}} {get_unit_str(metric)}<extra></extra>"
                    ), row=row_idx, col=1)

                    if metric == "外資買賣力度":
                        fig.add_hline(y=5.0, line=dict(color="red", width=2, dash="dash"), row=row_idx, col=1, annotation_text="+5%", annotation_position="top left")
                        fig.add_hline(y=-5.0, line=dict(color="green", width=2, dash="dash"), row=row_idx, col=1, annotation_text="-5%", annotation_position="bottom left")

                    if metric == "外資未平倉維持率":
                        fig.add_hline(y=90.0, line=dict(color="red", width=2, dash="dash"), row=row_idx, col=1, annotation_text="90% (警戒線)", annotation_position="top left")
                        fig.add_hline(y=85.0, line=dict(color="darkred", width=2, dash="solid"), row=row_idx, col=1, annotation_text="85% (強烈線)", annotation_position="bottom left")

                for r in range(1, num_plots + 1):
                    fig.update_xaxes(
                        type='category', showgrid=True, 
                        tickangle=-45 if r == num_plots else 0, 
                        showspikes=True, spikemode="across", spikesnap="cursor", 
                        spikethickness=1, spikecolor="#666666", spikedash="dash", 
                        row=r, col=1
                    )
                    fig.update_yaxes(showgrid=True, zeroline=True, zerolinewidth=1.5, zerolinecolor="gray", row=r, col=1)

                fig.update_layout(
                    height=200 * num_plots + 100, 
                    margin=dict(l=10, r=10, t=30, b=20), 
                    hovermode="x unified", 
                    showlegend=True, 
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    dragmode=False
                )
                
                for annotation in fig['layout']['annotations']:
                    annotation['x'] = 0
                    annotation['xanchor'] = 'left'
                    annotation['font'] = dict(size=13, color="#000000", family="Arial, sans-serif")

                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'scrollZoom': False, 'responsive': True})

            else:
                render_individual_tab(current_market, ticket, page_info)