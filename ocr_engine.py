import requests
import io
import base64
import re
import random
import time
from PIL import Image, ImageEnhance

def scan_image_gemini(image_url, api_keys_list):
    """
    OCR Engine: Dùng 'gemini-1.5-flash-002' (Mã cứng, không dùng alias).
    - Đây là bản Update tháng 9/2025, ổn định nhất của Google.
    - Chiến thuật: Cắt 12.5% + Xếp Tầng.
    """
    if isinstance(api_keys_list, str):
        valid_keys = [k.strip() for k in api_keys_list.split(',') if k.strip()]
    else:
        valid_keys = [k for k in api_keys_list if k.strip()]

    if not valid_keys:
        print("[OCR] ❌ Lỗi: Không có API Key!", flush=True)
        return []

    headers = {"User-Agent": "Mozilla/5.0"}
    session = requests.Session()

    try:
        # 1. TẢI ẢNH
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
        
        # 2. XỬ LÝ ẢNH
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

        # 3. GỬI GEMINI (Dùng ID 002)
        payload = {
            "contents": [{
                "parts": [
                    {"text": "Read these vertically stacked numbers (Print and Edition). Format: 'P-E'. Example: '79371-1, 79552-1'."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        
        results = []
        random.shuffle(valid_keys)

        for api_key in valid_keys:
            key_short = api_key[-4:]
            
            # --- ĐỔI THÀNH MÃ CỨNG: gemini-1.5-flash-002 ---
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-002:generateContent?key={api_key}"
            
            try:
                print(f"   => [GEMINI 002] 🚀 Đang gửi (Key ...{key_short})...", flush=True)
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
                                    if p > 0:
                                        clean_results.append((original_idx, p, e))
                            
                            if clean_results:
                                print(f"   => [GEMINI 002] ✅ OK: {clean_results}", flush=True)
                                return clean_results
                        else:
                            print(f"   => [GEMINI 002] ⚠️ Không thấy số. Text: {text.strip()}", flush=True)

                elif ocr_resp.status_code == 429:
                    print(f"   => [GEMINI 002] ⏳ Key ...{key_short} quá tải.", flush=True)
                    continue
                else:
                    # Nếu vẫn lỗi 404 thì do tài khoản của bạn bị Google phạt hoặc chặn model này
                    print(f"   => [GEMINI 002] 💀 LỖI {ocr_resp.status_code}: {ocr_resp.text}", flush=True)
                    continue

            except Exception as e:
                print(f"   => [GEMINI 002] ❌ Lỗi mạng: {e}", flush=True)
                continue
        
        return results

    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return []
