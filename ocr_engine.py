import requests
import io
import base64
import re
import random
import time
from PIL import Image, ImageEnhance

# Biến toàn cục để nhớ những key nào đang bị "phạt" (429)
# Để lần sau né nó ra, đỡ tốn thời gian thử
BAD_KEYS = {} 

def scan_image_gemini(image_url, api_keys_list):
    """
    OCR Engine: Gemini 3 Flash Preview
    - Hỗ trợ list key cực dài (50-100 key).
    - Tự động né các key đang bị 429 trong vòng 1 phút.
    """
    global BAD_KEYS
    
    # 1. Lọc và làm sạch danh sách Key
    if isinstance(api_keys_list, str):
        all_keys = [k.strip() for k in api_keys_list.split(',') if k.strip()]
    else:
        all_keys = [k for k in api_keys_list if k.strip()]

    if not all_keys:
        print("[OCR] ❌ Lỗi: Không có API Key!", flush=True)
        return []

    # 2. Cơ chế lọc Key thông minh (Smart Rotation)
    current_time = time.time()
    # Xóa các key đã hết hạn phạt (sau 60s)
    BAD_KEYS = {k: t for k, t in BAD_KEYS.items() if current_time - t < 60}
    
    # Chỉ lấy những key KHÔNG nằm trong danh sách phạt
    good_keys = [k for k in all_keys if k not in BAD_KEYS]
    
    # Nếu tất cả key đều bị phạt -> Buộc phải dùng lại tất cả (Reset)
    if not good_keys:
        good_keys = all_keys
        BAD_KEYS.clear()
        print("[OCR] ⚠️ Tất cả key đều đang quá tải! Đang thử lại vận may...", flush=True)

    # Xáo trộn ngẫu nhiên để chia tải
    random.shuffle(good_keys)

    headers = {"User-Agent": "Mozilla/5.0"}
    session = requests.Session()

    try:
        # TẢI ẢNH
        img_bytes = None
        for _ in range(2):
            try:
                resp = session.get(image_url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    img_bytes = resp.content
                    break
            except: time.sleep(0.2)
        
        if not img_bytes: return []

        original_img = Image.open(io.BytesIO(img_bytes))
        width, height = original_img.size
        
        # XỬ LÝ ẢNH (Cắt 12.5% + Xếp tầng)
        num_cards = 3
        if width > 1000: num_cards = 4
        card_width = width // num_cards
        
        crop_height = int(height * 0.125) 
        crop_top = height - crop_height
        
        stack_img = Image.new('RGB', (card_width, (crop_height + 20) * num_cards), (255, 0, 255))
        
        crops_data = [] 
        for i in range(num_cards):
            left = i * card_width
            right = (i + 1) * card_width
            crop = original_img.crop((left, crop_top, right, height))
            if crop.mode != 'RGB': crop = crop.convert('RGB')
            enhancer = ImageEnhance.Contrast(crop)
            crop = enhancer.enhance(2.0) 
            y_offset = i * (crop_height + 20)
            stack_img.paste(crop, (0, y_offset))
            crops_data.append(i)

        buffered = io.BytesIO()
        stack_img.save(buffered, format="JPEG", quality=90)
        img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        payload = {
            "contents": [{
                "parts": [
                    {"text": "Read these vertically stacked numbers. Format: 'P-E'. Example: '79371-1'."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        
        # THỬ TỪNG KEY
        for api_key in good_keys:
            key_short = api_key[-4:]
            
            # Model Gemini 3 Flash Preview
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
            
            try:
                print(f"   => [GEMINI 3] 🚀 Đang gửi (Key ...{key_short})...", flush=True)
                ocr_resp = session.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=8)
                
                if ocr_resp.status_code == 200:
                    data = ocr_resp.json()
                    if 'candidates' in data:
                        text = data['candidates'][0]['content']['parts'][0]['text']
                        matches = re.findall(r'(\d+)[\s\-\.·•|]+(\d+)', text)
                        
                        if matches:
                            clean_results = []
                            for idx, (p_str, e_str) in enumerate(matches):
                                if idx < len(crops_data):
                                    original_idx = crops_data[idx]
                                    p, e = int(p_str), int(e_str)
                                    if p > 0: clean_results.append((original_idx, p, e))
                            
                            if clean_results:
                                print(f"   => [GEMINI 3] ✅ OK: {clean_results}", flush=True)
                                return clean_results

                elif ocr_resp.status_code == 429:
                    print(f"   => [GEMINI 3] ⏳ Key ...{key_short} quá tải -> Tạm khóa 60s.", flush=True)
                    # Đưa key vào danh sách đen trong 60s
                    BAD_KEYS[api_key] = time.time()
                    continue
                else:
                    print(f"   => [GEMINI 3] 💀 Lỗi {ocr_resp.status_code}: {ocr_resp.text}", flush=True)
                    continue

            except Exception as e:
                print(f"   => [GEMINI 3] ❌ Lỗi mạng: {e}", flush=True)
                continue
        
        return []

    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return []
