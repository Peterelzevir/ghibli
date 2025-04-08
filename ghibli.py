"""
GhibliBotTelegram - Bot Telegram untuk mengubah foto menjadi gaya Studio Ghibli
--------------------------------------------------------------------------------
Fitur:
- Transformasi foto ke gaya Studio Ghibli
- Sistem referral untuk mengundang pengguna baru
- Dashboard admin dan statistik
- Konfigurasi terpusat
"""

import logging
import os
import time
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

import torch
from PIL import Image
import io
from diffusers import StableDiffusionImg2ImgPipeline

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ChatAction,
    ChatMember,
    Bot, 
    ParseMode,
    Message
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

# Import konfigurasi dan utilitas
from config import CONFIG
import utils

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Variabel global untuk model
model = None

# State untuk conversation handler
WAITING_FOR_PHOTO, PROCESSING = range(2)

# ============== MODEL AI FUNCTIONS ==============

def load_model():
    """Load model Ghibli-Diffusion"""
    model_id = CONFIG["model"]["model_id"]
    use_gpu = CONFIG["model"]["use_gpu"]
    
    dtype = torch.float16 if use_gpu and torch.cuda.is_available() else torch.float32
    logger.info("🔄 Loading Ghibli-Diffusion model...")
    
    pipe = StableDiffusionImg2ImgPipeline.from_pretrained(model_id, torch_dtype=dtype)
    device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
    pipe.to(device)
    
    if CONFIG["model"]["enable_attention_slicing"]:
        pipe.enable_attention_slicing()  # Optimize memory usage
    
    logger.info(f"✅ Model loaded on {device}!")
    return pipe

async def generate_ghibli_image(image, strength=None):
    """Generate gambar gaya Ghibli dari input image"""
    global model
    
    # Use default strength if not specified
    if strength is None:
        strength = CONFIG["features"]["default_strength"]
    
    # Clamp strength to valid range
    strength = max(CONFIG["features"]["min_strength"], 
                   min(CONFIG["features"]["max_strength"], strength))
    
    # Load model jika belum
    if model is None:
        model = load_model()
    
    # Preprocess image
    image = image.convert("RGB")
    image = image.resize((512, 512))  # Pastikan ukuran yang tepat
    
    # Prompt dari konfigurasi
    prompt = CONFIG["model"]["prompt"]
    negative_prompt = CONFIG["model"]["negative_prompt"]
    
    logger.info("🎨 Generating Ghibli image...")
    start_time = time.time()
    
    # Execute model in thread pool to avoid blocking
    result = await asyncio.to_thread(
        model, 
        prompt=prompt, 
        image=image, 
        strength=strength,
        negative_prompt=negative_prompt
    )
    
    process_time = time.time() - start_time
    logger.info(f"✨ Image generated in {process_time:.2f} seconds!")
    
    # Get first image from result
    result_image = result.images[0]
    
    return result_image, process_time

# ============== SUBSCRIPTION CHECK ==============

async def check_user_subscriptions(bot: Bot, user_id: int) -> Tuple[bool, List[Dict]]:
    """Cek status subscription user ke channel yang diperlukan"""
    not_joined = []
    
    for channel in CONFIG["channels"]["required_channels"]:
        try:
            member = await bot.get_chat_member(chat_id=channel["id"], user_id=user_id)
            status = member.status
            # Status valid: 'creator', 'administrator', 'member'
            if status not in [ChatMember.CREATOR, ChatMember.ADMINISTRATOR, ChatMember.MEMBER]:
                not_joined.append(channel)
        except Exception as e:
            logger.error(f"Error saat cek membership: {e}")
            not_joined.append(channel)
    
    return len(not_joined) == 0, not_joined

