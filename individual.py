import os
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from scrapers_ind import fetch_merged_stock_data

WEEK_DAYS = ["一", "二", "三", "四", "五", "六", "日"]
CACHE_DIR = "data_cache"

# =========================================================================
# 1. 完整欄位順序
# =========================================================================
IND_COLUMNS_ORDER = [
    "訊號燈", "收盤價", "美股收盤", "開盤價", "融資VS個股", "融資個股倍數",
    "漲/跌幅", "美股漲/跌", "成交量", "美股成交", "成交量倍數", "最高價", "最低價", "本益比",
    "月線", "季線", "半年線", "年線",
    "外資進出", "外資買賣力度", "外資累積", "投信進出", "自營商進出", "三大法人", "三大法人累積",
    "融資餘額(張)", "融資增減", "融資改變率", "融券餘額(張)", "融券增減", "券資比(%)",
    "券賣餘額", "券賣出量", "券賣還券", "借券賣出變動比"
]

# 2. 預設顯示欄位順序
DEFAULT_VISIBLE_COLUMNS = [
    "訊號燈", "收盤價", "美股收盤", "融資VS個股", "融資個股倍數",
    "漲/跌幅", "美股漲/跌", "成交量", "成交量倍數", "本益比",
    "外資進出", "外資買賣力度", "三大法人",
    "融資餘額(張)", "融資增減", "融資改變率",
    "券賣餘額", "券賣出量", "券賣還券", "借券賣出變動比"
]

# 3. 字體顯色指標
COLOR_METRICS = [
    "融資個股倍數", "漲/跌幅", "漲跌幅", "美股漲/跌", "美股漲/跌幅", 
    "外資買賣力度", "融資增減", "融券增減", "融資改變率"
]

AVAILABLE_CHART_METRICS = [
    "漲/跌幅", "成交量", "成交量倍數", "借券賣出變動比", "本益比", 
    "外資進出", "外資買賣力度", "外資累積", "法人進出(投信)", "自營商進出", "三大法人", "三大法人累積", 
    "融資餘額(張)", "融資增減", "融資改變率", "融券餘額(張)", "融券增減", "券資比(%)",
    "券賣出量", "券賣還券", "券賣餘額"
]

IND_GROUP_MAPPING = {
    "訊號燈": ("g1", "個股資訊", "訊號燈"),
    "收盤價": ("g1", "個股資訊", "收盤價"),
    "美股收盤": ("g1", "個股資訊", "美股收盤"),
    "開盤價": ("g1", "個股資訊", "開盤價"),
    "融資VS個股": ("g1", "個股資訊", "融資VS個股"),
    "融資個股倍數": ("g1", "個股資訊", "融資個股倍數"),
    "漲/跌幅": ("g1", "個股資訊", "漲/跌幅"),
    "美股漲/跌": ("g1", "個股資訊", "美股漲/跌"),
    "成交量": ("g1", "個股資訊", "成交量(股)"),
    "美股成交": ("g1", "個股資訊", "美股成交"),
    "成交量倍數": ("g1", "個股資訊", "成交量倍數"),
    "最高價": ("g1", "個股資訊", "最高價"),
    "最低價": ("g1", "個股資訊", "最低價"),
    "本益比": ("g1", "個股資訊", "本益比"),

    "月線": ("g2", "技術", "月線"),
    "季線": ("g2", "技術", "季線"),
    "半年線": ("g2", "技術", "半年線"),
    "年線": ("g2", "技術", "年線"),

    "外資進出": ("g3", "三大法人進出", "外資進出(股)"),
    "外資買賣力度": ("g3", "三大法人進出", "外資買賣力度"),
    "外資累積": ("g3", "三大法人進出", "外資累積"),
    "投信進出": ("g3", "三大法人進出", "投信進出(股)"),
    "自營商進出": ("g3", "三大法人進出", "自營商進出(股)"),
    "三大法人": ("g3", "三大法人進出", "三大法人(股)"),
    "三大法人累積": ("g3", "三大法人進出", "三大法人累積"),

    "融資餘額(張)": ("g4", "融資/融券", "融資餘額(張)"),
    "融資增減": ("g4", "融資/融券", "融資增減"),
    "融資改變率": ("g4", "融資/融券", "融資改變率"),
    "融券餘額(張)": ("g4", "融資/融券", "融券餘額(張)"),
    "融券增減": ("g4", "融資/融券", "融券增減"),
    "券資比(%)": ("g4", "融資/融券", "券資比(%)"),

    "券賣餘額": ("g5", "借券賣出", "券賣餘額(股)"),
    "券賣出量": ("g5", "借券賣出", "券賣出量(股)"),
    "券賣還券": ("g5", "借券賣出", "券賣還券(股)"),
    "借券賣出變動比": ("g5", "借券賣出", "借券賣出變動比")
}

def get_ind_unit_str(metric_name):
    if "漲/跌" in metric_name or "漲跌幅" in metric_name or "券資比" in metric_name or "率" in metric_name or "力度" in metric_name or "變動比" in metric_name:
        return "%"
    elif "本益比" in metric_name or "倍數" in metric_name:
        return "倍"
    elif "美股成交" in metric_name:
        return "股"
    elif "美股" in metric_name:
        return "美元"
    elif "進出" in metric_name or "累積" in metric_name or "餘額" in metric_name or "增減" in metric_name or "成交量" in metric_name or "借券" in metric_name or "券賣" in metric_name:
        return "張"
    else:
        return "元"

