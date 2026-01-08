import threading
from bot_logic import run_discord_bot
from web_server import run_web

if __name__ == "__main__":
    # 1. Chạy Web Server ở một luồng riêng (Daemon thread)
    # Daemon thread sẽ tự tắt khi chương trình chính tắt
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    # 2. Chạy Bot Discord ở luồng chính
    print("🚀 Đang khởi động hệ thống...")
    run_discord_bot()
