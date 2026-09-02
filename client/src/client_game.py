# client_game.py
import pygame
import pygame_gui
import asyncio
import json
import websockets
import sys

# Импортируем твои движковые зависимости, картинки и константы из общего модуля
from assets.common import *

os.system("cls")

def resource_path(relative_path):
    if getattr(sys, '_MEIPASS', False):
        base_path = sys._MEIPASS #type: ignore
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def load_image(path, size=TILESIZE):
    try:
        full_path = resource_path(path)
        
        #print(f"[DEBUG] Ищу картинку тут: {full_path}")
        
        image = pygame.image.load(full_path).convert_alpha()
        return pygame.transform.scale(image, (size, size))
    
    except Exception:
        surf = pygame.Surface((size, size))
        surf.fill((200, 0, 200))
        return surf
    
    
class ChessGameSession:
    def __init__(self, window_surface, ui_manager, username: str, stats: dict, game_id: str, color: str):
        self.screen = window_surface
        self.username = username
        self.rating = stats.get("rating", 1000)
        self.game_id = game_id
        self.color = color  # Твой цвет фигуры (белые/черные)
        
        # Полное состояние игры из твоего старого GameClient
        self.playing = False
        self.current_turn = "white"
        self.board = None
        self.status = ""
        self.selected_cell = None
        self.enemy_name = None
        self.enemy_rating = None
        self.websocket = None
        
        # Подключаем менеджер интерфейса с твоим единым theme.json
        self.manager = ui_manager
        
        # Точные координаты доски из твоего старого кода: (WIDTH // 4, HEIGHT // 2 - 320)
        # При 1200x900 это (300, 130)
        board_size = TILESIZE * 8
        self.board_left = WIDTH // 4
        self.board_top = HEIGHT // 2 - board_size//2
        self.board_rect = pygame.Rect(self.board_left, self.board_top, TILESIZE * 8, TILESIZE * 8)
        
        # Инициализируем элементы GUI и генерируем чистую стартовую поверхность доски
        self.setup_ui()
        self.update_board_surface()
        
        self.figures_images = {}
        self.ui_images = {}
        self.load_game_assets()

    def load_game_assets(self):
        """Загружает картинки в память один раз при старте игры"""
        try:
            for key, path in FIGURES_PATHS.items():

                self.figures_images[key] = load_image(path)
                
            print("--- [ASSETS] Все спрайты фигур успешно загружены в память ---")
            
            for key, path in UI_PATHS.items():
                
                self.ui_images[key] = load_image(path)

            print("--- [ASSETS] Все спрайты интерфейса успешно загружены в память ---")
            
        except pygame.error as e:
            print(f"ОШИБКА ЗАГРУЗКИ КАРТИНКИ: Проверь, лежат ли файлы по пути Sprites")
            print(e)
    
    def setup_ui(self):
        """Переводит твои старые координаты центров текста в аккуратные UILabel"""
        # Твои данные (Старый my_name_center = 120, 200 и my_rating_center = 120, 250)
        self.my_name_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(20, 180, 200, 40), text=self.username, manager=self.manager
        )
        self.my_rating_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(20, 220, 200, 40), text=f"Rating: {self.rating}", manager=self.manager
        )
        
        # Разделитель (vs_text_center = 120, HEIGHT // 2)
        pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(20, 430, 200, 40), text="VS", manager=self.manager
        )
        
        # Данные врага (enemy_name_center = 120, 600 и enemy_rating_center = 120, 650)
        self.enemy_name_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(20, 580, 200, 40), text="Waiting...", manager=self.manager
        )
        self.enemy_rating_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(20, 620, 200, 40), text="Rating: ???", manager=self.manager
        )
        
        # Центральный статус-лейбл для вывода ошибок и результатов матча
        self.status_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(300, 430, 640, 50), text="", manager=self.manager
        )
        
        # Твоя кнопка выхода/сдачи "<-" (Button(20, 20, 40, 40))
        self.exit_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(20, 20, 50, 40), text="<-", manager=self.manager
        )

    def update_ui_text(self):
        """Синхронизирует текстовые переменные класса с элементами GUI на экране"""
        if self.enemy_name:
            self.enemy_name_label.set_text(self.enemy_name)
            self.enemy_rating_label.set_text(f"Rating: {self.enemy_rating}")
        
        self.my_rating_label.set_text(f"Rating: {self.rating}")
        
        # Логика авто-статуса ожидания из твоего старого кода
        if not self.playing:
            self.status = "Ожидание второго игрока..."
        elif not any(word in self.status for word in ["Шах", "Противник", "Пат", "Время"]):
            self.status = ""
            
        self.status_label.set_text(self.status)

    def update_board_surface(self):
        """Отрисовка доски в self.board_surface. Вызывается строго при обновлении от сервера или клике"""
        self.board_surface = pygame.Surface((TILESIZE * 8, TILESIZE * 8))
        
        # 1. Рендерим клетки доски
        for y in range(8):
            for x in range(8):
                display_x, display_y = (7 - x, 7 - y) if self.color == "black" else (x, y)
                cell_color = (180, 135, 102) if (x + y) % 2 == 0 else (240, 217, 183)
                pygame.draw.rect(self.board_surface, cell_color, (display_x * TILESIZE, display_y * TILESIZE, TILESIZE, TILESIZE))
                
                # Подсветка выбранной клетки
                if self.selected_cell and self.selected_cell == (y, x):
                    pygame.draw.rect(self.board_surface, (0, 255, 0), (display_x * TILESIZE, display_y * TILESIZE, TILESIZE, TILESIZE), 4)

        # 2. Рендерим фигуры из пришедшей матрицы
        if self.board:              
            for y, row in enumerate(self.board):
                for x, figure in enumerate(row):
                    if figure:
                        display_x, display_y = (7 - x, 7 - y) if self.color == "black" else (x, y)
                        texture = self.figures_images.get(f'{figure.color}_{figure.type}')
                        if texture:
                            self.board_surface.blit(texture, (display_x * TILESIZE, display_y * TILESIZE))
                    
            # 3. Накладываем слои возможных ходов, если клетка выбрана
            if self.selected_cell:  
                possible_positions = ChessEngine.get_legal_moves(self.board, self.selected_cell)
                for pos in possible_positions:
                    py, px = pos
                    display_y, display_x = (7 - py, 7 - px) if self.color == "black" else (py, px)
                    
                    if self.board[py][px]:
                        texture = self.ui_images.get("attack_on_figure")

                    else:
                        texture = self.ui_images.get("possible_move")
                    
                    if texture:
                        self.board_surface.blit(texture, (display_x * TILESIZE, display_y * TILESIZE))

    async def listen_server(self):
        """Твой оригинальный асинхронный цикл прослушивания WebSocket эндпоинтов сервера"""
        uri = f"{ws_proto}://{server_adress}/ws/{self.game_id}/{self.color}/{self.username}"
        
        try:
            async with websockets.connect(uri, ssl=ssl_context) as ws:
                self.websocket = ws
                self.update_ui_text()
                
                async for message in self.websocket:
                    data = json.loads(message)
                    action = data.get("action")
                    
                    if action == "board_broadcast":
                        self.current_turn = data.get("current_turn", "white")
                        self.board = snapshot_to_real_board(data["data"])
                        # Мгновенно перерисовываем внутреннюю поверхность доски через self
                        self.update_board_surface()
                        
                    elif action == "Error":
                        print(data["data"])
                        
                    elif action == "game_status":
                        if data["data"] == "playing":
                            self.playing = True
                            self.status = ""
                            
                    elif action == "enemy_stats":
                        enemy_data = data["data"]
                        self.enemy_name = enemy_data["name"]
                        self.enemy_rating = enemy_data["rating"]
                        
                    elif action == "game_over":
                        end_data = data["data"]
                        self.rating = end_data["new_stats"]["rating"]
                        reason = end_data["reason"]
                        winner = end_data["winner"]
                        
                        if reason == "checkmate":
                            self.status = f"Шах и Мат! Победитель: {winner.upper()}"
                        elif reason == "stalemate":
                            self.status = "Пат!"
                        elif reason == "player_left":
                            self.status = "Противник вышел из матча." if winner == self.color else "Вы покинули игру."
                        elif reason == "Time's up":
                            self.status = "Время вышло! Авто-поражение." if winner != self.color else "Время вышло! Противник проиграл."
                        
                        self.update_ui_text()
                        await asyncio.sleep(2)
                        break  # Выходим из цикла при конце игры
                        
                    self.update_ui_text()
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f"Ошибка соединения: {e}")
            self.status = "Связь с сервером потеряна."
            self.update_ui_text()

    def handle_board_click(self, mouse_pos):
        """Твоя математика пересчета кликов мыши в индексы матрицы 8х8"""
        if not self.playing or not self.board_rect.collidepoint(mouse_pos):
            return
        if self.color != self.current_turn:
            return
            
        relative_x = mouse_pos[0] - self.board_left
        relative_y = mouse_pos[1] - self.board_top
        
        click_x = relative_x // TILESIZE
        click_y = relative_y // TILESIZE
        
        grid_x, grid_y = (7 - click_x, 7 - click_y) if self.color == "black" else (click_x, click_y)

        if self.selected_cell is None:
            target_figure = self.board[grid_y][grid_x] if self.board else None
            if target_figure and target_figure.color == self.color:
                self.selected_cell = (grid_y, grid_x)
                self.update_board_surface()
        else:
            start_pos = self.selected_cell
            end_pos = (grid_y, grid_x)
            
            if start_pos != end_pos:
                # Отправляем ход на сервер прямо из класса
                asyncio.create_task(self.websocket.send(json.dumps({ #type: ignore
                    "type": "make_move",
                    "start_pos": start_pos,
                    "end_pos": end_pos
                })))
                
            self.selected_cell = None
            self.update_board_surface()


