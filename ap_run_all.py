# ap_run_all.py
import subprocess, sys

def run(pyfile):
    print(f"\n=== Running: {pyfile} ===")
    cmd = [sys.executable, pyfile]
    subprocess.check_call(cmd)

def main():
    # در صورت داشتن نام‌های متفاوت، این لیست را مطابق فایل‌های خودت تنظیم کن
    steps = [
        "ap_cleaning.py",  # خروجی: data/processed/ap_clean.csv
        "ap_kpis.py",      # خروجی: data/processed/kpis_summary.csv/json و ...
        "ap_reports.py",   # خروجی: aging_open.csv, top_vendors.csv, cash_weekly.csv
        "ap_charts.py"     # خروجی: PNG ها در reports/
    ]
    for s in steps:
        run(s)

if __name__ == "__main__":
    main()
