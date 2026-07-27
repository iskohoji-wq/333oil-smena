"""
Конфигурация бота.
Все значения читаются из переменных окружения (Railway → Variables).
Ничего не хардкодим здесь, чтобы токен не утёк в GitHub.
"""
import os

BOT_TOKEN = os.environ["BOT_TOKEN"]

# Список Telegram ID владельцев через запятую, например: "8894977385,111222333"
OWNER_IDS = [
    int(x.strip())
    for x in os.environ.get("OWNER_IDS", "").split(",")
    if x.strip()
]

# Порт для HTTP API (Mini App будет обращаться сюда)
API_PORT = int(os.environ.get("PORT", 8080))

# Ссылки на Mini App (GitHub Pages), два разных экрана — оператор и владелец
OPERATOR_WEBAPP_URL = os.environ.get("OPERATOR_WEBAPP_URL", "")
OWNER_WEBAPP_URL = os.environ.get("OWNER_WEBAPP_URL", "")

# Имя владельца станции — для персонального приветствия
OWNER_NAME = os.environ.get("OWNER_NAME", "")

# Ключ Anthropic API для ИИ-блока (вопросы владельца на естественном языке).
# Без него /api/ai/ask будет возвращать понятную ошибку вместо падения.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

DATA_DIR = os.environ.get("DATA_DIR", "data")
