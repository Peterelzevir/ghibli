"""
Modul Utilitas dan Pengelolaan Database
---------------------------------------
Berisi fungsi-fungsi untuk mengelola database dan utilitas lainnya
"""

import json
import os
import time
import logging
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Union, Optional, Any

from config import CONFIG

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename=os.path.join(CONFIG["storage"]["logs_folder"], "bot.log") if os.path.exists(CONFIG["storage"]["logs_folder"]) else None
)
logger = logging.getLogger(__name__)

# ============== FILE & FOLDER MANAGEMENT ==============

def ensure_directories() -> None:
    """Memastikan semua direktori yang diperlukan sudah ada"""
    directories = [
        CONFIG["storage"]["temp_folder"],
        CONFIG["storage"]["backup_folder"],
        CONFIG["storage"]["result_folder"],
        CONFIG["storage"]["logs_folder"]
    ]
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")

def clean_temp_files(max_age: int = 24) -> None:
    """Membersihkan file temporary yang lebih tua dari max_age jam"""
    temp_folder = CONFIG["storage"]["temp_folder"]
    if not os.path.exists(temp_folder):
        return
    
    current_time = time.time()
    deleted_count = 0
    
    for filename in os.listdir(temp_folder):
        file_path = os.path.join(temp_folder, filename)
        # Cek jika file (bukan folder) dan lebih tua dari max_age jam
        if os.path.isfile(file_path) and current_time - os.path.getmtime(file_path) > max_age * 3600:
            os.remove(file_path)
            deleted_count += 1
    
    if deleted_count > 0:
        logger.info(f"Cleaned {deleted_count} temporary files older than {max_age} hours")

def backup_database() -> bool:
    """Membuat backup database"""
    db_file = CONFIG["storage"]["db_file"]
    backup_folder = CONFIG["storage"]["backup_folder"]
    
    if not os.path.exists(db_file):
        logger.warning(f"Cannot backup: Database file {db_file} does not exist")
        return False
    
    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_folder, f"backup_{timestamp}.json")
    
    try:
        with open(db_file, 'r') as src, open(backup_file, 'w') as dst:
            dst.write(src.read())
        logger.info(f"Database backup created: {backup_file}")
        return True
    except Exception as e:
        logger.error(f"Backup failed: {str(e)}")
        return False

# ============== DATABASE MANAGEMENT ==============

