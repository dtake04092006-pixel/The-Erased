import discord
import os
import asyncio
import time
from discord.ext import commands
from ocr_engine import scan_image_gemini

# --- CẤU HÌNH ---
intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix="!", intents=intents)

KARUTA_ID = 646937666251915264

# Hàng chờ xử lý ảnh
drop_queue = None

def get_api_keys():
    # Vẫn lấy từ biến GEMINI_API_KEY cho tiện (bạn đỡ phải sửa trên Render)
    # Nhưng nhớ là giá trị bên trong phải là Key của Groq nhé!
    keys = os.getenv("GEMINI_API_KEY", "")
    return keys.split(",") if keys else []

async def worker():
    """
    Nhân viên xử lý hàng chờ (Phiên bản tối ưu cho Groq)
    """
    global drop_queue
    print("🚀 Worker Groq đã khởi động...", flush=True)
    
    while True:
        if drop_queue is None:
            await asyncio.sleep(1)
            continue

        # Lấy việc từ hàng chờ
        ctx = await drop_queue.get()
        message, image_url, server_name = ctx
        
        try:
            # In ra để bạn thấy nó đang chạy vèo vèo
            print(f"⚡ [GROQ] Đang xử lý: {server_name} (Hàng chờ: {drop_queue.qsize()})", flush=True)
            
            api_keys = get_api_keys()
            
            # Chạy OCR (lúc này là chạy code Groq bên file kia)
            loop = asyncio.get_running_loop()
            ocr_results = await loop.run_in_executor(
                None, scan_image_gemini, image_url, api_keys
            )
            
            if ocr_results:
                print(f"✅ [OK] {server_name}: {ocr_results}", flush=True)
                await send_yoru_style_embed(message.channel, ocr_results)
            else:
                # Groq rất ít khi fail, nếu fail thường là do ảnh mờ hoặc ko có số
                print(f"⚠️ [SKIP] {server_name}: Không tìm thấy số.", flush=True)

        except Exception as e:
            print(f"❌ [ERR] {server_name}: {e}", flush=True)
        
        finally:
            drop_queue.task_done()
            # --- QUAN TRỌNG: NGHỈ 1.5 GIÂY ---
            # Groq giới hạn khoảng 30 req/phút bản Free. 
            # 1.5s nghỉ + 0.5s xử lý = 2s/req = 30 req/phút (Vừa khít, an toàn tuyệt đối)
            await asyncio.sleep(1.5)

@bot.event
async def on_ready():
    global drop_queue
    print(f"✅ Bot Online: {bot.user.name}")
    
    if drop_queue is None:
        drop_queue = asyncio.Queue()
        print("✅ Đã khởi tạo Hàng Chờ (Queue) cho 200 Server!", flush=True)
    
    # Chỉ cần 1 Worker là đủ cân 200 server với tốc độ của Groq
    bot.loop.create_task(worker())

@bot.event
async def on_message(message):
    if message.author.id != KARUTA_ID:
        return 

    # Check drop
    is_dropping = False
    if message.content and "dropping" in message.content.lower():
        is_dropping = True
    elif message.embeds:
        desc = message.embeds[0].description or ""
        if "dropping" in desc.lower():
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
        server_name = message.guild.name if message.guild else "DM"
        
        if drop_queue is not None:
            # Đẩy vào hàng chờ ngay lập tức
            print(f"📥 [QUEUE] +1 Drop từ {server_name}", flush=True)
            await drop_queue.put((message, image_url, server_name))

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
            embed.set_footer(text="Shadow OCR (Powered by Groq)")
            await channel.send(embed=embed)
        except: pass

@bot.event
async def on_close():
    pass

def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if token: bot.run(token)
    else: print("❌ Thiếu DISCORD_TOKEN")
