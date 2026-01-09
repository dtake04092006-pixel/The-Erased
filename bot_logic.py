import requests
import io
import base64
import re
import random
import time
from PIL import Image, ImageEnhance

def scan_image_gemini(image_url, api_keys):
    """
    OCR Engine: Sử dụng model gemini-1.5-flash-8b (Bản siêu nhẹ)
    """
    valid_keys = [k for k in api_keys if k.strip()]
    if not valid_keys: return []

    headers = {"User-Agent": "Mozilla/5.0"}
    session = requests.Session()

    try:
        # Tải ảnh
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
        
        # Cắt dải ngang dưới đáy (15%)
        print_crop_top = int(height * 0.85) 
        crop_img = img.crop((0, print_crop_top, width, height))
        
        if crop_img.mode != 'RGB': crop_img = crop_img.convert('RGB')
        
        # Tăng tương phản
        enhancer = ImageEnhance.Contrast(crop_img)
        crop_img = enhancer.enhance(1.5)
        
        # Resize nhỏ lại chút nữa để request nhẹ hơn
        if crop_img.width > 800:
            ratio = 800 / float(crop_img.width)
            new_height = int((float(crop_img.height) * float(ratio)))
            crop_img = crop_img.resize((800, new_height), Image.Resampling.LANCZOS)

        buffered = io.BytesIO()
        crop_img.save(buffered, format="JPEG", quality=80)
        img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        payload = {
            "contents": [{
                "parts": [
                    {"text": "Read Print and Edition. Output: 'P-E'. Example: '12-1, 567-2'."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        
        results = []
        random.shuffle(valid_keys)

        for api_key in valid_keys:
            # --- ĐỔI SANG MODEL 1.5 FLASH 8B (ỔN ĐỊNH HƠN) ---
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-8b:generateContent?key={api_key}"
            
            try:
                # Thêm timeout ngắn để nếu lag thì bỏ qua ngay
                ocr_resp = session.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=5)
                
                if ocr_resp.status_code == 200:
                    data = ocr_resp.json()
                    if 'candidates' in data:
                        text = data['candidates'][0]['content']['parts'][0]['text']
                        matches = re.findall(r'(\d+)[\s\-\.]+(\d+)', text)
                        if matches:
                            for i, (p_str, e_str) in enumerate(matches):
                                if i > 3: break
                                results.append((i, int(p_str), int(e_str)))
                            return results
                        else:
                            # Nếu API trả về 200 nhưng không đọc được số, coi như xong luôn để tránh thử lại tốn key
                            return []
                
                elif ocr_resp.status_code == 429:
                    print(f"[GEMINI] ⏳ Key ...{api_key[-4:]} hết lượt. Đổi...", flush=True)
                    continue
                elif ocr_resp.status_code == 400:
                    print(f"[GEMINI] ❌ Key ...{api_key[-4:]} lỗi 400 (Check lại key).", flush=True)
                    continue

            except Exception:
                continue
        
        return results

    except Exception:
        return []