def get_cache_csv_path(stock_id):
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{stock_id}_cache.csv")

def load_stock_csv_cache(stock_id):
    file_path = get_cache_csv_path(stock_id)
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path, dtype=str)
            if "pure_date" in df.columns:
                return df.set_index("pure_date").to_dict(orient="index")
        except Exception:
            return {}
    return {}

def save_stock_csv_cache(stock_id, cache_data):
    file_path = get_cache_csv_path(stock_id)
    try:
        rows = []
        for p_date, row in cache_data.items():
            r = dict(row)
            r["pure_date"] = p_date
            rows.append(r)
        
        df_save = pd.DataFrame(rows)
        if "pure_date" in df_save.columns:
            df_save = df_save.sort_values(by="pure_date", ascending=False)
            
        df_save.to_csv(file_path, index=False, encoding="utf-8-sig")
    except Exception as e:
        print(f"快取儲存失敗: {e}")
        
def parse_num(val):
    if isinstance(val, (pd.Series, np.ndarray, list)):
        if len(val) > 0:
            val = val[0]
        else:
            return None

    if pd.isna(val) or val is None:
        return None

    val_str = str(val).replace("億", "").replace("張", "").replace("%", "").replace("口", "").replace("百萬", "").replace(",", "").replace("+", "").strip()
    if val_str in ["", "-", "None", "N/A", "NaN", "nan", "抓取失敗", "無交易數據", "股市未開盤", "null"]:
        return None
    try:
        return float(val_str)
    except Exception:
        return None

def format_cell(x, col_name=None, is_first_col=False):
    if isinstance(x, (pd.Series, np.ndarray, list)):
        x = x[0] if len(x) > 0 else "-"

    val_str = str(x).strip() if x is not None else ""
    
    if col_name == "收盤價":
        if val_str in ["股市未開盤", "-", "", "None", "N/A", "nan", "NaN", "null"]:
            return "股市未開盤"

    if val_str in ["股市未開盤", "-", "", "None", "N/A", "nan", "NaN", "null"]:
        return "-"

    if col_name in ["融資VS個股", "訊號燈"]:
        return str(x) if val_str not in ["", "-", "None", "nan", "NaN"] else "-"
        
    num = parse_num(x)
    if num is None:
        return "股市未開盤" if col_name == "收盤價" else "-"
        
    if col_name in ["漲/跌幅", "漲跌幅", "美股漲/跌", "美股漲/跌幅", "融資改變率", "外資買賣力度", "借券賣出變動比"]:
        return f"{num:,.2f}%"
    
    # 針對要求無小數點的欄位採用整數格式化
    no_decimal_cols = [
        "成交量", "券賣餘額", "券賣出量", "券賣還券", 
        "外資進出", "投信進出", "自營商進出", 
        "外資累積", "三大法人累積", "三大法人",
        "融資餘額(張)", "融券餘額(張)"
    ]
    if col_name in no_decimal_cols:
        return f"{int(round(num)):,}"

    return f"{num:,.2f}"

def add_weekday(date_str):
    if "(" in date_str:
        return date_str
    try:
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return f"{date_str}({WEEK_DAYS[dt.weekday()]})"
    except Exception:
        return date_str

def get_exact_val(data_dict, keys):
    if not isinstance(data_dict, dict):
        return None
    for k in keys:
        if k in data_dict:
            v = data_dict[k]
            if parse_num(v) is not None or str(v).strip() not in ["", "-", "None", "N/A", "nan"]:
                return v

    for dict_k, v in data_dict.items():
        for target_k in keys:
            if target_k in str(dict_k):
                if parse_num(v) is not None or str(v).strip() not in ["", "-", "None", "N/A", "nan"]:
                    return v
    return None

