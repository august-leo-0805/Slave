import os
import re
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from urllib.parse import quote
from dotenv import load_dotenv

from .cache import CacheManager

load_dotenv()

class TFT(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("RIOT_API_KEY")
        self.cache=CacheManager(self.bot)

        self.platform_alias = {
            'kr': 'kr', 'jp': 'jp1', 'na': 'na1', 'euw': 'euw1', 'eune': 'eun1',
            'br': 'br1', 'lan': 'la1', 'las': 'la2', 'tr': 'tr1', 'ru': 'ru',
            'oc': 'oc1', 'ph': 'ph2', 'sg': 'sg2', 'th': 'th2', 'vn': 'vn2'
        }

        self.region_map = {
            'kr': 'asia', 'jp1': 'asia',
            'na1': 'americas', 'br1': 'americas', 'la1': 'americas', 'la2': 'americas',
            'euw1': 'europe', 'eun1': 'europe', 'tr1': 'europe', 'ru': 'europe',
            'oc1': 'sea', 'ph2': 'sea', 'sg2': 'sea', 'th2': 'sea', 'vn2': 'sea'
        }

    async def _request(self, session, base_url, endpoint):
        """기본 URL과 엔드포인트를 조합하여 요청을 보내고 JSON을 반환하는 공통 헬퍼 메서드"""
        url = f"{base_url}{endpoint}"
        headers = {"X-Riot-Token": self.api_key}

        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            pass
        return None

    async def get_latest_ddragon_version(self, session):
        try:
            async with session.get("https://ddragon.leagueoflegends.com/api/versions.json") as resp:
                if resp.status == 200:
                    versions = await resp.json()
                    return versions[0]
        except Exception:
            pass
        return "14.12.1"

    async def fetch_tft_data(self, platform, name, tag):
        routing = self.region_map.get(platform, 'asia')
        
        routing_base = f"https://{routing}.api.riotgames.com"
        platform_base = f"https://{platform}.api.riotgames.com"

        async with aiohttp.ClientSession() as session:
            acc_data = await self._request(session, routing_base, f"/riot/account/v1/accounts/by-riot-id/{quote(name)}/{quote(tag)}")
            if not acc_data:
                return None
            puuid = acc_data['puuid']

            sum_data = await self._request(session, platform_base, f"/tft/summoner/v1/summoners/by-puuid/{puuid}")
            if not sum_data:
                return None
            profile_icon = sum_data.get('profileIconId', 1)
            level = sum_data.get('summonerLevel', 0)

            league_data = await self._request(session, platform_base, f"/tft/league/v1/by-puuid/{puuid}") or []

            res = {
                "level": level,
                "icon": profile_icon,
                "ranked_tft": {"tier": "Unranked", "lp": 0, "w": 0, "l": 0},
                "double_up": {"tier": "Unranked", "lp": 0, "w": 0, "l": 0},
                "total_w": 0,
                "total_l": 0,
            }

            for entry in league_data:
                q_type = entry.get("queueType")
                info = {
                    "tier": f"{entry.get('tier', 'Unranked')} {entry.get('rank', '')}".strip(),
                    "lp": entry.get("leaguePoints", 0),
                    "w": entry.get("wins", 0),
                    "l": entry.get("losses", 0),
                }

                if q_type == "RANKED_TFT":
                    res["ranked_tft"] = info
                elif q_type == "RANKED_TFT_DOUBLE_UP":
                    res["double_up"] = info

                res["total_w"] += entry.get("wins", 0)
                res["total_l"] += entry.get("losses", 0)
            return res

    @app_commands.command(name="tft", description="전략적 팀 전투(TFT) 전적을 조회합니다.")
    @app_commands.choices(platform=[
        app_commands.Choice(name="KR (한국)", value="kr"),
        app_commands.Choice(name="NA (북미)", value="na"),
        app_commands.Choice(name="JP (일본)", value="jp"),
        app_commands.Choice(name="EUW (서유럽)", value="euw"),
        app_commands.Choice(name="EUNE (북동유럽)", value="eune"),
    ])
    @app_commands.describe(riot_id="라이엇 ID (예: Hide on bush#KR1)", platform="서버 지역 (기본값: KR)", force_update="캐시를 무시하고 강제 갱신 여부")
    async def tft_stats(self, interaction: discord.Interaction, riot_id: str, platform: str = "kr", force_update: bool = False):
        await interaction.response.defer()

        if "#" not in riot_id:
            embed = discord.Embed(description="💡 예시: `Hide on bush#KR1`처럼 태그(#)를 포함하여 입력해주세요.", color=0x808080)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        name, tag = riot_id.rsplit("#", 1)
        name, tag = name.strip(), tag.strip()

        platform_code = self.platform_alias.get(platform.lower(), platform.lower())
        if platform_code not in self.region_map:
            valid_list = ", ".join(self.platform_alias.keys())
            embed = discord.Embed(description=f"❌ 알 수 없는 지역입니다.\n지원: `{valid_list}`", color=0x808080)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        cache_key = f"tft {platform_code} - {riot_id}"
        data, level, icon = None, None, None

        if not force_update:
            cached_entry = self.cache.get(cache_key)
            if cached_entry:
                data = cached_entry.get('data')
                level = cached_entry.get('level')
                icon = cached_entry.get('icon')

        if data is None:
            try:
                raw_res = await self.fetch_tft_data(platform_code, name, tag)
                if not raw_res:
                    raise Exception("No Data")

                level = raw_res.pop("level")
                icon = raw_res.pop("icon")
                data = raw_res
            except Exception:
                embed = discord.Embed(description=f"❌ **{riot_id}** 소환사를 찾을 수 없습니다. (이름 및 태그 확인)", color=0x808080)
                return await interaction.followup.send(embed=embed, ephemeral=True)

            self.cache.set(cache_key, {
                "region": platform_code,
                "riotid": riot_id,
                "level": level,
                "icon": icon,
                "data": data
            })

        async with aiohttp.ClientSession() as session:
            ddragon_version = await self.get_latest_ddragon_version(session)

        opgg_region = re.sub(r'\d+', '', platform_code)
        encoded_id = quote(riot_id.replace('#', '-'))

        embed = discord.Embed(title=f"{riot_id}'s TFT", color=0x808080)
        embed.set_thumbnail(url=f"https://ddragon.leagueoflegends.com/cdn/{ddragon_version}/img/profileicon/{icon}.png")

        tft_ranked = data['ranked_tft']
        t_total = tft_ranked['w'] + tft_ranked['l']
        t_wr = round(tft_ranked['w'] / t_total * 100, 1) if t_total > 0 else 0
        embed.add_field(name="랭크 게임", value=f"**{tft_ranked['tier']}** | {tft_ranked['lp']} LP\n{tft_ranked['w']}승 {tft_ranked['l']}패 ({t_wr}%)", inline=False)

        double_up = data['double_up']
        d_total = double_up['w'] + double_up['l']
        d_wr = round(double_up['w'] / d_total * 100, 1) if d_total > 0 else 0
        embed.add_field(name="더블 업", value=f"**{double_up['tier']}** | {double_up['lp']} LP\n{double_up['w']}승 {double_up['l']}패 ({d_wr}%)", inline=False)

        embed.add_field(name="🔗 상세 전적", value=f"[전적 보러가기](https://www.op.gg/tft/summoners/{opgg_region}/{encoded_id})", inline=False)
        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(TFT(bot))