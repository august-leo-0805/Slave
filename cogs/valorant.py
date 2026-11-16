import os
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from urllib.parse import quote
from dotenv import load_dotenv

from .cache import CacheManager

load_dotenv()


class Valorant(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("HENRIK_API_KEY")
        self.base_url = "https://api.henrikdev.xyz"
        self.headers = {"Authorization": self.api_key}
        self.cache = CacheManager(self.bot)

    async def fetch_valorant_data(self, name: str, tag: str):
        """HenrikDev API를 호출하여 발로란트 프로필, MMR, 최근 5경기 상세 통계를 가져옵니다."""
        async with aiohttp.ClientSession() as session:
            acc_url = f"{self.base_url}/valorant/v1/account/{quote(name)}/{quote(tag)}"
            async with session.get(acc_url, headers=self.headers) as resp:
                if resp.status != 200:
                    return None
                acc_res = await resp.json()

            acc_data = acc_res.get("data", {})
            puuid = acc_data.get("puuid")
            region = acc_data.get("region", "ap")
            level = acc_data.get("account_level", 0)
            card_icon = acc_data.get("card", {}).get("small") or acc_data.get("card", {}).get("large")

            if not puuid:
                return None

            mmr_url = f"{self.base_url}/valorant/v2/by-puuid/mmr/{region}/{puuid}"
            tier = "Unranked"
            rr = 0
            highest_tier = "Unranked"

            async with session.get(mmr_url, headers=self.headers) as resp:
                if resp.status == 200:
                    mmr_res = await resp.json()
                    mmr_data = mmr_res.get("data", {})
                    curr_data = mmr_data.get("current_data", {})
                    tier = curr_data.get("currenttierpatched", "Unranked")
                    rr = curr_data.get("ranking_in_tier", 0)
                    
                    highest_rank_data = mmr_data.get("highest_rank", {})
                    highest_tier = highest_rank_data.get("patched_tier", "Unranked")

            matches_url = f"{self.base_url}/valorant/v3/by-puuid/matches/{region}/{puuid}?mode=competitive&size=5"
            recent_games = []

            async with session.get(matches_url, headers=self.headers) as resp:
                if resp.status == 200:
                    matches_res = await resp.json()
                    matches_list = matches_res.get("data", []) or []

                    for match in matches_list:
                        meta = match.get("metadata", {})
                        map_name = meta.get("map", "Unknown")
                        rounds_played = meta.get("rounds_played", 1) or 1

                        all_players = match.get("players", {}).get("all_players", [])
                        user_p = next((p for p in all_players if p.get("puuid") == puuid), None)

                        if user_p:
                            team_color = user_p.get("team", "").lower()
                            teams_info = match.get("teams", {})
                            user_team = teams_info.get(team_color, {})

                            win = user_team.get("has_won", False)
                            rounds_won = user_team.get("rounds_won", 0)
                            rounds_lost = user_team.get("rounds_lost", 0)

                            stats = user_p.get("stats", {})
                            kills = stats.get("kills", 0)
                            deaths = stats.get("deaths", 0)
                            assists = stats.get("assists", 0)
                            score = stats.get("score", 0)
                            
                            match_acs = round(score / rounds_played, 1) if rounds_played > 0 else 0.0

                            hs = stats.get("headshots", 0)
                            bs = stats.get("bodyshots", 0)
                            ls = stats.get("legshots", 0)
                            total_shots = hs + bs + ls
                            match_hs_pct = round((hs / total_shots * 100), 1) if total_shots > 0 else 0.0

                            character = user_p.get("character", "Unknown")

                            recent_games.append({
                                "win": win,
                                "rounds_won": rounds_won,
                                "rounds_lost": rounds_lost,
                                "kills": kills,
                                "deaths": deaths,
                                "assists": assists,
                                "acs": match_acs,
                                "hs_pct": match_hs_pct,
                                "agent": character,
                                "map": map_name
                            })

            return {
                "name": name,
                "tag": tag,
                "level": level,
                "card_icon": card_icon,
                "tier": tier,
                "rr": rr,
                "highest_tier": highest_tier,
                "recent_games": recent_games
            }

    @app_commands.command(name="val", description="발로란트 프로필 및 최근 5경기 상세 전적을 조회합니다.")
    @app_commands.describe(riot_id="RIOT ID(예: T1 TenZ#2001)", force_update="캐시를 무시하고 강제 갱신 여부")
    async def valorant_stats(self, interaction: discord.Interaction, riot_id: str, force_update: bool = False):
        await interaction.response.defer()

        if "#" not in riot_id:
            embed = discord.Embed(description="💡 예시: `T1 TenZ#2001`처럼 태그(#)를 포함하여 입력해주세요.", color=0x808080)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        name, tag = riot_id.rsplit("#", 1)
        name, tag = name.strip(), tag.strip()

        cache_key = f"valorant - {riot_id}"
        data = None

        if not force_update:
            cached_entry = self.cache.get(cache_key)
            if cached_entry:
                data = cached_entry.get("data")

        if data is None:
            try:
                data = await self.fetch_valorant_data(name, tag)
                if not data:
                    raise Exception("No Data")
            except Exception:
                embed = discord.Embed(description=f"❌ **{riot_id}** 플레이어를 찾을 수 없거나 데이터를 불러올 수 없습니다. (이름 및 태그 확인)", color=0x808080)
                return await interaction.followup.send(embed=embed, ephemeral=True)

            self.cache.set(cache_key, {"data": data})

        embed = discord.Embed(title=f"{data['name']}#{data['tag']}'s VALORANT", color=0x808080)

        if data.get("card_icon"):
            embed.set_thumbnail(url=data["card_icon"])

        embed.add_field(name="👤 계정 정보", value=f"레벨: {data['level']}\n현재 티어: {data['tier']} ({data['rr']} RR)\n최고 티어: {data['highest_tier']}", inline=False)

        recent_games = data.get("recent_games", [])
        if recent_games:
            total_games = len(recent_games)
            wins = sum(1 for g in recent_games if g["win"])
            win_rate = round((wins / total_games) * 100, 1)

            total_k = sum(g["kills"] for g in recent_games)
            total_d = sum(g["deaths"] for g in recent_games)
            total_a = sum(g["assists"] for g in recent_games)

            avg_k = round(total_k / total_games, 1)
            avg_d = round(total_d / total_games, 1)
            avg_a = round(total_a / total_games, 1)

            kd_ratio = round(total_k / total_d, 2) if total_d > 0 else float(total_k)
            avg_acs = round(sum(g["acs"] for g in recent_games) / total_games, 1)
            avg_hs = round(sum(g["hs_pct"] for g in recent_games) / total_games, 1)

            stats_text = (
                f"승률: {win_rate}% ({wins}승 / {total_games}전 - 최근 {total_games}경기 기준)\n"
                f"평균 KDA: {avg_k} / {avg_d} / {avg_a} (K/D: {kd_ratio})\n"
                f"평균 전투 점수(ACS): {avg_acs}\n"
                f"평균 헤드샷 정확도(HS%): {avg_hs}%"
            )
            embed.add_field(name="📊 최근 전투 지표 통계", value=stats_text, inline=False)

            history_text = ""
            for g in recent_games:
                result_badge = "🟢 승리" if g["win"] else "🔴 패배"
                history_text += (f"{result_badge} ({g['rounds_won']}:{g['rounds_lost']}) | **{g['agent']}** ({g['kills']}/{g['deaths']}/{g['assists']}, ACS: {g['acs']}) - {g['map']}\n")
            embed.add_field(name="📜 최근 매치 히스토리", value=history_text.strip(), inline=False)
        else:
            embed.add_field(name="📊 최근 전투 지표 통계", value="기록 없음", inline=False)
            embed.add_field(name="📜 최근 매치 히스토리", value="최근 경기 데이터가 없습니다.", inline=False)

        embed.add_field(name="🔗 상세 전적", value=f"[전적 보러가기](https://tracker.gg/valorant/profile/riot/{quote(riot_id)}/overview)", inline=False)

        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Valorant(bot))