import requests
import io
import base64
import re
import random
import time
from PIL import Image, ImageEnhance

def scan_image_gemini(image_url, api_keys_list):
    """
    OCR Engine: Chiến thuật GOM LƯỚI (Grid Strategy)
    1. Cắt dọc để tách từng thẻ (Chính xác cao).
    2. Ghép các thẻ con thành 1 ảnh lưới vuông (Tiết kiệm Request).
    3. Gửi Gemini 1 lần duy nhất.
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
        # 1. TẢI ẢNH GỐC
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
        
        # 2. CẮT DỌC VÀ GOM VÀO LƯỚI
        num_cards = 3
        if width > 1000: num_cards = 4
        card_width = width // num_cards
        
        # Tạo canvas vuông (đủ chỗ cho 4 thẻ)
        # Kích thước mỗi ô con trong lưới sẽ là 400x400 (đủ nét)
        grid_size = 800 
        cell_size = 400
        grid_img = Image.new('RGB', (grid_size, grid_size), (0, 0, 0)) # Nền đen
        
        crops_data = [] # Lưu vị trí để lát nữa map lại kết quả

        for i in range(num_cards):
            # Cắt từng thẻ ra
            left = i * card_width
            right = (i + 1) * card_width
            
            # Cắt lấy 20% đáy của thẻ đó (chỗ có số)
            print_crop_top = int(height * 0.80)
            crop = original_img.crop((left, print_crop_top, right, height))
            
            # Tăng nét cho từng miếng nhỏ
            if crop.mode != 'RGB': crop = crop.convert('RGB')
            enhancer = ImageEnhance.Contrast(crop)
            crop = enhancer.enhance(1.8)
            
            # Resize miếng nhỏ về chuẩn 380px để nhét vừa ô 400
            if crop.width > 380:
                ratio = 380 / float(crop.width)
                new_h = int(float(crop.height) * ratio)
                crop = crop.resize((380, new_h), Image.Resampling.LANCZOS)
            
            # Dán vào lưới 2x2
            # Ô 0: (0,0), Ô 1: (400,0), Ô 2: (0,400), Ô 3: (400,400)
            x_offset = (i % 2) * cell_size + 10 # +10 padding
            y_offset = (i // 2) * cell_size + 10
            
            grid_img.paste(crop, (x_offset, y_offset))
            crops_data.append(i) # Đánh dấu thẻ này là thẻ thứ i

        # Lưu ảnh lưới
        buffered = io.BytesIO()
        grid_img.save(buffered, format="JPEG", quality=90)
        img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 3. GỬI SANG GEMINI
        payload = {
            "contents": [{
                "parts": [
                    # Prompt mới: Bảo nó đọc từng ô
                    {"text": "This image contains 3 or 4 separate card snippets arranged in a grid. Identify Print Number and Edition for EACH snippet. Ignore the grid layout, just output the list of numbers found. Format: 'P-E'. Example: '79371-1, 79552-1'."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}}
                ]
            }]
        }
        
        results = []
        random.shuffle(valid_keys)

        for api_key in valid_keys:
            key_short = api_key[-4:]
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            
            try:
                print(f"   => [GEMINI] 🚀 Đang gửi ảnh LƯỚI (Key ...{key_short})...", flush=True)
                ocr_resp = session.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=7)
                
                if ocr_resp.status_code == 200:
                    data = ocr_resp.json()
                    if 'candidates' in data:
                        text = data['candidates'][0]['content']['parts'][0]['text']
                        
                        # Regex siêu mạnh bắt mọi thể loại
                        matches = re.findall(r'(\d+)[\s\-\.·•|]+(\d+)', text)
                        
                        if matches:
                            clean_results = []
                            for idx, (p_str, e_str) in enumerate(matches):
                                # Map lại với index thẻ gốc
                                if idx < len(crops_data):
                                    original_idx = crops_data[idx]
                                    p, e = int(p_str), int(e_str)
                                    if p > 0:
                                        clean_results.append((original_idx, p, e))
                            
                            if clean_results:
                                print(f"   => [GEMINI] ✅ Đã đọc được: {clean_results}", flush=True)
                                return clean_results
                        else:
                            print(f"   => [GEMINI] ⚠️ API OK nhưng không thấy số.", flush=True)

                elif ocr_resp.status_code == 429:
                    print(f"   => [GEMINI] ⏳ Key ...{key_short} quá tải. Đổi...", flush=True)
                    continue

            except Exception:
                continue
        
        return results

    except Exception as e:
        print(f"[OCR ERROR] {e}", flush=True)
        return []
