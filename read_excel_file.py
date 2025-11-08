from pathlib import Path
import pandas as pd

p = Path("data/raw")
files = list(p.glob("*.xlsx"))

file_path = files[0]
print("Using file:", file_path)

df = pd.read_excel(file_path)
print(df.head())