def format_scraped_dict_to_row(raw_data, date_str):
    if not raw_data or not isinstance(raw_data, dict):
        row = {col: "股市未開盤" for col in IND_COLUMNS_ORDER}
        row["pure_date"] = date_str
        row["日期"] = add_weekday(date_str)
        return row

    tw_open   = get_exact_val(raw_data, ["台股開盤價"])
    tw_close  = get_exact_val(raw_data, ["台股收盤價"])
    
    if parse_num(tw_open) is None and parse_num(tw_close) is None:
        row = {col: "股市未開盤" for col in IND_COLUMNS_ORDER}
        row["pure_date"] = date_str
        row["日期"] = add_weekday(date_str)
        return row

    tw_change = get_exact_val(raw_data, ["台股漲跌幅"])
    tw_vol    = get_exact_val(raw_data, ["台股成交量(股)"])
    tw_high   = get_exact_val(raw_data, ["台股最高價", "最高價"])
    tw_low    = get_exact_val(raw_data, ["台股最低價", "最低價"])

    us_close  = get_exact_val(raw_data, ["美股價(美元)"])
    us_change = get_exact_val(raw_data, ["美股漲跌幅"])
    us_vol    = get_exact_val(raw_data, ["美股成交量(股)"])

    foreign = get_exact_val(raw_data, ["外資進出(股)", "外資買賣超", "外資進出", "外資"])
    investment_trust = get_exact_val(raw_data, ["【來源：T86】投信進出(股)", "投信進出(股)", "投信買賣超", "投信進出", "投信"])
    dealer = get_exact_val(raw_data, ["自營商進出(股)", "自營商買賣超", "自營商進出", "自營商"])
    institutional_total = get_exact_val(raw_data, ["三大法人進出(股)", "三大法人買賣超", "三大法人"])

    # 融資融券與券賣欄位精確抓取
    margin_bal = get_exact_val(raw_data, ["【來源：MI_MARGN】融資餘額(張)", "融資餘額(張)", "融資餘額"])
    margin_chg = get_exact_val(raw_data, ["【來源：MI_MARGN】融資增減(張)", "融資增減(張)", "融資增減"])
    short_bal  = get_exact_val(raw_data, ["【來源：MI_MARGN】融券餘額(張)", "融券餘額(張)", "融券餘額"])
    short_chg  = get_exact_val(raw_data, ["【來源：MI_MARGN】融券增減(張)", "融券增減(張)", "融券增減"])
    short_ratio= get_exact_val(raw_data, ["【來源：MI_MARGN】券資比(%)", "券資比(%)", "券資比"])

    sbl_sell = get_exact_val(raw_data, ["券賣出量(股)", "券賣出量(千張)", "借券賣出"])
    sbl_return = get_exact_val(raw_data, ["券賣還券(股)", "券賣還券量(千張)", "借券還券"])
    sbl_bal = get_exact_val(raw_data, ["券賣餘額(股)", "券賣餘額(千張)", "借券賣出餘額"])

    return {
        "pure_date": date_str,
        "日期": add_weekday(date_str),
        "訊號燈": get_exact_val(raw_data, ["訊號燈", "燈號"]),
        "開盤價": tw_open,
        "收盤價": tw_close,
        "美股收盤": us_close,
        "漲/跌幅": tw_change,
        "美股漲/跌": us_change,
        "成交量": tw_vol,
        "美股成交": us_vol,
        "最高價": tw_high,
        "最低價": tw_low,
        "本益比": get_exact_val(raw_data, ["本益比"]),
        "月線": get_exact_val(raw_data, ["月線(20MA)", "月線"]),
        "季線": get_exact_val(raw_data, ["季線(60MA)", "季線"]),
        "半年線": get_exact_val(raw_data, ["半年線(120MA)", "120MA"]),
        "年線": get_exact_val(raw_data, ["年線(240MA)", "240MA"]),
        "外資進出": foreign,
        "投信進出": investment_trust,  # 修正投信對應
        "自營商進出": dealer,
        "三大法人": institutional_total,
        "融資餘額(張)": margin_bal,
        "融資增減": margin_chg,
        "融券餘額(張)": short_bal,    # 修正融券餘額
        "融券增減": short_chg,      # 修正融券增減
        "券資比(%)": short_ratio,   # 修正券資比
        "券賣餘額": sbl_bal,
        "券賣出量": sbl_sell,
        "券賣還券": sbl_return,
    }

