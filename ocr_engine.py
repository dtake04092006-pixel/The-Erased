import requests
import io
import base64
import re
import random
from PIL import Image

def scan_image_gemini(image_url, api_keys):
    """
    Logic kết hợp: Dùng AI Gemini nhưng cắt ảnh theo tỷ lệ chuẩn của code cũ (0.86)
    """
    valid_keys = [k for k in api_keys if k.strip()]
    if not valid_keys:
        print("[OCR] ❌ Chưa nhập GEMINI_API_KEY!")
        return []

    try:
        # Tải ảnh (Thử lại 3 lần giống code cũ để tránh mạng lag)
        img_bytes = None
        for attempt in range(3):
            try:
                resp = requests.get(image_url, timeout=10)
                if resp.status_code == 200:
                    img_bytes = resp.content
                    break
            except: pass
        
        if not img_bytes: return []

        img = Image.open(io.BytesIO(img_bytes))
        width, height = img.size
        
        # --- LOGIC CŨ: Xác định số thẻ ---
        # Code mẫu: num_cards = 4 if width > 1000 else 3
        num_cards = 3 
        if width > 1000: num_cards = 4
        
        card_width = width // num_cards
        results = []
        
        api_key = random.choice(valid_keys).strip()
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

        for i in range(num_cards):
            left = i * card_width
            right = (i + 1) * card_width
            
            # --- LOGIC CŨ: CẮT ẢNH Ở 0.86 (Chuẩn hơn 0.85) ---
            print_crop_top = int(height * 0.86) 
            crop_img = img.crop((left, print_crop_top, right, height))
            
            # --- FIX LỖI RGBA (Code cũ convert 'L' trắng đen, Gemini cần 'RGB' màu) ---
            if crop_img.mode in ("RGBA", "P"):
                crop_img = crop_img.convert("RGB")
            
            # Base64 hóa
            buffered = io.BytesIO()
            crop_img.save(buffered, format="JPEG")
            img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            # Prompt chuẩn
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Identify the Print Number and Edition Number. Output ONLY two numbers separated by a space. Format: 'Print Edition'. Example: '1234 2'. If edition is not visible, assume 1."},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                    ]
                }]
            }
            
            ocr_resp = requests.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=5)
            
            if ocr_resp.status_code == 200:
                data = ocr_resp.json()
                try:
                    if 'candidates' in data:
                        text_result = data['candidates'][0]['content']['parts'][0]['text']
                        numbers = re.findall(r'\d+', text_result)
                        
                        p_num, e_num = 0, 1
                        
                        if len(numbers) >= 2:
                            p_num = int(numbers[0])
                            e_num = int(numbers[1])
                        elif len(numbers) == 1:
                            # Logic dự phòng nếu dính số
                            p_num = int(numbers[0])
                        
                        if p_num > 0:
                            results.append((i, p_num, e_num))
                except: pass
            
        return results

    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return []
