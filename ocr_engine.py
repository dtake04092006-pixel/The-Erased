import requests
import io
import base64
import re
import random
import time
from PIL import Image

def scan_image_gemini(image_url, api_keys):
    """
    OCR Engine ONE-SHOT: Quét toàn bộ ảnh trong 1 Request.
    Phù hợp cho 200+ Server để tiết kiệm API Key.
    """
    valid_keys = [k for k in api_keys if k.strip()]
    if not valid_keys: return []

    session = requests.Session()

    try:
        # Tải ảnh
        img_bytes = None
        for attempt in range(3):
            try:
                resp = session.get(image_url, timeout=10)
                if resp.status_code == 200:
                    img_bytes = resp.content
                    break
            except: pass
        
        if not img_bytes: return []

        img = Image.open(io.BytesIO(img_bytes))
        
        # Resize ảnh gốc nếu quá to để gửi cho nhanh (Max width 1024 là đủ đọc)
        if img.width > 1024:
            ratio = 1024 / float(img.width)
            new_height = int((float(img.height) * float(ratio)))
            img = img.resize((1024, new_height), Image.Resampling.LANCZOS)

        # Chuyển đổi màu
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Nén ảnh
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=80)
        img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # --- PROMPT MỚI: ĐỌC TẤT CẢ THẺ CÙNG LÚC ---
        payload = {
            "contents": [{
                "parts": [
                    # Prompt này dạy Gemini đọc từ trái sang phải, trả về list
                    {"text": "Extract Print Number and Edition for ALL cards in this image, from left to right. Ignore visual effects. Output format for each card: 'Print-Edition'. Return list separated by comma. Example: '124-2, 55-1, 999-3'."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        
        results = []
        random.shuffle(valid_keys)

        for api_key in valid_keys:
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
            
            try:
                ocr_resp = session.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=8)
                
                if ocr_resp.status_code == 200:
                    data = ocr_resp.json()
                    if 'candidates' in data:
                        text_result = data['candidates'][0]['content']['parts'][0]['text']
                        print(f"[GEMINI] 🤖 Raw Response: {text_result.strip()}") # Debug xem nó trả về gì
                        
                        # Xử lý chuỗi trả về: Tìm tất cả cặp số
                        # Nó sẽ bắt các cặp số dạng: 123-2 hoặc 123 2
                        matches = re.findall(r'(\d+)[\s\-\.]+(\d+)', text_result)
                        
                        for idx, (p_str, e_str) in enumerate(matches):
                            # Giới hạn chỉ lấy 3 hoặc 4 thẻ đầu (tránh AI hallucination bịa thêm)
                            if idx > 3: break 
                            results.append((idx, int(p_str), int(e_str)))
                        
                        if results:
                            print(f"[GEMINI] ✅ One-Shot thành công: {results}")
                            return results # Trả về ngay, tiết kiệm thời gian
            
            except Exception as e:
                print(f"[GEMINI] Lỗi: {e}")
                continue # Thử key khác nếu lỗi mạng/429

        return results

    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return []
