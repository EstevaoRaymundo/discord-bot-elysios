"""Integração do sistema de rolagem com mensagens do Discord."""

import logging

import discord
from discord.ext import commands

from utils.dados import calcular_rolagem, dividir_mensagem


logger = logging.getLogger(__name__)


class Rolagem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        # Mensagens iniciadas com ! pertencem aos comandos.
        if message.content.startswith("!"):
            return

        resultado = calcular_rolagem(message.content)

        if resultado is None:
            return

        try:
            for indice, parte in enumerate(
                dividir_mensagem(resultado)
            ):
                await message.reply(
                    parte,
                    mention_author=indice == 0
                )
        except discord.Forbidden:
            logger.warning(
                "O bot não tem permissão para responder no canal %s.",
                message.channel
            )
        except discord.HTTPException:
            logger.exception(
                "Não foi possível enviar uma resposta de rolagem."
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Rolagem(bot))
