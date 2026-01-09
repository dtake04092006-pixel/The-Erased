import requests
import io
import base64
import re
import random
from PIL import Image

def scan_image_gemini(image_url, api_keys):
    """
    OCR Engine - Sử dụng Model 'gemini-3-flash-preview' (Theo ảnh Google AI Studio 2026 của bạn)
    """
    valid_keys = [k for k in api_keys if k.strip()]
    if not valid_keys:
        print("[OCR] ❌ Chưa nhập GEMINI_API_KEY trong Environment Variables!")
        return []

    try:
        # Tải ảnh (Retry 3 lần)
        img_bytes = None
        for attempt in range(3):
            try:
                resp = requests.get(image_url, timeout=10)
                if resp.status_code == 200:
                    img_bytes = resp.content
                    break
            except: pass
        
        if not img_bytes: 
            print("[OCR] ❌ Không tải được ảnh từ Discord (URL lỗi hoặc mạng lag).")
            return []

        img = Image.open(io.BytesIO(img_bytes))
        width, height = img.size
        
        # Logic cắt ảnh
        num_cards = 3 
        if width > 1000: num_cards = 4
        card_width = width // num_cards
        results = []
        
        # Chọn Key ngẫu nhiên
        api_key = random.choice(valid_keys).strip()
        key_suffix = api_key[-4:] if len(api_key) > 4 else "xxxx"
        
        # --- SỬA CHUẨN THEO ẢNH CỦA BẠN ---
        # Model: gemini-3-flash-preview
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"

        print(f"[GEMINI] 🚀 Bắt đầu quét {num_cards} thẻ (Model: Gemini 3 Flash)...", flush=True)

        for i in range(num_cards):
            left = i * card_width
            right = (i + 1) * card_width
            
            # Cắt 15% dưới (Tỷ lệ 0.86)
            print_crop_top = int(height * 0.86) 
            crop_img = img.crop((left, print_crop_top, right, height))
            
            # Fix lỗi RGBA
            if crop_img.mode in ("RGBA", "P"):
                crop_img = crop_img.convert("RGB")
            
            # Base64
            buffered = io.BytesIO()
            crop_img.save(buffered, format="JPEG")
            img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Identify the Print Number and Edition Number. Output ONLY two numbers separated by a space. Format: 'Print Edition'. Example: '1234 2'. If edition is not visible, assume 1."},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                    ]
                }]
            }
            
            print(f"[GEMINI] 📤 Thẻ {i+1}: Đang gửi tới Google (Key: ...{key_suffix})...", flush=True)
            
            try:
                ocr_resp = requests.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
                
                if ocr_resp.status_code == 200:
                    print(f"[GEMINI] ✅ Thẻ {i+1}: API OK (Status 200).", flush=True)
                    data = ocr_resp.json()
                    
                    if 'candidates' in data:
                        text_result = data['candidates'][0]['content']['parts'][0]['text']
                        numbers = re.findall(r'\d+', text_result)
                        
                        p_num, e_num = 0, 1
                        if len(numbers) >= 2:
                            p_num, e_num = int(numbers[0]), int(numbers[1])
                        elif len(numbers) == 1:
                            p_num = int(numbers[0])
                        
                        if p_num > 0:
                            print(f"[GEMINI] 🎯 Thẻ {i+1}: Tìm thấy Print #{p_num} Ed {e_num}", flush=True)
                            results.append((i, p_num, e_num))
                        else:
                            print(f"[GEMINI] ⚠️ Thẻ {i+1}: API trả về text nhưng không tìm thấy số: '{text_result.strip()}'", flush=True)
                else:
                    print(f"[GEMINI] ❌ Thẻ {i+1}: LỖI API! Status: {ocr_resp.status_code}", flush=True)
                    print(f"[GEMINI] 📜 Chi tiết lỗi: {ocr_resp.text}", flush=True)
            
            except Exception as req_err:
                 print(f"[GEMINI] ❌ Thẻ {i+1}: Lỗi kết nối mạng: {req_err}", flush=True)
            
        return results

    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return []
