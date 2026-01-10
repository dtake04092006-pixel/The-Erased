import requests
import io
import base64
import re
import random
import time
from PIL import Image, ImageEnhance

# Danh sách đen tạm thời (429 - Quá tải) -> Chờ 60s thả ra
TEMP_BANNED_KEYS = {} 
# Danh sách đen vĩnh viễn (Key chết/Hết hạn/Sai model) -> Xóa luôn
DEAD_KEYS = set()

def scan_image_gemini(image_url, api_keys_list):
    """
    OCR Engine: Gemini 3 Flash Preview (Theo yêu cầu).
    - Tự động xóa Key chết (400) và Key lỗi (404).
    """
    global TEMP_BANNED_KEYS, DEAD_KEYS
    
    # 1. Lọc và làm sạch danh sách Key
    if isinstance(api_keys_list, str):
        all_keys = [k.strip() for k in api_keys_list.split(',') if k.strip()]
    else:
        all_keys = [k for k in api_keys_list if k.strip()]

    # Chỉ lấy key chưa chết
    valid_keys = [k for k in all_keys if k not in DEAD_KEYS]

    if not valid_keys:
        print("[OCR] ❌ Lỗi: Tất cả Key đều đã chết!", flush=True)
        return []

    # 2. Cơ chế Cool-down (60s) cho Key quá tải
    current_time = time.time()
    TEMP_BANNED_KEYS = {k: t for k, t in TEMP_BANNED_KEYS.items() if current_time - t < 60}
    
    # Key sẵn sàng (Chưa chết và không bị quá tải)
    ready_keys = [k for k in valid_keys if k not in TEMP_BANNED_KEYS]
    
    # Nếu tất cả key sống đều đang bận (429) -> Reset tạm danh sách bận để thử lại vận may
    if not ready_keys and valid_keys:
        ready_keys = valid_keys
        TEMP_BANNED_KEYS.clear()
        # print("[OCR] ⚠️ Tất cả key đều bận! Thử lại...", flush=True)

    random.shuffle(ready_keys)

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
        for api_key in ready_keys:
            key_short = api_key[-4:]
            
            # --- MODEL GEMINI 3 FLASH PREVIEW ---
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
            
            try:
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
                                print(f"   => [GEMINI 3] ✅ OK (...{key_short}): {clean_results}", flush=True)
                                return clean_results

                # --- XỬ LÝ LỖI ---
                elif ocr_resp.status_code == 429:
                    print(f"   => [GEMINI 3] ⏳ Quá tải (...{key_short}) -> Né 60s.", flush=True)
                    TEMP_BANNED_KEYS[api_key] = time.time()
                    continue
                
                elif ocr_resp.status_code == 400: # Key Expired
                    print(f"   => [GEMINI 3] 💀 KEY CHẾT (...{key_short}) -> XÓA.", flush=True)
                    DEAD_KEYS.add(api_key)
                    continue
                
                # Quan trọng: Nếu vẫn bị 404 ở key nào thì xóa luôn key đó cho gọn
                elif ocr_resp.status_code == 404: 
                    print(f"   => [GEMINI 3] 💀 Lỗi 404 (...{key_short}) -> XÓA.", flush=True)
                    DEAD_KEYS.add(api_key)
                    continue

                else:
                    print(f"   => [GEMINI 3] ⚠️ Lỗi {ocr_resp.status_code} (...{key_short})", flush=True)
                    continue

            except Exception as e:
                print(f"   => [GEMINI 3] ❌ Lỗi mạng: {e}", flush=True)
                continue
        
        return []

    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return []
