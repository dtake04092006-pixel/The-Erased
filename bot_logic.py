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
drop_queue = asyncio.Queue()

def get_gemini_keys():
    keys = os.getenv("GEMINI_API_KEY", "")
    return keys.split(",") if keys else []

async def worker():
    """
    Nhân viên xử lý hàng chờ.
    Nó sẽ lấy từng drop ra và xử lý từ từ để không bị Google chặn.
    """
    print("👷 Worker đã khởi động, đang chờ việc...", flush=True)
    while True:
        # Lấy một drop từ hàng chờ
        ctx = await drop_queue.get()
        message, image_url, server_name = ctx
        
        try:
            print(f"⚡ [QUEUE] Đang xử lý: {server_name} (Còn lại trong hàng chờ: {drop_queue.qsize()})", flush=True)
            
            gemini_keys = get_gemini_keys()
            
            # Chạy OCR (Code OCR Engine của bạn)
            # Chạy trong Executor để không chặn luồng chính của Bot
            loop = asyncio.get_event_loop()
            ocr_results = await loop.run_in_executor(
                None, scan_image_gemini, image_url, gemini_keys
            )
            
            if ocr_results:
                print(f"✅ [DONE] {server_name}: {ocr_results}", flush=True)
                await send_yoru_style_embed(message.channel, ocr_results)
            else:
                pass # Không tìm thấy số hoặc lỗi OCR

        except Exception as e:
            print(f"❌ [WORKER ERROR] {server_name}: {e}", flush=True)
        
        finally:
            drop_queue.task_done()
            # --- QUAN TRỌNG NHẤT: NGHỈ NGƠI ---
            # Nghỉ 1 giây trước khi làm việc tiếp theo.
            # Điều này giúp request rải đều ra, không bị dồn cục.
            # Với 10 Key, bạn có thể giảm xuống 0.5 hoặc 0.2
            await asyncio.sleep(0.5) 

@bot.event
async def on_ready():
    print(f"✅ Bot Online: {bot.user.name}")
    print(f"✅ Đang canh gác trên {len(bot.guilds)} server!")
    # Khởi động 3 nhân viên xử lý song song
    # 3 nhân viên * 0.5s nghỉ = Xử lý được khoảng 6 drop/giây (An toàn cho 10 Key)
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
        # Thay vì xử lý ngay, ta ĐẨY VÀO HÀNG CHỜ
        print(f"📥 [QUEUE] Đã nhận drop từ {server_name}. Đang xếp hàng...", flush=True)
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
