import os, asyncio, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from client.src.client_main import manager
if __name__ == "__main__": asyncio.run(manager())