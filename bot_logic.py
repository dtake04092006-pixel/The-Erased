import requests
import io
import base64
import re
import random
import time
from PIL import Image

def scan_image_gemini(image_url, api_keys):
    """
    OCR Engine: Cắt thẻ (Crop) + Auto-Switch Key + Log chi tiết.
    """
    valid_keys = [k for k in api_keys if k.strip()]
    if not valid_keys:
        print("[OCR] ❌ Chưa nhập GEMINI_API_KEY!", flush=True)
        return []

    # Giả lập trình duyệt để không bị Discord chặn tải ảnh
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    session = requests.Session()

    try:
        # 1. TẢI ẢNH (Có Retry & Log)
        img_bytes = None
        for attempt in range(3):
            try:
                resp = session.get(image_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    img_bytes = resp.content
                    break
                else:
                    print(f"[OCR] ⚠️ Tải ảnh lỗi {resp.status_code} (Lần {attempt+1})", flush=True)
            except Exception as e:
                print(f"[OCR] ⚠️ Lỗi mạng khi tải ảnh: {e}", flush=True)
                time.sleep(0.5)
        
        if not img_bytes: 
            print("[OCR] ❌ Tải ảnh thất bại hoàn toàn!", flush=True)
            return []

        img = Image.open(io.BytesIO(img_bytes))
        width, height = img.size
        
        # Logic xác định số thẻ
        num_cards = 3 
        if width > 1000: num_cards = 4
        card_width = width // num_cards
        results = []
        
        print(f"[GEMINI] 📸 Ảnh {width}x{height} -> Cắt {num_cards} thẻ. Đang gửi đi...", flush=True)

        # 2. XỬ LÝ TỪNG THẺ
        for i in range(num_cards):
            left = i * card_width
            right = (i + 1) * card_width
            
            # Cắt 14% dưới cùng (Tỷ lệ 0.86 từ trên xuống)
            print_crop_top = int(height * 0.86) 
            crop_img = img.crop((left, print_crop_top, right, height))
            
            if crop_img.mode in ("RGBA", "P"):
                crop_img = crop_img.convert("RGB")
            
            # Base64
            buffered = io.BytesIO()
            crop_img.save(buffered, format="JPEG", quality=80)
            img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Read Print and Edition. Output format: 'Print Edition'. Example: '1234 2'. Assume 1 if no edition."},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                    ]
                }]
            }
            
            # Logic xoay vòng Key
            random.shuffle(valid_keys)
            card_done = False

            for api_key in valid_keys:
                key_short = api_key[-4:]
                api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
                
                try:
                    ocr_resp = session.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=6)
                    
                    if ocr_resp.status_code == 200:
                        data = ocr_resp.json()
                        if 'candidates' in data:
                            text = data['candidates'][0]['content']['parts'][0]['text']
                            nums = re.findall(r'\d+', text)
                            
                            p, e = 0, 1
                            if len(nums) >= 2: p, e = int(nums[0]), int(nums[1])
                            elif len(nums) == 1: p = int(nums[0])
                            
                            if p > 0:
                                print(f"[GEMINI] 🎯 Thẻ {i+1}: Print #{p} Ed {e} (Key ...{key_short})", flush=True)
                                results.append((i, p, e))
                            else:
                                print(f"[GEMINI] ⚠️ Thẻ {i+1}: Không thấy số. Raw: '{text.strip()}'", flush=True)
                        card_done = True
                        break # Done card, next
                    
                    elif ocr_resp.status_code == 429:
                        print(f"[GEMINI] ⏳ Key ...{key_short} quá tải (429). Đổi key...", flush=True)
                        continue
                    else:
                        print(f"[GEMINI] ❌ Lỗi {ocr_resp.status_code} key ...{key_short}", flush=True)
                        continue

                except Exception as e:
                    continue
            
            if not card_done:
                print(f"[GEMINI] 💀 Thẻ {i+1}: Thất bại mọi key.", flush=True)

        return results

    except Exception as e:
        print(f"[OCR ERROR] {e}", flush=True)
        return []
