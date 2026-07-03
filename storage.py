msg_cache = {}
chat_history = {}
owner_cache = {}

# Список пользователей, которым АДМИН вручную одобрил доступ
ALLOWED_USERS = set() 

# Глобальная статистика
stats = {
    "total_cached": 0,
    "total_edited": 0,
    "total_deleted": 0
}

LOGS_ACTIVE = True
