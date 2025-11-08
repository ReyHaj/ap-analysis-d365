# ap_charts.py
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt

PROC = Path("data/processed")
REPORTS = Path("reports")
REPORTS.mkdir(parents=True, exist_ok=True)

def save_bar(df, x, y, title, fname):
    ax = df.plot(kind="bar", x=x, y=y, rot=0, title=title, legend=False)
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    plt.tight_layout()
    out = REPORTS / fname
    plt.savefig(out, dpi=120)
    plt.close()
    print("Saved:", out)

def save_line(df, x, y, title, fname):
    ax = df.plot(kind="line", x=x, y=y, marker="o", title=title, legend=False)
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    plt.tight_layout()
    out = REPORTS / fname
    plt.savefig(out, dpi=120)
    plt.close()
    print("Saved:", out)

def main():
    aging_csv = PROC / "aging_open.csv"
    top_csv   = PROC / "top_vendors.csv"
    cash_csv  = PROC / "cash_weekly.csv"

    if aging_csv.exists():
        aging = pd.read_csv(aging_csv)
        save_bar(aging, "AgingBucket", "Amount", "AP Aging — Open Invoices", "ap_aging_bar.png")

    if top_csv.exists():
        top = pd.read_csv(top_csv).head(10)
        save_bar(top, "Vendor", "Amount", "Top 10 Vendors by Spend", "top_vendors_bar.png")

    if cash_csv.exists():
        cash = pd.read_csv(cash_csv, parse_dates=["DueWeek"])
        save_line(cash, "DueWeek", "Amount", "Weekly Cash Outflow (Open Invoices)", "cash_outflow_line.png")

if __name__ == "__main__":
    main()
