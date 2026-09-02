import uvicorn
import os
import sys

# На всякий случай жестко добавляем текущую директорию (корень) в пути Python
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    # Указываем точный путь до папки, за которой следить (чтобы не следил за клиентом)
    server_dir = os.path.join("server", "src")
    
    uvicorn.run(
        "server.src.server_main:app",  
        host="178.206.243.121", 
        port=51688, 
        reload=True,
        reload_dirs=[server_dir]
    )