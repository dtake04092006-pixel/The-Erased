import requests

# Dán 1 cái key của bạn vào đây
API_KEY = "DÁN_KEY_CỦA_BẠN_VÀO_ĐÂY" 

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
resp = requests.get(url)

print("=== DANH SÁCH MODEL GOOGLE CHO PHÉP BẠN DÙNG ===")
if resp.status_code == 200:
    for m in resp.json().get('models', []):
        if 'generateContent' in m['supportedGenerationMethods']:
            print(f"✅ {m['name']}")
else:
    print(f"❌ Lỗi lấy danh sách: {resp.text}")
