import os
import io
import base64
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from .cache import CacheManager

load_dotenv()

class Minecraft(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("MC_API_KEY")
        self.base_url = "https://mc-api.io"
        self.cache=CacheManager(self.bot)

    async def fetch_user_data(self, username, edition):
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/profile/{username}/{edition}"
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None, "player_not_found"
                data = await resp.json()

        name = data.get("name", username)
        uuid = data.get("uuid", "알 수 없음")
        platform = "Bedrock Edition" if edition.upper() == "BEDROCK" or "xuid" in data else "Java Edition"
        skin_render_url = f"{self.base_url}/render/BUST/{name}/{edition}"
        favicon_render_url = f"{self.base_url}/render/HEAD/{name}/{edition}"

        processed_data = {
            "name": name,
            "uuid": uuid,
            "edition": edition.upper(),
            "platform": platform,
            "skin_render_url": skin_render_url,
            "favicon_render_url": favicon_render_url,
            "raw_data": data
        }
        return processed_data, None

    async def fetch_server_data(self, edition, address):
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/server/{edition}/{address}"
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None, "server_not_found"
                data = await resp.json()
        return data, None

    @app_commands.command(name="mcuser", description="마인크래프트 유저의 닉네임, 플랫폼, 스킨 정보를 조회합니다.")
    @app_commands.describe(username="조회할 마인크래프트 닉네임", edition="에디션을 선택하세요 (JAVA 또는 BEDROCK)", force_update="캐시 강제 갱신 여부")
    @app_commands.choices(edition=[app_commands.Choice(name="Java Edition", value="JAVA"), app_commands.Choice(name="Bedrock Edition", value="BEDROCK")])
    async def user_lookup(self, interaction: discord.Interaction, username: str, edition: str = "JAVA", force_update: bool = False):
        await interaction.response.defer()

        cache_key = f"minecraft {edition.lower()} - {username.lower()}"
        stats = None

        if not force_update:
            cached_entry = self.cache.get(cache_key)
            if cached_entry:
                stats = cached_entry.get("data")

        if stats is None:
            stats, error = await self.fetch_user_data(username, edition)
            if error:
                return await interaction.followup.send(f"❌ {edition} 에디션에서 **{username}**님의 정보를 찾을 수 없습니다.", ephemeral=True)
            
            self.cache.set(cache_key, {"data": stats})

        embed = discord.Embed(title=f"{stats['name']}'s MINECRAFT", color=0x808080)
        embed.add_field(name="플랫폼", value=stats['platform'], inline=False)
        embed.set_thumbnail(url=stats['favicon_render_url'])
        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        embed.set_image(url=stats['skin_render_url'])

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="mcserver", description="마인크래프트 서버의 상태, 인원, 버전 및 MOTD 정보를 조회합니다.")
    @app_commands.describe(address="조회할 마인크래프트 서버 주소", edition="서버 에디션을 선택하세요 (JAVA 또는 BEDROCK)", force_update="캐시 강제 갱신 여부")
    @app_commands.choices(edition=[app_commands.Choice(name="Java Edition", value="JAVA"), app_commands.Choice(name="Bedrock Edition", value="BEDROCK")])
    async def server_lookup(self, interaction: discord.Interaction, address: str, edition: str = "JAVA", force_update: bool = False):
        await interaction.response.defer()

        cache_key = f"minecraft {edition.lower()} - {address.lower()}"
        data = None

        if not force_update:
            cached_entry = self.cache.get(cache_key)
            if cached_entry:
                data = cached_entry.get("data")

        if data is None:
            data, error = await self.fetch_server_data(edition, address)
            if error:
                return await interaction.followup.send(f"❌ **{address}** 서버를 찾을 수 없습니다. 주소를 다시 확인해주세요.", ephemeral=True)

            self.cache.set(cache_key, {"data": data})

        icon_raw = data.get("favicon", None)
        is_online = data.get("online", False)

        if not is_online:
            embed = discord.Embed(title=f"SERVER STATUS: {address}", color=0x808080)
            embed.add_field(name="상태", value="🔴 오프라인 (서버가 닫혀있거나 응답이 없습니다)", inline=False)
            embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
            return await interaction.followup.send(embed=embed)

        version_raw = data.get("version", "알 수 없음")
        version = version_raw.get("name", str(version_raw)) if isinstance(version_raw, dict) else str(version_raw)

        players_online = data.get("onlinePlayers")
        players_max = data.get("maxPlayers")
        if players_online is None or players_max is None:
            players_data = data.get("players", {})
            players_online = players_data.get("online", 0) if isinstance(players_data, dict) else 0
            players_max = players_data.get("max", 0) if isinstance(players_data, dict) else 0

        ping = data.get("ping", "측정 불가")
        ping_str = f"{ping}ms" if isinstance(ping, (int, float)) else str(ping)

        motd_raw = data.get("rawMotd")
        if not motd_raw:
            motd_data = data.get("motd", "설명이 없습니다.")
            motd_raw = motd_data.get("clean") or motd_data.get("raw", "설명이 없습니다.") if isinstance(motd_data, dict) else str(motd_data)
        motd = motd_raw[:1000] + "..." if len(motd_raw) > 1000 else motd_raw

        file = None
        if icon_raw and isinstance(icon_raw, str) and icon_raw.startswith("data:image"):
            try:
                base64_data = icon_raw.split(",")[1]
                image_bytes = base64.b64decode(base64_data)
                buffer = io.BytesIO(image_bytes)
                buffer.seek(0)
                file = discord.File(buffer, filename="server_icon.png")
            except Exception:
                pass

        embed = discord.Embed(title=f"SERVER STATUS: {address}", color=0x808080)
        embed.add_field(name="상태", value="🟢 온라인", inline=True)
        embed.add_field(name="버전", value=version, inline=True)
        embed.add_field(name="응답 속도 (Ping)", value=ping_str, inline=True)
        embed.add_field(name="플레이어", value=f"{players_online} / {players_max}", inline=False)
        embed.add_field(name="설명 (MOTD)", value=f"```{motd}```", inline=False)

        if file:
            embed.set_thumbnail(url="attachment://server_icon.png")

        embed.set_footer(text=f"Requested by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        
        if file:
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Minecraft(bot))