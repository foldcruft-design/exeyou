import os
from datetime import datetime

def save_deleted_photo(photo_bytes: bytes, user_id: int, full_name: str) -> str:
    """
    Физически сохраняет байты удаленного фото на диск в папку 'deleted_photos'
    """
    if not photo_bytes:
        return None
    
    folder = "deleted_photos"
    os.makedirs(folder, exist_ok=True)
        
    safe_name = "".join([c for c in full_name if c.isalpha() or c.isdigit() or c in ' _-']).strip()
    if not safe_name:
        safe_name = "user"
        
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{folder}/{timestamp}_{user_id}_{safe_name}.jpg"
    
    try:
        with open(filename, "wb") as f:
            f.write(photo_bytes)
        print(f"[MediaSaver] Фото сохранено локально: {filename}")
        return filename
    except Exception as e:
        print(f"[MediaSaver] Ошибка записи фото на диск: {e}")
        return None
