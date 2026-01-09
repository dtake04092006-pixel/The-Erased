import requests
import io
import base64
import re
import random
import time
from PIL import Image, ImageEnhance

def scan_image_gemini(image_url, api_keys_list):
    """
    OCR Engine: Quay về Gemini nhưng dùng model 1.5-flash-8b (Bản nhẹ nhất, trâu nhất).
    """
    # Xử lý input key (chuyển về list chuẩn)
    if isinstance(api_keys_list, str):
        valid_keys = [k.strip() for k in api_keys_list.split(',') if k.strip()]
    else:
        valid_keys = [k for k in api_keys_list if k.strip()]

    if not valid_keys:
        print("[OCR] ❌ Thiếu API Key!", flush=True)
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
        
        # 2. XỬ LÝ ẢNH (Cắt dải ngang + Tăng nét)
        print_crop_top = int(height * 0.85) 
        crop_img = img.crop((0, print_crop_top, width, height))
        
        if crop_img.mode != 'RGB': crop_img = crop_img.convert('RGB')
        
        # Tăng tương phản lên 1.5 để số rõ hơn
        enhancer = ImageEnhance.Contrast(crop_img)
        crop_img = enhancer.enhance(1.5)
        
        # Resize nhẹ
        if crop_img.width > 1000:
            ratio = 1000 / float(crop_img.width)
            new_height = int((float(crop_img.height) * float(ratio)))
            crop_img = crop_img.resize((1000, new_height), Image.Resampling.LANCZOS)

        buffered = io.BytesIO()
        crop_img.save(buffered, format="JPEG", quality=85)
        img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 3. GỬI SANG GEMINI 1.5 FLASH 8B
        payload = {
            "contents": [{
                "parts": [
                    # Prompt tối ưu cho dải ngang
                    {"text": "Read all Print and Edition numbers from left to right. Return list format: 'Print-Edition'. Example: '123-1, 456-2'. If no edition, assume 1."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        
        results = []
        random.shuffle(valid_keys)

        for api_key in valid_keys:
            # --- MODEL CHUẨN: gemini-1.5-flash-8b ---
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-8b:generateContent?key={api_key}"
            
            try:
                ocr_resp = session.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=6)
                
                if ocr_resp.status_code == 200:
                    data = ocr_resp.json()
                    if 'candidates' in data:
                        text = data['candidates'][0]['content']['parts'][0]['text']
                        
                        # Regex bắt cặp số
                        matches = re.findall(r'(\d+)[\s\-\.]+(\d+)', text)
                        if matches:
                            for i, (p_str, e_str) in enumerate(matches):
                                if i > 3: break
                                results.append((i, int(p_str), int(e_str)))
                            return results 
                        
                elif ocr_resp.status_code == 429:
                    print(f"[GEMINI] ⏳ Key ...{api_key[-4:]} quá tải. Đổi...", flush=True)
                    continue # Thử key khác
                else:
                    # Lỗi khác (400, 500) cũng thử đổi key
                    continue

            except Exception:
                continue
        
        return results

    except Exception:
        return []
