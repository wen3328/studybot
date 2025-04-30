
# 使用輕量版 Python 映像檔
FROM python:3.10-slim

# 設定工作目錄
WORKDIR /app

# 複製專案檔案
COPY . .

# 安裝 Python 套件
RUN pip install --no-cache-dir -r requirements.txt

# 啟動應用程式（使用 Gunicorn）
CMD ["gunicorn", "-b", ":8080", "app:app"]

