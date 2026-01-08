import discord
import os
from discord.ext import commands
from ocr_engine import scan_image_gemini

# Cấu hình Intent (Bắt buộc cho bot đọc nội dung tin nhắn)
intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix="!", intents=intents)

# Lấy API Key từ biến môi trường
def get_gemini_keys():
    keys = os.getenv("GEMINI_API_KEY", "")
    return keys.split(",") if keys else []

@bot.event
async def on_ready():
    print(f"✅ Bot đã online: {bot.user.name}")
    print("------ Sẵn sàng quét ảnh ------")

@bot.event
async def on_message(message):
    if message.author.bot and message.author.id != bot.user.id:
        # Logic: Nếu muốn bot tự động đọc ảnh của bot khác (ví dụ Karuta)
        # Bạn có thể thêm điều kiện kiểm tra ID của Karuta ở đây
        pass

    # Kiểm tra xem tin nhắn có ảnh không (Attachment hoặc Embed Image)
    image_url = None
    if message.attachments:
        image_url = message.attachments[0].url
    elif message.embeds and message.embeds[0].image:
        image_url = message.embeds[0].image.url

    # Nếu có ảnh, tiến hành quét
    if image_url:
        # Gửi thông báo "Đang quét" (tuỳ chọn)
        # temp_msg = await message.channel.send("🔍 Scanning...") 
        
        gemini_keys = get_gemini_keys()
        if not gemini_keys:
            print("⚠️ Chưa cấu hình GEMINI_API_KEY")
            return

        # Chạy OCR trong Thread Pool để không chặn bot
        ocr_results = await bot.loop.run_in_executor(None, scan_image_gemini, image_url, gemini_keys)

        if ocr_results:
            await send_yoru_style_embed(message.channel, ocr_results)
            # await temp_msg.delete() # Xóa tin nhắn chờ nếu muốn

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
        embed = discord.Embed(description="\n".join(description_lines), color=0x36393f)
        embed.set_footer(text="Shadow OCR • Gemini Powered")
        await channel.send(embed=embed)

def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ Lỗi: Chưa có DISCORD_TOKEN trong biến môi trường!")
        return
    bot.run(token)