def process_individual_dataframe(df):
    if df is None or df.empty:
        return df

    df_calc = df.copy()
    df_calc = df_calc.loc[:, ~df_calc.columns.duplicated()].copy()

    for col in IND_COLUMNS_ORDER:
        if col not in df_calc.columns:
            df_calc[col] = None

    foreign_nums = df_calc["外資進出"].apply(lambda v: parse_num(v) or 0.0)[::-1]
    inst_nums = df_calc["三大法人"].apply(lambda v: parse_num(v) or 0.0)[::-1]
    df_calc["外資累積"] = np.cumsum(foreign_nums).round(2)[::-1]
    df_calc["三大法人累積"] = np.cumsum(inst_nums).round(2)[::-1]

    df_asc = df_calc.iloc[::-1].copy()

    margin_bal = df_asc["融資餘額(張)"].apply(parse_num)
    margin_diff = df_asc["融資增減"].apply(parse_num)
    vol_val = df_asc["成交量"].apply(parse_num)

    margin_bal_filled = margin_bal.ffill()
    margin_bal_prev = margin_bal_filled.shift(1)

    margin_change_rate = np.where(
        (margin_bal_prev.notna()) & (margin_bal_prev != 0) & (margin_diff.notna()),
        100.0 * (margin_diff / margin_bal_prev),
        np.nan
    )
    df_asc["融資改變率"] = margin_change_rate

    change_col = "漲/跌幅" if "漲/跌幅" in df_asc.columns else None
    stock_change_rate = df_asc[change_col].apply(parse_num) if change_col else pd.Series(np.nan, index=df_asc.index)

    df_asc["融資VS個股"] = np.where(
        (margin_change_rate > stock_change_rate), "大",
        np.where((margin_change_rate < stock_change_rate), "小", "-")
    )

    vs_val = df_asc["融資VS個股"].values
    chg_rate_val = df_asc["融資改變率"].values
    streak_flags = []
    current_streak = 0
    for v, r in zip(vs_val, chg_rate_val):
        if v == "大" and pd.notna(r) and r > 0:
            current_streak += 1
        else:
            current_streak = 0
        streak_flags.append(current_streak >= 3)
    df_asc["融資VS個股_底色"] = streak_flags

    stock_multiple = np.where(
        (stock_change_rate.notna()) & (stock_change_rate != 0) & (~np.isnan(margin_change_rate)),
        margin_change_rate / stock_change_rate,
        np.nan
    )
    df_asc["融資個股倍數"] = stock_multiple

    foreign_val = df_asc["外資進出"].apply(parse_num)
    df_asc["外資買賣力度"] = np.where(
        (vol_val.notna()) & (vol_val != 0) & (foreign_val.notna()),
        100.0 * (foreign_val / vol_val),
        np.nan
    )

    sbl_sell_val = df_asc["券賣出量"].apply(parse_num)
    sbl_return_val = df_asc["券賣還券"].apply(parse_num)
    
    vol_val_clean = vol_val.dropna()
    vol_20d_sum_series = vol_val_clean.rolling(window=20, min_periods=1).sum()
    avg_vol_20 = vol_20d_sum_series / np.minimum(vol_val_clean.rolling(window=20, min_periods=1).count(), 20)
    
    vol_20d_sum_reindexed = vol_20d_sum_series.reindex(df_asc.index).ffill()
    avg_vol_20 = avg_vol_20.reindex(df_asc.index).ffill()

    df_asc["vol_20d_sum"] = vol_20d_sum_reindexed

    net_sbl_sell = np.where(
        (sbl_sell_val.notna()) & (sbl_return_val.notna()),
        sbl_sell_val - sbl_return_val,
        np.nan
    )

    sbl_change_ratio = np.where(
        (avg_vol_20.notna()) & (avg_vol_20 != 0) & (~np.isnan(net_sbl_sell)),
        100.0 * (net_sbl_sell / avg_vol_20),
        np.nan
    )
    df_asc["借券賣出變動比"] = sbl_change_ratio

    vol_multiple = np.where(
        (avg_vol_20.notna()) & (avg_vol_20 != 0) & (vol_val.notna()),
        vol_val / avg_vol_20,
        np.nan
    )
    df_asc["成交量倍數"] = vol_multiple

    signals = []
    for r_idx in range(len(df_asc)):
        ratio = sbl_change_ratio[r_idx]
        mult = vol_multiple[r_idx]
        chg = stock_change_rate.iloc[r_idx]

        if pd.isna(ratio) or pd.isna(mult) or pd.isna(chg):
            signals.append("")
            continue

        is_heavy_sell = ratio >= 3.0
        is_heavy_return = ratio <= -3.0
        is_mid_sell = ratio >= 1.0
        is_mid_return = ratio <= -1.0

        is_vol_burst = mult >= 1.5
        is_vol_lack = mult <= 1.0
        is_vol_shrink = mult <= 0.7

        is_big_rise = chg >= 2.0
        is_big_drop = chg <= -2.0
        is_consolidation = -1.5 <= chg <= 1.5

        if is_heavy_sell and is_vol_burst and is_big_drop:
            signals.append("空頭")
        elif is_heavy_return and is_vol_burst and is_big_rise:
            signals.append("強勢軋空")
        elif is_mid_return and is_vol_shrink and is_consolidation:
            signals.append("籌碼沉澱")
        elif is_mid_sell and is_vol_lack and is_consolidation:
            signals.append("高位壓盤")
        else:
            signals.append("")

    df_asc["訊號燈"] = signals

    df_calc = df_asc.iloc[::-1].copy()

    if "pure_date" in df_calc.columns:
        df_calc = df_calc.drop(columns=["pure_date"], errors="ignore")

    final_cols = ["日期"] + [c for c in IND_COLUMNS_ORDER if c in df_calc.columns] + ["融資VS個股_底色", "vol_20d_sum"]
    df_final = df_calc.loc[:, ~df_calc.columns.duplicated()]
    
    return df_final[[c for c in final_cols if c in df_final.columns]]

def load_or_fetch_ind_90_days(stock_id, force_refetch=False):
    cache_data = {} if force_refetch else load_stock_csv_cache(stock_id)
    
    trading_dates = []
    now = datetime.now()
    check_day = now

    if now.hour < 14:
        check_day = now - timedelta(days=1)
    
    while len(trading_dates) < 90:
        if check_day.weekday() < 5:
            trading_dates.append(check_day.strftime("%Y-%m-%d"))
        check_day -= timedelta(days=1)

    missing_dates = []
    for formatted_date in trading_dates:
        d_str = formatted_date.replace("-", "")
        if force_refetch or formatted_date not in cache_data:
            missing_dates.append(d_str)
        else:
            cached_close = cache_data[formatted_date].get("收盤價")
            # 只要收盤價無法解析出數值（包含「股市未開盤」、"-" 或空值），每次打開或更新時都重新查找
            if parse_num(cached_close) is None:
                missing_dates.append(d_str)

    if missing_dates:
        progress_bar = st.progress(0, text=f"⚡ 正在擷取 {stock_id} 缺漏的 {len(missing_dates)} 個交易日數據...")
        
        def task(d_str):
            formatted_date = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
            raw = fetch_merged_stock_data(stock_id, d_str)
            return formatted_date, format_scraped_dict_to_row(raw, formatted_date)

        completed = 0
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(task, d) for d in missing_dates]
            for f in as_completed(futures):
                completed += 1
                progress_bar.progress(min(completed / len(missing_dates), 1.0))
                formatted_date, res_row = f.result()
                cache_data[formatted_date] = res_row

        progress_bar.empty()

    ordered_rows = []
    for formatted_date in trading_dates:
        if formatted_date in cache_data:
            row = dict(cache_data[formatted_date])
            row["pure_date"] = formatted_date
            row["日期"] = add_weekday(formatted_date)
            ordered_rows.append(row)
        else:
            empty_row = {col: "股市未開盤" for col in IND_COLUMNS_ORDER}
            empty_row["pure_date"] = formatted_date
            empty_row["日期"] = add_weekday(formatted_date)
            ordered_rows.append(empty_row)

    df_all = pd.DataFrame(ordered_rows)
    processed_df = process_individual_dataframe(df_all)

    for idx, row in processed_df.iterrows():
        p_date = row["日期"].split("(")[0]
        if p_date in cache_data:
            cache_data[p_date]["vol_20d_sum"] = row.get("vol_20d_sum")
            cache_data[p_date]["借券賣出變動比"] = row.get("借券賣出變動比")

    save_stock_csv_cache(stock_id, cache_data)
    return processed_df

