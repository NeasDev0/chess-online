import asyncio
import pygame
import pygame_gui
from pygame_gui.core import ObjectID
import httpx
import os
import json

from assets.common import SERVER_URL, WIDTH, HEIGHT, THEME_PATH

config_file = "user_config.json"

def save_config(user, password):
    """
    Сохраняет или перезаписывает конфигурационный файл.
    Если файла нет — создаст. Если есть — перезапишет актуальными данными.
    """
    try:
        data = {
            "username": user, 
            "password": password,
            "remember_me": True
        }
        with open(config_file, "w", encoding="utf-8") as file:
            # Превращаем в строку и физически записываем в файл
            json.dump(data, file, ensure_ascii=False, indent=4) 
    except Exception as e:
        print(f"[DEBUG] Не удалось сохранить конфиг: {e}")
        

async def auto_login_check():
    """
    Проверяет файл конфигурации и пытается зайти.
    Возвращает (username, stats) при успехе, иначе None.
    """
    if not os.path.exists(config_file):
        return None
    
    try:
        with open(config_file, "r", encoding="utf-8") as file:
            cfg = json.load(file)
            
            username = cfg.get("username")
            password = cfg.get("password")
            remember_me = cfg.get("remember_me", False)
            
            # Если пользователь принудительно выключил автологин (нажал "Выйти")
            if not remember_me:
                return None

            if not username or not password:
                return None


            result = await send_auth_request("LOGIN", username, password, remember_me)

            if result["status"] == "success":
                stats = result.get("data", {})
                return username, stats
            
    except Exception as e:
        print(f"[DEBUG] Ошибка автологина: {e}")
        
    return None


async def send_auth_request(mode: str, username: str, password: str, remember_me: bool) -> dict:
    """
    Отправка асинхронного запроса на FastAPI.
    Возвращает словарь с ответом от сервера или ошибкой сети.
    """
    endpoint = "/login" if mode == "LOGIN" else "/register"
    url = f"{SERVER_URL}{endpoint}"
    payload = {"name": username, "password": password}
    
    try:
        async with httpx.AsyncClient(timeout=4.0, verify=False) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                server_json = response.json()
                if server_json.get("success"):
                    if remember_me:
                        save_config(username, password)
                    return {"status": "success", "data": server_json.get("data")}
                return {"status": "fail", "message": server_json.get("data", "Ошибка логики")}
            
            try:
                detail = response.json().get("detail", "Ошибка сервера")
            except Exception:
                detail = f"Ошибка сервера (код {response.status_code})"
            return {"status": "fail", "message": detail}
                
    except httpx.RequestError:
        return {"status": "fail", "message": "Не удалось подключиться к серверу"}


def load_saved_credentials() -> tuple[str, str] | tuple[None, None]:
    """
    Синхронно читает конфиг для автозаполнения полей.
    """
    if not os.path.exists(config_file):
        return None, None
    try:
        with open(config_file, "r", encoding="utf-8") as file:
            cfg = json.load(file)
            return cfg.get("username", ""), cfg.get("password", "")
    except Exception as e:
        print(f"[DEBUG] Не удалось прочитать данные для автозаполнения: {e}")
        return None, None

