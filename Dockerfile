# Sử dụng Python 3.9 slim để nhẹ
FROM python:3.9-slim

# Thiết lập thư mục làm việc
WORKDIR /app

# Copy file requirements và cài đặt thư viện
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn vào container
COPY . .

# Mở port (Render thường dùng 10000)
EXPOSE 10000

# Lệnh chạy file main.py
CMD ["python", "main.py"]
