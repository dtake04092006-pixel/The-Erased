import requests
import io
import base64
import re
import random
import time
from PIL import Image, ImageEnhance

# Danh sách đen tạm thời để né các key bị quá tải (429)
BAD_KEYS = {} 

def scan_image_gemini(image_url, api_keys_list):
    """
    OCR Engine: Gemini 2.5 Flash (Theo snippet bạn cung cấp).
    - Model ID: gemini-2.5-flash
    - Chiến thuật: Xếp Tầng + Cắt 12.5% + Smart Rotation Key.
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

    # 2. Cơ chế lọc Key thông minh
    current_time = time.time()
    # Xóa các key đã hết hạn phạt (sau 60s)
    BAD_KEYS = {k: t for k, t in BAD_KEYS.items() if current_time - t < 60}
    
    # Chỉ lấy những key KHÔNG nằm trong danh sách phạt
    good_keys = [k for k in all_keys if k not in BAD_KEYS]
    
    # Nếu tất cả key đều bị phạt -> Reset để thử lại vận may
    if not good_keys:
        good_keys = all_keys
        BAD_KEYS.clear()
        print("[OCR] ⚠️ Tất cả key đều bận! Đang thử lại...", flush=True)

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
        
        # XỬ LÝ ẢNH (Cắt 12.5% + Xếp tầng) - GIỮ NGUYÊN VÌ ĐÃ CHUẨN
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
            
            # --- CẬP NHẬT MODEL MỚI: gemini-2.5-flash ---
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            
            try:
                print(f"   => [GEMINI 2.5] 🚀 Đang gửi (Key ...{key_short})...", flush=True)
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
                                print(f"   => [GEMINI 2.5] ✅ OK: {clean_results}", flush=True)
                                return clean_results
                        else:
                             # 2.5 có thể trả về text nhưng không đúng định dạng, log ra xem
                            print(f"   => [GEMINI 2.5] ⚠️ Text: {text.strip()}", flush=True)

                elif ocr_resp.status_code == 429:
                    print(f"   => [GEMINI 2.5] ⏳ Key ...{key_short} quá tải -> Tạm né.", flush=True)
                    BAD_KEYS[api_key] = time.time()
                    continue
                else:
                    # In mã lỗi để xem có bị 404 nữa không
                    print(f"   => [GEMINI 2.5] 💀 Lỗi {ocr_resp.status_code}: {ocr_resp.text}", flush=True)
                    continue

            except Exception as e:
                print(f"   => [GEMINI 2.5] ❌ Lỗi mạng: {e}", flush=True)
                continue
        
        return []

    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return []
