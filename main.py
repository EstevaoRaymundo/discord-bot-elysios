import os

import discord
from discord.ext import commands
from dotenv import load_dotenv


# Carrega as variáveis do arquivo .env.
load_dotenv()


# =========================================================
# CONFIGURAÇÃO DO BOT
# =========================================================

intents = discord.Intents.default()
intents.message_content = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    case_insensitive=True
)


# =========================================================
# CARREGAMENTO DOS ARQUIVOS
# =========================================================

@bot.event
async def setup_hook():
    await bot.load_extension(
        "cogs.iniciativa"
    )


# =========================================================
# BOT ONLINE
# =========================================================

@bot.event
async def on_ready():
    print(
        f"Bot conectado como {bot.user}"
    )


# =========================================================
# SEUS COMANDOS DE ROLAGEM
# =========================================================

# Mantenha seus comandos de rolagem nesta parte.
#
# Exemplo:
#
# @bot.command()
# async def teste(ctx):
#     await ctx.send("Funcionando!")


# =========================================================
# INICIAR O BOT
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "O token do bot não foi encontrado. "
        "Configure DISCORD_TOKEN no arquivo .env."
    )

bot.run(TOKEN)