async def show_game_screen(window_surface: pygame.Surface, username: str, stats: dict, game_id: str, color: str) -> dict:
    """Внешняя функция-обертка для главного менеджера (main.py)"""
    
    clock = pygame.time.Clock()
    
    # Создаем сессию игры (по умолчанию закладываем белых, сервер перепишет если что)
    session = ChessGameSession(window_surface, pygame_gui.UIManager((WIDTH, HEIGHT), "assets/theme.json"), username, stats, game_id, color=color)
    
    # Запускаем фоновое чтение WebSocket, привязанное к объекту session
    listener_task = asyncio.create_task(session.listen_server())
    
    running = True
    while running:
        time_delta = clock.tick(60) / 1000.0
        mouse_pos = pygame.mouse.get_pos()
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                
            session.manager.process_events(event)
            
            # Обработка кликов по шахматной доске
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                session.handle_board_click(mouse_pos)
                
            # Обработка клика по GUI кнопке выхода/сдачи
            if event.type == pygame_gui.UI_BUTTON_PRESSED:
                if event.ui_element == session.exit_btn:
                    if session.websocket:
                        await session.websocket.send(json.dumps({"type": "give_up", "name": username}))
                    running = False
                    
        session.manager.update(time_delta)
        
        # --- ОТРИСОВКА КАДРА ---
        window_surface.fill((20, 20, 20))  # Твой оригинальный DARK фон экрана
        
        # Переносим готовую поверхность доски из объекта на экран
        window_surface.blit(session.board_surface, session.board_rect)
        
        # Отрисовываем GUI лейблы поверх всего
        session.manager.draw_ui(window_surface)
        
        pygame.display.flip()
        await asyncio.sleep(1 / 60)
        
        # Если сервер разорвал соединение и мы не играем — выходим в меню
        if listener_task.done() and not session.playing:
            running = False

    # Безопасно глушим фоновую задачу сети при выходе
    if not listener_task.done():
        listener_task.cancel()
        
    # Забираем из сессии обновленный рейтинг и возвращаем его в main.py
    stats["rating"] = session.rating
    return stats

