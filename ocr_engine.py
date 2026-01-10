import requests
import io
import base64
import re
import random
import time
from PIL import Image, ImageEnhance

# Danh sách đen tạm thời (429 - Quá tải)
TEMP_BANNED_KEYS = {} 
# Danh sách đen vĩnh viễn (400 - Key chết/Hết hạn)
DEAD_KEYS = set()

def scan_image_gemini(image_url, api_keys_list):
    """
    OCR Engine: Tự động loại bỏ Key chết (Expired) và Key quá tải (429).
    Model: gemini-1.5-flash (Bản chuẩn, ổn định nhất).
    """
    global TEMP_BANNED_KEYS, DEAD_KEYS
    
    # 1. Lọc và làm sạch danh sách Key đầu vào
    if isinstance(api_keys_list, str):
        all_keys = [k.strip() for k in api_keys_list.split(',') if k.strip()]
    else:
        all_keys = [k for k in api_keys_list if k.strip()]

    # Loại bỏ ngay các key đã xác định là CHẾT
    valid_keys = [k for k in all_keys if k not in DEAD_KEYS]

    if not valid_keys:
        print("[OCR] ❌ Lỗi: Tất cả Key đều đã chết hoặc không tồn tại!", flush=True)
        return []

    # 2. Cơ chế phục hồi Key bị quá tải (Cool-down)
    current_time = time.time()
    # Mở khóa các key bị phạt 429 sau 60 giây
    TEMP_BANNED_KEYS = {k: t for k, t in TEMP_BANNED_KEYS.items() if current_time - t < 60}
    
    # Danh sách key sẵn sàng chiến đấu
    ready_keys = [k for k in valid_keys if k not in TEMP_BANNED_KEYS]
    
    # Nếu tất cả đều bận, buộc phải thử lại toàn bộ (Reset tạm thời)
    if not ready_keys:
        ready_keys = valid_keys
        TEMP_BANNED_KEYS.clear()
        print("[OCR] ⚠️ Tất cả key đều bận! Đang thử lại vận may...", flush=True)

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
        
        # XỬ LÝ ẢNH (GIỮ NGUYÊN)
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
            
            # --- DÙNG BẢN CHUẨN: gemini-1.5-flash ---
            # Nếu bản này vẫn lỗi 404, hãy thử đổi lại thành gemini-2.5-flash hoặc gemini-3-flash-preview
            # Nhưng quan trọng nhất là code này sẽ tự lọc key chết.
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            
            try:
                # print(f"   => [GEMINI] 🚀 Đang gửi (Key ...{key_short})...", flush=True) # Tắt log này cho đỡ rối
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
                                print(f"   => [GEMINI] ✅ OK (Key ...{key_short}): {clean_results}", flush=True)
                                return clean_results

                # XỬ LÝ LỖI
                elif ocr_resp.status_code == 429:
                    print(f"   => [GEMINI] ⏳ Quá tải (...{key_short}) -> Né 60s.", flush=True)
                    TEMP_BANNED_KEYS[api_key] = time.time()
                    continue
                
                elif ocr_resp.status_code == 400:
                    print(f"   => [GEMINI] 💀 KEY CHẾT (...{key_short}) -> XÓA VĨNH VIỄN KHỎI LIST.", flush=True)
                    DEAD_KEYS.add(api_key) # Thêm vào danh sách tử thần
                    continue

                else:
                    print(f"   => [GEMINI] ⚠️ Lỗi {ocr_resp.status_code} (...{key_short})", flush=True)
                    continue

            except Exception as e:
                print(f"   => [GEMINI] ❌ Lỗi mạng: {e}", flush=True)
                continue
        
        return []

    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return []
