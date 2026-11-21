import os
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from .cache import CacheManager

load_dotenv()

class PUBG(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("PUBG_API_KEY")
        self.base_url = "https://api.pubg.com/shards"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/vnd.api+json"
        }
        self.current_season = None
        self.cache = CacheManager(self.bot)

        self.bot.loop.create_task(self.load_current_season())

    async def load_current_season(self):
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/steam/seasons"
                async with session.get(url, headers=self.headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for season in data.get('data', []):
                            if season['attributes'].get('isCurrentSeason'):
                                self.current_season = season['id']
                                return
        except Exception: 
            return

    async def fetch_pubg_data(self, platform, target_nick, mode, is_ranked):
        """API 호출 및 데이터 계산을 담당하는 로직"""
        async with aiohttp.ClientSession() as session:
            player_url = f"{self.base_url}/{platform}/players?filter[playerNames]={target_nick}"
            async with session.get(player_url, headers=self.headers) as resp:
                if resp.status != 200:
                    return None, "player_not_found"
                player_data = await resp.json()
                player_id = player_data['data'][0]['id']

            if is_ranked:
                if not self.current_season:
                    return None, "season_not_loaded"
                stats_url = f"{self.base_url}/{platform}/players/{player_id}/seasons/{self.current_season}/ranked"
            else:
                stats_url = f"{self.base_url}/{platform}/players/{player_id}/seasons/lifetime"

            async with session.get(stats_url, headers=self.headers) as resp:
                if resp.status != 200:
                    return None, "api_error"
                stats_data = await resp.json()

            stats_root = stats_data['data']['attributes']
            mode_stats = stats_root['rankedGameModeStats'] if is_ranked else stats_root['gameModeStats']
            game_stats = mode_stats.get(mode, {})

            if not game_stats or game_stats.get('roundsPlayed', 0) == 0:
                return None, "no_data"

            rounds = game_stats.get('roundsPlayed', 0)
            wins = game_stats.get('wins', 0)
            kills = game_stats.get('kills', 0)
            damage = game_stats.get('damageDealt', 0)
            top10s = game_stats.get('top10s', 0)
            deaths = rounds - wins
            
            processed_data = {
                "nickname": target_nick,
                "platform": platform,
                "mode_key": mode,
                "rounds": rounds,
                "kd": round(kills / deaths, 2) if deaths > 0 else kills,
                "adr": int(damage / rounds) if rounds > 0 else 0,
                "win_rate": round((wins / rounds) * 100, 1) if rounds > 0 else 0,
                "top10_rate": round((top10s / rounds) * 100, 1) if rounds > 0 else 0,
                "tier": game_stats.get('currentTier', {}).get('tier', 'Unranked') if is_ranked else "Normal",
                "sub_tier": game_stats.get('currentTier', {}).get('subTier', '') if is_ranked else "",
                "point": game_stats.get('currentRankPoint', 0) if is_ranked else 0
            }
            return processed_data, None

    @app_commands.command(name="pubg", description="배틀그라운드 전적을 조회합니다.")
    @app_commands.choices(platform=[
        app_commands.Choice(name="Steam", value="steam"),
        app_commands.Choice(name="Kakao", value="kakao"),
        app_commands.Choice(name="PSN", value="psn"),
        app_commands.Choice(name="Xbox", value="xbox")
    ])
    @app_commands.choices(mode=[
        app_commands.Choice(name="솔로", value="solo"),
        app_commands.Choice(name="듀오", value="duo"),
        app_commands.Choice(name="스쿼드", value="squad"),
        
    ])
    @app_commands.describe(nickname="배틀그라운드 닉네임", platform="플랫폼 (기본값: steam)", mode="게임 모드 (기본값: squad)", rank="경쟁전 여부 (기본값: False)", force_update="캐시를 무시하고 강제 갱신 여부")
    async def pubg_stats(self, interaction: discord.Interaction, nickname: str, platform: str = "steam", mode: str = "squad", rank: bool = False, force_update: bool = False):
        await interaction.response.defer(ephemeral=False)
        
        is_ranked = rank
        if is_ranked and mode != "squad":
            return await interaction.followup.send("랭크 조회는 스쿼드만 가능합니다.", ephemeral=True)

        actual_mode = mode.replace("ranked_", "")
        mode_type = f"ranked-{actual_mode}" if is_ranked else actual_mode
        cache_key = f"pubg {platform} - {nickname}"

        stats_content = None
        cached_entry = self.cache.get(cache_key) if not force_update else None

        if cached_entry:
            stats_content = cached_entry.get("data", {}).get(mode_type)

        if stats_content is None:
            stats, error = await self.fetch_pubg_data(platform, nickname, actual_mode, is_ranked)

            if error:
                error_msgs = {
                    "player_not_found": f"❌ **{nickname}**님을 찾을 수 없습니다.",
                    "season_not_loaded": "⚠️ 시즌 정보를 로드 중입니다.",
                    "api_error": "❌ API 응답 오류가 발생했습니다.",
                    "no_data": f"**{nickname}**님의 {actual_mode} 데이터가 없습니다."
                }
                return await interaction.followup.send(error_msgs.get(error, "⚠️ 오류 발생"), ephemeral=True)

            stats_content = {
                "adr": stats['adr'],
                "kd": stats['kd'],
                "win_rate": f"{stats['win_rate']}%",
                "top10": f"{stats['top10_rate']}%",
                "rounds": stats['rounds'],
                "tier": stats['tier'],
                "sub_tier": stats['sub_tier'],
                "point": stats['point']
            }

            mode_data_map = cached_entry.get("data", {}) if cached_entry else {}
            mode_data_map[mode_type] = stats_content
            self.cache.set(cache_key, {
                "nickname": nickname,
                "platform": platform,
                "data": mode_data_map
            })

        embed = discord.Embed(title=f"{nickname}'s PUBG({platform.upper()})", color=0x808080)
        if is_ranked:
            embed.add_field(name="티어", value=f"**{stats_content['tier']} {stats_content['sub_tier']}** ({stats_content['point']}pt)", inline=False)

        embed.add_field(name="모드", value=f"{actual_mode.upper()} {'(경쟁)' if is_ranked else ''}", inline=True)
        embed.add_field(name="판수", value=f"{stats_content['rounds']}회", inline=True)
        embed.add_field(name="K/D", value=f"**{stats_content['kd']}**", inline=True)
        embed.add_field(name="평균 딜량(ADR)", value=f"{stats_content['adr']}", inline=True)
        embed.add_field(name="승률 / Top10", value=f"{stats_content['win_rate']} / {stats_content['top10']}", inline=True)
        embed.add_field(name="🔗 상세 전적", value=f"[전적 보러가기](https://dak.gg/pubg/profile/{platform}/{nickname})", inline=False)
        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        
        return await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(PUBG(bot))