# ============== COMMAND HANDLERS ==============

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kirim pesan pengenalan ketika command /start digunakan"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Proses referral jika ada
    if context.args:
        start_param = context.args[0]
        ref_code = utils.extract_referral_code(start_param)
        
        if ref_code:
            success, referrer_data = utils.process_referral(user.id, ref_code)
            if success:
                # Kirim pesan ke referee (user baru)
                referrer_name = utils.get_referrer_name(int(referrer_data["user_id"]))
                referee_msg = CONFIG["messages"]["referral_welcome"].format(referrer_name=referrer_name)
                await update.message.reply_text(
                    f"{referee_msg}\n\n",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Kirim pesan ke referrer
                try:
                    referee_name = user.first_name or f"@{user.username}" if user.username else f"User {user.id}"
                    referrer_msg = CONFIG["messages"]["referral_success"].format(referee_name=referee_name)
                    await context.bot.send_message(
                        chat_id=int(referrer_data["user_id"]),
                        text=referrer_msg,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    logger.error(f"Error sending referral notification: {e}")
    
    # Update data user
    user_data = utils.get_user_data(user.id)
    user_data.update({
        "username": user.username or "",
        "first_name": user.first_name or "",
        "last_name": user.last_name or ""
    })
    utils.update_user_data(user.id, user_data)
    
    # Membuat keyboard untuk menu utama
    keyboard = [
        [
            InlineKeyboardButton("📸 Mulai Generate", callback_data="start_generate"),
            InlineKeyboardButton("ℹ️ Tutorial", callback_data="tutorial")
        ],
        [
            InlineKeyboardButton("🏆 Top Users", callback_data="top_users"),
            InlineKeyboardButton("📊 Statistik", callback_data="stats")
        ],
        [
            InlineKeyboardButton("🔗 Referral", callback_data="referral"),
            InlineKeyboardButton("🤖 About Bot", callback_data="about")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Pesan selamat datang dengan format Telegram
    welcome_message = (
        f"*{CONFIG['messages']['welcome']}*\n\n"
        f"*Limit harian lo:* `{user_data['remaining_limit']}/{CONFIG['features']['daily_limit']}` foto\n"
        f"*Terakhir generate:* {utils.format_time_ago(user_data.get('last_generation_time', None))}\n\n"
        f"```\n🔥 Pilih menu di bawah untuk mulai pakai fitur bot 🔥\n```"
    )
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kirim pesan bantuan ketika command /help digunakan"""
    help_text = (
        "*🚀 BANTUAN GHIBLIBOT 🚀*\n\n"
        "Ini cara pake bot keren ini:\n\n"
        "1️⃣ *Wajib join 3 channel* dulu sebelum bisa pake bot\n"
        "2️⃣ Bot cuma bisa dipake *di dalam grup yang diizinkan*\n"
        "3️⃣ Lo punya limit *2 generate per hari*\n"
        "4️⃣ Kirim foto dengan caption `/ghibli` di grup\n"
        "5️⃣ Tunggu proses... dan foto lo bakal berubah jadi gaya Ghibli!\n\n"
        
        "*Perintah yang tersedia:*\n"
        "🔹 `/start` - Mulai bot dan lihat menu utama\n"
        "🔹 `/help` - Tampilkan bantuan ini\n"
        "🔹 `/ghibli` - Generate foto dengan gaya Ghibli (kirim dengan foto)\n"
        "🔹 `/stats` - Lihat statistik penggunaan bot\n"
        "🔹 `/referral` - Dapatkan link referral kamu\n"
        "🔹 `/limit` - Cek limit harian kamu\n\n"
        
        "*🔗 FITUR REFERRAL 🔗*\n"
        "- Setiap orang yang join pakai link kamu dapat +1 limit\n"
        "- Kamu dapat +2 limit untuk setiap orang yang pakai link kamu\n"
        "- Jika 5+ orang pakai link kamu, kamu dapat bonus +3 limit tambahan\n\n"
        
        "_Bot ini menggunakan AI canggih untuk mengubah foto menjadi gaya Studio Ghibli yang memukau_ ✨"
    )
    
    # Tambah tombol untuk kembali ke menu utama
    keyboard = [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        help_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tampilkan info limit user"""
    user = update.effective_user
    user_data = utils.get_user_data(user.id)
    
    limit_text = (
        f"*📊 INFO LIMIT KAMU 📊*\n\n"
        f"👤 *User:* {user.first_name}\n"
        f"🎯 *Limit tersisa:* `{user_data['remaining_limit']}/{CONFIG['features']['daily_limit']}` per hari\n"
        f"🕒 *Reset limit:* Setiap jam 00:00 WIB\n"
        f"🔄 *Terakhir generate:* {utils.format_time_ago(user_data.get('last_generation_time', None))}\n\n"
        f"_Tips: Undang temen dengan link referral untuk nambah limit!_ 🔗"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔗 Dapatkan Link Referral", callback_data="referral")],
        [InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        limit_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tampilkan statistik bot"""
    db = utils.load_database()
    user = update.effective_user
    user_data = utils.get_user_data(user.id)
    
    total_users = db["stats"]["total_users"]
    total_generations = db["stats"]["total_generations"]
    total_referrals = db["referrals"]["total_conversions"]
    
    stats_text = (
        f"*📈 STATISTIK GHIBLIBOT 📈*\n\n"
        f"👥 *Total users:* `{total_users}`\n"
        f"🖼 *Total generate:* `{total_generations}`\n"
        f"🔗 *Total referrals:* `{total_referrals}`\n"
        f"👤 *Generate kamu:* `{user_data['total_generations']}`\n\n"
        
        f"*🏆 TOP 5 USERS 🏆*\n"
    )
    
    # Tambahkan top 5 users
    for i, user_stat in enumerate(db["stats"]["top_users"][:5], 1):
        name = user_stat["first_name"] or user_stat["username"] or f"User {user_stat['user_id']}"
        stats_text += f"{i}. {name}: `{user_stat['total_generations']}` generate\n"
    
    keyboard = [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        stats_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tampilkan referral link user"""
    user = update.effective_user
    referral_link = utils.create_referral_link(user.id)
    user_data = utils.get_user_data(user.id)
    
    referral_text = (
        f"*🔗 LINK REFERRAL KAMU 🔗*\n\n"
        f"{CONFIG['messages']['referral_info'].format(referral_link=referral_link)}\n\n"
        f"*Statistik Referral Kamu:*\n"
        f"👥 *Orang yang diundang:* `{len(user_data['referral']['referred_users'])}`\n"
        f"🎁 *Total bonus:* `{user_data['referral']['total_referrals'] * CONFIG['referral']['referrer_bonus']}`\n"
        f"🔥 *Bonus spesial:* `{'Sudah diklaim' if user_data['referral']['bonus_claimed'] else f'Belum (butuh {CONFIG['referral']['min_uses_for_extra_bonus']} undangan)'}`\n\n"
        f"_Share link ini ke teman-temanmu untuk dapatkan bonus limit!_ 🚀"
    )
    
    keyboard = [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        referral_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

# ============== ADMIN COMMANDS ==============

async def add_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command admin untuk menambah limit user"""
    user = update.effective_user
    
    # Cek apakah user memiliki permission
    if not utils.has_permission(user.id, "manage_limits"):
        await update.message.reply_text(
            "❌ *Lo gak punya permission buat command ini, bro!*",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Cek format perintah: /addlimit user_id amount
    if not context.args or len(context.args) != 2:
        await update.message.reply_text(
            "*❓ Format yang bener:* `/addlimit user_id jumlah`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text(
            "❌ *User ID dan jumlah harus angka, bro!*",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Tambah limit
    success, new_limit = utils.modify_user_limit(target_user_id, amount)
    
    if success:
        await update.message.reply_text(
            f"✅ *Berhasil menambah limit!*\n\n"
            f"👤 *User ID:* `{target_user_id}`\n"
            f"➕ *Ditambahkan:* `{amount}`\n"
            f"🔄 *Limit sekarang:* `{new_limit}`",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "❌ *Gagal menambah limit. Coba lagi nanti.*",
            parse_mode=ParseMode.MARKDOWN
        )

async def reduce_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command admin untuk mengurangi limit user"""
    user = update.effective_user
    
    # Cek apakah user memiliki permission
    if not utils.has_permission(user.id, "manage_limits"):
        await update.message.reply_text(
            "❌ *Lo gak punya permission buat command ini, bro!*",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Cek format perintah: /reducelimit user_id amount
    if not context.args or len(context.args) != 2:
        await update.message.reply_text(
            "*❓ Format yang bener:* `/reducelimit user_id jumlah`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        target_user_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text(
            "❌ *User ID dan jumlah harus angka, bro!*",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Kurangi limit (amount negative)
    success, new_limit = utils.modify_user_limit(target_user_id, -amount)
    
    if success:
        await update.message.reply_text(
            f"✅ *Berhasil mengurangi limit!*\n\n"
            f"👤 *User ID:* `{target_user_id}`\n"
            f"➖ *Dikurangi:* `{amount}`\n"
            f"🔄 *Limit sekarang:* `{new_limit}`",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "❌ *Gagal mengurangi limit. Coba lagi nanti.*",
            parse_mode=ParseMode.MARKDOWN
        )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command admin untuk broadcast pesan ke semua user"""
    user = update.effective_user
    
    # Cek apakah user memiliki permission
    if not utils.has_permission(user.id, "broadcast"):
        await update.message.reply_text(
            "❌ *Lo gak punya permission buat command ini, bro!*",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Cek format perintah: /broadcast pesan
    if not context.args:
        await update.message.reply_text(
            "*❓ Format yang bener:* `/broadcast pesan yang mau dikirim`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    broadcast_message = " ".join(context.args)
    db = utils.load_database()
    user_count = 0
    
    await update.message.reply_text(
        "*🔄 Memulai broadcast...*",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Kirim pesan ke semua user
    for user_id in db["users"]:
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=f"*📢 BROADCAST MESSAGE 📢*\n\n{broadcast_message}",
                parse_mode=ParseMode.MARKDOWN
            )
            user_count += 1
            
            # Sleep untuk menghindari rate limit
            if user_count % 20 == 0:
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error saat broadcast ke user {user_id}: {e}")
    
    await update.message.reply_text(
        f"✅ *Broadcast selesai!*\n\n"
        f"📨 *Pesan terkirim ke:* `{user_count}` user",
        parse_mode=ParseMode.MARKDOWN
    )

async def user_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command admin untuk melihat statistik spesifik user"""
    user = update.effective_user
    
    # Cek apakah user memiliki permission
    if not utils.has_permission(user.id, "view_stats"):
        await update.message.reply_text(
            "❌ *Lo gak punya permission buat command ini, bro!*",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Cek format perintah: /userstats user_id atau /userstats username
    if not context.args:
        await update.message.reply_text(
            "*❓ Format yang bener:* `/userstats user_id` atau `/userstats @username`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    target = context.args[0]
    db = utils.load_database()
    
    # Cari user berdasarkan ID atau username
    target_data = None
    target_id = None
    
    if target.startswith("@"):
        username = target[1:]  # Remove @
        for user_id, data in db["users"].items():
            if data.get("username") == username:
                target_data = data
                target_id = user_id
                break
    else:
        try:
            user_id = target
            if user_id in db["users"]:
                target_data = db["users"][user_id]
                target_id = user_id
        except ValueError:
            pass
    
    if not target_data:
        await update.message.reply_text(
            "❌ *User tidak ditemukan! Cek ID atau username.*",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Format statistik user
    user_stats = (
        f"*📊 STATISTIK USER 📊*\n\n"
        f"👤 *User ID:* `{target_id}`\n"
        f"👤 *Username:* `{target_data.get('username', 'Tidak ada')}`\n"
        f"👤 *Nama:* `{target_data.get('first_name', '')} {target_data.get('last_name', '')}`\n"
        f"📅 *Bergabung:* `{utils.format_time_ago(target_data.get('join_date', None))}`\n"
        f"🔢 *Total generate:* `{target_data.get('total_generations', 0)}`\n"
        f"🔄 *Limit tersisa:* `{target_data.get('remaining_limit', 0)}`\n"
        f"🎯 *Status:* `{target_data.get('status', 'active')}`\n"
        f"👑 *Role:* `{target_data.get('role', 'user')}`\n\n"
        
        f"*🔗 Referral Info:*\n"
        f"📌 *Direferral oleh:* `{target_data.get('referral', {}).get('referred_by', 'Tidak ada')}`\n"
        f"🔢 *Jumlah referral:* `{len(target_data.get('referral', {}).get('referred_users', []))}`\n"
        f"🎁 *Bonus claimed:* `{target_data.get('referral', {}).get('bonus_claimed', False)}`\n\n"
        
        f"*⏱ Aktivitas:*\n"
        f"🕒 *Terakhir generate:* `{utils.format_time_ago(target_data.get('last_generation_time', None))}`\n"
    )
    
    # Tambahkan tombol action jika memiliki permission
    keyboard = []
    if utils.has_permission(user.id, "manage_limits"):
        keyboard.append([
            InlineKeyboardButton("➕ Tambah 5 Limit", callback_data=f"admin_add_limit_{target_id}_5"),
            InlineKeyboardButton("➖ Kurangi 5 Limit", callback_data=f"admin_reduce_limit_{target_id}_5")
        ])
        
        # Tombol change role jika user adalah owner
        if utils.get_user_role(user.id) == "owner":
            keyboard.append([
                InlineKeyboardButton("👑 Make VIP", callback_data=f"admin_role_{target_id}_vip"),
                InlineKeyboardButton("🔄 Reset Role", callback_data=f"admin_role_{target_id}_user")
            ])
    
    keyboard.append([InlineKeyboardButton("🏠 Kembali", callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        user_stats,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

# ============== GHIBLI GENERATION HANDLER ==============

async def ghibli_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle command /ghibli untuk generate gambar"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    message = update.message
    
    # Cek apakah command dijalankan di grup yang diizinkan
    if not utils.is_in_allowed_group(chat_id):
        group_links = utils.get_allowed_groups_text()
        
        await message.reply_text(
            f"*{CONFIG['messages']['not_in_group']}*\n\n"
            f"Coba join dan gunakan di salah satu grup berikut:\n"
            f"{group_links}",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        return
    
    # Cek apakah ada foto yang dilampirkan
    if not message.photo:
        await message.reply_text(
            "*❌ Perintah ini harus dilampirkan dengan foto!*\n\n"
            "Caranya: Kirim foto dengan caption `/ghibli`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Cek apakah user telah subscribe ke semua channel
    subscribed, not_joined_channels = await check_user_subscriptions(context.bot, user.id)
    if not subscribed:
        channel_links = utils.get_required_channels_text()
        
        keyboard = [[InlineKeyboardButton("✅ Sudah Join Semua", callback_data="check_subscription")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(
            f"*{CONFIG['messages']['not_subscribed']}*\n\n"
            f"Join dulu channel berikut:\n"
            f"{channel_links}\n\n"
            f"Klik tombol di bawah setelah join semua channel.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        return
    
    # Cek limit user
    user_data = utils.get_user_data(user.id)
    
    if user_data["remaining_limit"] <= 0:
        keyboard = [[InlineKeyboardButton("🔄 Cek Limit", callback_data="check_limit")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(
            f"*{CONFIG['messages']['limit_exceeded']}*\n\n"
            f"Limit reset setiap jam 00:00 WIB.\n"
            f"Tunggu besok atau gunakan link referral untuk dapat bonus limit.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Ambil foto yang dikirim user
    photo_file = await message.photo[-1].get_file()
    
    # Buat folder temp jika belum ada
    utils.ensure_directories()
    
    # Download foto
    photo_path = f"{CONFIG['storage']['temp_folder']}/{user.id}_{int(time.time())}_input.jpg"
    await photo_file.download_to_drive(photo_path)
    
    # Kirim pesan proses
    process_message = await message.reply_text(
        f"*{CONFIG['messages']['processing']}*\n\n"
        "```\n"
        "⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛ 0%\n"
        "```\n\n"
        "_Harap tunggu, proses ini membutuhkan waktu..._",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Update pesan proses untuk simulasi progress
    progress_steps = 10
    for i in range(1, progress_steps + 1):
        filled = "⬜" * i
        empty = "⬛" * (progress_steps - i)
        
        try:
            await process_message.edit_text(
                f"*{CONFIG['messages']['processing']}*\n\n"
                f"```\n"
                f"{filled}{empty} {i*10}%\n"
                f"```\n\n"
                f"_Harap tunggu, proses ini membutuhkan waktu..._",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error updating progress: {e}")
        
        await asyncio.sleep(0.5)
    
    # Tandai bot sedang mengetik
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
    
    try:
        # Load image
        input_image = Image.open(photo_path)
        
        # Generate image dengan strength dari preferensi user atau default
        strength = user_data["preferences"].get("strength", CONFIG["features"]["default_strength"])
        
        # Generate image
        start_time = time.time()
        result_image, process_time = await generate_ghibli_image(input_image, strength)
        
        # Simpan hasil
        result_path = f"{CONFIG['storage']['temp_folder']}/{user.id}_{int(time.time())}_output.jpg"
        result_image.save(result_path)
        
        # Update limit dan statistik user
        user_data["remaining_limit"] -= 1
        user_data["total_generations"] += 1
        user_data["last_generation_time"] = datetime.now().isoformat()
        utils.update_user_data(user.id, user_data)
        utils.update_user_stats(user.id, user_data)
        
        # Kirim gambar hasil
        with open(result_path, 'rb') as photo:
            # Prepare caption
            caption = (
                f"*{CONFIG['messages']['success']}*\n\n"
                f"👤 *Dibuat oleh:* [{user.first_name}](tg://user?id={user.id})\n"
                f"⏱ *Waktu proses:* `{process_time:.2f}` detik\n"
                f"🔄 *Limit tersisa:* `{user_data['remaining_limit']}/{CONFIG['features']['daily_limit']}`\n\n"
                f"_Powered by GhibliBotTelegram_ 🤖"
            )
            
            # Prepare keyboard
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Bikin Lagi", callback_data="start_generate"),
                    InlineKeyboardButton("🔗 Share Referral", callback_data="referral")
                ],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=message.message_id
            )
        
        # Delete process message
        await process_message.delete()
        
        # Simpan hasil secara permanen jika diaktifkan dalam konfigurasi
        if CONFIG["storage"]["keep_results"]:
            result_perm_path = f"{CONFIG['storage']['result_folder']}/{user.id}_{int(time.time())}_output.jpg"
            result_image.save(result_perm_path)
        else:
            # Hapus file temporary
            try:
                os.remove(photo_path)
                os.remove(result_path)
            except Exception as e:
                logger.error(f"Error removing temp files: {e}")
        
    except Exception as e:
        logger.error(f"Error generating image: {e}")
        
        await process_message.edit_text(
            f"*{CONFIG['messages']['error']}*\n\n"
            f"Detail error: `{str(e)}`\n\n"
            f"Silakan coba lagi dengan foto lain.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Hapus file temporary
        try:
            os.remove(photo_path)
        except:
            pass

# ============== CALLBACK HANDLERS ==============

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback dari inline buttons"""
    query = update.callback_query
    user = query.from_user
    data = query.data
    
    # Acknowledge the button click
    await query.answer()
    
    # Handle admin actions yang memerlukan permission
    if data.startswith("admin_"):
        # Extract action type and parameters
        parts = data.split("_")
        if len(parts) < 3:
            return
        
        action = parts[1]
        
        # Check permissions berdasarkan action
        required_permission = "view_stats"  # Default permission
        if action == "add_limit" or action == "reduce_limit":
            required_permission = "manage_limits"
        elif action == "role":
            required_permission = "all"  # Only owner can change roles
        
        if not utils.has_permission(user.id, required_permission):
            await query.edit_message_text(
                "❌ *Lo gak punya permission buat melakukan aksi ini, bro!*",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Process admin actions
        if action == "add_limit" and len(parts) >= 4:
            target_id = parts[2]
            amount = int(parts[3])
            success, new_limit = utils.modify_user_limit(int(target_id), amount)
            
            if success:
                await query.edit_message_text(
                    f"✅ *Limit berhasil ditambahkan!*\n\n"
                    f"👤 *User ID:* `{target_id}`\n"
                    f"➕ *Ditambahkan:* `{amount}`\n"
                    f"🔄 *Limit sekarang:* `{new_limit}`\n\n"
                    f"_Kembali ke menu dalam 3 detik..._",
                    parse_mode=ParseMode.MARKDOWN
                )
                # Sleep dan redirect ke menu
                await asyncio.sleep(3)
                await back_to_menu(update, context)
            
        elif action == "reduce_limit" and len(parts) >= 4:
            target_id = parts[2]
            amount = int(parts[3])
            success, new_limit = utils.modify_user_limit(int(target_id), -amount)
            
            if success:
                await query.edit_message_text(
                    f"✅ *Limit berhasil dikurangi!*\n\n"
                    f"👤 *User ID:* `{target_id}`\n"
                    f"➖ *Dikurangi:* `{amount}`\n"
                    f"🔄 *Limit sekarang:* `{new_limit}`\n\n"
                    f"_Kembali ke menu dalam 3 detik..._",
                    parse_mode=ParseMode.MARKDOWN
                )
                # Sleep dan redirect ke menu
                await asyncio.sleep(3)
                await back_to_menu(update, context)
        
        elif action == "role" and len(parts) >= 4:
            target_id = parts[2]
            new_role = parts[3]
            
            # Update role user di database
            user_data = utils.get_user_data(int(target_id))
            user_data["role"] = new_role
            success = utils.update_user_data(int(target_id), user_data)
            
            if success:
                await query.edit_message_text(
                    f"✅ *Role user berhasil diubah!*\n\n"
                    f"👤 *User ID:* `{target_id}`\n"
                    f"👑 *Role baru:* `{new_role}`\n\n"
                    f"_Kembali ke menu dalam 3 detik..._",
                    parse_mode=ParseMode.MARKDOWN
                )
                # Sleep dan redirect ke menu
                await asyncio.sleep(3)
                await back_to_menu(update, context)
        
        return
    
    # Handle standard menu callbacks
    if data == "back_to_menu":
        await back_to_menu(update, context)
    
    elif data == "start_generate":
        await start_generate_callback(update, context)
    
    elif data == "tutorial":
        await tutorial_callback(update, context)
    
    elif data == "top_users":
        await top_users_callback(update, context)
    
    elif data == "stats":
        await stats_callback(update, context)
    
    elif data == "about":
        await about_callback(update, context)
    
    elif data == "check_subscription":
        await check_subscription_callback(update, context)
    
    elif data == "check_limit":
        await check_limit_callback(update, context)
    
    elif data == "referral":
        await referral_callback(update, context)

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback untuk kembali ke menu utama"""
    query = update.callback_query
    user = query.from_user
    
    # Update data user
    user_data = utils.get_user_data(user.id)
    
    keyboard = [
        [
            InlineKeyboardButton("📸 Mulai Generate", callback_data="start_generate"),
            InlineKeyboardButton("ℹ️ Tutorial", callback_data="tutorial")
        ],
        [
            InlineKeyboardButton("🏆 Top Users", callback_data="top_users"),
            InlineKeyboardButton("📊 Statistik", callback_data="stats")
        ],
        [
            InlineKeyboardButton("🔗 Referral", callback_data="referral"),
            InlineKeyboardButton("🤖 About Bot", callback_data="about")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_message = (
        f"*{CONFIG['messages']['welcome']}*\n\n"
        f"*Limit harian lo:* `{user_data['remaining_limit']}/{CONFIG['features']['daily_limit']}` foto\n"
        f"*Terakhir generate:* {utils.format_time_ago(user_data.get('last_generation_time', None))}\n\n"
        f"```\n🔥 Pilih menu di bawah untuk mulai pakai fitur bot 🔥\n```"
    )
    
    await query.edit_message_text(
        welcome_message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def start_generate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback untuk mulai generate"""
    query = update.callback_query
    user = query.from_user
    chat_id = update.effective_chat.id
    
    # Cek apakah callback di grup yang diizinkan
    if not utils.is_in_allowed_group(chat_id) and chat_id > 0:  # chat_id > 0 berarti private chat
        group_links = utils.get_allowed_groups_text()
        
        keyboard = [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"*{CONFIG['messages']['not_in_group']}*\n\n"
            f"Coba join dan gunakan di salah satu grup berikut:\n"
            f"{group_links}",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        return
    
    # Cek apakah user telah subscribe ke semua channel
    subscribed, not_joined_channels = await check_user_subscriptions(context.bot, user.id)
    if not subscribed:
        channel_links = utils.get_required_channels_text()
        
        keyboard = [
            [InlineKeyboardButton("✅ Sudah Join Semua", callback_data="check_subscription")],
            [InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"*{CONFIG['messages']['not_subscribed']}*\n\n"
            f"Join dulu channel berikut:\n"
            f"{channel_links}\n\n"
            f"Klik tombol di bawah setelah join semua channel.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        return
    
    # Cek limit user
    user_data = utils.get_user_data(user.id)
    
    if user_data["remaining_limit"] <= 0:
        keyboard = [
            [
                InlineKeyboardButton("🔄 Cek Limit", callback_data="check_limit"),
                InlineKeyboardButton("🔗 Referral", callback_data="referral")
            ],
            [InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"*{CONFIG['messages']['limit_exceeded']}*\n\n"
            f"Limit reset setiap jam 00:00 WIB.\n"
            f"Undang teman dengan link referral untuk mendapat bonus limit tambahan!",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Instruksi generate
    keyboard = [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    instructions = (
        f"*📸 Cara Generate Foto Ghibli 📸*\n\n"
        f"1️⃣ Kirim foto di *grup yang diizinkan*\n"
        f"2️⃣ Tambahkan caption `/ghibli`\n"
        f"3️⃣ Tunggu sampai proses selesai\n\n"
        f"*Limit tersisa:* `{user_data['remaining_limit']}/{CONFIG['features']['daily_limit']}` foto\n\n"
        f"_Catatan: Foto lo bakal diubah ke style Studio Ghibli yang keren abis!_ ✨"
    )
    
    await query.edit_message_text(
        instructions,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def tutorial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback untuk menampilkan tutorial"""
    query = update.callback_query
    
    keyboard = [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    channel_links = utils.get_required_channels_text()
    
    tutorial = (
        f"*📚 TUTORIAL GHIBLIBOT 📚*\n\n"
        f"*Cara Pakai Bot:*\n"
        f"1️⃣ Join ketiga channel yang diperlukan:\n"
        f"{channel_links}\n\n"
        f"2️⃣ Pastikan lo ada di grup yang diizinkan\n\n"
        f"3️⃣ Kirim foto dengan caption `/ghibli`\n\n"
        f"4️⃣ Tunggu proses selesai (biasanya 10-30 detik)\n\n"
        f"5️⃣ Tadaaa! Foto lo udah berubah jadi style Ghibli!\n\n"
        f"_Note: Lo punya limit {CONFIG['features']['daily_limit']} foto per hari. Limit reset jam 00:00 WIB._\n\n"
        
        f"*🔗 SISTEM REFERRAL 🔗*\n"
        f"- Klik menu 'Referral' untuk mendapatkan link referral kamu\n"
        f"- Share link ke teman untuk mendapatkan bonus limit:\n"
        f"  • Teman dapat bonus +{CONFIG['referral']['referee_bonus']} limit\n"
        f"  • Kamu dapat bonus +{CONFIG['referral']['referrer_bonus']} limit\n"
        f"  • Jika {CONFIG['referral']['min_uses_for_extra_bonus']}+ orang pakai link kamu, dapat bonus tambahan +{CONFIG['referral']['extra_bonus']} limit\n\n"
        
        f"*💡 Tips:*\n"
        f"- Hasil terbaik untuk foto dengan pencahayaan bagus\n"
        f"- Hindari foto yang terlalu gelap atau blur\n"
        f"- Foto wajah close-up biasanya memberikan hasil terbaik!"
    )
    
    await query.edit_message_text(
        tutorial,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

async def top_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback untuk menampilkan top users"""
    query = update.callback_query
    db = utils.load_database()
    
    # Buat keyboard untuk tombol navigasi
    keyboard = [
        [
            InlineKeyboardButton("👥 Top Users", callback_data="top_users"),
            InlineKeyboardButton("🔗 Top Referrers", callback_data="top_referrers")
        ],
        [InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    top_users_text = "*🏆 TOP 10 USERS 🏆*\n\n"
    
    if not db["stats"]["top_users"]:
        top_users_text += "_Belum ada data pengguna._\n"
    else:
        for i, user_stat in enumerate(db["stats"]["top_users"], 1):
            name = user_stat["first_name"] or user_stat["username"] or f"User {user_stat['user_id']}"
            top_users_text += f"{i}. {name}: `{user_stat['total_generations']}` generate\n"
    
    await query.edit_message_text(
        top_users_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def top_referrers_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback untuk menampilkan top referrers"""
    query = update.callback_query
    db = utils.load_database()
    
    # Buat keyboard untuk tombol navigasi
    keyboard = [
        [
            InlineKeyboardButton("👥 Top Users", callback_data="top_users"),
            InlineKeyboardButton("🔗 Top Referrers", callback_data="top_referrers")
        ],
        [InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    top_referrers_text = "*🔗 TOP 10 REFERRERS 🔗*\n\n"
    
    if "top_referrers" not in db["stats"] or not db["stats"]["top_referrers"]:
        top_referrers_text += "_Belum ada data referral._\n"
    else:
        for i, user_stat in enumerate(db["stats"]["top_referrers"], 1):
            name = user_stat["first_name"] or user_stat["username"] or f"User {user_stat['user_id']}"
            top_referrers_text += f"{i}. {name}: `{user_stat['total_referrals']}` referrals\n"
    
    await query.edit_message_text(
        top_referrers_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback untuk menampilkan statistik"""
    query = update.callback_query
    user = query.from_user
    db = utils.load_database()
    user_data = utils.get_user_data(user.id)
    
    total_users = db["stats"]["total_users"]
    total_generations = db["stats"]["total_generations"]
    total_referrals = db["referrals"]["total_conversions"]
    
    stats_text = (
        f"*📈 STATISTIK GHIBLIBOT 📈*\n\n"
        f"👥 *Total users:* `{total_users}`\n"
        f"🖼 *Total generate:* `{total_generations}`\n"
        f"🔗 *Total referrals:* `{total_referrals}`\n"
        f"🔄 *Limit tersisa:* `{user_data['remaining_limit']}/{CONFIG['features']['daily_limit']}`\n"
        f"🕒 *Terakhir generate:* {utils.format_time_ago(user_data.get('last_generation_time', None))}\n\n"
        
        f"*⚡️ INFO BOT ⚡️*\n"
        f"🚀 Status: `Online`\n"
        f"💻 Server: `{'GPU' if torch.cuda.is_available() else 'CPU'} Optimized`\n"
        f"🧠 Model: `{CONFIG['model']['model_id'].split('/')[-1]}`\n"
        f"📊 Version: `{CONFIG['bot']['version']}`\n"
        f"📅 Last Update: `{CONFIG['bot']['release_date']}`\n\n"
        
        f"*📊 USER STATS 📊*\n"
        f"🖼 *Total generate:* `{user_data['total_generations']}`\n"
        f"🔗 *Referrals:* `{len(user_data['referral']['referred_users'])}`\n"
        f"👑 *Role:* `{utils.get_user_role(user.id)}`\n\n"
        
        f"_Bot ini menggunakan model Stable Diffusion yang dioptimalkan untuk style Studio Ghibli._"
    )
    
    keyboard = [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        stats_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def about_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback untuk menampilkan info about bot"""
    query = update.callback_query
    
    keyboard = [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    channel_links = utils.get_required_channels_text()
    
    about_text = (
        f"*🤖 TENTANG GHIBLIBOT 🤖*\n\n"
        f"{CONFIG['bot']['name']} adalah bot keren yang mengubah foto biasa menjadi karya seni bergaya Studio Ghibli. Bot ini menggunakan teknologi AI canggih untuk menghasilkan transformasi foto yang memukau.\n\n"
        
        f"*🌟 FITUR 🌟*\n"
        f"• Transformasi foto ke style Ghibli\n"
        f"• Proses super cepat dengan GPU\n"
        f"• Interface yang user-friendly\n"
        f"• Sistem referral untuk bonus limit\n"
        f"• Statistik penggunaan\n"
        f"• Sistem limit harian\n\n"
        
        f"*👨‍💻 DEVELOPER 👨‍💻*\n"
        f"Bot ini dibuat oleh @{CONFIG['bot']['username']}\n\n"
        
        f"*📢 CHANNEL & GRUP 📢*\n"
        f"{channel_links}\n\n"
        
        f"*📝 VERSI BOT 📝*\n"
        f"Version: `{CONFIG['bot']['version']}`\n"
        f"Last Update: `{CONFIG['bot']['release_date']}`\n\n"
        
        f"_Thanks for using {CONFIG['bot']['name']}!_ ❤️"
    )
    
    await query.edit_message_text(
        about_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback untuk memeriksa subscription"""
    query = update.callback_query
    user = query.from_user
    
    # Cek subscription lagi
    subscribed, not_joined_channels = await check_user_subscriptions(context.bot, user.id)
    
    if not subscribed:
        channel_links = utils.get_required_channels_text()
        
        keyboard = [
            [InlineKeyboardButton("✅ Sudah Join Semua", callback_data="check_subscription")],
            [InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"*❌ Lo masih belum join semua channel!*\n\n"
            f"Join dulu channel berikut:\n"
            f"{channel_links}\n\n"
            f"Klik tombol di bawah setelah join semua channel.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
    else:
        keyboard = [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"*✅ Keren! Lo udah join semua channel!*\n\n"
            f"Sekarang lo bisa pakai bot ini dengan mengirim foto dengan caption `/ghibli` di grup yang diizinkan.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

async def check_limit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback untuk memeriksa limit"""
    query = update.callback_query
    user = query.from_user
    user_data = utils.get_user_data(user.id)
    
    keyboard = [
        [InlineKeyboardButton("🔗 Dapatkan Link Referral", callback_data="referral")],
        [InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    limit_text = (
        f"*📊 INFO LIMIT KAMU 📊*\n\n"
        f"👤 *User:* {user.first_name}\n"
        f"🎯 *Limit tersisa:* `{user_data['remaining_limit']}/{CONFIG['features']['daily_limit']}` per hari\n"
        f"🕒 *Reset limit:* Setiap jam 00:00 WIB\n"
        f"🔄 *Terakhir generate:* {utils.format_time_ago(user_data.get('last_generation_time', None))}\n\n"
        f"_Tips: Undang temen dengan link referral untuk nambah limit!_ 🔗"
    )
    
    await query.edit_message_text(
        limit_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def referral_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback untuk menampilkan referral link"""
    query = update.callback_query
    user = query.from_user
    
    # Generate or get referral link
    referral_link = utils.create_referral_link(user.id)
    user_data = utils.get_user_data(user.id)
    
    keyboard = [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    referral_text = (
        f"*🔗 LINK REFERRAL KAMU 🔗*\n\n"
        f"{CONFIG['messages']['referral_info'].format(referral_link=referral_link)}\n\n"
        f"*Statistik Referral Kamu:*\n"
        f"👥 *Orang yang diundang:* `{len(user_data['referral']['referred_users'])}`\n"
        f"🎁 *Total bonus:* `{user_data['referral']['total_referrals'] * CONFIG['referral']['referrer_bonus']}`\n"
        f"🔥 *Bonus spesial:* `{'Sudah diklaim' if user_data['referral']['bonus_claimed'] else f'Belum (butuh {CONFIG['referral']['min_uses_for_extra_bonus']} undangan)'}`\n\n"
        f"_Share link ini ke teman-temanmu untuk dapatkan bonus limit!_ 🚀"
    )
    
    await query.edit_message_text(
        referral_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

# ============== ERROR HANDLER ==============

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors dalam bot"""
    logger.error(f"Exception while handling an update: {context.error}")
    
    # Log error secara detail
    if update:
        logger.error(f"Update: {update}")
        if update.effective_message:
            text = f"❌ *Error!* Terjadi kesalahan saat memproses permintaan Anda. Coba lagi nanti."
            await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ============== MAIN FUNCTION ==============

def main() -> None:
    """Fungsi utama untuk menjalankan bot"""
    # Pastikan semua direktori yang dibutuhkan sudah ada
    utils.ensure_directories()
    
    # Bersihkan file temporary lama
    utils.clean_temp_files()
    
    # Buat aplikasi bot dengan token dari konfigurasi
    application = Application.builder().token(CONFIG["bot"]["token"]).build()
    
    # Tambahkan handlers untuk commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ghibli", ghibli_command))
    application.add_handler(CommandHandler("limit", limit_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("referral", referral_command))
    
    # Tambahkan handlers untuk command admin
    application.add_handler(CommandHandler("addlimit", add_limit_command))
    application.add_handler(CommandHandler("reducelimit", reduce_limit_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("userstats", user_stats_command))
    
    # Tambahkan handler untuk callback query
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Tambahkan error handler
    application.add_error_handler(error_handler)
    
    # Start the Bot
    application.run_polling()
    logger.info(f"{CONFIG['bot']['name']} started!")

if __name__ == "__main__":
    main()
