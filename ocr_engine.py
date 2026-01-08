import requests
import io
import base64
import re
import random
from PIL import Image

def scan_image_gemini(image_url, api_keys):
    """
    Hàm nhận URL ảnh và List API Key.
    Trả về list: [(index, print_num, edition_num), ...]
    """
    valid_keys = [k for k in api_keys if k.strip()]
    if not valid_keys:
        print("[OCR] ❌ Chưa nhập GEMINI_API_KEY!")
        return []

    try:
        # Tải ảnh
        resp = requests.get(image_url, timeout=10)
        if resp.status_code != 200: return []
        
        img = Image.open(io.BytesIO(resp.content))
        width, height = img.size
        
        # Xác định số lượng thẻ (logic Karuta: >1000px thường là 4 thẻ, <1000px là 3 thẻ)
        num_cards = 4 if width > 1000 else 3
        card_width = width // num_cards
        
        results = []
        
        # Chọn ngẫu nhiên key để load balancing
        api_key = random.choice(valid_keys).strip()
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

        for i in range(num_cards):
            left = i * card_width
            right = (i + 1) * card_width
            # Cắt 15% dưới cùng của thẻ (nơi chứa Print/Edition)
            print_crop_top = int(height * 0.85) 
            crop_img = img.crop((left, print_crop_top, right, height))
            
            # Chuyển sang Base64
            buffered = io.BytesIO()
            crop_img.save(buffered, format="JPEG")
            img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            # Prompt tối ưu cho Gemini
            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Identify the Print Number and Edition Number. Output ONLY two numbers separated by a space. Format: 'Print Edition'. Example: '1234 2'. If edition is not visible, assume 1."},
                        {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                    ]
                }]
            }
            
            # Gọi API
            ocr_resp = requests.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
            
            if ocr_resp.status_code == 200:
                data = ocr_resp.json()
                try:
                    text_result = data['candidates'][0]['content']['parts'][0]['text']
                    numbers = re.findall(r'\d+', text_result)
                    
                    p_num, e_num = 0, 1
                    if len(numbers) >= 2:
                        p_num, e_num = int(numbers[0]), int(numbers[1])
                    elif len(numbers) == 1:
                        p_num = int(numbers[0])
                    
                    if p_num > 0:
                        results.append((i, p_num, e_num))
                except:
                    continue
                    
        return results

    except Exception as e:
        print(f"[OCR ERROR] {e}")
        return []
