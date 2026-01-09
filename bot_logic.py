import requests
import io
import base64
import re
import random
import time
from PIL import Image

def scan_image_gemini(image_url, api_keys):
    """
    OCR Engine: CẮT NGANG (Horizontal Crop)
    - Cắt 1 dải ngang dưới đáy ảnh (chứa Print/Edition của cả 3 thẻ).
    - Gửi 1 lần duy nhất lên Google -> Tiết kiệm 3 lần request.
    """
    valid_keys = [k for k in api_keys if k.strip()]
    if not valid_keys:
        print("[OCR] ❌ Chưa nhập GEMINI_API_KEY!", flush=True)
        return []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    session = requests.Session()

    try:
        # 1. TẢI ẢNH
        img_bytes = None
        for attempt in range(3):
            try:
                resp = session.get(image_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    img_bytes = resp.content
                    break
            except: time.sleep(0.5)
        
        if not img_bytes: return []

        img = Image.open(io.BytesIO(img_bytes))
        width, height = img.size
        
        # --- LOGIC CẮT NGANG (QUAN TRỌNG) ---
        # Thay vì chia cột, ta cắt một dải ngang ở đáy (14% dưới cùng)
        # Dải này sẽ chứa toàn bộ chân của 3 (hoặc 4) thẻ
        print_crop_top = int(height * 0.86) 
        
        # Cắt: (Từ trái 0, Từ trên 86%, Đến hết phải, Đến hết dưới)
        crop_img = img.crop((0, print_crop_top, width, height))
        
        # Chuyển màu & Nén
        if crop_img.mode in ("RGBA", "P"):
            crop_img = crop_img.convert("RGB")
        
        # Resize bề ngang max 1000px cho nhẹ (Gemini vẫn đọc tốt)
        if crop_img.width > 1000:
            ratio = 1000 / float(crop_img.width)
            new_height = int((float(crop_img.height) * float(ratio)))
            crop_img = crop_img.resize((1000, new_height), Image.Resampling.LANCZOS)

        buffered = io.BytesIO()
        crop_img.save(buffered, format="JPEG", quality=80)
        img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # --- PROMPT MỚI: DẠY GEMINI ĐỌC DẢI NGANG ---
        payload = {
            "contents": [{
                "parts": [
                    # Prompt này bảo nó: Nhìn từ trái sang phải, thấy cặp số nào thì liệt kê ra hết
                    {"text": "Look at this image strip from left to right. Identify Print Number and Edition for each card section. Output a list of 'Print-Edition' pairs. Example output: '1234-1, 567-2, 99-1'."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        
        results = []
        random.shuffle(valid_keys)
        success = False

        # Thử gửi (vẫn có Auto-Switch Key để an toàn)
        for api_key in valid_keys:
            key_short = api_key[-4:]
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
            
            try:
                print(f"[GEMINI] 🚀 Đang gửi dải ảnh ngang (Key ...{key_short})...", flush=True)
                ocr_resp = session.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=8)
                
                if ocr_resp.status_code == 200:
                    data = ocr_resp.json()
                    if 'candidates' in data:
                        text = data['candidates'][0]['content']['parts'][0]['text']
                        
                        # Regex tìm tất cả cặp số (dạng 123-1 hoặc 123 1)
                        # Nó sẽ trả về list các cặp [(123, 1), (567, 2), ...]
                        matches = re.findall(r'(\d+)[\s\-\.]+(\d+)', text)
                        
                        if matches:
                            print(f"[GEMINI] ✅ Đọc thành công: {matches}", flush=True)
                            for i, (p_str, e_str) in enumerate(matches):
                                # Giới hạn 4 thẻ để tránh lỗi
                                if i > 3: break
                                results.append((i, int(p_str), int(e_str)))
                            success = True
                            break # Xong việc, thoát vòng lặp key
                        else:
                            print(f"[GEMINI] ⚠️ Không tìm thấy số nào trong dải ảnh.", flush=True)
                            # Không break, thử key khác xem có thông minh hơn không (hiếm khi cần)
                            break 

                elif ocr_resp.status_code == 429:
                    print(f"[GEMINI] ⏳ Key ...{key_short} quá tải. Đổi key...", flush=True)
                    continue
                else:
                    print(f"[GEMINI] ❌ Lỗi {ocr_resp.status_code}. Đổi key...", flush=True)
                    continue

            except Exception as e:
                print(f"[GEMINI] 🔌 Lỗi mạng: {e}", flush=True)
                continue
        
        return results

    except Exception as e:
        print(f"[OCR ERROR] {e}", flush=True)
        return []
