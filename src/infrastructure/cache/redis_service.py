import redis
import json
import logging
from typing import Optional, Any
import os

logger = logging.getLogger(__name__)

class RedisService:
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL")
        self.client = None
        if self.redis_url:
            try:
                self.client = redis.from_url(self.redis_url, decode_responses=True)
                # Test connection
                self.client.ping()
                logger.info("Connected to Redis for caching.")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}. Caching disabled.")
                self.client = None
        else:
            logger.info("REDIS_URL not set. Caching disabled.")

    def get(self, key: str) -> Optional[Any]:
        if not self.client:
            return None
        try:
            data = self.client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning(f"Redis get error: {e}")
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 60):
        if not self.client:
            return
        try:
            # Handle Pydantic models & lists
            if hasattr(value, "dict"):
                 serialized = value.json()
            else:
                 # Custom serializer for lists of objects if needed, 
                 # or rely on json.dumps default
                 serialized = json.dumps(value, default=lambda o: o.dict() if hasattr(o, "dict") else str(o))
            
            self.client.setex(key, ttl_seconds, serialized)
        except Exception as e:
            logger.warning(f"Redis set error: {e}")

    def delete(self, key: str):
        if not self.client:
            return
        try:
            self.client.delete(key)
        except Exception as e:
            logger.warning(f"Redis delete error: {e}")
