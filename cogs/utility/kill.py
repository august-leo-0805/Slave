import json
import os
from pathlib import Path
import random
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

class Kill(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        base_path = Path(__file__).resolve().parents[2]
        
        self.dying_file = os.path.join(base_path, "data/dying_data.json")
        with open(self.dying_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.monsters = data['kill_command']['monsters']
            self.death_messages = data['kill_command']['death_messages']

    @app_commands.command(name="kill", description="대상 또는 본인의 사망 사유를 보여줍니다.")
    @app_commands.describe(target="사망 대상 (유저를 지목하거나 자유로운 텍스트 입력 가능)")
    async def kill_reason(self, interaction: discord.Interaction, target: Optional[str] = None):
        if target is None:
            target_name = interaction.user.display_name
            target_is_author = True
        else:
            if target.startswith("<@") and target.endswith(">"):
                clean_id = target.strip("<@!>")
                member = interaction.guild.get_member(int(clean_id)) if clean_id.isdigit() else None
                target_name = member.display_name if member else target
                target_is_author = (member == interaction.user)
            else:
                target_name = target
                target_is_author = (target == interaction.user.name or target == interaction.user.display_name)

        chosen_msg = random.choice(self.death_messages)

        if "{attacker}" in chosen_msg:
            if target is None or target_is_author:
                attacker_name = f"[**{random.choice(self.monsters)}**]"
            else:
                possible_attackers = [f"[**{random.choice(self.monsters)}**]", f"[**{interaction.user.display_name}**]"]
                attacker_name = random.choice(possible_attackers)

            full_message = chosen_msg.format(attacker=attacker_name)
        else:
            full_message = chosen_msg

        embed = discord.Embed(description=f"[**{target_name}**]이(가) {full_message}", color=0x808080)
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Kill(bot))