async def show_auth_screen(window_surface: pygame.Surface, is_logout: bool) -> tuple[str, dict] | tuple[None, None]: #type: ignore
    """
    Показывает экран авторизации с использованием theme.json.
    """
    if not is_logout:
        try:
            auto_data = await auto_login_check()
            if auto_data is not None:
                # Если автологин вернул (username, stats), сразу отдаем их в main.py
                print(f"[DEBUG] Автологин сработал для: {auto_data[0]}")
                return auto_data  
            
        except Exception as e:
            print(f"[DEBUG] Ошибка при попытке автологина: {e}")
            # Если упало с ошибкой, не ломаем игру, а просто идем к ручному вводу
            pass
    
    pygame.display.set_caption("Chess - Авторизация")
    
    saved_user, saved_pass = load_saved_credentials()
    
    
    manager = pygame_gui.UIManager((WIDTH, HEIGHT), "assets/theme.json")
    clock = pygame.time.Clock()

    current_mode = "REGISTER"
    remember_me = False
    
    # --- ГЕОМЕТРИЯ ЭЛЕМЕНТОВ ---
    btn_width = 400
    left_x = WIDTH // 2 - btn_width // 2
    
    # Заголовок: огромный запас 600x80, чтобы влез любой шрифт и регистр
    title_width = 600
    title_rect = pygame.Rect(WIDTH // 2 - title_width // 2, 110, title_width, 80)
    
    # Поля ввода смещены чуть ниже с шагом, чтобы ничего не перекрывалось
    name_label_rect = pygame.Rect(left_x, 225, btn_width, 30)
    name_input_rect = pygame.Rect(left_x, 260, btn_width, 50)
    
    pass_label_rect = pygame.Rect(left_x, 330, btn_width, 30)
    pass_input_rect = pygame.Rect(left_x, 365, btn_width, 50)
    
    # Чекбокс и текст
    checkbox_size = 30
    checkbox_rect = pygame.Rect(left_x, 435, checkbox_size, checkbox_size)
    
    
    # Кнопки авторизации
    error_rect = pygame.Rect(left_x, 495, btn_width, 30)
    submit_btn_rect = pygame.Rect(left_x, 535, btn_width, 50)
    switch_btn_rect = pygame.Rect(left_x, 605, btn_width, 40)
    

    # --- СОЗДАНИЕ UI ---
    
    checkbox = pygame_gui.elements.UICheckBox(
        relative_rect=checkbox_rect,
        text="Запомнить меня",
        manager=manager,
        object_id=ObjectID(class_id='@my_checkbox')
    )

    
    title_label = pygame_gui.elements.UILabel(
        relative_rect=title_rect, 
        text="РЕГИСТРАЦИЯ", 
        manager=manager,
        object_id=ObjectID(class_id='@title_label')
    )

    pygame_gui.elements.UILabel(
        relative_rect=name_label_rect, 
        text="Введите никнейм:", 
        manager=manager,
        object_id=ObjectID(class_id='@input_label')
    )
    
    username_input = pygame_gui.elements.UITextEntryLine(
        relative_rect=name_input_rect, 
        manager=manager
    )
    username_input.set_text_length_limit(15)
    
    pygame_gui.elements.UILabel(
        relative_rect=pass_label_rect, 
        text="Введите пароль:", 
        manager=manager,
        object_id=ObjectID(class_id='@input_label')
    )
    
    password_input = pygame_gui.elements.UITextEntryLine(
        relative_rect=pass_input_rect, 
        manager=manager
    )
    password_input.set_text_hidden(True)

    error_label = pygame_gui.elements.UILabel(
        relative_rect=error_rect, 
        text="", 
        manager=manager,
        object_id=ObjectID(class_id='@error_label')
    )

    submit_button = pygame_gui.elements.UIButton(
        relative_rect=submit_btn_rect, 
        text='Создать аккаунт', 
        manager=manager
    )

    switch_mode_button = pygame_gui.elements.UIButton(
        relative_rect=switch_btn_rect, 
        text="Уже есть аккаунт? Войти", 
        manager=manager,
        object_id=ObjectID(class_id='@switch_button')
    )

    if saved_user:
        username_input.set_text(saved_user)
    if saved_pass:
        password_input.set_text(saved_pass)
    
    # --- ИГРОВОЙ ЦИКЛ ЭКРАНА ---
    running = True
    is_connecting = False

    while running:
        time_delta = clock.tick(60) / 1000.0 
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None, None

            if not is_connecting:
                manager.process_events(event)
                
            if event.type == pygame_gui.UI_CHECK_BOX_CHECKED:
                if event.ui_element == checkbox:
                    remember_me = True
                    print("[DEBUG] Галочка поставлена")
            
            if event.type == pygame_gui.UI_CHECK_BOX_UNCHECKED:
                if event.ui_element == checkbox:
                    remember_me = False
                    print("[DEBUG] Галочка снята")          

            if event.type == pygame_gui.UI_BUTTON_PRESSED and not is_connecting:
                
                # 1. Смена режима
                if event.ui_element == switch_mode_button:
                    error_label.set_text("")
                    if current_mode == "LOGIN":
                        current_mode = "REGISTER"
                        title_label.set_text("Регистрация")
                        submit_button.set_text("Создать аккаунт")
                        switch_mode_button.set_text("Уже есть аккаунт? Войти")
                    else:
                        current_mode = "LOGIN"
                        title_label.set_text("Вход")
                        submit_button.set_text("Войти")
                        switch_mode_button.set_text("Нет аккаунта? Зарегистрироваться")
                    
                    username_input.set_text("")
                    password_input.set_text("")

                # 2. Отправка данных
                elif event.ui_element == submit_button:
                    username = username_input.get_text().strip()
                    password = password_input.get_text().strip()
                    
                    if not username or not password:
                        error_label.set_text("Заполните все поля!")
                        continue
                    
                    is_connecting = True
                    error_label.set_text("Связь с сервером...")
                    
                    manager.update(time_delta)
                    window_surface.fill((255, 228, 225))
                    manager.draw_ui(window_surface)
                    pygame.display.update()
                    
                    result = await send_auth_request(current_mode, username, password, remember_me)
                    is_connecting = False
                    
                    if result["status"] == "success":
                        stats = result.get("data", {})
                        
                        return username, stats
                    else:
                        error_label.set_text(result["message"])

        manager.update(time_delta)
        window_surface.fill((255, 228, 225)) 
        manager.draw_ui(window_surface)
        pygame.display.update()
        await asyncio.sleep(0)