def render_ind_custom_html_table(df, visible_metrics):
    html = ['<div class="custom-table-container"><table class="custom-table">']
    
    header_groups = []
    for col in visible_metrics:
        if col in IND_GROUP_MAPPING:
            grp_id, grp_title, _ = IND_GROUP_MAPPING[col]
            if header_groups and header_groups[-1]["id"] == grp_id:
                header_groups[-1]["span"] += 1
            else:
                header_groups.append({"id": grp_id, "title": grp_title, "span": 1})

    html.append('<thead><tr><th rowspan="2" class="sticky-corner">基本<br>日期</th>')
    for grp in header_groups:
        html.append(f'<th colspan="{grp["span"]}">{grp["title"]}</th>')
    html.append('</tr><tr>')

    for col in visible_metrics:
        if col in IND_GROUP_MAPPING:
            _, _, col_label = IND_GROUP_MAPPING[col]
            html.append(f'<th>{col_label}</th>')
        else:
            html.append(f'<th>{col}</th>')
    html.append('</tr></thead><tbody>')

    for row_idx, row in df.iterrows():
        html.append('<tr>')
        html.append(f'<td class="date-cell">{row.get("日期", "-")}</td>')
        
        margin_chg_rate_num = parse_num(row.get("融資改變率"))

        for col_idx, col in enumerate(visible_metrics):
            raw_val = row.get(col)
            val_display = format_cell(raw_val, col)
            
            if val_display in ["-", "股市未開盤", "無交易數據", "", "None"]:
                html.append(f'<td class="nodata-cell">{val_display}</td>')
            else:
                num_val = parse_num(raw_val)
                classes = ["value-cell"]
                cell_style = ""

                if col in COLOR_METRICS and num_val is not None:
                    if num_val > 0:
                        classes.append("pos-val")
                    elif num_val < 0:
                        classes.append("neg-val")

                if col == "借券賣出變動比" and num_val is not None:
                    if num_val >= 3.0:
                        classes.append("bg-pink")
                    elif num_val <= -3.0:
                        classes.append("bg-light-green")

                elif col == "訊號燈":
                    val_str = str(raw_val).strip()
                    if val_str == "空頭":
                        classes.append("bg-light-green")
                    elif val_str == "強勢軋空":
                        classes.append("bg-pink")

                elif col in ["融資VS個股", "融資vs個股"]:
                    if row.get("融資VS個股_底色", False):
                        classes.append("bg-light-green")

                elif col == "融資個股倍數":
                    if num_val is not None and num_val >= 2.0 and margin_chg_rate_num is not None and margin_chg_rate_num < 0:
                        classes.append("bg-pink")

                elif col == "外資買賣力度" and num_val is not None:
                    if num_val > 5.0:
                        classes.append("bg-pink")
                    elif num_val < -5.0:
                        classes.append("bg-light-green")

                elif col == "成交量倍數" and num_val is not None:
                    if num_val >= 1.5:
                        classes.append("bg-pink")
                    elif num_val <= 0.7:
                        classes.append("bg-light-green")

                elif col in ["漲/跌幅", "漲跌幅", "美股漲/跌", "美股漲/跌幅"] and num_val is not None:
                    if num_val >= 2.0:
                        classes.append("bg-pink")
                    elif num_val <= -2.0:
                        classes.append("bg-light-green")

                class_str = " ".join(classes)
                style_str = f' {cell_style}' if cell_style else ''
                html.append(f'<td class="{class_str}"{style_str}>{val_display}</td>')
        html.append('</tr>')

    html.append('</tbody></table></div>')
    return "".join(html)

