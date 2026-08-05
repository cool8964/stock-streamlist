import requests
import pandas as pd
import random
import time
import yfinance as yf
from datetime import datetime, timedelta

# 台股對應美股 ADR 的對照表
ADR_MAPPING = {
    "2330": "TSM",   # 台積電
    "2303": "UMC",   # 聯電
    "2412": "CHT",   # 中華電信
    "3711": "ASX",   # 日月光投控
    "2454": "MDTKF", # 聯發科 (OTC)
    "2317": "HNHPF"  # 鴻海 (OTC)
}

def fetch_merged_stock_data(stock_id, target_date_str="20260702"):
    """
    抓取指定台股與美股 ADR 於特定日期的綜合資料
    target_date_str 格式: YYYYMMDD
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest"
    }
    
    merged_data = {"股票代號": stock_id, "查詢日期": target_date_str}
    target_dt = datetime.strptime(target_date_str, "%Y%m%d")

    # =========================================================================
    # 段落一：美股 ADR 歷史數據抓取
    # =========================================================================
    if stock_id in ADR_MAPPING:
        adr_ticker = ADR_MAPPING[stock_id]
        merged_data["【來源：美股】美股ADR代號"] = adr_ticker
        
        try:
            ticker = yf.Ticker(adr_ticker)
            start_date = (target_dt - timedelta(days=7)).strftime("%Y-%m-%d")
            end_date = (target_dt + timedelta(days=2)).strftime("%Y-%m-%d")
            
            hist = ticker.history(start=start_date, end=end_date)
            
            if not hist.empty:
                hist.index = pd.to_datetime(hist.index).date
                target_date_obj = target_dt.date()
                valid_hist = hist[hist.index <= target_date_obj]
                
                if len(valid_hist) >= 1:
                    latest_row = valid_hist.iloc[-1]
                    last_price = round(float(latest_row["Close"]), 2)
                    volume = int(latest_row["Volume"])
                    
                    if len(valid_hist) >= 2:
                        prev_close = float(valid_hist.iloc[-2]["Close"])
                        pct_change = round(((last_price - prev_close) / prev_close) * 100, 2)
                        pct_change_str = f"{pct_change:+.2f}%"
                    else:
                        pct_change_str = "N/A"

                    merged_data["【來源：美股】美股價(美元)"] = last_price
                    merged_data["【來源：美股】美股漲跌幅"] = pct_change_str
                    merged_data["【來源：美股】美股成交量(股)"] = volume
                else:
                    merged_data["【來源：美股】ADR資訊"] = "無對應日期數據"
            else:
                merged_data["【來源：美股】ADR資訊"] = "抓取失敗"

        except Exception as e:
            print(f"【美股 ADR 抓取異常】: {e}")
            merged_data["【來源：美股】ADR資訊"] = "抓取失敗"
    else:
        merged_data["【來源：美股】美股ADR代號"] = "無在美上市ADR"

    # =========================================================================
    # 段落二：抓取台股價格、漲跌價差、漲跌幅、成交量、本益比
    # =========================================================================
    mi_url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&date={target_date_str}&type=ALL"
    try:
        time.sleep(random.uniform(0.1, 0.3))
        res = requests.get(mi_url, headers=headers, timeout=10)
        if res.status_code == 200 and "json" in res.headers.get("Content-Type", "").lower():
            data = res.json()
            if data.get("stat") == "OK":
                target_table = None
                for table in data.get("tables", []):
                    if "每日收盤行情" in table.get("title", ""):
                        target_table = table.get("data", [])
                        break
                
                if target_table:
                    for row in target_table:
                        if row[0].strip() == stock_id:
                            c_val = float(row[8].replace(",", "").strip())
                            merged_data["【來源：MI_INDEX】台股開盤價"] = float(row[5].replace(",", "").strip())
                            merged_data["【來源：MI_INDEX】台股最高價"] = float(row[6].replace(",", "").strip())
                            merged_data["【來源：MI_INDEX】台股最低價"] = float(row[7].replace(",", "").strip())
                            merged_data["【來源：MI_INDEX】台股收盤價"] = c_val
                            
                            sign = row[9].strip()
                            change_p = row[10].strip().replace(",", "")
                            sign_str = "+" if ("+" in sign or "red" in sign) else ("-" if ("-" in sign or "green" in sign) else "")
                            
                            merged_data["【來源：MI_INDEX】台股漲跌價差"] = f"{sign_str}{change_p}"
                            
                            try:
                                diff_val = float(change_p) if sign_str != "-" else -float(change_p)
                                prev_close = c_val - diff_val
                                if prev_close > 0:
                                    merged_data["【來源：MI_INDEX】台股漲跌幅"] = f"{(diff_val / prev_close) * 100:+.2f}%"
                            except:
                                merged_data["【來源：MI_INDEX】台股漲跌幅"] = "N/A"

                            merged_data["【來源：MI_INDEX】台股成交量(股)"] = round(int(row[2].replace(",", "").strip()))
                            merged_data["【來源：MI_INDEX】本益比"] = row[15].strip().replace(",", "")
                            break
    except Exception as e:
        print(f"【MI_INDEX 抓取異常】: {e}")

    # =========================================================================
    # 段落三：抓取當日三大法人買賣超
    # =========================================================================
    t86_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={target_date_str}&selectType=ALL"
    try:
        time.sleep(random.uniform(0.1, 0.3))
        res = requests.get(t86_url, headers=headers, timeout=10)
        if res.status_code == 200 and "json" in res.headers.get("Content-Type", "").lower():
            data = res.json()
            if data.get("stat") == "OK":
                raw_data = data.get("data", [])
                for row in raw_data:
                    if row[0].strip() == stock_id:
                        def parse_sheets(v):
                            return round(float(v.replace(",", "").strip()))
                        
                        foreign = parse_sheets(row[4])
                        sitc = parse_sheets(row[10])
                        dealer = parse_sheets(row[11]) 
                        total_inst = round(foreign + sitc + dealer, 2)
                        
                        merged_data["【來源：T86】外資進出(股)"] = foreign
                        merged_data["【來源：T86】投信進出(股)"] = sitc
                        merged_data["【來源：T86】自營商進出(股)"] = dealer
                        merged_data["【來源：T86】三大法人進出(股)"] = total_inst
                        break
    except Exception as e:
        print(f"【T86 當日抓取異常】: {e}")

    # =========================================================================
    # 段落四：抓取融資融券與券資比
    # =========================================================================
    margin_url = f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=json&date={target_date_str}&selectType=ALL"
    try:
        time.sleep(random.uniform(0.1, 0.3))
        res = requests.get(margin_url, headers=headers, timeout=10)
        if res.status_code == 200 and "json" in res.headers.get("Content-Type", "").lower():
            data = res.json()
            if data.get("stat") == "OK":
                target_table = None
                for table in data.get("tables", []):
                    if "融資融券" in table.get("title", ""):
                        target_table = table.get("data", [])
                        break
                
                if target_table:
                    for row in target_table:
                        if row[0].strip() == stock_id:
                            margin_buy_prev_sheets = float(row[5].replace(",", "").strip())
                            margin_buy_today_sheets = float(row[6].replace(",", "").strip())
                            
                            margin_sell_prev_sheets = float(row[11].replace(",", "").strip())
                            margin_sell_today_sheets = float(row[12].replace(",", "").strip())
                            
                            margin_buy_change_sheets = round(margin_buy_today_sheets - margin_buy_prev_sheets, 2)
                            margin_sell_change_sheets = round(margin_sell_today_sheets - margin_sell_prev_sheets, 2)
                            
                            if margin_buy_today_sheets > 0:
                                short_margin_ratio = round(100 * (margin_sell_today_sheets / margin_buy_today_sheets), 2)
                                short_margin_ratio_str = f"{short_margin_ratio}%"
                            else:
                                short_margin_ratio_str = "N/A"

                            # 確保鍵值名稱與後續處理一致
                            merged_data["【來源：MI_MARGN】融資餘額(張)"] = margin_buy_today_sheets
                            merged_data["【來源：MI_MARGN】融資增減(張)"] = margin_buy_change_sheets
                            merged_data["【來源：MI_MARGN】融券餘額(張)"] = margin_sell_today_sheets
                            merged_data["【來源：MI_MARGN】融券增減(張)"] = margin_sell_change_sheets
                            merged_data["【來源：MI_MARGN】券資比(%)"] = short_margin_ratio_str
                            break
    except Exception as e:
        print(f"【MI_MARGN 抓取異常】: {e}")

    # =========================================================================
    # 🔥【新增】段落五：抓取借券賣出資料 (來源：TWT93U)
    # =========================================================================
    twt93u_url = f"https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?response=json&date={target_date_str}&selectType=ALL"
    try:
        time.sleep(random.uniform(0.1, 0.3))
        res = requests.get(twt93u_url, headers=headers, timeout=10)
        if res.status_code == 200 and "json" in res.headers.get("Content-Type", "").lower():
                data = res.json()
                if data.get("stat") == "OK":
                    raw_data = data.get("data", [])
                    for row in raw_data:
                        if row[0].strip() == stock_id:
                            sbl_sell = round(float(row[9].replace(",", "").strip()))
                            sbl_return = round(float(row[10].replace(",", "").strip()))
                            sbl_bal = round(float(row[12].replace(",", "").strip()))
        
                            # 修正單位為 (股)
                            merged_data["【來源：TWT93U】券賣出量(股)"] = sbl_sell
                            merged_data["【來源：TWT93U】券賣還券(股)"] = sbl_return
                            merged_data["【來源：TWT93U】券賣餘額(股)"] = sbl_bal
                            break
    except Exception as e:
        print(f"【TWT93U 抓取異常】: {e}")

    # =========================================================================
    # 段落六：計算技術均線 (MA)
    # =========================================================================
    all_prices = []
    for i in range(26):
        fetch_date = (target_dt - pd.DateOffset(months=i)).strftime("%Y%m01")
        hist_url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={fetch_date}&stockNo={stock_id}"
        try:
            time.sleep(random.uniform(0.1, 0.2))
            h_res = requests.get(hist_url, headers=headers, timeout=5)
            if h_res.status_code == 200:
                h_data = h_res.json()
                if h_data.get("stat") == "OK" and "data" in h_data:
                    for r in h_data["data"]:
                        date_parts = r[0].split("/")
                        year = int(date_parts[0]) + 1911
                        row_date_str = f"{year}{date_parts[1]}{date_parts[2]}"
                        if row_date_str <= target_date_str:
                            all_prices.append((row_date_str, float(r[6].replace(",", "").strip())))
        except Exception:
            pass
            
    df_price = pd.DataFrame(all_prices, columns=["date", "close"]).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    
    merged_data["【來源：STOCK_DAY計算】月線(20MA)"] = round(df_price["close"].tail(20).mean(), 2) if len(df_price) >= 20 else "資料不足"
    merged_data["【來源：STOCK_DAY計算】季線(60MA)"] = round(df_price["close"].tail(60).mean(), 2) if len(df_price) >= 60 else "資料不足"
    merged_data["【來源：STOCK_DAY計算】半年線(120MA)"] = round(df_price["close"].tail(120).mean(), 2) if len(df_price) >= 120 else "資料不足"
    merged_data["【來源：STOCK_DAY計算】年線(240MA)"] = round(df_price["close"].tail(240).mean(), 2) if len(df_price) >= 240 else "資料不足"

    return merged_data

# ==========================================
# 測試執行
# ==========================================
if __name__ == "__main__":
    print("\n--- 測試 2330 台積電 ---")
    data_2330 = fetch_merged_stock_data("0052", "20260731")
    for k, v in data_2330.items():
        print(f"{k}: {v}")