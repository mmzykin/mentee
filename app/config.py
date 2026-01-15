"""Bot configuration constants."""
import os
from datetime import timedelta, timezone

# Telegram Bot Token
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Code execution timeout in seconds
EXEC_TIMEOUT = 10

# Admin usernames (without @)
ADMIN_USERNAMES = ["qwerty1492", "redd_dd", "gixal9"]

# Bonus points awarded per task approval
BONUS_POINTS_PER_APPROVAL = 1

# Moscow timezone (UTC+3)
MSK = timezone(timedelta(hours=3))
