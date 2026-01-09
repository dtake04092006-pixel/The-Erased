import requests
import io
import base64
import re
import random
import time
from PIL import Image, ImageEnhance

def scan_image_gemini(image_url, api_keys_list):
    """
    OCR Engine: Tối ưu hóa cho Karuta (Ảnh 836x419)
    - Model: gemini-1.5-flash (Bản chuẩn, cân bằng giữa thông minh và tốc độ).
    - Kỹ thuật: Cắt dải ngang (Horizontal Crop) + Tăng tương phản.
    - Regex: Fix lỗi dấu chấm giữa (·).
    """
    # Xử lý đầu vào danh sách Key
    if isinstance(api_keys_list, str):
        valid_keys = [k.strip() for k in api_keys_list.split(',') if k.strip()]
    else:
        valid_keys = [k for k in api_keys_list if k.strip()]

    if not valid_keys:
        print("[OCR] ❌ Lỗi: Chưa nhập API Key trong biến môi trường!", flush=True)
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    session = requests.Session()

    try:
        # 1. TẢI ẢNH (Retry 2 lần nếu mạng lag)
        img_bytes = None
        for _ in range(2):
            try:
                resp = session.get(image_url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    img_bytes = resp.content
                    break
            except: time.sleep(0.2)
        
        if not img_bytes: return []

        img = Image.open(io.BytesIO(img_bytes))
        width, height = img.size
        
        # 2. XỬ LÝ ẢNH
        # Cắt lấy 20% dưới đáy (Chứa toàn bộ hàng số)
        print_crop_top = int(height * 0.80) 
        crop_img = img.crop((0, print_crop_top, width, height))
        
        if crop_img.mode != 'RGB': crop_img = crop_img.convert('RGB')
        
        # Tăng tương phản lên 1.8 lần (Chữ trắng nổi bật trên nền tối)
        enhancer = ImageEnhance.Contrast(crop_img)
        crop_img = enhancer.enhance(1.8)
        
        # Chỉ resize nếu ảnh quá khổ (>1200px), còn ảnh Karuta chuẩn 836px thì giữ nguyên cho nét
        if crop_img.width > 1200:
            ratio = 1200 / float(crop_img.width)
            new_height = int((float(crop_img.height) * float(ratio)))
            crop_img = crop_img.resize((1200, new_height), Image.Resampling.LANCZOS)

        buffered = io.BytesIO()
        crop_img.save(buffered, format="JPEG", quality=90)
        img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 3. GỬI SANG GEMINI
        payload = {
            "contents": [{
                "parts": [
                    # Prompt dạy nó đọc từ trái qua phải
                    {"text": "Look at the numbers at the bottom. Extract all 'Print Number' and 'Edition' pairs from left to right. The format is usually like '12345 · 1'. Return ONLY a list formatted as 'P-E'. Example output: '79371-1, 79552-1'."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        
        results = []
        random.shuffle(valid_keys) # Trộn key để không bị dồn vào 1 cái

        for api_key in valid_keys:
            # Dùng bản 1.5 Flash chuẩn (Không dùng 8b vì 8b hơi kém thông minh với ảnh dẹt)
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            
            try:
                ocr_resp = session.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=7)
                
                if ocr_resp.status_code == 200:
                    data = ocr_resp.json()
                    if 'candidates' in data:
                        text = data['candidates'][0]['content']['parts'][0]['text']
                        
                        # --- REGEX FIX LỖI DẤU CHẤM (·) ---
                        # Bắt: Số + (dấu cách/gạch/chấm/bullet) + Số
                        matches = re.findall(r'(\d+)[\s\-\.·•|]+(\d+)', text)
                        
                        if matches:
                            # Lọc kết quả rác
                            clean_results = []
                            for i, (p_str, e_str) in enumerate(matches):
                                if i > 3: break # Chỉ lấy tối đa 4 thẻ đầu
                                p, e = int(p_str), int(e_str)
                                if p > 0: # Print phải lớn hơn 0
                                    clean_results.append((i, p, e))
                            
                            if clean_results:
                                return clean_results # Trả về ngay nếu thành công
                        
                elif ocr_resp.status_code == 429:
                    print(f"[GEMINI] ⏳ Key ...{api_key[-4:]} quá tải. Đang đổi key...", flush=True)
                    continue # Thử key tiếp theo

            except Exception:
                continue
        
        return results # Trả về rỗng nếu thất bại hết các key

    except Exception:
        return []
