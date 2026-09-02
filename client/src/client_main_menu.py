import asyncio, pygame, pygame_gui, httpx, os
from assets.common import SERVER_URL, bg_color, WIDTH, HEIGHT, FONT_PATH

os.system("cls")


async def request_matchmaking(username: str) -> tuple | None:
    """
    Отправляет запрос на сервер для поиска игры.
    Возвращает game_id, если матч найден, или None, если произошла ошибка.
    """
    
    url = f"{SERVER_URL}/matchmake"
    payload = {"name": username, "time_limit": 600}
    
    try:
        # Увеличиваем таймаут, так как поиск соперника может занять время
        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                # Сервер должен вернуть что-то вроде {"game_id": "match_12345"}
                data = response.json().get("data")
                return data.get("game_id"), data.get("color")
            
    except httpx.RequestError:
        return None
    
    return None


async def show_main_menu(username, stats):
    """Показывает главное меню. Возвращает (menu_action, game_id)."""
    
    pygame.init()
    window_surface = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Chess - Главное меню")
    

    manager = pygame_gui.UIManager((WIDTH, HEIGHT), theme_path="theme.json")
    clock = pygame.time.Clock()
    
    # 2. Регистрируем пути к шрифтам ОДИН раз (чтобы JSON знал, где их взять)
    font_filename = FONT_PATH
    if not os.path.exists(font_filename):
        font_filename = "Impact.ttf" if os.path.exists("Impact.ttf") else "impact.ttf"
        
    manager.add_font_paths(font_name="Impact", regular_path=font_filename)

    # 3. Просто создаем элементы интерфейса. Никаких настроек шрифтов и цветов в коде!
    title_label = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(312, 50, 400, 60), 
        text="ШАХМАТЫ ОНЛАЙН", 
        manager=manager
    )

    stats_text = f"Игрок: {username}  |  Рейтинг: {stats.get('rating', 300)}  |  Серия: {stats.get('win_streak', 0)}"
    stats_label = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(112, 130, 800, 40), 
        text=stats_text, 
        manager=manager
    )

    # Кнопки автоматически станут синими со шрифтом Impact (размер 28), как в JSON!
    multi_btn = pygame_gui.elements.UIButton(relative_rect=pygame.Rect(362, 250, 300, 60), text='Мультиплеер', manager=manager)
    single_btn = pygame_gui.elements.UIButton(relative_rect=pygame.Rect(362, 340, 300, 60), text='Одиночная игра', manager=manager)
    exit_btn = pygame_gui.elements.UIButton(relative_rect=pygame.Rect(362, 430, 300, 60), text='Выйти из игры', manager=manager)
    logout_btn = pygame_gui.elements.UIButton(relative_rect=pygame.Rect(362, 520, 300, 60), text='Выйти из аккаунта', manager=manager)
    status_label = pygame_gui.elements.UILabel(relative_rect=pygame.Rect(312, 520, 400, 40), text="", manager=manager)

    # --- ИГРОВОЙ ЦИКЛ МЕНЮ ---
    running = True
    is_searching = False # Флаг: ищем ли мы сейчас игру

    while running:
        time_delta = clock.tick(60) / 1000.0
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "QUIT", None, None

            # Если идет поиск игры, временно блокируем интерфейс меню
            if not is_searching:
                manager.process_events(event)

            if event.type == pygame_gui.UI_BUTTON_PRESSED and not is_searching:
                if event.ui_element == multi_btn:
                    # Включаем режим поиска
                    is_searching = True
                    status_label.set_text("Поиск соперника... Пожалуйста, подождите")
                    
                    # Форсированно обновляем экран, чтобы надпись "Поиск..." появилась сразу
                    manager.update(time_delta)
                    window_surface.fill(bg_color)
                    manager.draw_ui(window_surface)
                    pygame.display.update()
                    
                    # Уходим в асинхронное ожидание сервера FastAPI
                    response = await request_matchmaking(username)
                    if response:
                         
                        game_id, color = response

                        if game_id:
                            # УРА! Игра нашлась, сервер дал ID. Закрываем меню и отдаем данные в main.py
                            return "MULTIPLAYER", game_id, color
                        
                        else:
                            # Ошибка сети или никто не зашел в игру
                            is_searching = False
                            status_label.set_text("Ошибка: соперник не найден или сервер упал")
                
                elif event.ui_element == single_btn:
                    return "SINGLEPLAYER", None, "white"
                    
                elif event.ui_element == exit_btn:
                    return "QUIT", None, None
                
                elif event.ui_element == logout_btn:
                    return "LOGOUT", None, None

        manager.update(time_delta)
        window_surface.fill(bg_color)
        manager.draw_ui(window_surface)
        pygame.display.update()
        await asyncio.sleep(0)
        
