import copy, os, ssl, sys, random

TILESIZE = 80
BWR = 25 #BaseWinReward
RFS = 5 #RewardForStreak
bg_color = (250, 250, 255)

if getattr(sys, 'frozen', False):
    # Если запущен скомпилированный .exe
    BASE_EXE_DIR = os.path.dirname(sys.executable)
else:
    # Если запущен обычный .py скрипт
    BASE_EXE_DIR = os.path.dirname(os.path.abspath(__file__))


ASSETS_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITES_DIR = os.path.join(ASSETS_DIR, "Sprites")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
FONT_PATH = os.path.join(FONTS_DIR, "Impact.ttf")
THEME_PATH = os.path.join(ASSETS_DIR, "theme.json")
server_txt_path = os.path.join(BASE_EXE_DIR, "server_adress.txt")

server_adress = "127.0.0.1:8000"

DEFAULT_STATS = {
    "rating": 300,
    "wins": 0,
    "losses": 0,
    "win_streak": 0,
    "games_played": 0,
    "level": 0,
    "experience": 0
}

def get_experience(winner : bool, PvP: bool, **stats):
    result = 0
    if winner: result += 300
    else: result += 100
    
    result += random.randint(-15, 15)
    
    if PvP: result *= random.uniform(1.2, 1.5)

    result -= stats["win_streak"] * RFS**2
    
    if PvP: result += stats["rating"] // 10
    else: result -= stats["rating"] // 10
    
    return result
    
    
def calculate_level_experience(level, experience):
    lvl, exp = level, experience
    
    # Защита от отрицательного опыта (опыт не может быть меньше 0)
    if exp < 0:
        exp = 0
        
    while True:
        lvl_str = str(lvl)
        
        # ЗАЩИТА ОТ КРАША: Если уровень стал выше, чем есть в LEVELS,
        # значит игрок достиг максимального лвла. Тормозим цикл.
        if lvl_str not in LEVELS:
            break
            
        if exp >= LEVELS[lvl_str]:
            exp -= LEVELS[lvl_str]
            lvl += 1
        else:
            # Опыта больше не хватает для апгрейда — выходим
            break
        
    return lvl, exp



# ПРОВЕРКА: Если этот файл импортирован сервером, мы вообще НЕ ищем текстовик
# Мы проверяем, есть ли слово "server" в названии главного запускаемого файла
is_server = "server" in sys.argv[0].lower()

if not is_server:
    # Этот блок выполнится ТОЛЬКО на клиенте
    if getattr(sys, 'frozen', False):
        BASE_EXE_DIR = os.path.dirname(sys.executable)
    else:
        # Для обычного .py клиента выходим на уровень выше папки assets
        BASE_EXE_DIR = os.path.dirname(ASSETS_DIR)
        
    server_txt_path = os.path.join(BASE_EXE_DIR, "server_adress.txt")
    
    if os.path.exists(server_txt_path):
        try:
            with open(server_txt_path, encoding="utf-8") as f:
                text = f.read().strip()
                if text:
                    server_adress = text
        except Exception:
            pass


ssl_context = None if server_adress  == "127.0.0.1:8000" else ssl._create_unverified_context()
http_proto = "http" if server_adress == "127.0.0.1:8000" else "https"
ws_proto = "ws" if server_adress == "127.0.0.1:8000" else "wss"
SERVER_URL = f"{http_proto}://{server_adress}"

random.seed(1030)
LEVELS = {}
for i in range(1,101):
    LEVELS[str(i)] = (i * 250) + random.randrange(25, 125, 5)


WIDTH, HEIGHT = 1200, 900

class Figure:
    def __init__(self, type: str, color:str, id: str):
        self.type = type
        self.color = color
        self.id = id
        self.has_moved: bool = False
    
    def to_dict(self):
        """Для отправки по сети"""
        return {
            "id": self.id,
            "color": self.color,
            "type": self.type,
            "has_moved": self.has_moved
        }


