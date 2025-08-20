# auth/ad_auth.py
import ldap
from dotenv import load_dotenv
import os

load_dotenv()

# Настройки AD
AD_SERVER = os.getenv("AD_SERVER")  # например, "ldap://ad.company.com"
AD_DOMAIN = os.getenv("AD_DOMAIN")  # например, "company.com"

def authenticate_user(username: str, password: str) -> tuple[bool, str]:
    """
    Аутентификация через Active Directory с помощью python-ldap.
    Использует формат user@domain.com
    """
    if not AD_SERVER or not AD_DOMAIN:
        return False, "Ошибка конфигурации: проверьте AD_SERVER и AD_DOMAIN в .env"

    username = username.strip()
    password = password.strip()

    if not username or not password:
        return False, "Логин и пароль обязательны"

    try:
        # Инициализация подключения
        conn = ldap.initialize(AD_SERVER)
        conn.protocol_version = ldap.VERSION3
        conn.set_option(ldap.OPT_REFERRALS, 0)  # Важно для Active Directory

        # Формат: user@domain.com
        user_dn = f"{username}@{AD_DOMAIN}"

        # Пробуем подключиться
        conn.simple_bind_s(user_dn, password)

        # Успешно → получим ФИО (опционально)
        try:
            base_dn = ".".join(["DC=" + part for part in AD_DOMAIN.split(".")])
            search_filter = f"(sAMAccountName={username})"
            result = conn.search_s(base_dn, ldap.SCOPE_SUBTREE, search_filter, ['displayName'])

            if result:
                entry = result[0][1]
                full_name = entry.get('displayName', [username])[0].decode('utf-8')
            else:
                full_name = username
        except Exception as e:
            print(f"⚠️ Не удалось получить ФИО: {e}")
            full_name = username

        conn.unbind()
        return True, full_name

    except ldap.INVALID_CREDENTIALS:
        return False, "Неверный логин или пароль"
    except ldap.SERVER_DOWN:
        return False, "Не удалось подключиться к серверу AD"
    except Exception as e:
        print(f"❌ Ошибка AD: {e}")
        return False, f"Ошибка аутентификации: {str(e)}"