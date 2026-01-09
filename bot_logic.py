import discord
import os
import asyncio
import time
from discord.ext import commands
from ocr_engine import scan_image_gemini

# --- CẤU HÌNH BOT ---
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

KARUTA_ID = 646937666251915264

# Biến toàn cục cho hàng chờ
drop_queue = None

def get_api_keys():
    # Lấy danh sách 10 Key từ Render
    keys = os.getenv("GEMINI_API_KEY", "")
    return keys.split(",") if keys else []

async def worker():
    """
    Nhân viên xử lý (Worker): Làm việc cần mẫn, không bao giờ spam.
    """
    global drop_queue
    print("👷 Worker GEMINI đã khởi động và sẵn sàng!", flush=True)
    
    while True:
        # Chờ queue được khởi tạo xong
        if drop_queue is None:
            await asyncio.sleep(1)
            continue

        # Lấy 1 drop ra để xử lý
        ctx = await drop_queue.get()
        message, image_url, server_name = ctx
        
        try:
            # In log để theo dõi tình trạng hàng chờ
            print(f"⚡ [XỬ LÝ] {server_name} (Hàng chờ còn: {drop_queue.qsize()})", flush=True)
            
            api_keys = get_api_keys()
            loop = asyncio.get_running_loop()
            
            # Gọi OCR Engine chạy ngầm
            ocr_results = await loop.run_in_executor(
                None, scan_image_gemini, image_url, api_keys
            )
            
            if ocr_results:
                print(f"✅ [OK] {server_name}: {ocr_results}", flush=True)
                await send_yoru_style_embed(message.channel, ocr_results)
            else:
                # Nếu không đọc được số (hoặc ảnh mờ), chỉ log nhẹ, không spam lỗi
                pass

        except Exception as e:
            print(f"❌ [ERR] {server_name}: {e}", flush=True)
        
        finally:
            drop_queue.task_done()
            # --- TỐC ĐỘ AN TOÀN CHO 200 SERVER ---
            # Nghỉ 2.0 giây giữa các lần xử lý.
            # Đảm bảo 10 Key của bạn hồi phục Quota kịp thời.
            await asyncio.sleep(2.0)

@bot.event
async def on_ready():
    global drop_queue
    print(f"✅ Bot Online: {bot.user.name}")
    print(f"✅ Đang hoạt động trên {len(bot.guilds)} server.")
    
    # Khởi tạo Queue trong vòng lặp chính (Fix lỗi RuntimeError)
    if drop_queue is None:
        drop_queue = asyncio.Queue()
    
    # Chỉ chạy 1 Worker duy nhất để kiểm soát tốc độ tuyệt đối
    bot.loop.create_task(worker())

@bot.event
async def on_message(message):
    # Chỉ nhận tin từ Karuta (ID chuẩn)
    if message.author.id != KARUTA_ID:
        return 

    # Kiểm tra xem có phải là Drop không
    is_dropping = False
    if message.content and "dropping" in message.content.lower():
        is_dropping = True
    elif message.embeds:
        desc = message.embeds[0].description or ""
        if "dropping" in desc.lower():
            is_dropping = True

    if not is_dropping:
        return

    # Lấy URL ảnh
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
        
        # Đẩy ngay vào hàng chờ, bot sẽ xử lý sau
        if drop_queue is not None:
            print(f"📥 [QUEUE] +1 Drop từ {server_name}", flush=True)
            await drop_queue.put((message, image_url, server_name))

    await bot.process_commands(message)

async def send_yoru_style_embed(channel, results):
    """Gửi tin nhắn kết quả đẹp như Yoru Bot"""
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    description_lines = []
    
    for idx, print_num, edition_num in results:
        if idx < len(number_emojis):
            # Định dạng: #12345 · ◈1
            line = f"{number_emojis[idx]} | **#{print_num} · ◈{edition_num}**"
            description_lines.append(line)
    
    if description_lines:
        try:
            embed = discord.Embed(description="\n".join(description_lines), color=0x36393f)
            embed.set_footer(text="Shadow OCR")
            await channel.send(embed=embed)
        except: pass

def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if token: bot.run(token)
    else: print("❌ Thiếu DISCORD_TOKEN")