def render_individual_tab(market, stock_id, page_info):
    head_col1, head_col2, head_col3 = st.columns([3, 1, 1])
    with head_col1:
        st.subheader(f"📊 {stock_id} - {page_info.get('name', '自選股')}")
    
    with head_col2:
        if st.button("⚡ 即時更新", key=f"btn_refresh_{market}_{stock_id}", use_container_width=True):
            with st.spinner(f"正在更新 {stock_id} 最新數據..."):
                updated_df = load_or_fetch_ind_90_days(stock_id, force_refetch=True)
                if "store" in st.session_state and market in st.session_state.store and stock_id in st.session_state.store[market]:
                    st.session_state.store[market][stock_id]["df"] = updated_df
                else:
                    page_info["df"] = updated_df
                st.toast(f"✅ {stock_id} 數據已成功更新！", icon="🚀")
                st.rerun()

    with head_col3:
        if st.button("❌ 關閉分頁", key=f"btn_close_{market}_{stock_id}", use_container_width=True):
            if "store" in st.session_state and market in st.session_state.store and stock_id in st.session_state.store[market]:
                del st.session_state.store[market][stock_id]
                st.rerun()
            else:
                st.info("單獨測試模式下無可刪除的 Session 分頁")

    df = page_info.get("df")

    if df is None or df.empty:
        if st.button("🚀 載入 90 天歷史數據", key=f"btn_fetch_{stock_id}", use_container_width=True):
            with st.spinner(f"爬取與計算 {stock_id} 數據中..."):
                df = load_or_fetch_ind_90_days(stock_id)
                page_info["df"] = df
                st.rerun()
    else:
        st.caption(f"📅 已載入完整 {len(df)} 個交易日數據（快取檔：`data_cache/{stock_id}_cache.csv`）")
        
        st.markdown("""
        <div style="background-color: #f8f9fa; border-left: 4px solid #0047AB; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 13px; color: #333333; line-height: 1.5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            <div style="margin-bottom: 3px;">
                📌 <span style="font-weight: bold; color: #296873;">計算公式與欄位提示說明 (Note) :</span>
            </div>
            • <span style="font-weight: bold; color: #296873;">融資改變率</span> = 100% * (今日融資增減 / 昨日融資餘額)<br>
            • <span style="font-weight: bold; color: #296873;">融資vs個股</span>：當「融資改變率」&gt;「個股漲跌幅」時顯示「大」，反之為「小」。 若 <span style="background-color: #d1e7dd; color: #0f5132; padding: 1px 5px; border-radius: 3px; font-size: 12px;">連續三天(或以上)為「大」且融資改變率皆為正數</span> : 準備到高點可以賣。<br>
            • <span style="font-weight: bold; color: #296873;">融資個股倍數</span> = 融資改變率是個股漲跌幅的幾倍。當 <span style="background-color: #f8d7da; color: #842029; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&ge; 2 且融資改變率為負數</span> : 準備到低點可以買。<br>
            • <span style="font-weight: bold; color: #296873;">漲跌幅</span>： <span style="background-color: #f8d7da; color: #842029; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&ge; 2%</span> : 大漲 | -1.5% ~ 1.5% : 盤整 | <span style="background-color: #d1e7dd; color: #0f5132; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&le; -2%</span> : 大跌。<br>
            • <span style="font-weight: bold; color: #296873;">成交量倍數</span> = 成交量 / 近20日平均成交量。 <span style="background-color: #f8d7da; color: #842029; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&ge; 1.5</span> : 成交爆量 | &lt; 1.5 : 量能不足 | <span style="background-color: #d1e7dd; color: #0f5132; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&lt; 0.7</span> : 成交縮量。<br>
            • <span style="font-weight: bold; color: #296873;">外資買賣力度</span> = 100% * (外資進出量 / 個股成交量)。 <span style="background-color: #f8d7da; color: #842029; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&gt; 5%</span> : 外資做多；<span style="background-color: #d1e7dd; color: #0f5132; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&lt; -5%</span> : 外資做空。<br>
            • <span style="font-weight: bold; color: #296873;">借券賣出變動比</span> = 100 * (券賣出量 - 券賣還券) / 近20日平均成交量。 <span style="background-color: #f8d7da; color: #842029; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&ge; 3%</span> : 大量賣出 | <span style="background-color: #d1e7dd; color: #0f5132; padding: 1px 5px; border-radius: 3px; font-size: 12px;">&le; -3%</span> : 大量還券 | &ge; 1% : 中量賣出 | &le; -1% : 中量還券。<br>
            • <span style="font-weight: bold; color: #296873;">訊號燈觸發條件</span>（需三條件同時成立）：</span><br>
            &nbsp;&nbsp;- <span style="background-color: #d1e7dd; color: #0f5132; padding: 1px 5px; border-radius: 3px; font-weight: bold; font-size: 12px;">空頭</span>：大量賣出 + 成交爆量 + 大跌 （代表開始走空，避免做多）<br>
            &nbsp;&nbsp;- <span style="background-color: #f8d7da; color: #842029; padding: 1px 5px; border-radius: 3px; font-weight: bold; font-size: 12px;">強勢軋空</span>：大量還券 + 成交爆量 + 大漲 （代表開始走多，避免借券）<br>
            &nbsp;&nbsp;- <span style="font-weight: bold;">籌碼沉澱</span>：中量還券 + 成交縮量 + 盤整 （代表等待突破，未來不明）<br>
            &nbsp;&nbsp;- <span style="font-weight: bold;">高位壓盤</span>：中量賣出 + 量能不足 + 盤整 （代表向上動能不足，觀望不動作）
        </div>
        """, unsafe_allow_html=True)

        us_cols = ["美股收盤", "美股漲/跌", "美股漲/跌幅", "美股成交"]
        has_us_data = any(c in df.columns and df[c].apply(parse_num).notna().any() for c in us_cols)
        
        current_columns_order = [c for c in IND_COLUMNS_ORDER if has_us_data or c not in us_cols]

        col_key = f"col_select_v7_{market}_{stock_id}"
        if col_key not in st.session_state:
            st.session_state[col_key] = [c for c in DEFAULT_VISIBLE_COLUMNS if c in current_columns_order]

        user_selected = st.session_state.get(col_key, DEFAULT_VISIBLE_COLUMNS)
        selected_visible_columns = [c for c in current_columns_order if c in user_selected]

        table_html = render_ind_custom_html_table(df, selected_visible_columns)
        st.markdown(table_html, unsafe_allow_html=True)

        st.multiselect(
            "⚙️ 調整表格顯示欄位（點擊可切換隱藏 / 顯示）：",
            options=current_columns_order,
            default=selected_visible_columns,
            key=col_key
        )

        st.markdown("---")

        selected_charts = st.multiselect(
            "請選擇要開啟的額外指標圖表（可複選，最多 3 個）：",
            options=AVAILABLE_CHART_METRICS,
            max_selections=3,
            key=f"multi_{market}_{stock_id}"
        )
        
        base_plots = ["K線與成交量"]
        if has_us_data:
            base_plots.append("美股複合圖表")

        all_plots_to_render = base_plots + selected_charts
        
        total_plots = len(all_plots_to_render)
        if total_plots == 1:
            row_heights = [1.0]
        elif total_plots == 2:
            row_heights = [0.6, 0.4]
        else:
            sub_height = 0.4 / (total_plots - 1)
            row_heights = [0.6] + [sub_height] * (total_plots - 1)

        subplot_titles = ["📈 K線 / 技術均線 / 成交量"]
        if has_us_data:
            subplot_titles.append("🇺🇸 美股收盤(美元)與成交量(股)")

        subplot_titles.extend([
            f"📍 {m} <span style='font-size:12px; color:gray;'> ({get_ind_unit_str(m)})</span>" for m in selected_charts
        ])

        specs = [[{"secondary_y": True}]] * total_plots

        fig = make_subplots(
            rows=total_plots,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=row_heights,
            subplot_titles=subplot_titles,
            specs=specs
        )
        
        chart_df = df.copy().iloc[::-1].reset_index(drop=True)
        x_vals = chart_df["日期"]
        
        def clean_series(column_name):
            if column_name in chart_df.columns:
                return chart_df[column_name].apply(parse_num)
            return pd.Series([np.nan] * len(chart_df))

        o = clean_series("開盤價")
        h = clean_series("最高價")
        l = clean_series("最低價")
        c = clean_series("收盤價")

        vol_vals = clean_series("成交量")
        vol_colors = ['rgba(239, 83, 80, 0.4)' if (pd.notna(op) and pd.notna(cl) and cl >= op) else 'rgba(38, 166, 154, 0.4)' for op, cl in zip(o, c)]

        fig.add_trace(
            go.Bar(
                x=x_vals, y=vol_vals,
                name="成交量",
                marker_color=vol_colors,
                hovertemplate="成交量: %{y:,.0f}股<extra></extra>"
            ),
            row=1, col=1, secondary_y=True
        )

        fig.add_trace(
            go.Candlestick(
                x=x_vals,
                open=o, high=h, low=l, close=c,
                name="K線",
                increasing_line_color='#ef5350',
                decreasing_line_color='#26a69a',
                showlegend=True,
                hovertext=[f"開:{op:.2f} 高:{hi:.2f} 低:{lo:.2f} 收:{cl:.2f}" if pd.notna(cl) else "無資料" 
                           for op, hi, lo, cl in zip(o, h, l, c)],
                hovertemplate="%{hovertext}<extra></extra>"
            ),
            row=1, col=1, secondary_y=False
        )

        ma_configs = [("月線", "#ff7f0e"), ("季線", "#2ca02c"), ("半年線", "#9467bd"), ("年線", "#8c564b")]
        for ma_name, color in ma_configs:
            ma_vals = clean_series(ma_name)
            fig.add_trace(
                go.Scatter(
                    x=x_vals, y=ma_vals, mode='lines',
                    line=dict(color=color, width=1.5),
                    name=ma_name, connectgaps=True,
                    hovertemplate=f"{ma_name}: %{{y:,.2f}}元<extra></extra>"
                ),
                row=1, col=1, secondary_y=False
            )

        if not vol_vals.dropna().empty:
            max_vol = vol_vals.max()
            # 將倍數從 3.5 調小（例如 2.0），讓圖表放大、避免偏低的成交量看起來像貼平歸零
            fig.update_yaxes(
                range=[0, max_vol * 2.0], 
                showgrid=False, 
                title_text="成交量(股)", 
                row=1, 
                col=1, 
                secondary_y=True
            )

        current_row = 2
        if has_us_data:
            us_c = clean_series("美股收盤")
            us_v = clean_series("美股成交")

            fig.add_trace(
                go.Bar(
                    x=x_vals, y=us_v, name="美股成交",
                    marker_color="rgba(180, 180, 180, 0.4)",
                    hovertemplate="美股成交: %{y:,.0f}股<extra></extra>"
                ),
                row=2, col=1, secondary_y=True
            )
            
            fig.add_trace(
                go.Scatter(
                    x=x_vals, y=us_c, mode='lines',
                    line=dict(color='#1f77b4', width=2),
                    name="美股收盤", connectgaps=True,
                    hovertemplate="美股收盤: %{y:,.2f}美元<extra></extra>"
                ),
                row=2, col=1, secondary_y=False
            )
            fig.update_yaxes(title_text="美元", row=2, col=1, secondary_y=False)
            fig.update_yaxes(title_text="股", showgrid=False, row=2, col=1, secondary_y=True)
            current_row += 1

        for metric in selected_charts:
            numeric_y = clean_series(metric)
            valid_y = numeric_y.dropna()
            if not valid_y.empty and valid_y.min() < 0 and valid_y.max() > 0:
                y_pos = numeric_y.apply(lambda v: v if (pd.notna(v) and v >= 0) else (0 if pd.notna(v) else np.nan))
                y_neg = numeric_y.apply(lambda v: v if (pd.notna(v) and v <= 0) else (0 if pd.notna(v) else np.nan))
                fig.add_trace(
                    go.Scatter(x=x_vals, y=y_pos, mode='lines', fill='tozeroy', fillcolor='rgba(255, 77, 79, 0.25)', line=dict(width=0), connectgaps=True, showlegend=False, hoverinfo='skip'),
                    row=current_row, col=1, secondary_y=False
                )
                fig.add_trace(
                    go.Scatter(x=x_vals, y=y_neg, mode='lines', fill='tozeroy', fillcolor='rgba(82, 196, 26, 0.25)', line=dict(width=0), connectgaps=True, showlegend=False, hoverinfo='skip'),
                    row=current_row, col=1, secondary_y=False
                )

            fig.add_trace(
                go.Scatter(
                    x=x_vals, y=numeric_y, mode='lines',
                    line=dict(color='#007bff', width=2),
                    name=metric, connectgaps=True,
                    hovertemplate=f"{metric}: %{{y:,.2f}}{get_ind_unit_str(metric)}<extra></extra>"
                ),
                row=current_row, col=1, secondary_y=False
            )
            fig.update_yaxes(title_text=get_ind_unit_str(metric), row=current_row, col=1, secondary_y=False)
            current_row += 1

        fig.update_xaxes(
            type='category',
            showgrid=True,
            rangeslider_visible=False,
            showspikes=True,
            spikemode='across+marker',
            spikesnap='cursor',
            spikedash='dash',
            spikecolor='#ef5350',
            spikethickness=1.5,
            matches='x'
        )

        for r in range(1, total_plots):
            fig.update_xaxes(showticklabels=False, row=r, col=1)

        fig.update_yaxes(showgrid=True)

        chart_height = 450 + 150 * (total_plots - 1)

        fig.update_layout(
            height=int(chart_height),
            margin=dict(l=10, r=10, t=30, b=20),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
            hovermode="x unified",
            hoverlabel=dict(bgcolor="rgba(255, 255, 255, 0.9)", font_size=12),
            dragmode=False
        )

        for annotation in fig['layout']['annotations']:
            annotation['x'] = 0
            annotation['xanchor'] = 'left'
            annotation['font'] = dict(size=13, color="#000000", family="Arial, sans-serif")

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'scrollZoom': False, 'responsive': True})

