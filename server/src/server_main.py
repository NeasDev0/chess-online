import json, os, uuid, time, asyncio, traceback, logging, aiofiles, random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from contextlib import asynccontextmanager
from assets.common import *
from .server_security import hash_password, verify_password


os.system("cls")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

db = "database.json"
# Блокировка гарантирует атомарность: два игрока не запишут в файл в одну миллисекунду
db_lock = asyncio.Lock()

all_games = {}
waiting_lobbies = {}


async def print_games_count():
	"""
	Алгоритм: Бесконечный цикл, который каждые 10 секунд выводит в консоль текущее количество активных игр.
	Возвращает: Ничего (работает как фоновая задача).
	"""
	while True:
		print(f"Games count: {len(all_games)}")
		await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app):
	"""
	Алгоритм: Управляет жизненным циклом FastAPI. Создает задачу счетчика игр при старте и отменяет ее при завершении работы сервера.
	Возвращает: Управление (yield) приложению FastAPI.
	"""
	task = asyncio.create_task(print_games_count())
	yield
	task.cancel()


app = FastAPI(lifespan=lifespan)


# --- БЕЗОПАСНАЯ АСИНХРОННАЯ БАЗА ДАННЫХ ---

async def load_db() -> dict:
	"""
	Алгоритм: Проверяет наличие файла БД. Если он есть, асинхронно читает его и парсит JSON. В случае ошибки декодирования или отсутствия файла возвращает пустой словарь.
	Возвращает: dict (содержимое базы данных).
	"""
	if not os.path.exists(db):
		return {}
	try:
		async with aiofiles.open(db, "r", encoding="utf-8") as f:
			content = await f.read()
			return json.loads(content) if content else {}
	except json.JSONDecodeError:
		return {}


async def save_db(data: dict):
	"""
	Алгоритм: Проверяет данные на пустоту. Если данные есть, сохраняет их во временный файл, а затем мгновенно (на уровне ОС) заменяет основной файл временным для предотвращения потери данных при сбое.
	Возвращает: Ничего.
	"""
	if not data or len(data) == 0:
		print("ОШИБКА: Попытка сохранить пустую базу! Отмена.")
		return
	
	temp_file = db + ".tmp"
	
	async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
		await f.write(json.dumps(data, ensure_ascii=False, indent=4))
	
	os.replace(temp_file, db)


async def update_player_rating(name: str, is_winner: bool) -> dict:
	"""
	Алгоритм: Блокирует базу, загружает ее, находит игрока. Рассчитывает новый рейтинг, победы/поражения, стрик и опыт в зависимости от исхода игры. Обновляет базу и сохраняет ее.
	Возвращает: dict (обновленные данные игрока вместе с его именем).
	"""
	async with db_lock:
		db_content = await load_db()
		
		player = find_player_in_db(db_content, name)
		
		if is_winner:
			reward = BWR + RFS * player["win_streak"]
			player["rating"] += reward
			player["wins"] += 1
			player["win_streak"] = player["win_streak"] + 1
			player["games_played"] = player["games_played"] + 1
		else:
			player["rating"] = max(0, player["rating"] - 25)
			player["losses"] += 1
			player["win_streak"] = 0
			player["games_played"] = player["games_played"] + 1
		
		player["level"], player["experience"] = calculate_level_experience(
			player["level"], 
			player["experience"] + get_experience(is_winner, True, **player)
		)
		
		await save_db(db_content)
		print(f"--- [END] update_player_rating для {name} сохранен ---")
		return {"name": name, **player}


async def fetch_player_stats(name: str) -> dict:
	"""
	Алгоритм: Безопасно загружает базу, ищет игрока (или берет дефолтные статы), копирует данные и удаляет хэш пароля для безопасной передачи на клиент.
	Возвращает: dict (чистая статистика игрока).
	"""
	async with db_lock:
		db_content = await load_db()
		
	player_data = db_content.get(name, DEFAULT_STATS)
	
	stats = player_data.copy()
	stats.pop("hashed_password", None)
	return {"name": name, **stats}


def find_player_in_db(db_content: dict, name: str) -> dict:
	"""
	Алгоритм: Проверяет наличие ключа (имени) в словаре базы данных. Если нет — создает новую запись на основе шаблона по умолчанию.
	Возвращает: dict (ссылка на словарь с данными конкретного игрока внутри БД).
	"""
	if name not in db_content:
		db_content[name] = DEFAULT_STATS.copy()
	return db_content[name]


def get_normal_dict(action: str, success: bool, data: dict | str | list) -> dict:
	"""
	Алгоритм: Оборачивает переданные параметры в стандартизированный словарь для отправки по сети.
	Возвращает: dict (стандартная структура ответа).
	"""
	return {"action": action, "success": success, "data": data}


# --- УПРАВЛЕНИЕ КОМНАТАМИ ---

