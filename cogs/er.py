import os
import asyncio
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from urllib.parse import quote
from dotenv import load_dotenv

from .cache import CacheManager

load_dotenv()


class EternalReturn(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("ER_API_KEY")
        self.base_url = "https://open-api.bser.io"
        self.headers = {
            "x-api-key": self.api_key,
            "accept": "application/json"
        }
        self.current_season = None
        self.cache = CacheManager(self.bot)

        self.divisions = ["IV", "III", "II", "I"]
        self.tier_data = {
            "메테오라이트": {"start_mmr": 6400, "interval": 300},
            "다이아몬드": {"start_mmr": 5000, "interval": 350},
            "플래티넘": {"start_mmr": 3600, "interval": 350},
            "골드": {"start_mmr": 2400, "interval": 300},
            "실버": {"start_mmr": 1400, "interval": 250},
            "브론즈": {"start_mmr": 600,  "interval": 200},
            "아이언": {"start_mmr": 0,    "interval": 150},
        }

        self.bot.loop.create_task(self.load_current_season())

    async def load_current_season(self):
        """API를 통해 현재 활성화된 시즌 ID를 가져옵니다."""
        url = f"{self.base_url}/v2/data/Season"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        res_data = await resp.json()
                        if res_data.get("code") == 200:
                            for season in res_data.get("data", []):
                                if season.get("isCurrent") in (1, True):
                                    self.current_season = season.get("seasonID") or season.get("seasonId")
                                    return
        except Exception:
            pass

    def get_tier_by_mmr(self, mmr: int, rank: int = 0) -> str:
        """MMR 티어 반환 함수"""
        if rank > 0 and mmr >= 6000:
            if rank <= 300:
                return "이터니티"
            elif rank <= 1000:
                return "데미갓"

        if mmr >= 7600:
            return "미스릴"

        for tier_name, info in self.tier_data.items():
            if mmr >= info["start_mmr"]:
                idx = min(3, (mmr - info["start_mmr"]) // info["interval"])
                return f"{tier_name} {self.divisions[idx]}"

        return "Unranked"

    def _parse_user_stat(self, stat_json: dict, target_matching_mode: int) -> dict:
        """유저 통계 JSON을 파싱합니다."""
        user_stats_list = stat_json.get("userStats", [])
        if user_stats_list and isinstance(user_stats_list, list):
            user_stat = next(
                (s for s in user_stats_list if s.get("matchingMode") == target_matching_mode),
                user_stats_list[0]
            )
            return {
                "games": user_stat.get("totalGames", 0),
                "wins": user_stat.get("totalWins", 0),
                "top1": round(user_stat.get("top1", 0.0) * 100, 1),
                "top3": round(user_stat.get("top3", 0.0) * 100, 1),
                "avg_rank": round(user_stat.get("averageRank", 0.0), 1),
                "kills": round(user_stat.get("averageKills", 0.0), 1),
                "assistants": round(user_stat.get("averageAssistants", 0.0), 1),
                "hunts": round(user_stat.get("averageHunts", 0.0), 1)
            }
        return {
            "games": 0,
            "wins": 0,
            "top1": 0.0,
            "top3": 0.0,
            "avg_rank": 0.0,
            "kills": 0.0,
            "assistants": 0.0,
            "hunts": 0.0
        }

    async def fetch_er_data(self, nickname: str, serverCode: str = None):
        """일반전 및 랭크전 데이터를 모두 조회하여 통합 구조로 반환합니다."""
        if self.current_season is None:
            await self.load_current_season()
        season_id = self.current_season if self.current_season is not None else 0

        async with aiohttp.ClientSession() as session:
            user_url = f"{self.base_url}/v1/user/nickname?query={quote(nickname)}"
            async with session.get(user_url, headers=self.headers) as resp:
                if resp.status != 200:
                    return None

                user_data = await resp.json()
                if user_data.get("code") != 200 or not user_data.get("user"):
                    return None

                raw_users = user_data["user"]
                if isinstance(raw_users, dict):
                    raw_users = [raw_users]

                if serverCode is None and len(raw_users) > 1:
                    return "AMBIGUOUS"

                target_user = raw_users[0]
                if serverCode:
                    for u in raw_users:
                        user_server = u.get("serverName", "").lower()
                        if serverCode.lower() in user_server:
                            target_user = u
                            break

                user_id = target_user.get("userId") or target_user.get("userNum")
                name = target_user.get("nickname", nickname)

            async def get_json(url: str) -> dict:
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return {}

            rank_url = f"{self.base_url}/v1/rank/uid/{user_id}/{season_id}/3"
            rank_stat_url = f"{self.base_url}/v2/user/stats/uid/{user_id}/{season_id}/3"
            normal_stat_url = f"{self.base_url}/v2/user/stats/uid/{user_id}/0/3"

            rank_json, rank_stat_json, normal_stat_json = await asyncio.gather(
                get_json(rank_url),
                get_json(rank_stat_url),
                get_json(normal_stat_url),
            )

            rank_info = {"tier": "Unranked", "mmr": 0, "rank": 0}
            user_rank = rank_json.get("userRank", {})
            if user_rank:
                mmr = user_rank.get("mmr", 0)
                rank_num = user_rank.get("rank", 0) or user_rank.get("serverRank", 0)
                tier_name = user_rank.get("tierName") or self.get_tier_by_mmr(mmr, rank_num)
                rank_info = {"tier": tier_name, "mmr": mmr, "rank": rank_num}

            rank_stat = self._parse_user_stat(rank_stat_json, target_matching_mode=3)
            normal_stat = self._parse_user_stat(normal_stat_json, target_matching_mode=2)

            return {
                "nickname": name,
                "server": serverCode.lower() if serverCode else "asia",
                "data": {
                    "normal": normal_stat,
                    "rank": {
                        **rank_info,
                        **rank_stat
                    }
                }
            }

    @app_commands.command(name="er", description="이터널 리턴 유저 전적 정보를 조회합니다.")
    @app_commands.choices(
        server=[
            app_commands.Choice(name="ASIA", value="asia"),
            app_commands.Choice(name="ASIA2", value="asia2"),
            app_commands.Choice(name="ASIA3", value="asia3"),
            app_commands.Choice(name="NA", value="na"),
            app_commands.Choice(name="EU", value="eu"),
            app_commands.Choice(name="SA", value="sa"),
        ]
    )
    @app_commands.describe(
        nickname="조회할 유저 닉네임",
        is_rank="랭크 조회 여부 (기본값: False / 일반전)",
        server="게임 서버 지역 (선택 사항)",
        force_update="캐시 강제 갱신 여부"
    )
    async def er_stats(self, interaction: discord.Interaction, nickname: str, is_rank: bool = False, server: str = None, force_update: bool = False):
        await interaction.response.defer()

        server_key = server.lower() if server else "asia"
        cache_key = f"er {server_key} - {nickname.lower()}"

        cached_entry = None
        if not force_update:
            entry = self.cache.get(cache_key)
            # 기존 캐시 포맷과 충돌하지 않도록 normal/rank 키가 모두 있는 경우만 유효 처리
            if entry and isinstance(entry.get("data"), dict) and "normal" in entry["data"] and "rank" in entry["data"]:
                cached_entry = entry

        if cached_entry is None:
            try:
                fetched = await self.fetch_er_data(nickname, server)
                if fetched == "AMBIGUOUS":
                    embed = discord.Embed(
                        description=f"⚠️ **{nickname}** 닉네임을 가진 유저가 여러 서버에 존재합니다.\n정확한 조회를 위해 서버(리전)를 지정해 주세요.",
                        color=0x808080
                    )
                    return await interaction.followup.send(embed=embed, ephemeral=True)
                if not fetched:
                    raise Exception("데이터 없음")
            except Exception:
                embed = discord.Embed(
                    description=f"❌ **{nickname}** 유저를 찾을 수 없거나 데이터 조회를 실패했습니다.",
                    color=0x808080
                )
                return await interaction.followup.send(embed=embed, ephemeral=True)

            self.cache.set(cache_key, fetched)
            cached_entry = fetched

        display_nickname = cached_entry.get("nickname", nickname)
        mode_key = "rank" if is_rank else "normal"
        st = cached_entry["data"].get(mode_key, {})

        encoded_name = quote(display_nickname)
        embed = discord.Embed(title=f"{display_nickname}'s ETERNAL RETURN", color=0x808080)

        if is_rank:
            tier = st.get("tier", "Unranked")
            mmr = st.get("mmr", 0)
            rank_num = st.get("rank", 0)
            embed.add_field(name="⚔️ 스쿼드 랭크", value=f"**{tier}**\nMMR: {mmr} (순위: {rank_num}위)", inline=False)
            stat_field_name = "📊 시즌 통계"
            empty_msg = "이번 시즌 랭크 기록이 없습니다."
        else:
            embed.add_field(name="🎮 게임 모드", value="**일반전 (스쿼드)**", inline=False)
            stat_field_name = "📊 일반전 통계"
            empty_msg = "일반전 기록이 없습니다."

        if st and st.get("games", 0) > 0:
            stat_value = (
                f"🎮 판수: **{st['games']}판** (승리: {st['wins']}회)\n"
                f"🏆 승률: **{st['top1']}%** | Top 3: **{st['top3']}%**\n"
                f"📈 평균 등수: **{st['avg_rank']}위**\n"
                f"⚔️ 평균 K/A: **{st['kills']}** / **{st['assistants']}**\n"
                f"🦇 평균 야생동물: **{st['hunts']}개**"
            )
        else:
            stat_value = empty_msg

        embed.add_field(name=stat_field_name, value=stat_value, inline=False)
        embed.add_field(name="🔗 상세 전적", value=f"[전적 보러가기](https://dak.gg/er/profile/{encoded_name})", inline=False)
        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(EternalReturn(bot))