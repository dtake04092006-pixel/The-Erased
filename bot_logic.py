import discord
import os
from discord.ext import commands
from ocr_engine import scan_image_gemini

# Cấu hình Intent (BẮT BUỘC ĐỂ ĐỌC ĐƯỢC EMBED CỦA KARUTA)
intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix="!", intents=intents)

# ID của Karuta (Thay đổi nếu cần check bot khác)
KARUTA_ID = 646937666251915264

def get_gemini_keys():
    keys = os.getenv("GEMINI_API_KEY", "")
    return keys.split(",") if keys else []

@bot.event
async def on_ready():
    print(f"✅ Bot đã online: {bot.user.name} (ID: {bot.user.id})")
    print(f"✅ Đang lắng nghe tin nhắn từ Karuta (ID: {KARUTA_ID})...")

@bot.event
async def on_message(message):
    # 1. LOG DEBUG: In ra mọi tin nhắn bot nhìn thấy để biết Intent có hoạt động không
    # Nếu dòng này không hiện, nghĩa là bạn CHƯA BẬT INTENT trên web Discord Developer
    print(f"[DEBUG] Tin nhắn mới từ: {message.author.name} (ID: {message.author.id})")

    # 2. BỘ LỌC KARUTA: Chỉ xử lý nếu người gửi là Karuta
    if message.author.id != KARUTA_ID:
        return # Không phải Karuta thì bỏ qua luôn

    print("[DEBUG] -> Phát hiện tin nhắn từ Karuta! Đang kiểm tra ảnh...")

    # 3. LẤY ẢNH TỪ EMBED (Karuta dùng Embed)
    image_url = None
    if message.embeds:
        # Karuta thường để ảnh ở embed.image
        if message.embeds[0].image:
            image_url = message.embeds[0].image.url
        # Hoặc đôi khi ở thumbnail (ít gặp)
        elif message.embeds[0].thumbnail:
            image_url = message.embeds[0].thumbnail.url
    
    # (Dự phòng) Kiểm tra file đính kèm
    elif message.attachments:
        image_url = message.attachments[0].url

    # 4. TIẾN HÀNH QUÉT
    if image_url:
        print(f"[DEBUG] -> Tìm thấy ảnh: {image_url}")
        print("[DEBUG] -> Đang gửi sang Gemini để đọc số...")
        
        gemini_keys = get_gemini_keys()
        if not gemini_keys:
            print("❌ LỖI: Chưa cấu hình GEMINI_API_KEY trong Environment Variables")
            return

        # Chạy OCR
        ocr_results = await bot.loop.run_in_executor(None, scan_image_gemini, image_url, gemini_keys)
        
        if ocr_results:
            print(f"[SUCCESS] ✅ Đọc được: {ocr_results}")
            await send_yoru_style_embed(message.channel, ocr_results)
        else:
            print("[INFO] ⚠️ Gemini không tìm thấy số Print/Edition nào trong ảnh này.")
    else:
        print("[DEBUG] -> Tin nhắn Karuta này không có ảnh.")

    await bot.process_commands(message)

async def send_yoru_style_embed(channel, results):
    """Gửi Embed style Yoru"""
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    description_lines = []
    
    for idx, print_num, edition_num in results:
        if idx < len(number_emojis):
            line = f"{number_emojis[idx]} | **#{print_num} · ◈{edition_num}**"
            description_lines.append(line)
    
    if description_lines:
        try:
            embed = discord.Embed(description="\n".join(description_lines), color=0x36393f)
            embed.set_footer(text="Shadow OCR • Gemini Powered")
            await channel.send(embed=embed)
            print("[DEBUG] -> Đã gửi Embed kết quả vào kênh.")
        except Exception as e:
            print(f"❌ LỖI GỬI TIN: Bot có thể thiếu quyền gửi tin hoặc Embed Links. Chi tiết: {e}")

def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Lỗi: Chưa có DISCORD_TOKEN trong biến môi trường!")
        return
    bot.run(token)
