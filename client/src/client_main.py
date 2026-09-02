import asyncio, pygame, pygame_gui

from .client_main_menu import show_main_menu
from .client_auth import show_auth_screen
from .client_game import show_game_screen
from assets.common import WIDTH, HEIGHT, THEME_PATH



async def manager():
    pygame.init()
    window_surface = pygame.display.set_mode((WIDTH, HEIGHT))
    ui_manager = pygame_gui.UIManager((WIDTH, HEIGHT), THEME_PATH)
    
    
    current_stage = "AUTH"
    app_running = True
    
    
    while app_running:
        if current_stage in ("AUTH", "LOGOUT"):
            # Если мы пришли из LOGOUT, передаем True, чтобы сбросить автовход
            force_logout = (current_stage == "LOGOUT")
            
            auth_result = await show_auth_screen(window_surface, force_logout)
           
            if not any(auth_result):
                break
            
            username, stats = auth_result
            current_stage = "MENU"
        
        elif current_stage == "MENU":
            current_stage, game_id, color = await show_main_menu(username, stats) #type: ignore
        
        elif current_stage == "QUIT":
            app_running = False
            return
            
            
        elif current_stage == "MULTIPLAYER":
            stats = await show_game_screen(window_surface, username, stats, game_id, color) #type: ignore
            current_stage = "MENU"
            
        elif current_stage == "SINGLEPLAYER":
            print(f"Singleplayer is not ready.")
            current_stage = "MENU"
        
    pygame.quit()
            
