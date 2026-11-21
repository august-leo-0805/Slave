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

class LOL(commands.Cog):
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

    async def get_champion_mapping(self, session, version):
        """챔피언 숫자 ID(Key)를 한글 이름(Name)으로 변환해주는 맵을 생성합니다."""
        url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/ko_KR/champion.json"
        id_to_ko_name = {}
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for champ_info in data.get('data', {}).values():
                        id_to_ko_name[int(champ_info['key'])] = champ_info['name']
        except Exception:
            pass
        return id_to_ko_name

    async def fetch_lol_data(self, platform, name, tag):
        routing = self.region_map.get(platform, 'asia')

        routing_base = f"https://{routing}.api.riotgames.com"
        platform_base = f"https://{platform}.api.riotgames.com"

        async with aiohttp.ClientSession() as session:
            ddragon_version = await self.get_latest_ddragon_version(session)
            champ_map = await self.get_champion_mapping(session, ddragon_version)

            acc_data = await self._request(session, routing_base, f"/riot/account/v1/accounts/by-riot-id/{quote(name)}/{quote(tag)}")
            if not acc_data:
                return None
            puuid = acc_data['puuid']

            sum_data = await self._request(session, platform_base, f"/lol/summoner/v4/summoners/by-puuid/{puuid}")
            if not sum_data:
                return None
            profile_icon = sum_data.get('profileIconId', 1)
            level = sum_data.get('summonerLevel', 0)

            league_data = await self._request(session, platform_base, f"/lol/league/v4/entries/by-puuid/{puuid}") or []
            mastery_data = await self._request(session, platform_base, f"/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}/top?count=3") or []

            masteries = []
            for m in mastery_data:
                c_id = m.get('championId')
                c_name = champ_map.get(c_id, f"ID:{c_id}")
                masteries.append({
                    "championName": c_name,
                    "level": m.get('championLevel'),
                    "points": m.get('championPoints')
                })

            match_ids = await self._request(session, routing_base, f"/lol/match/v5/matches/by-puuid/{puuid}/ids?count=5") or []
            recent_games = []
            for m_id in match_ids:
                m_data = await self._request(session, routing_base, f"/lol/match/v5/matches/{m_id}")
                if m_data:
                    participants = m_data['info']['participants']
                    user_p = next((p for p in participants if p['puuid'] == puuid), None)
                    if user_p:
                        recent_games.append({
                            "win": user_p['win'],
                            "kills": user_p['kills'],
                            "deaths": user_p['deaths'],
                            "assists": user_p['assists'],
                            "champion": champ_map.get(user_p.get('championId'), user_p['championName'])
                        })

            res = {
                "level": level, "icon": profile_icon,
                "solo": {"tier": "Unranked", "lp": 0, "w": 0, "l": 0},
                "flex": {"tier": "Unranked", "lp": 0, "w": 0, "l": 0},
                "total_w": 0, "total_l": 0,
                "masteries": masteries,
                "recent_games": recent_games
            }

            for entry in league_data:
                q_type = entry['queueType']
                info = {
                    "tier": f"{entry['tier']} {entry['rank']}",
                    "lp": entry['leaguePoints'],
                    "w": entry['wins'],
                    "l": entry['losses']
                }
                if q_type == 'RANKED_SOLO_5x5':
                    res['solo'] = info
                elif q_type == 'RANKED_FLEX_SR':
                    res['flex'] = info
                res['total_w'] += entry['wins']
                res['total_l'] += entry['losses']

            return res

    @app_commands.command(name="lol", description="리그 오브 레전드(LoL) 전적을 조회합니다.")
    @app_commands.choices(platform=[
        app_commands.Choice(name="KR (한국)", value="kr"),
        app_commands.Choice(name="NA (북미)", value="na"),
        app_commands.Choice(name="JP (일본)", value="jp"),
        app_commands.Choice(name="EUW (서유럽)", value="euw"),
        app_commands.Choice(name="EUNE (북동유럽)", value="eune"),
    ])
    @app_commands.describe(riot_id="라이엇 ID (예: Hide on bush#KR1)", platform="서버 지역 (기본값: KR)", force_update="캐시를 무시하고 강제 갱신 여부")
    async def lol_stats(self, interaction: discord.Interaction, riot_id: str, platform: str = "kr", force_update: bool = False):
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

        cache_key = f"lol {platform_code} - {riot_id}"
        data, level, icon = None, None, None

        if not force_update:
            cached_entry = self.cache.get(cache_key)
            if cached_entry:
                data = cached_entry.get('data')
                level = cached_entry.get('level')
                icon = cached_entry.get('icon')

        if data is None:
            try:
                raw_res = await self.fetch_lol_data(platform_code, name, tag)
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

        embed = discord.Embed(title=f"{riot_id}'s LOL", color=0x808080)
        embed.set_thumbnail(url=f"https://ddragon.leagueoflegends.com/cdn/{ddragon_version}/img/profileicon/{icon}.png")

        s = data['solo']
        s_total = s['w'] + s['l']
        s_wr = round(s['w'] / s_total * 100, 1) if s_total > 0 else 0
        embed.add_field(name="🏆 솔로 랭크", value=f"**{s['tier']}** | {s['lp']} LP\n{s['w']}승 {s['l']}패 ({s_wr}%)", inline=False)

        f = data['flex']
        f_total = f['w'] + f['l']
        f_wr = round(f['w'] / f_total * 100, 1) if f_total > 0 else 0
        embed.add_field(name="⚔️ 자유 랭크", value=f"**{f['tier']}** | {f['lp']} LP\n{f['w']}승 {f['l']}패 ({f_wr}%)", inline=False)

        masteries = data.get('masteries', [])
        if masteries:
            m_text = "".join([f"{idx}. **{m['championName']}** (Lv.{m['level']})\n" for idx, m in enumerate(masteries, 1)])
            embed.add_field(name="🔥 모스트 숙련도 TOP 3", value=m_text, inline=False)

        recent_games = data.get('recent_games', [])
        if recent_games:
            wins = sum(1 for g in recent_games if g['win'])
            losses = len(recent_games) - wins
            r_text = "".join([f"{'🟢 승' if g['win'] else '🔴 패'} | **{g['champion']}** ({g['kills']}/{g['deaths']}/{g['assists']})\n" for g in recent_games])
            embed.add_field(name=f"📊 최근 5경기 ({wins}승 {losses}패)", value=r_text, inline=False)

        embed.add_field(name="🔗 상세 전적", value=f"[전적 보러가기](https://www.op.gg/summoners/{opgg_region}/{encoded_id})", inline=False)
        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(LOL(bot))