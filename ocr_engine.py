import requests
import io
import base64
import re
import random
import time
from PIL import Image, ImageEnhance

def scan_image_gemini(image_url, api_keys_list):
    """
    OCR Engine: Mode 'Nhiều Chuyện' (Full Logs)
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

        img = Image.open(io.BytesIO(img_bytes))
        width, height = img.size
        
        # 2. XỬ LÝ
        print_crop_top = int(height * 0.80) 
        crop_img = img.crop((0, print_crop_top, width, height))
        
        if crop_img.mode != 'RGB': crop_img = crop_img.convert('RGB')
        
        enhancer = ImageEnhance.Contrast(crop_img)
        crop_img = enhancer.enhance(1.8)
        
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
                    {"text": "Extract all 'Print Number' and 'Edition' pairs from left to right. Format: 'P-E'. Example: '79371-1, 79552-1'."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        
        results = []
        random.shuffle(valid_keys)

        for api_key in valid_keys:
            key_short = api_key[-4:] # Lấy 4 số cuối của key để in log cho gọn
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            
            try:
                # --- IN LOG GỬI ---
                print(f"   => [GEMINI] 🚀 Đang gửi ảnh (Key ...{key_short})...", flush=True)
                
                ocr_resp = session.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=7)
                
                if ocr_resp.status_code == 200:
                    data = ocr_resp.json()
                    if 'candidates' in data:
                        text = data['candidates'][0]['content']['parts'][0]['text']
                        
                        # --- IN LOG KẾT QUẢ RAW TỪ GOOGLE ---
                        # print(f"   => [GEMINI RAW] {text.strip()}", flush=True) # Bật dòng này nếu muốn soi kỹ

                        matches = re.findall(r'(\d+)[\s\-\.·•|]+(\d+)', text)
                        
                        if matches:
                            clean_results = []
                            for i, (p_str, e_str) in enumerate(matches):
                                if i > 3: break
                                p, e = int(p_str), int(e_str)
                                if p > 0: clean_results.append((i, p, e))
                            
                            if clean_results:
                                # --- IN LOG THÀNH CÔNG ---
                                print(f"   => [GEMINI] ✅ Đã đọc được: {clean_results}", flush=True)
                                return clean_results
                        else:
                            print(f"   => [GEMINI] ⚠️ API OK nhưng không thấy số.", flush=True)
                        
                elif ocr_resp.status_code == 429:
                    print(f"   => [GEMINI] ⏳ Key ...{key_short} quá tải. Đổi key...", flush=True)
                    continue

            except Exception as e:
                print(f"   => [GEMINI] ❌ Lỗi mạng với key ...{key_short}: {e}", flush=True)
                continue
        
        return results

    except Exception:
        return []
