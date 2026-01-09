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

# Khởi tạo là None, sẽ tạo Queue thật khi Bot đã vào guồng
drop_queue = None 

def get_gemini_keys():
    keys = os.getenv("GEMINI_API_KEY", "")
    return keys.split(",") if keys else []

async def worker():
    """
    Nhân viên xử lý hàng chờ.
    """
    global drop_queue
    print("👷 Worker đã khởi động, đang chờ việc...", flush=True)
    
    while True:
        # Chờ queue được khởi tạo
        if drop_queue is None:
            await asyncio.sleep(1)
            continue

        # Lấy việc
        ctx = await drop_queue.get()
        message, image_url, server_name = ctx
        
        try:
            print(f"⚡ [QUEUE] Đang xử lý: {server_name} (Còn lại: {drop_queue.qsize()})", flush=True)
            
            gemini_keys = get_gemini_keys()
            
            # Chạy OCR trong luồng riêng để không chặn bot
            loop = asyncio.get_running_loop()
            ocr_results = await loop.run_in_executor(
                None, scan_image_gemini, image_url, gemini_keys
            )
            
            if ocr_results:
                print(f"✅ [DONE] {server_name}: {ocr_results}", flush=True)
                await send_yoru_style_embed(message.channel, ocr_results)
            else:
                pass 

        except Exception as e:
            print(f"❌ [WORKER ERROR] {server_name}: {e}", flush=True)
        
        finally:
            drop_queue.task_done()
            # Nghỉ 0.5s để tránh spam Google (có thể giảm xuống 0.2 nếu nhiều key)
            await asyncio.sleep(0.5)

@bot.event
async def on_ready():
    global drop_queue
    print(f"✅ Bot Online: {bot.user.name}")
    
    # --- FIX LỖI Ở ĐÂY: TẠO QUEUE TRONG LOOP CỦA BOT ---
    if drop_queue is None:
        drop_queue = asyncio.Queue()
        print("✅ Đã khởi tạo Hàng Chờ (Queue) thành công!", flush=True)
    
    # Khởi động 3 nhân viên
    for _ in range(3):
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
        
        # Đẩy vào hàng chờ (nếu queue đã sẵn sàng)
        if drop_queue is not None:
            print(f"📥 [QUEUE] Đã nhận drop từ {server_name}. Đang xếp hàng...", flush=True)
            await drop_queue.put((message, image_url, server_name))
        else:
            print(f"⚠️ [WARN] Drop từ {server_name} bị bỏ qua vì Bot chưa load xong Queue.", flush=True)

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
        except: pass

@bot.event
async def on_close():
    pass

def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if token: bot.run(token)
    else: print("❌ Thiếu DISCORD_TOKEN")
        
