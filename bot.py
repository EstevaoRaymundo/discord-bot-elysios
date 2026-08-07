import os
import random
import re
import traceback
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

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

# Necessário para comandos como !iniciativa e !ping.
intents.message_content = True


class ElysiosBot(commands.Bot):
    """
    Classe principal do bot.

    O setup_hook é executado antes de o bot ficar online
    e carrega os arquivos existentes dentro da pasta cogs.
    """

    async def setup_hook(self) -> None:
        try:
            await self.load_extension("cogs.iniciativa")
            print("✅ cogs.iniciativa carregado com sucesso.")

        except Exception as erro:
            print("❌ Não foi possível carregar cogs.iniciativa.")

            traceback.print_exception(
                type(erro),
                erro,
                erro.__traceback__
            )

            raise


bot = ElysiosBot(
    command_prefix="!",
    intents=intents,
    case_insensitive=True,
    help_command=None
)


# =========================================================
# SISTEMA DE ROLAGEM
# =========================================================

# Formatos aceitos:
#
# 1d30
# 1d30+5
# 1d30-5
# 1d30+35%
# 1d30-35%
# 2d20
#
# A mensagem precisa conter apenas a rolagem.

PADRAO_ROLAGEM = re.compile(
    r"^\s*"
    r"(?P<quantidade>\d*)"
    r"[dD]"
    r"(?P<faces>\d+)"
    r"(?P<modificador>[+-]\d+(?:[.,]\d+)?%?)?"
    r"\s*$"
)


def formatar_numero(valor: Decimal) -> str:
    """
    Mostra até duas casas decimais.

    Exemplos:
    18.20 -> 18.2
    20.00 -> 20
    12.56 -> 12.56
    """

    valor = valor.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )

    texto = format(valor, "f")

    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")

    return texto


def calcular_rolagem(expressao: str) -> Optional[str]:
    """
    Calcula uma expressão de dado e devolve a mensagem
    já formatada.

    Retorna None quando a mensagem não é uma rolagem.
    """

    correspondencia = PADRAO_ROLAGEM.fullmatch(expressao)

    if correspondencia is None:
        return None

    quantidade_texto = correspondencia.group("quantidade")
    faces_texto = correspondencia.group("faces")
    modificador = correspondencia.group("modificador")

    quantidade = (
        int(quantidade_texto)
        if quantidade_texto
        else 1
    )

    faces = int(faces_texto)

    # Proteções contra rolagens exageradas.
    if quantidade < 1 or quantidade > 100:
        return (
            "❌ A quantidade de dados precisa estar "
            "entre 1 e 100."
        )

    if faces < 2 or faces > 100000:
        return (
            "❌ A quantidade de faces precisa estar "
            "entre 2 e 100000."
        )

    resultados = [
        random.randint(1, faces)
        for _ in range(quantidade)
    ]

    soma_dados = sum(resultados)
    resultado_final = Decimal(soma_dados)

    if modificador:
        sinal = modificador[0]
        valor_texto = modificador[1:]

        try:
            if valor_texto.endswith("%"):
                porcentagem_texto = (
                    valor_texto[:-1]
                    .replace(",", ".")
                )

                porcentagem = Decimal(
                    porcentagem_texto
                )

                fator = porcentagem / Decimal("100")

                if sinal == "+":
                    resultado_final *= (
                        Decimal("1") + fator
                    )
                else:
                    resultado_final *= (
                        Decimal("1") - fator
                    )

            else:
                valor_numerico = Decimal(
                    valor_texto.replace(",", ".")
                )

                if sinal == "+":
                    resultado_final += valor_numerico
                else:
                    resultado_final -= valor_numerico

        except InvalidOperation:
            return "❌ O modificador da rolagem é inválido."

    resultado_formatado = formatar_numero(
        resultado_final
    )

    if quantidade == 1:
        dados_formatados = f"[{resultados[0]}]"
    else:
        dados_formatados = (
            "["
            + ", ".join(
                str(resultado)
                for resultado in resultados
            )
            + "]"
        )

    expressao_formatada = expressao.strip()

    return (
        f"`  {resultado_formatado}  ` "
        f"⟵ {dados_formatados} "
        f"{expressao_formatada}"
    )


@bot.listen("on_message")
async def ouvir_rolagens(
    message: discord.Message
) -> None:
    """
    Escuta mensagens que contenham apenas uma expressão
    de rolagem.

    Como isto é um listener e não substitui on_message,
    os comandos ! continuam funcionando normalmente.
    """

    if message.author.bot:
        return

    # Mensagens iniciadas com ! pertencem ao sistema
    # de comandos e não ao sistema de rolagem.
    if message.content.startswith("!"):
        return

    resultado = calcular_rolagem(
        message.content
    )

    if resultado is None:
        return

    try:
        await message.reply(
            resultado,
            mention_author=True
        )

    except discord.Forbidden:
        print(
            "❌ O bot não tem permissão para responder "
            f"no canal {message.channel}."
        )


# =========================================================
# COMANDO DE TESTE
# =========================================================

@bot.command(name="ping")
async def ping(ctx: commands.Context) -> None:
    await ctx.reply(
        "🏓 Os comandos com prefixo estão funcionando!",
        mention_author=False
    )


# =========================================================
# BOT ONLINE
# =========================================================

@bot.event
async def on_ready() -> None:
    if bot.user is None:
        return

    print("=" * 50)
    print(f"✅ Bot conectado como: {bot.user}")
    print(f"✅ ID do bot: {bot.user.id}")
    print("✅ Comandos carregados:")

    for comando in bot.walk_commands():
        print(f"   - {comando.qualified_name}")

    print("=" * 50)


# =========================================================
# ERROS GERAIS DOS COMANDOS
# =========================================================

@bot.event
async def on_command_error(
    ctx: commands.Context,
    erro: commands.CommandError
) -> None:
    """
    Erros tratados pelo próprio Cog não chegam aqui.
    Este evento trata os demais erros do bot.
    """

    if hasattr(ctx.command, "on_error"):
        return

    if ctx.cog is not None:
        metodo_erro = ctx.cog._get_overridden_method(
            ctx.cog.cog_command_error
        )

        if metodo_erro is not None:
            return

    erro_original = getattr(
        erro,
        "original",
        erro
    )

    # Ignora mensagens comuns que começam com !
    # mas que não correspondem a um comando.
    if isinstance(
        erro_original,
        commands.CommandNotFound
    ):
        return

    print(
        "❌ Erro em um comando:",
        repr(erro_original)
    )

    try:
        await ctx.reply(
            "❌ Ocorreu um erro ao executar esse comando.",
            mention_author=False
        )
    except discord.HTTPException:
        pass


# =========================================================
# TOKEN
# =========================================================

# Aceita DISCORD_TOKEN ou TOKEN no arquivo .env.
TOKEN = (
    os.getenv("DISCORD_TOKEN")
    or os.getenv("TOKEN")
)

if not TOKEN:
    raise RuntimeError(
        "O token não foi encontrado.\n"
        "Coloque DISCORD_TOKEN=seu_token no arquivo .env."
    )


# =========================================================
# INICIAR
# =========================================================

bot.run(TOKEN)