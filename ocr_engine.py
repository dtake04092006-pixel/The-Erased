import requests
import io
import base64
import re
import random
import time
import os
from PIL import Image, ImageEnhance

# --- CẤU HÌNH GROQ ---
# Bạn cần nhập GROQ_API_KEY vào biến môi trường trên Render
# Nếu có nhiều Key, cách nhau bằng dấu phẩy: key1,key2,key3
def get_groq_keys(api_keys_raw):
    # Nếu api_keys_raw là list (do code cũ truyền vào), gộp lại rồi tách ra
    if isinstance(api_keys_raw, list):
        # Đây là fix tạm nếu code bot_logic vẫn truyền list
        return [k for k in api_keys_raw if k.strip()]
    return [k.strip() for k in api_keys_raw.split(',') if k.strip()]

def scan_image_gemini(image_url, api_keys_list):
    """
    OCR Engine: Chuyển sang dùng GROQ (Llama 3.2 Vision).
    Tên hàm giữ nguyên là 'scan_image_gemini' để không phải sửa bên bot_logic.py
    nhưng ruột thì chạy bằng Groq.
    """
    # Lọc key (Groq Key thường bắt đầu bằng 'gsk_')
    valid_keys = [k for k in api_keys_list if k.strip()]
    if not valid_keys:
        print("[OCR] ❌ Thiếu GROQ_API_KEY!", flush=True)
        return []

    headers_img = {"User-Agent": "Mozilla/5.0"}
    session = requests.Session()

    try:
        # 1. TẢI ẢNH & XỬ LÝ (Giữ nguyên logic Cắt Ngang cũ vì nó tối ưu)
        img_bytes = None
        for _ in range(2):
            try:
                resp = session.get(image_url, headers=headers_img, timeout=5)
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
        
        # Tăng tương phản cho Llama dễ đọc
        enhancer = ImageEnhance.Contrast(crop_img)
        crop_img = enhancer.enhance(1.5)
        
        # Resize nhỏ lại (Groq giới hạn kích thước ảnh input)
        if crop_img.width > 800:
            ratio = 800 / float(crop_img.width)
            new_height = int((float(crop_img.height) * float(ratio)))
            crop_img = crop_img.resize((800, new_height), Image.Resampling.LANCZOS)

        buffered = io.BytesIO()
        crop_img.save(buffered, format="JPEG", quality=80)
        img_b64 = f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"

        # 2. GỬI SANG GROQ
        random.shuffle(valid_keys)
        
        for api_key in valid_keys:
            # Endpoint chuẩn của Groq
            url = "https://api.groq.com/openai/v1/chat/completions"
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                # Model Vision của Groq (QUAN TRỌNG: Phải dùng đúng tên này)
                "model": "llama-3.2-11b-vision-preview",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract Print Number and Edition. Return ONLY list format: 'P-E'. Example: '123-1, 56-2'. If no edition, use 1."},
                            {"type": "image_url", "image_url": {"url": img_b64}}
                        ]
                    }
                ],
                "temperature": 0.1, # Giảm sáng tạo để đọc số chuẩn hơn
                "max_tokens": 100
            }

            try:
                # Gửi request
                resp = session.post(url, json=payload, headers=headers, timeout=6)
                
                if resp.status_code == 200:
                    data = resp.json()
                    content = data['choices'][0]['message']['content']
                    
                    # Regex tìm số
                    matches = re.findall(r'(\d+)[\s\-\.]+(\d+)', content)
                    if matches:
                        results = []
                        for i, (p_str, e_str) in enumerate(matches):
                            if i > 3: break
                            results.append((i, int(p_str), int(e_str)))
                        return results
                    else:
                        # Groq trả lời nhưng không tìm thấy số
                        return []
                
                elif resp.status_code == 429:
                    print(f"[GROQ] ⏳ Key ...{api_key[-4:]} bị Rate Limit. Đổi key...", flush=True)
                    continue
                else:
                    print(f"[GROQ] ❌ Lỗi {resp.status_code}: {resp.text}", flush=True)
                    continue

            except Exception as e:
                print(f"[GROQ] 🔌 Lỗi mạng: {e}", flush=True)
                continue
        
        return []

    except Exception:
        return []