def get_database_schema() -> Dict:
    """Mendapatkan struktur database default"""
    return {
        "users": {},
        "stats": {
            "total_generations": 0,
            "total_users": 0,
            "total_referrals": 0,
            "top_users": [],
            "top_referrers": []
        },
        "referrals": {
            "active_links": {},
            "total_conversions": 0
        },
        "meta": {
            "version": CONFIG["bot"]["version"],
            "last_backup": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    }

def get_user_schema() -> Dict:
    """Mendapatkan struktur data default untuk user baru"""
    return {
        "user_id": "",
        "username": "",
        "first_name": "",
        "last_name": "",
        "join_date": datetime.now().isoformat(),
        "status": "active",
        "role": "user",
        "remaining_limit": CONFIG["features"]["daily_limit"],
        "total_generations": 0,
        "last_reset_date": datetime.now().strftime("%Y-%m-%d"),
        "last_generation_time": None,
        "referral": {
            "referral_code": "",
            "referred_by": None,
            "referred_users": [],
            "total_referrals": 0,
            "bonus_claimed": False,
            "link_created_at": None
        },
        "preferences": {
            "strength": CONFIG["features"]["default_strength"],
            "notifications": True
        }
    }

def load_database() -> Dict:
    """Memuat database dari file JSON"""
    db_file = CONFIG["storage"]["db_file"]
    
    if os.path.exists(db_file):
        try:
            with open(db_file, 'r') as f:
                db = json.load(f)
            
            # Validasi dan update struktur jika diperlukan
            if "meta" not in db:
                db["meta"] = get_database_schema()["meta"]
            if "referrals" not in db:
                db["referrals"] = get_database_schema()["referrals"]
            
            # Update 'updated_at' metadata
            db["meta"]["updated_at"] = datetime.now().isoformat()
            
            return db
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading database: {str(e)}")
            # Backup corrupt file jika ada
            if os.path.exists(db_file):
                corrupt_backup = f"{db_file}.corrupt.{int(time.time())}"
                os.rename(db_file, corrupt_backup)
                logger.warning(f"Corrupt database backed up to {corrupt_backup}")
    
    # Jika file tidak ada atau terjadi error, buat database baru
    db = get_database_schema()
    save_database(db)
    return db

def save_database(db: Dict) -> bool:
    """Menyimpan database ke file JSON"""
    db_file = CONFIG["storage"]["db_file"]
    temp_file = f"{db_file}.temp"
    
    try:
        # Update metadata
        db["meta"]["updated_at"] = datetime.now().isoformat()
        
        # Tulis ke file temporary dulu
        with open(temp_file, 'w') as f:
            json.dump(db, f, indent=2)
        
        # Ganti file asli dengan atomic operation
        if os.path.exists(db_file):
            os.replace(temp_file, db_file)
        else:
            os.rename(temp_file, db_file)
        
        # Buat backup otomatis jika diperlukan
        if CONFIG["storage"]["auto_backup"]:
            last_backup_str = db["meta"].get("last_backup")
            if not last_backup_str or datetime.now() - datetime.fromisoformat(last_backup_str) > timedelta(hours=CONFIG["storage"]["backup_interval"]):
                if backup_database():
                    db["meta"]["last_backup"] = datetime.now().isoformat()
                    # Simpan lagi dengan metadata backup yang diperbarui
                    with open(db_file, 'w') as f:
                        json.dump(db, f, indent=2)
        
        return True
    except Exception as e:
        logger.error(f"Error saving database: {str(e)}")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return False

# ============== USER MANAGEMENT ==============

def get_user_data(user_id: int) -> Dict:
    """Mendapatkan data user, buat entry baru jika belum ada"""
    db = load_database()
    user_id_str = str(user_id)
    
    if user_id_str not in db["users"]:
        # User baru
        user_data = get_user_schema()
        user_data["user_id"] = user_id_str
        db["users"][user_id_str] = user_data
        db["stats"]["total_users"] += 1
        save_database(db)
    else:
        user_data = db["users"][user_id_str]
        
        # Cek apakah perlu reset limit harian
        today = datetime.now().strftime("%Y-%m-%d")
        if user_data["last_reset_date"] != today:
            # Reset limit berdasarkan role
            if get_user_role(user_id) == "vip":
                user_data["remaining_limit"] = CONFIG["features"]["vip_daily_limit"]
            else:
                user_data["remaining_limit"] = CONFIG["features"]["daily_limit"]
            user_data["last_reset_date"] = today
            db["users"][user_id_str] = user_data
            save_database(db)
    
    return user_data

def update_user_data(user_id: int, update_data: Dict) -> bool:
    """Update data user di database"""
    db = load_database()
    user_id_str = str(user_id)
    
    if user_id_str in db["users"]:
        # Update hanya field yang ada di update_data
        for key, value in update_data.items():
            if key in db["users"][user_id_str]:
                if isinstance(value, dict) and isinstance(db["users"][user_id_str][key], dict):
                    # Nested update untuk dictionary
                    db["users"][user_id_str][key].update(value)
                else:
                    db["users"][user_id_str][key] = value
        
        return save_database(db)
    else:
        logger.warning(f"Attempted to update non-existent user: {user_id}")
        return False

def get_user_role(user_id: int) -> str:
    """Mendapatkan role user (owner, admin, moderator, vip, user)"""
    user_id_int = int(user_id)
    
    # Cek role dari konfigurasi
    for role, data in CONFIG["users"].items():
        if user_id_int in data["user_ids"]:
            return role
    
    # Jika tidak ada di konfigurasi, cek dari database
    db = load_database()
    user_id_str = str(user_id)
    
    if user_id_str in db["users"]:
        return db["users"][user_id_str].get("role", "user")
    
    return "user"  # Default role

def has_permission(user_id: int, permission: str) -> bool:
    """Cek apakah user memiliki permission tertentu"""
    role = get_user_role(user_id)
    
    # Owner memiliki semua permission
    if role == "owner":
        return True
    
    # Cek permission berdasarkan role
    if role in CONFIG["users"]:
        return permission in CONFIG["users"][role]["permissions"] or "all" in CONFIG["users"][role]["permissions"]
    
    return False  # Default tidak memiliki permission

def modify_user_limit(user_id: int, amount: int) -> Tuple[bool, int]:
    """Modify limit user (tambah/kurang), returns (success, new_limit)"""
    user_data = get_user_data(user_id)
    
    # Hitung limit baru (tidak boleh negatif)
    new_limit = max(0, user_data["remaining_limit"] + amount)
    
    # Update database
    success = update_user_data(user_id, {"remaining_limit": new_limit})
    
    return success, new_limit

def update_user_stats(user_id: int, user_data: Dict) -> None:
    """Update statistik user setelah generate gambar"""
    db = load_database()
    
    # Update total generasi global
    db["stats"]["total_generations"] += 1
    
    # Update top users
    user_id_str = str(user_id)
    update_top_list(db, "top_users", user_id_str, user_data, "total_generations")
    
    save_database(db)

def update_top_list(db: Dict, list_name: str, user_id: str, user_data: Dict, sort_key: str, max_entries: int = 10) -> None:
    """Update daftar top users berdasarkan kriteria tertentu"""
    # Cari user di list
    found = False
    for user in db["stats"][list_name]:
        if user["user_id"] == user_id:
            user[sort_key] = user_data[sort_key]
            user["username"] = user_data["username"]
            user["first_name"] = user_data["first_name"]
            found = True
            break
    
    # Jika tidak ditemukan, tambahkan ke list
    if not found:
        db["stats"][list_name].append({
            "user_id": user_id,
            "username": user_data["username"],
            "first_name": user_data["first_name"],
            "last_name": user_data.get("last_name", ""),
            sort_key: user_data[sort_key]
        })
    
    # Urutkan list berdasarkan sort_key (descending)
    db["stats"][list_name] = sorted(
        db["stats"][list_name], 
        key=lambda x: x[sort_key], 
        reverse=True
    )
    
    # Batasi jumlah entries
    db["stats"][list_name] = db["stats"][list_name][:max_entries]

# ============== REFERRAL SYSTEM ==============

def generate_referral_code(user_id: int) -> str:
    """Generate kode referral unik untuk user"""
    # Combine user_id with timestamp and salt for uniqueness
    salt = CONFIG["bot"]["name"] + str(time.time())
    data = f"{user_id}:{salt}"
    
    # Generate a short hash
    hash_obj = hashlib.md5(data.encode())
    hash_digest = hash_obj.digest()
    
    # Convert to base64 and make URL-safe
    code = base64.urlsafe_b64encode(hash_digest).decode('utf-8')
    
    # Take first 8 characters for a shorter code
    return code[:8]

def create_referral_link(user_id: int) -> str:
    """Buat atau dapatkan link referral untuk user"""
    db = load_database()
    user_id_str = str(user_id)
    user_data = get_user_data(user_id)
    
    # Cek apakah user sudah memiliki kode referral
    if not user_data["referral"]["referral_code"]:
        # Generate kode baru
        ref_code = generate_referral_code(user_id)
        
        # Update user data
        user_data["referral"]["referral_code"] = ref_code
        user_data["referral"]["link_created_at"] = datetime.now().isoformat()
        update_user_data(user_id, {"referral": user_data["referral"]})
        
        # Simpan kode ke daftar referral aktif
        db["referrals"]["active_links"][ref_code] = {
            "user_id": user_id_str,
            "created_at": datetime.now().isoformat(),
            "uses": 0
        }
        save_database(db)
    
    # Format link referral
    link_format = CONFIG["referral"]["referral_link_format"]
    return link_format.format(
        bot_username=CONFIG["bot"]["username"],
        user_id=user_id,
        ref_code=user_data["referral"]["referral_code"]
    )

def process_referral(referee_id: int, ref_code: str) -> Tuple[bool, Optional[Dict]]:
    """Proses referral dan berikan bonus, returns (success, referrer_data)"""
    db = load_database()
    
    # Periksa apakah kode referral valid
    if ref_code not in db["referrals"]["active_links"]:
        return False, None
    
    referral_info = db["referrals"]["active_links"][ref_code]
    referrer_id = referral_info["user_id"]
    
    # Periksa apakah referee mencoba menggunakan referral miliknya sendiri
    if str(referee_id) == referrer_id:
        return False, None
    
    # Periksa apakah referee sudah pernah menggunakan referral
    referee_data = get_user_data(referee_id)
    if referee_data["referral"]["referred_by"]:
        return False, None
    
    # Berikan bonus kepada referee
    referee_bonus = CONFIG["referral"]["referee_bonus"]
    modify_user_limit(referee_id, referee_bonus)
    
    # Update data referee
    referee_data["referral"]["referred_by"] = referrer_id
    update_user_data(referee_id, {"referral": referee_data["referral"]})
    
    # Berikan bonus kepada referrer
    referrer_bonus = CONFIG["referral"]["referrer_bonus"]
    referrer_data = get_user_data(int(referrer_id))
    modify_user_limit(int(referrer_id), referrer_bonus)
    
    # Update data referrer
    if str(referee_id) not in referrer_data["referral"]["referred_users"]:
        referrer_data["referral"]["referred_users"].append(str(referee_id))
    referrer_data["referral"]["total_referrals"] += 1
    update_user_data(int(referrer_id), {"referral": referrer_data["referral"]})
    
    # Update statistik referral
    db["referrals"]["active_links"][ref_code]["uses"] += 1
    db["referrals"]["total_conversions"] += 1
    
    # Berikan bonus tambahan jika mencapai threshold
    min_uses = CONFIG["referral"]["min_uses_for_extra_bonus"]
    if not referrer_data["referral"]["bonus_claimed"] and len(referrer_data["referral"]["referred_users"]) >= min_uses:
        extra_bonus = CONFIG["referral"]["extra_bonus"]
        modify_user_limit(int(referrer_id), extra_bonus)
        referrer_data["referral"]["bonus_claimed"] = True
        update_user_data(int(referrer_id), {"referral": referrer_data["referral"]})
    
    # Update top referrers
    update_top_list(db, "top_referrers", referrer_id, referrer_data, "total_referrals")
    
    save_database(db)
    return True, referrer_data

def extract_referral_code(start_parameter: str) -> Optional[str]:
    """Ekstrak kode referral dari parameter start"""
    if start_parameter and start_parameter.startswith("ref_"):
        parts = start_parameter.split("_")
        if len(parts) >= 2:
            return parts[1]
    return None

def get_referrer_name(user_id: int) -> str:
    """Dapatkan nama referrer yang readable"""
    user_data = get_user_data(user_id)
    if user_data["first_name"]:
        return user_data["first_name"]
    elif user_data["username"]:
        return f"@{user_data['username']}"
    else:
        return f"User {user_id}"

# ============== HELPER FUNCTIONS ==============

def format_time_ago(timestamp_str: Optional[str]) -> str:
    """Format waktu 'xxx yang lalu' dari timestamp"""
    if not timestamp_str:
        return "Belum pernah"
    
    try:
        timestamp = datetime.fromisoformat(timestamp_str)
        now = datetime.now()
        delta = now - timestamp
        
        if delta.days > 30:
            months = delta.days // 30
            return f"{months} bulan yang lalu"
        elif delta.days > 0:
            return f"{delta.days} hari yang lalu"
        elif delta.seconds >= 3600:
            return f"{delta.seconds // 3600} jam yang lalu"
        elif delta.seconds >= 60:
            return f"{delta.seconds // 60} menit yang lalu"
        else:
            return f"{delta.seconds} detik yang lalu"
    except (ValueError, TypeError):
        return "Waktu tidak valid"

def is_in_allowed_group(chat_id: int) -> bool:
    """Cek apakah chat berada di grup yang diizinkan"""
    for group in CONFIG["channels"]["allowed_groups"]:
        if chat_id == group["id"]:
            return True
    return False

def get_allowed_groups_text() -> str:
    """Dapatkan teks grup yang diizinkan untuk ditampilkan"""
    groups = CONFIG["channels"]["allowed_groups"]
    group_links = []
    
    for i, group in enumerate(groups, 1):
        name = group["name"]
        # Format link proper tidak tersedia, ini contoh
        link = f"https://t.me/joinchat/{name.replace(' ', '_')}"
        group_links.append(f"{i}. [{name}]({link})")
    
    return "\n".join(group_links)

def get_required_channels_text() -> str:
    """Dapatkan teks channel yang diperlukan untuk ditampilkan"""
    channels = CONFIG["channels"]["required_channels"]
    channel_links = []
    
    for i, channel in enumerate(channels, 1):
        username = channel["username"]
        link = channel["link"]
        description = channel.get("description", "")
        
        if description:
            channel_links.append(f"{i}. [{username}]({link}) - _{description}_")
        else:
            channel_links.append(f"{i}. [{username}]({link})")
    
    return "\n".join(channel_links)

def resize_image(img_path: str, max_size: int = 512) -> str:
    """Mengubah ukuran gambar dan mengembalikan path gambar yang baru"""
    # Implementasi fungsi ini menggunakan PIL/Pillow
    from PIL import Image
    
    try:
        with Image.open(img_path) as img:
            # Hitung rasio aspek untuk mempertahankan proporsi
            width, height = img.size
            aspect_ratio = width / height
            
            if width > height:
                new_width = min(width, max_size)
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = min(height, max_size)
                new_width = int(new_height * aspect_ratio)
            
            # Resize gambar
            resized_img = img.resize((new_width, new_height), Image.LANCZOS)
            
            # Simpan dengan path baru
            filename, ext = os.path.splitext(img_path)
            resized_path = f"{filename}_resized{ext}"
            resized_img.save(resized_path)
            
            return resized_path
    except Exception as e:
        logger.error(f"Error resizing image {img_path}: {str(e)}")
        return img_path  # Return original path if error
