import discord
import os
import time
from discord.ext import commands
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from ocr_engine import scan_image_gemini

# --- CẤU HÌNH ---
intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix="!", intents=intents)
executor = ThreadPoolExecutor(max_workers=3)
recent_drops = deque(maxlen=5)

KARUTA_ID = 646937666251915264

def get_gemini_keys():
    keys = os.getenv("GEMINI_API_KEY", "")
    return keys.split(",") if keys else []

@bot.event
async def on_ready():
    print(f"✅ Bot Online: {bot.user.name}")
    print(f"✅ Đang chờ Karuta 'dropping'...")

@bot.event
async def on_message(message):
    if message.author.id != KARUTA_ID:
        return 

    # Lấy tên Server
    server_name = message.guild.name if message.guild else "Direct Message"
    
    # Rate limit
    now = time.time()
    recent_drops.append(now)
    if len(recent_drops) >= 5 and now - recent_drops[0] < 10:
        print(f"[{server_name}] [WARN] ⚠️ Quá nhiều drops, bỏ qua...", flush=True)
        return

    # Check chữ "dropping"
    is_dropping = False
    if message.content and "dropping" in message.content.lower():
        is_dropping = True
    if not is_dropping and message.embeds:
        desc = message.embeds[0].description or ""
        title = message.embeds[0].title or ""
        if "dropping" in desc.lower() or "dropping" in title.lower():
            is_dropping = True

    if not is_dropping:
        return

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
        print(f"[{server_name}] 🔍 [DETECT] Phát hiện Drop! Đang gửi sang Gemini...", flush=True)
        gemini_keys = get_gemini_keys()
        
        try:
            ocr_results = await bot.loop.run_in_executor(
                executor, scan_image_gemini, image_url, gemini_keys
            )
            
            if ocr_results:
                print(f"[{server_name}] ✅ [SUCCESS] Đọc thành công!", flush=True)
                for idx, print_num, edition_num in ocr_results:
                    print(f"   ➤ Thẻ {idx+1}: Print #{print_num} | Edition {edition_num}", flush=True)
                
                await send_yoru_style_embed(message.channel, ocr_results)
            else:
                print(f"[{server_name}] ⚠️ [EMPTY] Quét xong nhưng không thấy số.", flush=True)
        except Exception as e:
            print(f"[{server_name}] ❌ [ERROR] Lỗi OCR: {e}", flush=True)

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
            
            # Log đã gửi
            server_name = channel.guild.name if hasattr(channel, 'guild') and channel.guild else "DM"
            print(f"[{server_name}] 📤 [SENT] Đã gửi kết quả vào kênh: #{channel.name}", flush=True)
            
        except Exception as e:
            print(f"[ERROR] Không gửi được embed: {e}", flush=True)

@bot.event
async def on_close():
    executor.shutdown(wait=True)

# --- QUAN TRỌNG: ĐÂY LÀ HÀM MÀ MAIN.PY ĐANG TÌM KIẾM ---
def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if token: 
        bot.run(token)
    else:
        print("❌ Lỗi: Chưa có DISCORD_TOKEN trong biến môi trường!", flush=True)
