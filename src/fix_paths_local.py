"""
Sửa đường dẫn ảnh từ Colab (/content/...) → Local (D:/...)
Chạy 1 lần duy nhất sau khi tải folder skin_cancer từ Drive về.
"""
import pandas as pd
import os
from config import BASE, DATA_DIR

# Đường dẫn cũ trên Colab
OLD_PREFIX = '/content/data/isic2019'
NEW_PREFIX = DATA_DIR   # D:\DoAnTriTueNhanTao\data\isic2019

files_to_fix = [
    f'{BASE}/isic2019_metadata.csv',
    f'{BASE}/train.csv',
    f'{BASE}/val.csv',
    f'{BASE}/test.csv',
    f'{BASE}/results/binary_test_predictions.csv',
    f'{BASE}/results/multiclass_test_predictions.csv',
]

for path in files_to_fix:
    if not os.path.exists(path):
        print(f"⚠️  Không có: {path}")
        continue

    df = pd.read_csv(path)
    if 'img_path' not in df.columns:
        print(f"⚠️  Không có cột img_path: {path}")
        continue

    # Đếm số dòng cần sửa
    mask = df['img_path'].str.startswith(OLD_PREFIX, na=False)
    n_fix = mask.sum()

    # Sửa
    df['img_path'] = df['img_path'].str.replace(OLD_PREFIX, NEW_PREFIX, regex=False)
    df.to_csv(path, index=False)

    print(f"✓ {os.path.basename(path):40s} — đã sửa {n_fix} dòng")

print("\n✅ Xong! Tất cả đường dẫn đã chuyển sang local.")