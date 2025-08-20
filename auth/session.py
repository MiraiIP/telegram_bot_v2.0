# auth/session.py
import redis
import uuid
import json
from datetime import timedelta
from dotenv import load_dotenv
import os

load_dotenv()

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

SESSION_EXPIRY_DAYS = int(os.getenv("SESSION_EXPIRY_DAYS", 1))
MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", 3))
LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", 20))


def create_session(user_id, username, full_name):
    session_id = str(uuid.uuid4())
    session_data = {"user_id": user_id, "username": username, "full_name": full_name}
    expiry = timedelta(days=SESSION_EXPIRY_DAYS)
    r.setex(session_id, expiry, json.dumps(session_data))
    r.delete(f"login_attempts:{user_id}")  # сброс
    return session_id


def get_session(session_id):
    data = r.get(session_id)
    return json.loads(data) if data else None


def increment_login_attempts(user_id):
    key = f"login_attempts:{user_id}"
    attempts = r.incr(key)
    if attempts == 1:
        r.expire(key, timedelta(minutes=LOCKOUT_MINUTES))
    return attempts


def is_user_locked(user_id):
    attempts = r.get(f"login_attempts:{user_id}")
    return attempts and int(attempts) >= MAX_LOGIN_ATTEMPTS