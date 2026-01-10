import discord
import os
import asyncio
import time
import requests
import io
from discord.ext import commands
from PIL import Image, ImageEnhance
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
                # In log kết quả thành công
                print_str = " | ".join([f"#{p}·{e}" for _, p, e in ocr_results])
                print(f"✅ [DONE] {server_name} -> {print_str}", flush=True)
                
                await send_yoru_style_embed(message.channel, ocr_results)
            else:
                # Log thất bại nhưng không spam
                print(f"❌ [FAIL] {server_name}: Không tìm thấy số nào.", flush=True)

        except Exception as e:
            print(f"💀 [ERROR] {server_name}: {e}", flush=True)
        
        finally:
            drop_queue.task_done()
            # --- TỐC ĐỘ AN TOÀN CHO 200 SERVER ---
            # Nghỉ 2.0 giây giữa các lần xử lý.
            await asyncio.sleep(2.0)

@bot.event
async def on_ready():
    global drop_queue
    print(f"✅ Bot Online: {bot.user.name}")
    print(f"✅ Đang hoạt động trên {len(bot.guilds)} server.")
    
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

# --- LỆNH DEBUG: XEM ẢNH SAU KHI CẮT (Hỗ trợ Reply) ---
@bot.command(name="view_crop")
async def view_crop(ctx):
    """
    Gửi lại ảnh đã qua xử lý (Cắt 12.5% + Tăng nét + Xếp tầng) để kiểm tra.
    Hỗ trợ: Gửi ảnh trực tiếp hoặc Reply tin nhắn có ảnh.
    """
    image_url = None
    
    # 1. Kiểm tra Reply
    if ctx.message.reference:
        try:
            ref_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if ref_message.attachments:
                image_url = ref_message.attachments[0].url
            elif ref_message.embeds:
                if ref_message.embeds[0].image:
                    image_url = ref_message.embeds[0].image.url
                elif ref_message.embeds[0].thumbnail:
                    image_url = ref_message.embeds[0].thumbnail.url
        except: pass

    # 2. Kiểm tra tin nhắn hiện tại
    if not image_url:
        if ctx.message.attachments:
            image_url = ctx.message.attachments[0].url
        elif ctx.message.embeds and ctx.message.embeds[0].image:
            image_url = ctx.message.embeds[0].image.url

    if not image_url:
        await ctx.send("❌ Không tìm thấy ảnh! Hãy **Reply** vào tin nhắn Drop hoặc gửi ảnh kèm lệnh.")
        return

    status_msg = await ctx.send("🔍 Đang phẫu thuật ảnh (Cắt 12.5% + Tăng nét)...")

    try:
        # Tải ảnh
        resp = requests.get(image_url)
        img = Image.open(io.BytesIO(resp.content))
        width, height = img.size

        # --- TÁI HIỆN QUY TRÌNH OCR_ENGINE ---
        num_cards = 3
        if width > 1000: num_cards = 4
        card_width = width // num_cards
        
        # Cắt 12.5% đáy (Chuẩn)
        crop_height = int(height * 0.125) 
        crop_top = height - crop_height
        
        # Tạo khung ảnh xếp tầng (Padding 10px, Nền Tím để dễ nhìn biên giới)
        stack_img = Image.new('RGB', (card_width, (crop_height + 10) * num_cards), (255, 0, 255))
        
        for i in range(num_cards):
            left = i * card_width
            right = (i + 1) * card_width
            
            # Cắt
            crop = img.crop((left, crop_top, right, height))
            
            # Convert & Tăng nét (Contrast 2.0)
            if crop.mode != 'RGB': crop = crop.convert('RGB')
            enhancer = ImageEnhance.Contrast(crop)
            crop = enhancer.enhance(2.0) 
            
            # Dán vào cột
            y_offset = i * (crop_height + 10)
            stack_img.paste(crop, (0, y_offset))

        # Gửi ảnh kết quả
        with io.BytesIO() as image_binary:
            stack_img.save(image_binary, 'PNG')
            image_binary.seek(0)
            await ctx.send(
                content=f"✅ **Góc nhìn của Gemini:**\n- Kích thước gốc: {width}x{height}\n- Cắt đáy: 12.5% (Cao {crop_height}px)\n- Contrast: 2.0 (Siêu tương phản)\n- Xếp tầng: {num_cards} thẻ", 
                file=discord.File(fp=image_binary, filename='debug_view.png')
            )
        
        await status_msg.delete()

    except Exception as e:
        await ctx.send(f"❌ Lỗi debug: {e}")

def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if token: bot.run(token)
    else: print("❌ Thiếu DISCORD_TOKEN")