if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="個股單獨測試")
    
    st.markdown("""
        <style>
        .block-container {
            padding-top: 3.8rem !important;
            padding-bottom: 2rem !important;
            padding-left: 0.8rem !important;
            padding-right: 0.8rem !important;
        }
        
        .custom-table-container {
            width: 100%;
            overflow-x: auto;
            max-height: 450px;
            overflow-y: auto;
            border: 1px solid #dcdcdc;
            border-radius: 4px;
            margin-bottom: 0.8rem;
            position: relative;
        }
        .custom-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 14px;
            white-space: nowrap;
        }
        
        .custom-table th {
            position: sticky;
            top: 0;
            background-color: #f0f0f0 !important;
            color: #111111 !important;
            font-weight: bold !important;
            border: 1px solid #dcdcdc;
            padding: 8px 10px;
            text-align: center;
            z-index: 2;
        }
        .custom-table tr:nth-child(2) th {
            top: 35px;
            border-bottom: 2.5px solid #333333 !important;
        }
        
        .custom-table th.sticky-corner {
            position: sticky;
            top: 0;
            left: 0;
            z-index: 3 !important;
            background-color: #e5e5e5 !important;
            border-right: 2.5px solid #333333 !important;
        }

        .custom-table td.date-cell {
            position: sticky;
            left: 0;
            background-color: #f5f5f5 !important;
            color: #000000 !important;
            font-weight: bold !important;
            border: 1px solid #e0e0e0;
            border-right: 2.5px solid #333333 !important;
            padding: 8px 10px;
            z-index: 1;
            text-align: center;
        }

        .custom-table td.value-cell {
            color: #111111;
            font-weight: bold !important;
            border: 1px solid #eeeeee;
            padding: 8px 10px;
            text-align: right;
        }

        .custom-table td.value-cell.pos-val {
            color: #d32f2f !important;
        }
        .custom-table td.value-cell.neg-val {
            color: #2e7d32 !important;
        }

        .custom-table td.nodata-cell {
            color: #888888 !important;
            font-weight: normal !important;
            border: 1px solid #eeeeee;
            padding: 8px 10px;
            text-align: center;
        }
        .custom-table tr:hover td {
            background-color: #f7f7f7 !important;
        }

        .bg-pink { background-color: #f8d7da !important; }
        .bg-light-green { background-color: #d4edda !important; }

        span[data-baseweb="tag"],
        div[data-baseweb="tag"] {
            background-color: #dce6f1 !important;
            border: 1px solid #c2d3e4 !important;
            border-radius: 6px !important;
        }

        span[data-baseweb="tag"] *,
        div[data-baseweb="tag"] * {
            background-color: transparent !important;
            border: none !important;
            outline: none !important;
            box-shadow: none !important;
            color: #334155 !important;
            fill: #475569 !important;
        }

        span[data-baseweb="tag"] svg:hover,
        div[data-baseweb="tag"] svg:hover {
            fill: #1e293b !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title("🧪 Individual 模組獨立測試環境")

    if "store" not in st.session_state:
        st.session_state.store = {"上市": {}, "上櫃": {}}

    col_input, col_market = st.columns([2, 1])
    with col_input:
        test_stock_id = st.text_input("輸入測試股票代號:", value="2330")
    with col_market:
        test_market = st.selectbox("選擇市場:", ["上市", "上櫃"])

    if test_stock_id not in st.session_state.store[test_market]:
        st.session_state.store[test_market][test_stock_id] = {
            "name": f"測試股票_{test_stock_id}",
            "df": None
        }

    st.divider()
    page_info = st.session_state.store[test_market][test_stock_id]
    
    render_individual_tab(test_market, test_stock_id, page_info)