import bcrypt


def hash_password(password: str) -> str:
    """Трансформирует сырой пароль в хэш-строку для хранения в БД"""
    # bcrypt работает с байтами, поэтому кодируем строку
    password_bytes = password.encode('utf-8')
    # Генерируем соль
    salt = bcrypt.gensalt()
    # Хэшируем и декодируем обратно в строку для удобного сохранения в текстовое поле БД
    hashed_password = bcrypt.hashpw(password_bytes, salt)
    return hashed_password.decode('utf-8')




def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Сравнивает сырой пароль с хэшем из БД. Возвращает True, если совпадают"""
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    # Метод checkpw защищен от атак по времени (timing attacks)
    return bcrypt.checkpw(password_bytes, hashed_bytes)


