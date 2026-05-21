import asyncio
from typing import Dict, Any

class AppState:
    def __init__(self):
        self.scraper_registry: Dict[str, Any] = {}
        self.cache: Dict[str, Any] = {} #In-memory mock for Redis
        self.queue: asyncio.Queue = asyncio.Queue() #Background event engine
        self.lock: asyncio.Lock = asyncio.Lock()
#Global state container instance
state = AppState()