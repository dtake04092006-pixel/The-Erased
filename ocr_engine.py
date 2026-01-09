import requests
import io
import base64
import re
import random
import time
from PIL import Image

def scan_image_gemini(image_url, api_keys):
    """
    OCR Engine: Tự động đổi Key (Round-Robin) khi gặp lỗi 429.
    Model: gemini-3-flash-preview
    """
    # Lọc danh sách key hợp lệ
    valid_keys = [k for k in api_keys if k.strip()]
    if not valid_keys:
        print("[OCR] ❌ Chưa nhập GEMINI_API_KEY!")
        return []

    # Dùng Session để giữ kết nối (Tăng tốc)
    session = requests.Session()

    try:
        # Tải ảnh
        img_bytes = None
        for attempt in range(3):
            try:
                resp = session.get(image_url, timeout=10)
                if resp.status_code == 200:
                    img_bytes = resp.content
                    break
            except: pass
        
        if not img_bytes: return []

        img = Image.open(io.BytesIO(img_bytes))
        width, height = img.size
        
        num_cards = 3 
        if width > 1000: num_cards = 4
        card_width = width // num_cards
        results = []
        
        print(f"[GEMINI] 🚀 Đang quét {num_cards} thẻ với {len(valid_keys)} API Key dự phòng...", flush=True)

        for i in range(num_cards):
            left = i * card_width
            right = (i + 1) * card_width
            
            # Cắt ảnh & Xử lý
            print_crop_top = int(height * 0.86) 
            crop_img = img.crop((left, print_crop_top, right, height))
            
            if crop_img.mode in ("RGBA", "P"):
                crop_img = crop_img.convert("RGB")
            
            # Resize & Nén ảnh để gửi nhanh hơn
            if crop_img.width > 300:
                ratio = 300 / float(crop_img.width)
                new_height = int((float(crop_img.height) * float(ratio)))
                crop_img = crop_img.resize((300, new_height), Image.Resampling.LANCZOS)

            buffered = io.BytesIO()
            crop_img.save(buffered, format="JPEG", quality=70)
            img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Identify the Print Number and Edition Number. Output ONLY two numbers separated by a space. Format: 'Print Edition'. Example: '1234 2'. If edition is not visible, assume 1."},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                    ]
                }]
            }
            
            # --- LOGIC XOAY VÒNG KEY (QUAN TRỌNG NHẤT) ---
            # Trộn danh sách key để không bị dồn vào 1 key đầu tiên
            random.shuffle(valid_keys)
            
            card_success = False
            
            # Thử lần lượt từng Key trong danh sách
            for api_key in valid_keys:
                key_suffix = api_key[-4:] if len(api_key) > 4 else "xxxx"
                api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
                
                try:
                    # Gửi request
                    ocr_resp = session.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=5)
                    
                    # Nếu thành công (200)
                    if ocr_resp.status_code == 200:
                        data = ocr_resp.json()
                        if 'candidates' in data:
                            text_result = data['candidates'][0]['content']['parts'][0]['text']
                            numbers = re.findall(r'\d+', text_result)
                            
                            p_num, e_num = 0, 1
                            if len(numbers) >= 2:
                                p_num, e_num = int(numbers[0]), int(numbers[1])
                            elif len(numbers) == 1:
                                p_num = int(numbers[0])
                            
                            if p_num > 0:
                                print(f"[GEMINI] 🎯 Thẻ {i+1}: Print #{p_num} Ed {e_num} (Key ...{key_suffix})", flush=True)
                                results.append((i, p_num, e_num))
                            else:
                                print(f"[GEMINI] ⚠️ Thẻ {i+1}: Không thấy số (Key ...{key_suffix})", flush=True)
                        
                        card_success = True
                        break # THOÁT VÒNG LẶP KEY -> Sang thẻ tiếp theo
                    
                    # Nếu bị chặn 429 -> Đừng dừng lại -> Thử Key tiếp theo!
                    elif ocr_resp.status_code == 429:
                        print(f"[GEMINI] ⚠️ Key ...{key_suffix} bị quá tải (429). Đang đổi sang Key khác...", flush=True)
                        continue 
                    
                    else:
                        print(f"[GEMINI] ❌ Lỗi {ocr_resp.status_code} với Key ...{key_suffix}. Đổi Key...", flush=True)
                        continue

                except Exception as e:
                    print(f"[GEMINI] 🔌 Lỗi mạng với Key ...{key_suffix}: {e}", flush=True)
                    continue
            
            if not card_success:
                print(f"[GEMINI] 💀 Thẻ {i+1}: Thất bại! Đã thử hết tất cả {len(valid_keys)} Key mà vẫn lỗi.", flush=True)

        return results

    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return []
