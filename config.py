"""
Konfigurasi Bot Telegram Ghibli Style
-------------------------------------
File ini berisi semua parameter konfigurasi untuk GhibliBotTelegram
"""

# Konfigurasi Bot
BOT_CONFIG = {
    "token": "YOUR_TELEGRAM_BOT_TOKEN",
    "name": "GhibliBotTelegram",
    "username": "ghibli_style_bot",
    "version": "1.3.0",
    "release_date": "08/04/2025",
    "description": "Bot keren buat ngerubah foto jadi gaya Studio Ghibli",
}

# Konfigurasi Owner dan Admin
USER_ROLES = {
    "owner": {
        "user_ids": [123456789],  # Ganti dengan ID Telegram owner
        "permissions": ["all"]  # Owner punya semua permission
    },
    "admin": {
        "user_ids": [234567890, 345678901],  # Ganti dengan ID Telegram admin
        "permissions": ["manage_limits", "broadcast", "view_stats"]
    },
    "moderator": {
        "user_ids": [456789012, 567890123],  # Ganti dengan ID Telegram moderator
        "permissions": ["view_stats", "add_limit"]
    }
}

# Konfigurasi Channel dan Grup
CHANNEL_CONFIG = {
    "required_channels": [
        {"username": "channel1", "id": -1001234567890, "link": "https://t.me/channel1", "description": "Channel Utama"},
        {"username": "channel2", "id": -1001234567891, "link": "https://t.me/channel2", "description": "Channel Updates"},
        {"username": "channel3", "id": -1001234567892, "link": "https://t.me/channel3", "description": "Channel Community"}
    ],
    "allowed_groups": [
        {"name": "Grup Utama", "id": -1001234567893, "description": "Grup resmi untuk generate gambar Ghibli"},
        {"name": "VIP Group", "id": -1001234567894, "description": "Grup khusus untuk user VIP"}
    ]
}

# Konfigurasi Fitur dan Limit
FEATURE_CONFIG = {
    "daily_limit": 2,  # Limit default per hari
    "vip_daily_limit": 5,  # Limit untuk user VIP
    "min_strength": 0.3,  # Minimum strength untuk gaya Ghibli
    "max_strength": 0.8,  # Maximum strength untuk gaya Ghibli
    "default_strength": 0.6,  # Default strength untuk gaya Ghibli
    "process_timeout": 60,  # Timeout dalam detik untuk proses generate
    "enable_watermark": True,  # Tambahkan watermark pada hasil
    "watermark_text": "@your_username",  # Teks watermark
}

# Konfigurasi Referral
REFERRAL_CONFIG = {
    "enable_referral": True,  # Aktifkan sistem referral
    "referrer_bonus": 2,  # Bonus limit untuk referrer
    "referee_bonus": 1,  # Bonus limit untuk referee (yang diundang)
    "min_uses_for_extra_bonus": 5,  # Jumlah minimum referral untuk dapat bonus tambahan
    "extra_bonus": 3,  # Bonus tambahan jika mencapai minimum uses
    "referral_link_format": "https://t.me/{bot_username}?start=ref_{user_id}",  # Format link referral
    "referral_expire_days": 30,  # Masa berlaku referral dalam hari
}

# Konfigurasi Database dan File
STORAGE_CONFIG = {
    "db_file": "users_data.json",  # File database utama
    "backup_folder": "backups",  # Folder untuk backup database
    "temp_folder": "temp_images",  # Folder untuk gambar sementara
    "result_folder": "results",  # Folder untuk menyimpan hasil
    "logs_folder": "logs",  # Folder untuk log
    "auto_backup": True,  # Backup otomatis
    "backup_interval": 24,  # Interval backup dalam jam
    "keep_results": False,  # Simpan hasil generate secara permanen
    "max_results_age": 7,  # Hapus hasil setelah x hari
}

# Konfigurasi Model AI
MODEL_CONFIG = {
    "model_id": "nitrosocke/Ghibli-Diffusion",  # ID model Diffusion
    "use_gpu": True,  # Gunakan GPU jika tersedia
    "optimize_memory": True,  # Optimize penggunaan memory
    "enable_attention_slicing": True,  # Enable attention slicing untuk mengurangi penggunaan memory
    "prompt": "Ghibli-style anime painting, soft pastel colors, highly detailed, masterpiece",  # Prompt default
    "negative_prompt": "lowres, bad anatomy, bad hands, cropped, worst quality",  # Negative prompt default
}

# Konfigurasi Bot Messages
MESSAGES = {
    "welcome": "🌟 Halo {first_name}! Selamat datang di GhibliBotTelegram! 🌟\n\n_Bot keren buat ngerubah foto lo jadi gaya Studio Ghibli yang aesthetic abis_ ✨",
    "not_in_group": "❌ Bot ini cuma bisa dipake di grup yang diizinkan!",
    "not_subscribed": "❌ Lo belum join semua channel yang diperlukan!",
    "limit_exceeded": "❌ Limit harian lo udah abis, bro!",
    "processing": "🔄 Sedang memproses foto...",
    "success": "✨ Foto Ghibli lo udah jadi! ✨",
    "error": "❌ Error saat memproses gambar!",
    "referral_success": "🎉 Selamat! Kamu berhasil mengundang {referee_name} menggunakan link referral kamu!",
    "referral_welcome": "👋 Halo! Kamu bergabung menggunakan referral dari {referrer_name} dan mendapatkan bonus +1 limit!",
    "referral_info": "🔗 Link referral kamu: {referral_link}\n\nSetiap orang yang pakai link kamu akan dapat +1 limit, dan kamu dapat +2 limit untuk setiap orang yang menggunakan link kamu!",
}

# Export all config as a dictionary for easy access
CONFIG = {
    "bot": BOT_CONFIG,
    "users": USER_ROLES,
    "channels": CHANNEL_CONFIG,
    "features": FEATURE_CONFIG,
    "referral": REFERRAL_CONFIG,
    "storage": STORAGE_CONFIG,
    "model": MODEL_CONFIG,
    "messages": MESSAGES,
}
