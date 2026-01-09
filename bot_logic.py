import discord
import os
import asyncio
from discord.ext import commands
from concurrent.futures import ThreadPoolExecutor
from ocr_engine import scan_image_gemini

# --- CẤU HÌNH ---
intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix="!", intents=intents)

# TĂNG LÊN 50 WORKERS ĐỂ CÂN 200 SERVER
executor = ThreadPoolExecutor(max_workers=50)

KARUTA_ID = 646937666251915264

def get_gemini_keys():
    keys = os.getenv("GEMINI_API_KEY", "")
    return keys.split(",") if keys else []

@bot.event
async def on_ready():
    print(f"✅ Bot Online: {bot.user.name}")
    print(f"✅ Sẵn sàng chiến đấu trên {len(bot.guilds)} server!")

@bot.event
async def on_message(message):
    # Chỉ nhận tin từ Karuta
    if message.author.id != KARUTA_ID:
        return 

    # Check nhanh nội dung drop
    is_dropping = False
    if message.content and "dropping" in message.content.lower():
        is_dropping = True
    elif message.embeds:
        desc = message.embeds[0].description or ""
        if "dropping" in desc.lower():
            is_dropping = True

    if not is_dropping:
        return

    # --- ĐÃ XÓA BỎ ĐOẠN CHECK "RATE LIMIT" Ở ĐÂY ---
    # Bot sẽ xử lý mọi drop ngay lập tức bất kể tốc độ

    # Lấy ảnh
    image_url = None
    if message.embeds:
        if message.embeds[0].image:
            image_url = message.embeds[0].image.url
        elif message.embeds[0].thumbnail:
            image_url = message.embeds[0].thumbnail.url
    elif message.attachments:
        image_url = message.attachments[0].url

    if image_url:
        server_name = message.guild.name if message.guild else "DM"
        # Log gọn lại để đỡ rối mắt
        print(f"[{server_name}] ⚡ DROP! Gửi Gemini...", flush=True)
        
        gemini_keys = get_gemini_keys()
        
        try:
            # Chạy OCR bất đồng bộ
            ocr_results = await bot.loop.run_in_executor(
                executor, scan_image_gemini, image_url, gemini_keys
            )
            
            if ocr_results:
                print(f"[{server_name}] ✅ KẾT QUẢ: {ocr_results}", flush=True)
                await send_yoru_style_embed(message.channel, ocr_results)
            else:
                # Log lỗi nhưng không spam
                pass 
        except Exception as e:
            print(f"[{server_name}] ❌ Lỗi: {e}", flush=True)

    await bot.process_commands(message)

async def send_yoru_style_embed(channel, results):
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    description_lines = []
    
    for idx, print_num, edition_num in results:
        if idx < len(number_emojis):
            line = f"{number_emojis[idx]} | **#{print_num} · ◈{edition_num}**"
            description_lines.append(line)
    
    if description_lines:
        try:
            embed = discord.Embed(description="\n".join(description_lines), color=0x36393f)
            embed.set_footer(text="Shadow OCR")
            await channel.send(embed=embed)
            print(f"   => 📤 Đã gửi tin nhắn cho {channel.guild.name}", flush=True)
        except: pass

@bot.event
async def on_close():
    executor.shutdown(wait=True)

def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if token: bot.run(token)
    else: print("❌ Thiếu DISCORD_TOKEN")