class Game:
	def __init__(self, game_id: str, timer: int):
		self.game_id = game_id
		self.engine = ChessEngine()
		self.players = {}
		self.connections = {"white": None, "black": None}
		self.status = "waiting"
		self.time_remainder = {"white": timer, "black": timer}
		self.turn_remainder = timer // 10
		self.timer = timer
		self.start_time = None
		self.game_start_time = None
		self.gaming_time = None
	
	async def time_counter(self):
		"""
		Алгоритм: Пока игра в статусе "playing", проверяет оставшееся время для текущего хода. Если время истекло, завершает игру победой оппонента.
		Возвращает: Ничего.
		"""
		while self.status == "playing":
			if self.start_time:
				spent = time.time() - self.start_time
				current_rem = self.time_remainder[self.engine.current_turn] - spent

				if current_rem <= 0 or spent >= self.turn_remainder:
					winner = "black" if self.engine.current_turn == "white" else "white"
					await self.end_game("Time's up", winner)
					return 
				
			await asyncio.sleep(1)
			
	async def broadcast(self, message: dict):
		"""
		Алгоритм: Проходит по всем активным WebSocket-подключениям в комнате и отправляет им JSON-сообщение, игнорируя ошибки отключения.
		Возвращает: Ничего.
		"""
		for color, ws in self.connections.items():
			if ws:
				try:
					await ws.send_json(message) #type: ignore
				except Exception:
					pass

	async def end_game(self, reason: str, winner_color: str | None):
		"""
		Алгоритм: Универсальная функция завершения игры. Меняет статус, считает время сессии, обновляет статистику обоих игроков в БД (или обрабатывает пат), отправляет финальный пакет данных участникам и удаляет комнату из общего пула.
		Возвращает: Ничего.
		"""
		if self.game_start_time: 
			self.gaming_time = time.time() - self.game_start_time
		
		if self.status == "game_over":
			return
		
		was_playing = (self.status == "playing" or self.status == "finished")
		self.status = "game_over"
		game_key = self.game_id 
		
		if not was_playing:
			all_games.pop(game_key, None)
			return
		
		for color in ["white", "black"]:
			player_data = self.players.get(color, {})
			player_name = player_data.get("name") if isinstance(player_data, dict) else None
			
			if not player_name:
				continue
				
			is_winner = (color == winner_color) if winner_color else False
			
			if reason == "stalemate":
				current_db = await load_db()
				updated_stats = current_db.get(player_name, DEFAULT_STATS)
			else:
				updated_stats = await update_player_rating(player_name, is_winner)
			
			ws = self.connections.get(color)
			if ws:
				payload = get_normal_dict("game_over", True, {
					"reason": reason,
					"winner": winner_color,
					"new_stats": updated_stats,
					"gaming_time": self.gaming_time
				})
				
				try:
					await ws.send_json(payload) #type: ignore
				except Exception:
					pass
			
		all_games.pop(game_key, None)


# --- PYDANTIC МОДЕЛИ ---

class AuthModel(BaseModel):
	name: str
	password: str
	
class JoinGameModel(BaseModel):
	name: str
	time_limit: int
	
class NicknameModel(BaseModel):
	name: str


# --- API ЭНДПОИНТЫ ---

@app.post("/register")
async def register(data: AuthModel):
	"""
	Алгоритм: Блокирует БД, проверяет занятость ника и длину полей. Хэширует пароль, создает профиль на базе дефолтных статов, сохраняет в БД и возвращает чистые статы для автологина.
	Возвращает: dict (результат регистрации и статы).
	"""
	async with db_lock:
		db_content = await load_db()
		
		if data.name in db_content:
			return get_normal_dict("register", False, "Пользователь с таким именем уже существует")
		
		if len(data.name) < 3 or len(data.password) < 6:
			return get_normal_dict("register", False, "Имя должно быть от 3 символов, пароль — от 6")
		
		hashed = hash_password(data.password)
		client_stats = DEFAULT_STATS.copy()
		
		db_content[data.name] = {
			"hashed_password": hashed,
			**client_stats
		}
		
		await save_db(db_content)
		
	logger.info(f"Успешная регистрация и автологин игрока: {data.name}")
	return get_normal_dict("register", True, client_stats)


@app.post("/login")
async def login(data: AuthModel):
	"""
	Алгоритм: Проверяет наличие игрока в БД и корректность пароля (сверяя хэши). Удаляет хэш из ответа и возвращает статистику.
	Возвращает: dict (результат входа и чистые статы).
	"""
	async with db_lock:
		db_content = await load_db()
	
	if data.name not in db_content:
		return get_normal_dict("login", False, "Неверное имя пользователя или пароль")
	
	player_data = db_content[data.name]
	
	if "hashed_password" not in player_data:
		return get_normal_dict("login", False, "У этого аккаунта нет пароля. Зарегистрируйтесь заново")
	
	if not verify_password(data.password, player_data["hashed_password"]):
		return get_normal_dict("login", False, "Неверное имя пользователя или пароль")
	
	client_stats = player_data.copy()
	client_stats.pop("hashed_password", None)
	
	logger.info(f"Игрок {data.name} успешно вошел в систему")
	return get_normal_dict("login", True, client_stats)


