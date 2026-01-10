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
            print(f"⚡ [XỬ LÝ] {server_name} (Hàng chờ: {drop_queue.qsize()})", flush=True)
            
            api_keys = get_api_keys()
            loop = asyncio.get_running_loop()
            
            ocr_results = await loop.run_in_executor(
                None, scan_image_gemini, image_url, api_keys
            )
            
            if ocr_results:
                print_str = " | ".join([f"#{p}·{e}" for _, p, e in ocr_results])
                print(f"✅ [DONE] {server_name} -> {print_str}", flush=True)
                await send_yoru_style_embed(message.channel, ocr_results)
            else:
                print(f"❌ [FAIL] {server_name}: Không tìm thấy số.", flush=True)

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
    # --- FIX QUAN TRỌNG: XỬ LÝ LỆNH TRƯỚC ---
    # Bot phải nghe lệnh của chủ nhân trước khi lọc tin nhắn rác
    await bot.process_commands(message)

    # Sau đó mới kiểm tra: Nếu không phải Karuta thì bỏ qua (không phải Drop)
    if message.author.id != KARUTA_ID: 
        return 

    # --- LOGIC XỬ LÝ DROP (Giữ nguyên) ---
    is_dropping = False
    if message.content and "dropping" in message.content.lower():
        is_dropping = True
    elif message.embeds:
        desc = message.embeds[0].description or ""
        if "dropping" in desc.lower():
            is_dropping = True

    if not is_dropping:
        return

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
            print(f"📥 [QUEUE] +1 Drop từ {server_name}", flush=True)
            await drop_queue.put((message, image_url, server_name))

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

# --- LỆNH DEBUG: VIEW CROP ---
@bot.command(name="view_crop")
async def view_crop(ctx):
    image_url = None
    # Ưu tiên lấy ảnh từ Reply
    if ctx.message.reference:
        try:
            ref_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if ref_message.attachments:
                image_url = ref_message.attachments[0].url
            elif ref_message.embeds:
                if ref_message.embeds[0].image: image_url = ref_message.embeds[0].image.url
                elif ref_message.embeds[0].thumbnail: image_url = ref_message.embeds[0].thumbnail.url
        except: pass

    # Nếu không reply, lấy ảnh từ tin nhắn hiện tại
    if not image_url:
        if ctx.message.attachments:
            image_url = ctx.message.attachments[0].url
        elif ctx.message.embeds and ctx.message.embeds[0].image:
            image_url = ctx.message.embeds[0].image.url

    if not image_url:
        await ctx.send("❌ Không tìm thấy ảnh! Hãy **Reply** vào tin nhắn Drop rồi gõ `!view_crop`.")
        return

    msg = await ctx.send("🔍 Đang mổ xẻ ảnh (Cắt 12.5% + Xếp tầng)...")

    try:
        resp = requests.get(image_url)
        img = Image.open(io.BytesIO(resp.content))
        width, height = img.size

        # --- LOGIC CẮT ---
        num_cards = 3
        if width > 1000: num_cards = 4
        card_width = width // num_cards
        
        crop_height = int(height * 0.125) 
        crop_top = height - crop_height
        
        # Tạo ảnh debug
        stack_img = Image.new('RGB', (card_width, (crop_height + 10) * num_cards), (255, 0, 255))
        
        for i in range(num_cards):
            left = i * card_width
            right = (i + 1) * card_width
            crop = img.crop((left, crop_top, right, height))
            
            if crop.mode != 'RGB': crop = crop.convert('RGB')
            enhancer = ImageEnhance.Contrast(crop)
            crop = enhancer.enhance(2.0) 
            
            y_offset = i * (crop_height + 10)
            stack_img.paste(crop, (0, y_offset))

        with io.BytesIO() as image_binary:
            stack_img.save(image_binary, 'PNG')
            image_binary.seek(0)
            await ctx.send(content=f"✅ **Mắt thần Gemini nhìn thấy:**", file=discord.File(fp=image_binary, filename='debug.png'))
        
        await msg.delete()

    except Exception as e:
        await ctx.send(f"❌ Lỗi: {e}")

def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if token: bot.run(token)
    else: print("❌ Thiếu DISCORD_TOKEN")
