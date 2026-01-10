import discord
import os
import asyncio
import time
from discord.ext import commands
from ocr_engine import scan_image_gemini

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

KARUTA_ID = 646937666251915264
drop_queue = None

def get_api_keys():
    keys = os.getenv("GEMINI_API_KEY", "")
    return keys.split(",") if keys else []

async def worker():
    global drop_queue
    print("👷 Worker GEMINI đã khởi động...", flush=True)
    while True:
        if drop_queue is None:
            await asyncio.sleep(1)
            continue

        ctx = await drop_queue.get()
        message, image_url, server_name = ctx
        
        try:
            # In ra server đang xử lý
            print(f"⚡ [XỬ LÝ] {server_name} (Hàng chờ: {drop_queue.qsize()})", flush=True)
            
            api_keys = get_api_keys()
            loop = asyncio.get_running_loop()
            
            ocr_results = await loop.run_in_executor(
                None, scan_image_gemini, image_url, api_keys
            )
            
            if ocr_results:
                # --- IN LOG KẾT QUẢ CUỐI CÙNG ---
                print_str = " | ".join([f"#{p}·{e}" for _, p, e in ocr_results])
                print(f"✅ [DONE] {server_name} -> {print_str}", flush=True)
                
                await send_yoru_style_embed(message.channel, ocr_results)
            else:
                # --- IN LOG THẤT BẠI ---
                print(f"❌ [FAIL] {server_name}: Không tìm thấy số nào.", flush=True)

        except Exception as e:
            print(f"💀 [ERROR] {server_name}: {e}", flush=True)
        
        finally:
            drop_queue.task_done()
            await asyncio.sleep(2.0)

@bot.event
async def on_ready():
    global drop_queue
    print(f"✅ Bot Online: {bot.user.name}")
    if drop_queue is None: drop_queue = asyncio.Queue()
    bot.loop.create_task(worker())

@bot.event
async def on_message(message):
    if message.author.id != KARUTA_ID: return 
    is_dropping = False
    if message.content and "dropping" in message.content.lower(): is_dropping = True
    elif message.embeds and "dropping" in (message.embeds[0].description or "").lower(): is_dropping = True
    if not is_dropping: return

    image_url = None
    if message.embeds:
        if message.embeds[0].image: image_url = message.embeds[0].image.url
        elif message.embeds[0].thumbnail: image_url = message.embeds[0].thumbnail.url
    elif message.attachments: image_url = message.attachments[0].url

    if image_url:
        server_name = message.guild.name if message.guild else "DM"
        if drop_queue is not None:
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
            embed.set_footer(text="Shadow OCR")
            await channel.send(embed=embed)
        except: pass

# --- LỆNH DEBUG: XEM ẢNH SAU KHI CẮT ---
from PIL import Image, ImageEnhance
import io
import requests

@bot.command(name="view_crop")
async def view_crop(ctx):
    """
    Gửi ảnh kèm lệnh !view_crop để xem bot cắt ghép thế nào.
    """
    # 1. Lấy ảnh từ tin nhắn
    image_url = None
    if ctx.message.attachments:
        image_url = ctx.message.attachments[0].url
    elif ctx.message.embeds and ctx.message.embeds[0].image:
        image_url = ctx.message.embeds[0].image.url
    
    if not image_url:
        await ctx.send("❌ Hãy gửi ảnh kèm lệnh `!view_crop` hoặc reply vào tin nhắn có ảnh.")
        return

    await ctx.send("🔍 Đang phẫu thuật ảnh... Đợi xíu...")

    try:
        # 2. Tải ảnh về
        resp = requests.get(image_url)
        img = Image.open(io.BytesIO(resp.content))
        width, height = img.size

        # 3. Tái hiện quy trình xử lý (Giống hệt ocr_engine.py)
        num_cards = 3
        if width > 1000: num_cards = 4
        card_width = width // num_cards
        
        # Tỷ lệ cắt 12.5%
        crop_height = int(height * 0.125) 
        crop_top = height - crop_height
        
        # Tạo khung ảnh xếp tầng (Padding 10px)
        stack_img = Image.new('RGB', (card_width, (crop_height + 10) * num_cards), (255, 0, 255)) # Nền tím để dễ nhìn phần ghép
        
        for i in range(num_cards):
            left = i * card_width
            right = (i + 1) * card_width
            
            # Cắt
            crop = img.crop((left, crop_top, right, height))
            
            # Convert & Tăng nét
            if crop.mode != 'RGB': crop = crop.convert('RGB')
            enhancer = ImageEnhance.Contrast(crop)
            crop = enhancer.enhance(2.0) # Contrast 2.0
            
            # Dán vào cột
            y_offset = i * (crop_height + 10)
            stack_img.paste(crop, (0, y_offset))

        # 4. Gửi ảnh kết quả lại cho bạn
        with io.BytesIO() as image_binary:
            stack_img.save(image_binary, 'PNG')
            image_binary.seek(0)
            await ctx.send(
                content=f"✅ **Góc nhìn của Gemini:**\n- Cắt đáy: 12.5% ({crop_height}px)\n- Contrast: 2.0\n- Chiến thuật: Xếp tầng", 
                file=discord.File(fp=image_binary, filename='debug_view.png')
            )

    except Exception as e:
        await ctx.send(f"❌ Lỗi debug: {e}")
        

def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if token: bot.run(token)
    else: print("❌ Thiếu DISCORD_TOKEN")
