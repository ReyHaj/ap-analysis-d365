from pathlib import Path
import pandas as pd
import numpy as np

PROC = Path("data/processed")
RAW  = Path("data/raw")
PROC.mkdir(parents=True, exist_ok=True)

def _safe_to_datetime(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df

def _ensure_features(df):
    df["IsPaid"] = False
    if "Status" in df.columns:
        df["IsPaid"] = df["IsPaid"] | df["Status"].astype(str).str.lower().eq("paid")
    if "PaidDate" in df.columns:
        df["IsPaid"] = df["IsPaid"] | df["PaidDate"].notna()

    today = pd.Timestamp.today().normalize()
    if "DueDate" in df.columns:
        dpd_today = (today - df["DueDate"]).dt.days
        dpd_paid  = (df["PaidDate"] - df["DueDate"]).dt.days if "PaidDate" in df.columns else np.nan
        df["DaysPastDue"] = np.where(df["IsPaid"], dpd_paid, dpd_today)
        df["DaysPastDue"] = df["DaysPastDue"].fillna(0).clip(lower=0)
    else:
        df["DaysPastDue"] = 0

    if "AgingBucket" not in df.columns:
        bins   = [-1, 0, 30, 60, 90, np.inf]
        labels = ["Current","0–30","31–60","61–90",">90"]
        df["AgingBucket"] = pd.cut(df["DaysPastDue"], bins=bins, labels=labels)
    return df

def load_clean_or_raw():
    clean_csv = PROC / "ap_clean.csv"
    if clean_csv.exists():
        df = pd.read_csv(clean_csv)
    else:
        files = sorted(RAW.glob("*.xlsx"))
        if not files:
            raise FileNotFoundError("No cleaned CSV or raw Excel found.")
        df = pd.read_excel(files[0])
    df = _safe_to_datetime(df, ["InvoiceDate","DueDate","PaidDate"])
    df = _ensure_features(df)
    return df

def report_aging_open(df: pd.DataFrame) -> Path:
    open_df = df.loc[~df["IsPaid"]].copy()
    grp = open_df.groupby("AgingBucket").agg(
        Amount=("Amount","sum"),
        Count=("AgingBucket","size")
    ).reset_index().sort_values("AgingBucket")
    out = PROC / "aging_open.csv"
    grp.to_csv(out, index=False)
    return out

def report_top_vendors(df: pd.DataFrame, top_n: int = 10) -> Path:
    grp = (
        df.groupby("Vendor")
          .agg(Amount=("Amount","sum"), CountInvoices=("Vendor","size"))
          .sort_values("Amount", ascending=False)
          .head(top_n)
          .reset_index()
    )
    out = PROC / "top_vendors.csv"
    grp.to_csv(out, index=False)
    return out

def report_cash_weekly(df: pd.DataFrame) -> Path:
    open_df = df.loc[~df["IsPaid"]].copy()
    open_df["DueWeek"] = open_df["DueDate"].dt.to_period("W").dt.start_time
    grp = (
        open_df.groupby("DueWeek")["Amount"]
               .sum()
               .reset_index()
               .sort_values("DueWeek")
    )
    out = PROC / "cash_weekly.csv"
    grp.to_csv(out, index=False)
    return out

def main():
    df = load_clean_or_raw()
    # اطمینان از وجود ستون Amount
    if "Amount" not in df.columns:
        raise ValueError("Column 'Amount' is required for reports.")
    p1 = report_aging_open(df)
    p2 = report_top_vendors(df, top_n=10)
    p3 = report_cash_weekly(df)

    print("\n--- REPORTS ---")
    print("Saved:", p1)
    print("Saved:", p2)
    print("Saved:", p3)

if __name__ == "__main__":
    main()