FIGURES_PATHS = {}
for color in ['white', 'black']:
    for piece in ['pawn', 'rook', 'knight', 'bishop', 'queen', 'king']: # Пешка, Ладья, Конь, Слон, Ферзь, Король
        key = f"{color}_{piece}"
        FIGURES_PATHS[key] = os.path.join(SPRITES_DIR, f"{key}.png")
        
        
UI_PATHS = {}
try:
    UI_PATHS["attack_on_figure"] = os.path.join(SPRITES_DIR, "attack_on_figure.png")
    UI_PATHS["possible_move"] = os.path.join(SPRITES_DIR, "possible_move.png")
    
except Exception as e:
    print(e)


class ChessEngine:
    def __init__(self):
        self.board: list[list[Figure | None]] = self.create_board()
        self.current_turn: str = "white"
    
    def create_board(self) -> list[list[Figure | None]]:
        board: list[list[Figure | None]] = [[None for _ in range(8)] for _ in range(8)]
        next_id = 0
        
        # Пани
        for i in range(8):
            board[1][i] = Figure("pawn", "black", str(next_id))
            board[6][i] = Figure("pawn", "white", str(next_id))
            next_id += 1
            
        # Ладьи, Кони, Слоны
        for i, f_type in [(0, "rook"), (7, "rook"), (1, "knight"), (6, "knight"), (2, "bishop"), (5, "bishop")]:
            board[0][i] = Figure(f_type, "black", str(next_id))
            board[7][i] = Figure(f_type, "white", str(next_id))
            next_id += 1
            
        # Ферзи и Короли
        board[0][3] = Figure("queen", "black", str(next_id))
        board[7][3] = Figure("queen", "white", str(next_id))
        next_id += 1
        
        board[0][4] = Figure("king", "black", str(next_id))
        board[7][4] = Figure("king", "white", str(next_id))
        
        return board
    
    def get_board_snapshot(self) -> list:
        """Флаттен доски в 1D массив для отправки по сети."""
        snapshot = []
        for row in self.board:
            for figure in row:
                if figure:
                    snapshot.append(figure.to_dict())
                else:
                    snapshot.append(None)
        return snapshot  

    def check_game_over(self) -> str | None:
        color = self.current_turn
        for y in range(8):
            for x in range(8):
                fig = self.board[y][x]
                if fig and fig.color == color:
                    if self.get_legal_moves(self.board, (y, x)):
                        return None

        if ChessEngine.king_is_in_check(self.board, color):
            return "checkmate"
        return "stalemate"

    def check_move(self, select_pos: tuple[int, int], wish_pos: tuple[int, int]) -> bool:
        y, x = select_pos
        target_y, target_x = wish_pos
        
        select_pos_tuple = (y, x)
        wish_pos_tuple = (target_y, target_x)
        
        # Теперь Pylance на 100% уверен, что это tuple[int, int]
        if wish_pos_tuple in ChessEngine.get_legal_moves(self.board, select_pos_tuple):
            moving_figure = self.board[y][x]
            
            # Делаем ход
            self.board[target_y][target_x] = moving_figure
            self.board[y][x] = None
            
            if moving_figure:
                moving_figure.has_moved = True
            return True
        return False

    # --- СТАТИЧЕСКИЕ МЕТОДЫ ЛОГИКИ (Доступны и клиенту, и серверу) ---

    @staticmethod
    def king_is_in_check(board: list[list[Figure | None]], color: str) -> bool:
        king_pos = None
        enemy_color = "white" if color == "black" else "black"
        
        for y in range(8):
            for x in range(8):
                fig = board[y][x]
                if fig and fig.type == "king" and fig.color == color:
                    king_pos = (y, x)
                    break
            if king_pos: 
                break
                
        if not king_pos: 
            return False
                
        for y in range(8):
            for x in range(8):
                fig = board[y][x]
                if fig and fig.color == enemy_color:
                    if king_pos in ChessEngine.get_pseudo_moves(board, (y, x)):
                        return True
        return False

    @staticmethod
    def get_legal_moves(board: list[list[Figure | None]], figure_pos: tuple[int, int]) -> list[tuple[int, int]]:
        y, x = figure_pos
        figure = board[y][x]
        if not figure: 
            return []
        
        pseudo_moves = ChessEngine.get_pseudo_moves(board, figure_pos)
        legal_moves = []
        
        for move in pseudo_moves:
            target_y, target_x = move
            temp_board = copy.deepcopy(board)
            
            temp_board[target_y][target_x] = temp_board[y][x]
            temp_board[y][x] = None
            
            if not ChessEngine.king_is_in_check(temp_board, figure.color):
                legal_moves.append(move)
                
        return legal_moves

    @staticmethod
    def get_pseudo_moves(board: list[list[Figure | None]], figure_pos: tuple[int, int]) -> list[tuple[int, int]]:
        y, x = figure_pos
        figure = board[y][x]
        pseudo_moves = []
        
        if not figure: 
            return pseudo_moves
        
        if figure.type == "pawn":
            direct = -1 if figure.color == "white" else 1
            startpos = 6 if figure.color == "white" else 1
            
            for i in range(1, 3):
                if i == 2 and y != startpos: 
                    continue
                new_y = y + (i * direct)
                if 0 <= new_y < 8:
                    if not board[new_y][x]:
                        pseudo_moves.append((new_y, x))
                    else:
                        break
            
            for dx in [-1, 1]:
                ny, nx = y + direct, x + dx
                if 0 <= ny < 8 and 0 <= nx < 8:
                    target = board[ny][nx]
                    if target and target.color != figure.color:
                        pseudo_moves.append((ny, nx))
                    
        elif figure.type == "rook":
            return ChessEngine.get_sliding_moves(board, y, x, [(-1,0), (1,0), (0,-1), (0,1)], figure.color)
        elif figure.type == "bishop":
            return ChessEngine.get_sliding_moves(board, y, x, [(-1,-1), (-1,1), (1,-1), (1,1)], figure.color)
        elif figure.type == "queen":
            return ChessEngine.get_sliding_moves(board, y, x, [(-1,-1), (-1,1), (1,-1), (1,1), (-1,0), (1,0), (0,-1), (0,1)], figure.color)
        elif figure.type == "knight":
            directions = [(-1,-2), (1,-2), (-2, -1), (-2, 1), (-1, 2), (1, 2), (2, -1), (2, 1)]
            for dy, dx in directions:
                ny, nx = y + dy, x + dx
                if 0 <= ny < 8 and 0 <= nx < 8:
                    pos_fig = board[ny][nx]
                    if not pos_fig or pos_fig.color != figure.color:
                        pseudo_moves.append((ny, nx))
                        
        elif figure.type == "king":
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    if not dy and not dx: 
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < 8 and 0 <= nx < 8:
                        pos_fig = board[ny][nx]
                        if not pos_fig or pos_fig.color != figure.color:
                            pseudo_moves.append((ny, nx))
                            
        return pseudo_moves

    @staticmethod
    def get_sliding_moves(board: list[list[Figure | None]], y: int, x: int, directions: list[tuple[int, int]], color: str) -> list[tuple[int, int]]:
        moves = []
        for dy, dx in directions:
            for i in range(1, 8):
                ny, nx = y + i * dy, x + i * dx
                if not (0 <= ny < 8 and 0 <= nx < 8): 
                    break
                
                target = board[ny][nx]
                if target:
                    if target.color != color:
                        moves.append((ny, nx))
                    break
                moves.append((ny, nx))
        return moves


def snapshot_to_real_board(board_snapshot: list) -> list[list[Figure | None]]:
    """Преобразует одномерный JSON-снимок сети в двумерную структуру доски."""
    real_board = []
    for y in range(8):
        row = []
        for figure in board_snapshot[y*8 : y*8+8]:
            if figure:
                row.append(Figure(figure["type"], figure["color"], figure["id"]))
            else:
                row.append(None)
        real_board.append(row)
    return real_board