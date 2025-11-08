from pathlib import Path
import pandas as pd
import numpy as np

RAW = Path("data/raw")
PROC = Path("data/processed")
PROC.mkdir(parents=True, exist_ok=True)

def _safe_to_datetime(df: pd.DataFrame, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df

def _ensure_features(df: pd.DataFrame) -> pd.DataFrame:
    # IsPaid
    df["IsPaid"] = False
    if "Status" in df.columns:
        df["IsPaid"] = df["IsPaid"] | df["Status"].astype(str).str.lower().eq("paid")
    if "PaidDate" in df.columns:
        df["IsPaid"] = df["IsPaid"] | df["PaidDate"].notna()

    # DaysPastDue
    today = pd.Timestamp.today().normalize()
    if "DueDate" in df.columns:
        dpd_today = (today - df["DueDate"]).dt.days
        dpd_paid  = (df["PaidDate"] - df["DueDate"]).dt.days if "PaidDate" in df.columns else np.nan
        df["DaysPastDue"] = np.where(df["IsPaid"], dpd_paid, dpd_today)
        df["DaysPastDue"] = df["DaysPastDue"].fillna(0).clip(lower=0)
    else:
        df["DaysPastDue"] = 0

    # AgingBucket (در صورت نبودن، بساز)
    if "AgingBucket" not in df.columns:
        bins   = [-1, 0, 30, 60, 90, np.inf]
        labels = ["Current","0–30","31–60","61–90",">90"]
        df["AgingBucket"] = pd.cut(df["DaysPastDue"], bins=bins, labels=labels)
    return df

def _parse_terms_days(s):
    """استخراج روز از Terms (مثلاً Net 30 → 30)."""
    if pd.isna(s):
        return np.nan
    import re
    m = re.search(r"(\d+)", str(s))
    return int(m.group(1)) if m else np.nan

def load_clean_or_raw():
    # ترجیح: ap_clean.csv
    clean_csv = PROC / "ap_clean.csv"
    if clean_csv.exists():
        df = pd.read_csv(clean_csv)
    else:
        # fallback: اولین اکسل موجود
        files = sorted(RAW.glob("*.xlsx"))
        if not files:
            raise FileNotFoundError("No cleaned CSV or raw Excel found.")
        df = pd.read_excel(files[0])
    df = _safe_to_datetime(df, ["InvoiceDate","DueDate","PaidDate"])
    return df

def main():
    df = load_clean_or_raw()
    df = _ensure_features(df)

    # محاسبه KPIها
    today = pd.Timestamp.today().normalize()
    kpis = {}

    # پایه
    kpis["invoices_total"] = int(len(df))
    kpis["amount_total"]   = float(df["Amount"].sum()) if "Amount" in df.columns else None

    # باز/سررسید گذشته
    open_mask = ~df["IsPaid"]
    overdue_mask = open_mask & (df["DaysPastDue"] > 0)

    kpis["open_count"]   = int(open_mask.sum())
    kpis["open_amount"]  = float(df.loc[open_mask, "Amount"].sum()) if "Amount" in df.columns else None
    kpis["overdue_count"]  = int(overdue_mask.sum())
    kpis["overdue_amount"] = float(df.loc[overdue_mask, "Amount"].sum()) if "Amount" in df.columns else None
    kpis["pct_overdue_amount"] = (
        float(kpis["overdue_amount"] / kpis["open_amount"] * 100.0) if kpis["open_amount"] not in (0, None) else None
    )

    # تمرکز تأمین‌کننده‌ها (Top 10 share)
    if set(["Vendor","Amount"]).issubset(df.columns):
        vendor_sum = df.groupby("Vendor")["Amount"].sum().sort_values(ascending=False)
        top10 = vendor_sum.head(10).sum()
        total_amt = vendor_sum.sum()
        kpis["top10_vendor_share_pct"] = float(top10 / total_amt * 100.0) if total_amt else None
        kpis["top_vendor_name"] = str(vendor_sum.index[0]) if len(vendor_sum) else None
        kpis["top_vendor_amount"] = float(vendor_sum.iloc[0]) if len(vendor_sum) else None

    # متوسط روز پرداخت برای فاکتورهای پرداخت‌شده
    if set(["InvoiceDate","PaidDate"]).issubset(df.columns):
        paid = df[df["IsPaid"]].copy()
        paid["DaysToPay"] = (paid["PaidDate"] - paid["InvoiceDate"]).dt.days
        if len(paid):
            kpis["days_to_pay_avg"]   = float(paid["DaysToPay"].mean())
            kpis["days_to_pay_median"] = float(paid["DaysToPay"].median())

    # تاخیر پرداخت نسبت به سررسید (PaidDate - DueDate)
    if set(["DueDate","PaidDate"]).issubset(df.columns):
        paid2 = df[df["IsPaid"]].copy()
        paid2["DelayVsDue"] = (paid2["PaidDate"] - paid2["DueDate"]).dt.days
        if len(paid2):
            kpis["delay_vs_due_avg"] = float(paid2["DelayVsDue"].mean())
            kpis["delay_vs_due_pct_late"] = float((paid2["DelayVsDue"] > 0).mean() * 100.0)

    # تعهد نقدی 7 و 30 روز آینده (برای فاکتورهای باز)
    if set(["DueDate","Amount"]).issubset(df.columns):
        horizon = (df["DueDate"] - today).dt.days
        kpis["cash_out_next_7"]  = float(df.loc[open_mask & (horizon.between(0,7)),  "Amount"].sum())
        kpis["cash_out_next_30"] = float(df.loc[open_mask & (horizon.between(0,30)), "Amount"].sum())

    # ترکیبات ارزی
    if "Currency" in df.columns and "Amount" in df.columns:
        ccy = df.groupby("Currency").agg(
            count=("Currency","size"),
            amount=("Amount","sum")
        ).reset_index()
        ccy_csv = PROC / "kpi_currency_breakdown.csv"
        ccy.to_csv(ccy_csv, index=False)

    # Terms (اگر موجود)
    if "Terms" in df.columns:
        terms_days = df["Terms"].map(_parse_terms_days)
        if terms_days.notna().any():
            kpis["terms_days_avg"]   = float(terms_days.mean())
            kpis["terms_days_median"] = float(terms_days.median())

    # ذخیره KPIها
    kpi_df = pd.DataFrame([kpis])
    kpi_csv = PROC / "kpis_summary.csv"
    kpi_json = PROC / "kpis_summary.json"
    kpi_df.to_csv(kpi_csv, index=False)
    kpi_df.to_json(kpi_json, orient="records", force_ascii=False, indent=2)

    print("\n--- KPI SUMMARY ---")
    for k,v in kpis.items():
        print(f"{k}: {v}")
    print(f"\nSaved: {kpi_csv}\nSaved: {kpi_json}")
    if "kpi_currency_breakdown.csv" in [p.name for p in PROC.iterdir()]:
        print("Saved: data/processed/kpi_currency_breakdown.csv")

if __name__ == "__main__":
    main()
