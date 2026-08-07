import os
import traceback

import discord
from discord.ext import commands
from dotenv import load_dotenv


# =========================================================
# VARIÁVEIS DE AMBIENTE
# =========================================================

load_dotenv()


# =========================================================
# CONFIGURAÇÃO DO BOT
# =========================================================

intents = discord.Intents.default()

# Necessário para comandos com prefixo, como !iniciativa.
intents.message_content = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    case_insensitive=True,
    help_command=None
)


# =========================================================
# CARREGAMENTO DOS ARQUIVOS
# =========================================================

@bot.event
async def setup_hook():
    try:
        await bot.load_extension(
            "cogs.iniciativa"
        )

        print(
            "✅ Sistema de iniciativa carregado."
        )

    except Exception as erro:
        print(
            "❌ Erro ao carregar o sistema de iniciativa:"
        )

        traceback.print_exception(
            type(erro),
            erro,
            erro.__traceback__
        )

        raise


# =========================================================
# BOT ONLINE
# =========================================================

@bot.event
async def on_ready():
    print(
        f"✅ Bot conectado como {bot.user}"
    )

    print(
        f"✅ ID do bot: {bot.user.id}"
    )


# =========================================================
# COMANDO DE TESTE
# =========================================================

@bot.command(
    name="ping"
)
async def ping(ctx: commands.Context):
    await ctx.reply(
        "🏓 O sistema de comandos está funcionando!",
        mention_author=False
    )


# =========================================================
# EVENTO DE MENSAGENS
# =========================================================

@bot.event
async def on_message(message: discord.Message):
    # Impede que o bot responda às próprias mensagens
    # ou às mensagens de outros bots.
    if message.author.bot:
        return

    # Esta linha é obrigatória para fazer comandos como
    # !ping e !iniciativa funcionarem.
    await bot.process_commands(message)

    # Impede que o seu sistema de dados tente interpretar
    # os comandos iniciados com !.
    if message.content.startswith("!"):
        return

    # =====================================================
    # COLE ABAIXO O SEU CÓDIGO ATUAL DE ROLAGEM
    # =====================================================

    # Exemplo de local:
    #
    # conteudo = message.content.strip()
    #
    # resultado = verificar_rolagem(conteudo)
    #
    # if resultado:
    #     await message.reply(resultado)
    #
    # IMPORTANTE:
    # Não crie outro @bot.event async def on_message.
    # Seu código de rolagem deve ficar dentro deste evento.


# =========================================================
# TOKEN
# =========================================================

TOKEN = os.getenv(
    "DISCORD_TOKEN"
)

if not TOKEN:
    raise RuntimeError(
        "A variável DISCORD_TOKEN não foi encontrada."
    )


# =========================================================
# INICIAR O BOT
# =========================================================

bot.run(TOKEN)