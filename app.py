# app.py — AP Analysis Dashboard (Streamlit)
from pathlib import Path
import pandas as pd
import numpy as np
import streamlit as st

RAW  = Path("data/raw")
PROC = Path("data/processed")
PROC.mkdir(parents=True, exist_ok=True)

ALLOWED_CCY = {"USD","EUR","GBP","CAD","AUD","JPY"}

# ---------- Utilities ----------
def _find_xlsx():
    files = sorted(RAW.glob("*.xlsx"))
    if not files:
        st.error("No Excel file found in data/raw/. Please put your AP .xlsx there.")
        st.stop()
    return files[0]

def _to_datetime(s):
    return pd.to_datetime(s, errors="coerce")

def _clean(df: pd.DataFrame) -> pd.DataFrame:
    # 1) APID present
    df = df[df["APID"].notna() & (df["APID"].astype(str).str.strip() != "")]
    # 2) Amount > 0
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    df = df[df["Amount"] > 0]
    # 3) dates -> datetime and valid
    for c in ["InvoiceDate","DueDate","PaidDate"]:
        if c in df.columns:
            df[c] = _to_datetime(df[c])
    df = df[df["InvoiceDate"].notna() & df["DueDate"].notna()]
    # 4) DueDate >= InvoiceDate
    df = df[df["DueDate"] >= df["InvoiceDate"]]
    # 5) valid currency
    if "Currency" in df.columns:
        df["Currency"] = df["Currency"].astype(str).str.strip()
        df = df[df["Currency"].isin(ALLOWED_CCY)]
    # 6) drop duplicates on composite key
    df["CompositeKey"] = (
        df["APID"].astype(str) + "|" +
        df["Vendor"].astype(str) + "|" +
        df["InvoiceDate"].astype(str) + "|" +
        df["Amount"].astype(str)
    )
    df = df.drop_duplicates(subset="CompositeKey", keep="first").drop(columns=["CompositeKey"])
    return df

@st.cache_data
def load_data():
    clean_csv = PROC / "ap_clean.csv"
    if clean_csv.exists():
        df = pd.read_csv(clean_csv, parse_dates=["InvoiceDate","DueDate","PaidDate"])
        return df, True  # already cleaned
    # otherwise read raw and clean on the fly
    xlsx = _find_xlsx()
    df = pd.read_excel(xlsx)
    df = _clean(df)
    # persist for reuse
    df.to_csv(clean_csv, index=False)
    return df, False

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    # IsPaid flag
    df["IsPaid"] = False
    if "Status" in df.columns:
        df["IsPaid"] = df["IsPaid"] | df["Status"].astype(str).str.lower().eq("paid")
    if "PaidDate" in df.columns:
        df["IsPaid"] = df["IsPaid"] | df["PaidDate"].notna()
    # DaysPastDue
    today = pd.Timestamp.today().normalize()
    dpd_today = (today - df["DueDate"]).dt.days
    dpd_paid  = (df["PaidDate"] - df["DueDate"]).dt.days if "PaidDate" in df.columns else 0
    arr = np.where(df["IsPaid"], dpd_paid, dpd_today).astype("float")
    arr = arr.clip(min=0)   # به جای clip(lower=0)
    df["DaysPastDue"] = arr
    
    # Aging buckets
    bins   = [-1, 0, 30, 60, 90, np.inf]
    labels = ["Current","0–30","31–60","61–90",">90"]
    df["AgingBucket"] = pd.cut(df["DaysPastDue"], bins=bins, labels=labels)
    return df

def kpi_block(df: pd.DataFrame):
    total = len(df)
    open_mask = ~df["IsPaid"]
    overdue_mask = open_mask & (df["DaysPastDue"] > 0)
    overdue_amt = df.loc[overdue_mask, "Amount"].sum() if "Amount" in df.columns else 0.0
    col1,col2,col3,col4 = st.columns(4)
    col1.metric("Invoices", f"{total:,}")
    col2.metric("Open", f"{open_mask.sum():,}")
    col3.metric("Overdue", f"{overdue_mask.sum():,}")
    col4.metric("Overdue Amount", f"{overdue_amt:,.0f}")

# ---------- App ----------
st.set_page_config(page_title="AP Analysis (D365-style)", layout="wide")
st.title("Accounts Payable — Interactive Dashboard")

df, from_processed = load_data()
df = compute_features(df)

with st.sidebar:
    st.header("Filters")
    # Date range (InvoiceDate)
    min_d, max_d = df["InvoiceDate"].min(), df["InvoiceDate"].max()
    d_from, d_to = st.date_input("Invoice Date range", value=(min_d.date(), max_d.date()))
    # Vendors
    vendors = sorted(df["Vendor"].astype(str).unique())
    sel_vendors = st.multiselect("Vendors", vendors)
    # Currency
    if "Currency" in df.columns:
        currs = sorted(df["Currency"].unique())
        sel_ccy = st.multiselect("Currency", currs)
    else:
        sel_ccy = []

# apply filters
mask = (df["InvoiceDate"].dt.date >= d_from) & (df["InvoiceDate"].dt.date <= d_to)
if sel_vendors:
    mask &= df["Vendor"].astype(str).isin(sel_vendors)
if sel_ccy:
    mask &= df["Currency"].isin(sel_ccy)
df_f = df.loc[mask].copy()

st.subheader("KPIs")
kpi_block(df_f)

# Aging (Open)
st.subheader("Aging — Open Invoices")
open_df = df_f.loc[~df_f["IsPaid"]]
aging = open_df.groupby("AgingBucket")["Amount"].sum().reindex(["Current","0–30","31–60","61–90",">90"]).fillna(0)
st.bar_chart(aging)

# Top Vendors
st.subheader("Top Vendors by Spend")
top_vendors = df_f.groupby("Vendor")["Amount"].sum().sort_values(ascending=False).head(10)
st.bar_chart(top_vendors)

# Cash weekly
st.subheader("Cash Outflow by Week (Open)")
if not open_df.empty:
    open_df["DueWeek"] = open_df["DueDate"].dt.to_period("W").dt.start_time
    cash_weekly = open_df.groupby("DueWeek")["Amount"].sum().reset_index().sort_values("DueWeek")
    st.line_chart(cash_weekly.set_index("DueWeek"))
else:
    st.info("No open invoices in current filters.")

# Data table + downloads
st.subheader("Data (filtered)")
st.dataframe(df_f.head(200))
st.download_button("Download filtered CSV", df_f.to_csv(index=False).encode("utf-8"), file_name="ap_filtered.csv")

# Badges
st.caption(f"{'Loaded from processed' if from_processed else 'Cleaned from raw'} • Rows: {len(df):,}")
