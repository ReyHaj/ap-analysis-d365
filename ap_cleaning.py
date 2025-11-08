from pathlib import Path
import os
import time
import pandas as pd
import numpy as np

RAW = Path("data/raw")
PROC = Path("data/processed")
PROC.mkdir(parents=True, exist_ok=True)

ALLOWED_CCY = {"USD","EUR","GBP","CAD","AUD","JPY"}

def find_excel():
    files = sorted(RAW.glob("*.xlsx"))
    if not files:
        raise FileNotFoundError("No Excel file found in data/raw/")
    return files[0]

def to_datetime_safe(s):
    return pd.to_datetime(s, errors="coerce")

def safe_save_csv(df: pd.DataFrame, out_path: Path, retries: int = 5, sleep_s: float = 0.5):
    """
    ذخیره امن CSV: اول در فایل موقتی می‌نویسد و بعد با os.replace جایگزین می‌کند.
    اگر PermissionError خورد (فایل قفل بود)، چندبار امتحان می‌کند.
    """
    tmp = out_path.with_suffix(".tmp")
    for i in range(retries):
        try:
            df.to_csv(tmp, index=False)
            os.replace(tmp, out_path)
            return
        except PermissionError:
            if tmp.exists():
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
            time.sleep(sleep_s)
    # آخرین تلاش: نام جایگزین با timestamp
    fallback = out_path.with_name(out_path.stem + f"_{int(time.time())}" + out_path.suffix)
    df.to_csv(fallback, index=False)
    print(f"[WARN] Could not write to {out_path} (locked). Saved to fallback: {fallback}")

def main():
    xlsx = find_excel()
    print("Using:", xlsx)

    df_raw = pd.read_excel(xlsx)
    print("Raw rows:", len(df_raw))

    # ---- ساخت گزارش اولیه روی دیتای خام ----
    df_chk = df_raw.copy()

    # APID missing
    apid_missing = df_chk["APID"].isna() | (df_chk["APID"].astype(str).str.strip() == "")

    # Amount <= 0
    amt_num = pd.to_numeric(df_chk["Amount"], errors="coerce")
    amt_invalid = amt_num.isna() | (amt_num <= 0)

    # Dates to datetime
    for c in ["InvoiceDate","DueDate","PaidDate"]:
        if c in df_chk.columns:
            df_chk[c] = to_datetime_safe(df_chk[c])

    # invalid dates (InvoiceDate or DueDate is NaT)
    inv_invoice = df_chk["InvoiceDate"].isna()
    inv_due     = df_chk["DueDate"].isna()
    invalid_dates = inv_invoice | inv_due

    # DueDate before InvoiceDate
    due_before_invoice = df_chk["DueDate"] < df_chk["InvoiceDate"]

    # invalid currency
    ccy_invalid = ~df_chk["Currency"].astype(str).str.strip().isin(ALLOWED_CCY)

    # duplicates (composite key)
    compkey = (
        df_chk["APID"].astype(str) + "|" +
        df_chk["Vendor"].astype(str) + "|" +
        df_chk["InvoiceDate"].astype(str) + "|" +
        df_chk["Amount"].astype(str)
    )
    is_dup = compkey.duplicated(keep=False)

    # خلاصه کیفیت داده (روی خام)
    dq_summary_raw = {
        "missing_APID": int(apid_missing.sum()),
        "amount_zero_negative_or_na": int(amt_invalid.sum()),
        "invalid_invoice_date": int(inv_invoice.sum()),
        "invalid_due_date": int(inv_due.sum()),
        "due_before_invoice": int(due_before_invoice.sum()),
        "invalid_currency": int(ccy_invalid.sum()),
        "duplicates": int(is_dup.sum()),
        "missing_values_total": int(df_chk.isna().sum().sum()),
    }

    print("\n--- DATA QUALITY (RAW) ---")
    for k, v in dq_summary_raw.items():
        print(f"{k}: {v}")

    # ---- اعمال پاکسازی بر اساس قوانین تایید شده ----
    drop_mask = (
        apid_missing |
        amt_invalid |
        invalid_dates |
        due_before_invoice |
        ccy_invalid |
        is_dup
    )

    rows_total = len(df_raw)
    rows_removed = int(drop_mask.sum())
    df_clean = df_raw.loc[~drop_mask].copy()

    # اطمینان از نوع عددی Amount
    df_clean["Amount"] = pd.to_numeric(df_clean["Amount"], errors="coerce")

    # ذخیره امن
    out_csv = PROC / "ap_clean.csv"
    safe_save_csv(df_clean, out_csv)

    print("\n--- CLEANING SUMMARY ---")
    print(f"rows_total: {rows_total}")
    print(f"rows_removed: {rows_removed}")
    print(f"rows_cleaned: {len(df_clean)}")
    print(f"saved: {out_csv.resolve()}")

    # گزارش بعد از پاکسازی
    print("\n📊 Data Quality Summary (CLEANED):")
    # معیارهای کلیدی بعد از پاکسازی باید صفر یا بسیار کم باشند
    print({
        "missing_APID": int(df_clean['APID'].isna().sum() + (df_clean['APID'].astype(str).str.strip() == '').sum()),
        "amount_zero_negative_or_na": int((pd.to_numeric(df_clean['Amount'], errors='coerce') <= 0).sum()),
        "invalid_invoice_date": int(pd.to_datetime(df_clean['InvoiceDate'], errors='coerce').isna().sum()),
        "invalid_due_date": int(pd.to_datetime(df_clean['DueDate'], errors='coerce').isna().sum()),
        "due_before_invoice": int((pd.to_datetime(df_clean['DueDate'], errors='coerce') < pd.to_datetime(df_clean['InvoiceDate'], errors='coerce')).sum()),
        "invalid_currency": int((~df_clean['Currency'].astype(str).str.strip().isin(ALLOWED_CCY)).sum()),
        "duplicates": int((
            df_clean['APID'].astype(str) + "|" +
            df_clean['Vendor'].astype(str) + "|" +
            df_clean['InvoiceDate'].astype(str) + "|" +
            df_clean['Amount'].astype(str)
        ).duplicated(keep=False).sum())
    })

if __name__ == "__main__":
    # نکته ویندوز: اگر فایل ap_clean.csv را در Excel باز داری، ببند؛
    # همچنین Preview Pane اکسپلورر ویندوز (View > Preview Pane) می‌تواند فایل را قفل کند.
    main()
