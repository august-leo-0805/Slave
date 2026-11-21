import random
import discord
from discord import app_commands
from discord.ext import commands

class Choose(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="choose", description="여러 선택지 중 하나를 무작위로 골라줍니다.")
    @app_commands.describe(options="선택지들을 띄어쓰기로 구분하여 입력해주세요 (예: 짜장면 짬뽕 탕수육)")
    async def choose(self, interaction: discord.Interaction, options: str):
        option_list = [opt.strip() for opt in options.split() if opt.strip()]

        if len(option_list) < 2:
            embed = discord.Embed(
                title="❓ 선택지가 부족함",
                description="최소 2개 이상의 선택지를 띄어쓰기로 구분하여 입력해주세요.\n예: `/choose 짜장면 짬뽕 탕수육`",
                color=0x808080
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)
            
        select = random.choice(option_list)

        embed = discord.Embed(
            title="🤔 제 선택은요...",
            description=f"작성하신 **{len(option_list)}개**의 선택지 중에서 골라봤어요!",
            color=0x808080
        )
        embed.add_field(name="📋 후보 목록", value=f"`{'`, `'.join(option_list)}`", inline=False)
        embed.add_field(name="✨ 최종 결정", value=f"🎉 **{select}**", inline=False)
        embed.set_footer(text=f"요청자: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Choose(bot))