@app.post("/matchmake")
async def matchmake(payload: JoinGameModel):
	"""
	Алгоритм: Ищет ожидающее лобби с нужным лимитом времени. Если находит — подключает вторым игроком (за черных) и запускает таймер игры. Иначе — создает новую комнату (за белых) и ставит в ожидание.
	Возвращает: dict (данные для подключения к комнате и цвет).
	"""
	requested_time = payload.time_limit
	player_name = payload.name

	lobbies = waiting_lobbies.get(requested_time, [])
	
	# Защита от Race Condition (если лобби опустело за долю секунды)
	if lobbies:
		try:
			game_id = lobbies.pop(0)
			game = all_games[game_id]
			game.status = "playing"
			game.players["black"] = await fetch_player_stats(player_name)
			game.start_time = time.time()
			game.game_start_time = time.time()
			asyncio.create_task(game.time_counter())
			
			return get_normal_dict("connection_to_server", True, {"game_id": game_id, "color": "black"})
		except IndexError:
			pass
	
	new_id = str(uuid.uuid4())
	game = Game(new_id, requested_time)
	game.players["white"] = await fetch_player_stats(player_name)
	all_games[new_id] = game
	
	if requested_time not in waiting_lobbies:
		waiting_lobbies[requested_time] = []
	waiting_lobbies[requested_time].append(new_id)
	
	return get_normal_dict("connection_to_server", True, {"game_id": new_id, "color": "white"})


@app.post("/get_rating")
async def get_rating(data: NicknameModel):
	"""
	Алгоритм: Вызывает функцию безопасного получения статистики игрока по его нику.
	Возвращает: dict (статистика игрока).
	"""
	stats = await fetch_player_stats(data.name)
	return get_normal_dict("player_stats", True, stats)
	

@app.websocket("/ws/{game_id}/{color}/{name}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, color: str, name: str):
	"""
	Алгоритм: Принимает WS-соединение. Если комната полная — рассылает статусы и снимки доски, стартуя игру. Слушает входящие сообщения (ходы или сдачу). Обновляет игровое поле и таймеры, обрабатывает отключения игроков и уничтожение пустых комнат.
	Возвращает: Ничего.
	"""
	await websocket.accept()
	game = all_games.get(game_id)
	
	if not game:
		await websocket.close()
		return

	game.connections[color] = websocket
	
	if game.connections.get("white") and game.connections.get("black"):
		await game.broadcast(get_normal_dict("game_status", True, "playing"))
		await game.connections["white"].send_json(get_normal_dict("enemy_stats", True, game.players["black"]))
		await game.connections["black"].send_json(get_normal_dict("enemy_stats", True, game.players["white"]))
		
		await game.broadcast({
			"action": "board_broadcast",
			"success": True,
			"data": game.engine.get_board_snapshot(),
			"current_turn": game.engine.current_turn
		})
		game.start_time = time.time()
	else:
		await websocket.send_json(get_normal_dict("game_status", True, "waiting_for_player"))
	
	try:
		while True:
			data = await websocket.receive_json()
			
			if data.get("type") == "give_up":
				if game.status == "playing":
					game.status = "finished"
					winner = "black" if color == "white" else "white"
					await game.end_game("player_left", winner)
				break
			
			if data.get("type") == "make_move":
				if game.engine.current_turn != color:
					await websocket.send_json(get_normal_dict("Error", False, "Not your turn!"))
					continue
				
				start_pos = data.get("start_pos")
				end_pos = data.get("end_pos")
				
				if start_pos is not None and end_pos is not None:
					moving_figure = game.engine.board[start_pos[0]][start_pos[1]]
					if not moving_figure or moving_figure.color != color:
						await websocket.send_json(get_normal_dict("Error", False, "Это не ваша фигура!"))
						continue
					
					if game.engine.check_move(start_pos, end_pos):
						spent = time.time() - game.start_time
						game.time_remainder[game.engine.current_turn] -= spent
						game.engine.current_turn = "black" if color == "white" else "white"
						game.start_time = time.time()
						
						await game.broadcast({
							"action": "board_broadcast",
							"success": True,
							"data": game.engine.get_board_snapshot(),
							"current_turn": game.engine.current_turn
						})
						
						result = game.engine.check_game_over() 
						if result:
							game.status = "finished"
							winner = color if result == "checkmate" else None
							await game.end_game(result, winner)
							break
					else:
						await websocket.send_json(get_normal_dict("Error", False, "Invalid move!"))
						
	except WebSocketDisconnect:
		pass		
				
	except Exception:
		logger.error(f"Критическая ошибка в комнате {game_id}: {traceback.format_exc(limit=1)}")
		
	finally:
		if color in game.connections:
			del game.connections[color]

		if game.status == "playing":
			game.status = "finished" 
			winner_color = "black" if color == "white" else "white"
			await game.end_game("player_left", winner_color)
			print(f"Winner = {winner_color}")
			
		elif game.status == "waiting":
			if game_id in waiting_lobbies.get(game.timer, []):
				waiting_lobbies[game.timer].remove(game_id)
		
		# Уничтожение комнаты, если она пуста
		if game_id in all_games and not game.connections.get("white") and not game.connections.get("black"):
			all_games.pop(game_id, None)