import json
import os
from pathlib import Path
import random
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

class Menu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        base_path = Path(__file__).resolve().parents[2]

        self.menu_file = os.path.join(base_path, "data/menu_data.json")
        with open(self.menu_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.menu_list = data['menu_command']['menu_list']
            self.time_data = data['menu_command']['time_data']

    @app_commands.command(name="menu", description="머먹을지 Slave가 추천해줍니다.")
    @app_commands.describe(category="추천받고 싶은 카테고리 (선택사항)")
    async def recommend_menu(self, interaction: discord.Interaction, category: Optional[str] = None):
        target_list = None
        display_category = category

        if category:
            if category in self.time_data:
                target_list = self.time_data[category]
            elif category in self.menu_list:
                target_list = self.menu_list[category]

        if not target_list:
            combined_menus = []
            for m in self.menu_list.values():
                combined_menus.extend(m)
            for t in self.time_data.values():
                combined_menus.extend(t)
            target_list = list(set(combined_menus))
            display_category = "전체 메뉴"
            
        food = random.choice(target_list)
        embed = discord.Embed(
            title="🍴 메뉴 추천 시스템",
            description=f"{interaction.user.mention}님, **{display_category}** 카테고리에서 골라봤어요!",
            color=0x808080
        )
        embed.add_field(name="오늘의 추천", value=f"✨ **{food}**", inline=False)
        embed.set_footer(text="팁: 메뉴 카테고리를 정하면, 더 정확한 결과를 얻을수 있어요")
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Menu(bot))