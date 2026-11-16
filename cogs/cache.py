import json
import os
import time
from discord.ext import commands, tasks

class CacheManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        base_path = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(base_path, "..", "data")
        self.cache_file = os.path.join(self.data_dir, "tracking.json")
        
        self._ensure_cache_file()

        if not self.clean_cache_task.is_running():
            self.clean_cache_task.start()

    def cog_unload(self):
        self.clean_cache_task.stop()

    def _ensure_cache_file(self):
        """캐시 저장 디렉터리 및 파일이 없을 경우 생성을 보장합니다."""
        os.makedirs(self.data_dir, exist_ok=True)
        if not os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump({}, f)
            except Exception:
                pass

    def load_all(self) -> dict:
        """캐시 파일 전체를 읽어옵니다."""
        if not os.path.exists(self.cache_file):
            return {}
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def get(self, key: str, ttl: int = 1500) -> dict | None:
        """특정 key의 캐시 데이터를 가져옵니다. (기본 TTL: 25분/1500초)"""
        cache = self.load_all()
        entry = cache.get(key)
        if not entry:
            return None
        
        timestamp = entry.get("timestamp", 0)
        if time.time() - timestamp < ttl:
            return entry
        return None

    def set(self, key: str, payload: dict):
        """캐시 데이터를 저장하고 파일에 동기화합니다."""
        cache = self.load_all()
        payload["timestamp"] = time.time()
        cache[key] = payload
        
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    @tasks.loop(minutes=10)
    async def clean_cache_task(self):
        """10분마다 30분(1800초)이 지난 오래된 캐시 항목을 정리합니다."""
        if not os.path.exists(self.cache_file):
            return

        try:
            data = self.load_all()
            current_time = time.time()
            new_data = {k: v for k, v in data.items() if current_time - v.get('timestamp', 0) < 1800}
            
            if len(data) != len(new_data):
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(new_data, f, ensure_ascii=False, indent=4)
                print(f"🧹 캐시 정리 완료: 만료된 {len(data) - len(new_data)}개의 항목 삭제됨.")

        except Exception as e:
            print(f"❌ 캐시 정리 중 오류 발생: {e}")

async def setup(bot):
    await bot.add_cog(CacheManager(bot))