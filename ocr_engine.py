import requests
import io
import base64
import re
import random
import time
from PIL import Image, ImageEnhance

def scan_image_gemini(image_url, api_keys_list):
    """
    OCR Engine: Chiến thuật XẾP TẦNG + CẮT SÁT ĐÁY (12.5%)
    - Giống logic tham khảo: Tách riêng vùng Print ra khỏi vùng Anime.
    - Tiết kiệm: Gộp 3 thẻ thành 1 ảnh dọc để gửi 1 request.
    """
    if isinstance(api_keys_list, str):
        valid_keys = [k.strip() for k in api_keys_list.split(',') if k.strip()]
    else:
        valid_keys = [k for k in api_keys_list if k.strip()]

    if not valid_keys: return []

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
        
        # 2. XỬ LÝ: TÁCH CỘT & XẾP CHỒNG
        # Xác định số lượng thẻ dựa trên chiều rộng (Karuta 3 thẻ ~836px, 4 thẻ ~1100px)
        num_cards = 3
        if width > 1000: num_cards = 4
        card_width = width // num_cards
        
        # --- TỶ LỆ CẮT QUAN TRỌNG (12.5%) ---
        # Chiều cao thẻ ~419px. Vùng Print chỉ khoảng 50px dưới cùng.
        # 50 / 419 ≈ 0.12 (12%)
        # Ta lấy 0.125 để vừa khít, loại bỏ hoàn toàn chữ tên Anime ở trên.
        crop_height = int(height * 0.125)
        crop_top = height - crop_height
        
        # Tạo ảnh dài để xếp chồng (giống tờ sớ)
        # Cộng thêm 10px padding màu đen giữa các thẻ để Gemini phân biệt rõ
        stack_img = Image.new('RGB', (card_width, (crop_height + 10) * num_cards), (0, 0, 0))
        
        crops_data = [] 

        for i in range(num_cards):
            left = i * card_width
            right = (i + 1) * card_width
            
            # Cắt lấy đúng vùng Print nhỏ xíu
            crop = original_img.crop((left, crop_top, right, height))
            
            # Tăng tương phản tối đa (Contrast = 2.0)
            # Giúp chữ trắng nổi bần bật trên nền đen, loại bỏ nhiễu nền
            if crop.mode != 'RGB': crop = crop.convert('RGB')
            enhancer = ImageEnhance.Contrast(crop)
            crop = enhancer.enhance(2.0) 
            
            # Dán vào cột dọc
            y_offset = i * (crop_height + 10)
            stack_img.paste(crop, (0, y_offset))
            crops_data.append(i)

        # Lưu ảnh vào RAM
        buffered = io.BytesIO()
        stack_img.save(buffered, format="JPEG", quality=100) # Quality 100 để nét nhất
        img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

        # 3. GỬI GEMINI
        payload = {
            "contents": [{
                "parts": [
                    # Prompt bảo nó đọc lần lượt từ trên xuống
                    {"text": "Read these card numbers from TOP to BOTTOM. Each row is a different card. Extract 'Print Number' and 'Edition'. The format is usually '12345 · 1'. Return ONLY a list formatted as 'P-E'. Example: '79371-1, 79552-1'."},
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
                print(f"   => [GEMINI] 🚀 Đang gửi ảnh XẾP TẦNG (Key ...{key_short})...", flush=True)
                ocr_resp = session.post(api_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=8)
                
                if ocr_resp.status_code == 200:
                    data = ocr_resp.json()
                    if 'candidates' in data:
                        text = data['candidates'][0]['content']['parts'][0]['text']
                        
                        # Regex bắt số (Hỗ trợ dấu chấm Karuta và các ký tự lạ)
                        matches = re.findall(r'(\d+)[\s\-\.·•|]+(\d+)', text)
                        
                        if matches:
                            clean_results = []
                            for idx, (p_str, e_str) in enumerate(matches):
                                # Map lại đúng thứ tự thẻ
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

            except Exception as e:
                print(f"   => [GEMINI] ❌ Lỗi: {e}", flush=True)
                continue
        
        return results

    except Exception:
        return []
