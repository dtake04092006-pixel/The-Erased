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

def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if token: bot.run(token)
    else: print("❌ Thiếu DISCORD_TOKEN")
