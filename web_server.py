from flask import Flask, render_template
import os

app = Flask(__name__)

@app.route('/')
def index():
    # Render file index.html từ thư mục templates
    return render_template('index.html')

@app.route('/health')
def health():
    return "OK", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    # Host 0.0.0.0 bắt buộc để chạy trên Render
    app.run(host='0.0.0.0', port=port)
