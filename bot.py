"""Ponto de entrada do bot Elysios."""

import loggin
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Mantém estas funções disponíveis para imports já existentes de bot.py.
from utils.dados import (
    PADRAO_ROLAGEM,
    calcular_rolagem,
    formatar_numero,
)


load_dotenv()

logger = logging.getLogger(__name__)

EXTENSOES = (
    "cogs.iniciativa",
    "cogs.rolagem",
)


intents = discord.Intents.default()

# Necessário para comandos com prefixo e rolagens em mensagens.
intents.message_content = True


class ElysiosBot(commands.Bot):
    """Classe principal do bot."""

    async def setup_hook(self) -> None:
        for extensao in EXTENSOES:
            try:
                await self.load_extension(extensao)
                logger.info("Extensão %s carregada.", extensao)
            except Exception:
                logger.exception(
                    "Não foi possível carregar a extensão %s.",
                    extensao
                )
                raise


bot = ElysiosBot(
    command_prefix="!",
    intents=intents,
    case_insensitive=True,
    help_command=None
)


@bot.command(name="ping")
async def ping(ctx: commands.Context) -> None:
    await ctx.reply(
        "🏓 Os comandos com prefixo estão funcionando!",
        mention_author=False
    )


@bot.event
async def on_ready() -> None:
    if bot.user is None:
        return

    logger.info("Bot conectado como: %s", bot.user)
    logger.info("ID do bot: %s", bot.user.id)
    logger.info(
        "Comandos carregados: %s",
        ", ".join(
            comando.qualified_name
            for comando in bot.walk_commands()
        )
    )


@bot.event
async def on_command_error(
    ctx: commands.Context,
    erro: commands.CommandError
) -> None:
    """Trata erros não processados pelo próprio comando ou Cog."""

    if hasattr(ctx.command, "on_error"):
        return

    if ctx.cog is not None:
        metodo_erro = ctx.cog._get_overridden_method(
            ctx.cog.cog_command_error
        )

        if metodo_erro is not None:
            return

    erro_original = getattr(erro, "original", erro)

    if isinstance(erro_original, commands.CommandNotFound):
        return

    logger.error(
        "Erro em um comando.",
        exc_info=(
            type(erro_original),
            erro_original,
            erro_original.__traceback__
        )
    )

    try:
        await ctx.reply(
            "❌ Ocorreu um erro ao executar esse comando.",
            mention_author=False
        )
    except discord.HTTPException:
        logger.exception(
            "Não foi possível enviar a mensagem de erro do comando."
        )


def obter_token() -> str:
    """Obtém o token sem executar a conexão durante imports e testes."""

    token = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")

    if not token:
        raise RuntimeError(
            "O token não foi encontrado.\n"
            "Coloque DISCORD_TOKEN=seu_token no arquivo .env."
        )

    return token


def configurar_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )


def main() -> None:
    configurar_logging()
    bot.run(obter_token(), log_handler=None)


if __name__ == "__main__":
    main()
