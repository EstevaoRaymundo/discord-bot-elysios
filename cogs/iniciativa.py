import random
import re
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands


ChaveIniciativa = Tuple[int, int]


class Iniciativa(commands.Cog):
    """
    Sistema de iniciativa.

    Uma iniciativa diferente pode existir em cada canal.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.iniciativas: Dict[
            ChaveIniciativa,
            dict
        ] = {}

    # =====================================================
    # PERMISSÕES
    # =====================================================

    async def cog_check(
        self,
        ctx: commands.Context
    ) -> bool:
        """
        Todos os comandos deste Cog exigem a permissão
        Gerenciar Mensagens.
        """

        if ctx.guild is None:
            raise commands.NoPrivateMessage()

        permissoes = ctx.channel.permissions_for(
            ctx.author
        )

        if not permissoes.manage_messages:
            raise commands.MissingPermissions(
                ["manage_messages"]
            )

        return True

    # =====================================================
    # FUNÇÕES AUXILIARES
    # =====================================================

    @staticmethod
    def obter_chave(
        ctx: commands.Context
    ) -> Optional[ChaveIniciativa]:
        """
        Usa o ID do servidor e do canal como chave.
        """

        if ctx.guild is None:
            return None

        return (
            ctx.guild.id,
            ctx.channel.id
        )

    @staticmethod
    def separar_participantes(
        texto: str
    ) -> List[str]:
        """
        Separa participantes por vírgula, ponto e vírgula
        ou quebra de linha.

        Também remove nomes repetidos.
        """

        nomes = re.split(
            r"[,;\n]+",
            texto
        )

        participantes: List[str] = []
        nomes_adicionados = set()

        for nome in nomes:
            nome = nome.strip()

            if not nome:
                continue

            nome_normalizado = nome.casefold()

            if nome_normalizado in nomes_adicionados:
                continue

            nomes_adicionados.add(
                nome_normalizado
            )

            participantes.append(nome)

        return participantes

    @staticmethod
    def dividir_lista(
        participantes: List[str]
    ) -> List[str]:
        """
        Divide listas grandes para respeitar o limite
        de caracteres dos campos do Discord.
        """

        campos: List[str] = []
        campo_atual = ""

        for posicao, participante in enumerate(
            participantes,
            start=1
        ):
            linha = (
                f"**{posicao}.** {participante}\n"
            )

            if len(campo_atual) + len(linha) > 1000:
                campos.append(campo_atual)
                campo_atual = ""

            campo_atual += linha

        if campo_atual:
            campos.append(campo_atual)

        return campos

    def criar_embed(
        self,
        dados: dict
    ) -> discord.Embed:
        """
        Monta o painel da iniciativa.
        """

        embed = discord.Embed(
            title=f"⚔️ {dados['titulo']}",
            description=(
                "A ordem dos turnos foi sorteada "
                "aleatoriamente."
            ),
            color=discord.Color.dark_red()
        )

        campos = self.dividir_lista(
            dados["participantes"]
        )

        for numero, campo in enumerate(
            campos,
            start=1
        ):
            nome_campo = (
                "🎲 Ordem dos turnos"
                if numero == 1
                else "🎲 Continuação"
            )

            embed.add_field(
                name=nome_campo,
                value=campo,
                inline=False
            )

        embed.add_field(
            name="👥 Participantes",
            value=str(
                len(dados["participantes"])
            ),
            inline=True
        )

        embed.add_field(
            name="🛡️ Criada por",
            value=f"<@{dados['criador_id']}>",
            inline=True
        )

        embed.set_footer(
            text=(
                "Use !iniciativa ver para mostrar "
                "a ordem novamente."
            )
        )

        return embed

    # =====================================================
    # !INICIATIVA
    # =====================================================

    @commands.group(
        name="iniciativa",
        invoke_without_command=True
    )
    async def iniciativa(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Mostra a ajuda quando o usuário digita
        somente !iniciativa.
        """

        embed = discord.Embed(
            title="⚔️ Sistema de iniciativa",
            description=(
                "**Iniciar uma iniciativa**\n"
                "`!iniciativa iniciar Título / "
                "Jogador 1, Jogador 2`\n\n"

                "**Ver a iniciativa atual**\n"
                "`!iniciativa ver`\n\n"

                "**Encerrar a iniciativa**\n"
                "`!iniciativa encerrar`"
            ),
            color=discord.Color.dark_red()
        )

        await ctx.reply(
            embed=embed,
            mention_author=False
        )

    # =====================================================
    # !INICIATIVA INICIAR
    # =====================================================

    @iniciativa.command(name="iniciar")
    async def iniciativa_iniciar(
        self,
        ctx: commands.Context,
        *,
        conteudo: str = ""
    ) -> None:
        """
        Exemplo:

        !iniciativa iniciar Ataque ao Castelo /
        Deki, Finn, Christian, Annaliz
        """

        chave = self.obter_chave(ctx)

        if chave is None:
            return

        if chave in self.iniciativas:
            await ctx.reply(
                "Já existe uma iniciativa ativa "
                "neste canal.\n"
                "Use `!iniciativa encerrar` antes "
                "de iniciar outra.",
                mention_author=False
            )
            return

        conteudo = conteudo.strip()

        if not conteudo:
            await ctx.reply(
                "Informe o título e os participantes.\n\n"
                "**Exemplo:**\n"
                "`!iniciativa iniciar Ataque ao Castelo / "
                "Deki, Finn, Christian, Annaliz`",
                mention_author=False
            )
            return

        # Divide o conteúdo na primeira barra.
        titulo, separador, texto_participantes = (
            conteudo.partition("/")
        )

        titulo = titulo.strip()
        texto_participantes = (
            texto_participantes.strip()
        )

        if not separador:
            await ctx.reply(
                "Coloque uma `/` entre o título e os "
                "participantes.\n\n"
                "**Exemplo:**\n"
                "`!iniciativa iniciar Ataque ao Castelo / "
                "Deki, Finn, Christian`",
                mention_author=False
            )
            return

        if not titulo:
            await ctx.reply(
                "Informe o título da iniciativa "
                "antes da `/`.",
                mention_author=False
            )
            return

        if len(titulo) > 100:
            await ctx.reply(
                "O título pode ter no máximo "
                "100 caracteres.",
                mention_author=False
            )
            return

        participantes = self.separar_participantes(
            texto_participantes
        )

        if len(participantes) < 2:
            await ctx.reply(
                "Informe pelo menos dois participantes.\n\n"
                "**Exemplo:**\n"
                "`!iniciativa iniciar Missão da Floresta / "
                "Deki, Finn`",
                mention_author=False
            )
            return

        if len(participantes) > 50:
            await ctx.reply(
                "Uma iniciativa pode ter no máximo "
                "50 participantes.",
                mention_author=False
            )
            return

        # random.sample cria uma nova lista embaralhada.
        # Como os nomes repetidos já foram removidos,
        # ninguém aparecerá duas vezes.
        ordem_sorteada = random.sample(
            participantes,
            k=len(participantes)
        )

        dados = {
            "titulo": titulo,
            "participantes": ordem_sorteada,
            "criador_id": ctx.author.id
        }

        self.iniciativas[chave] = dados

        embed = self.criar_embed(dados)

        await ctx.send(
            content=(
                f"{ctx.author.mention} iniciou uma "
                "nova iniciativa!"
            ),
            embed=embed
        )

    # =====================================================
    # !INICIATIVA VER
    # =====================================================

    @iniciativa.command(name="ver")
    async def iniciativa_ver(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Mostra novamente a ordem salva.
        """

        chave = self.obter_chave(ctx)

        if chave is None:
            return

        dados = self.iniciativas.get(chave)

        if dados is None:
            await ctx.reply(
                "Não existe uma iniciativa ativa "
                "neste canal.",
                mention_author=False
            )
            return

        embed = self.criar_embed(dados)

        await ctx.reply(
            embed=embed,
            mention_author=False
        )

    # =====================================================
    # !INICIATIVA ENCERRAR
    # =====================================================

    @iniciativa.command(name="encerrar")
    async def iniciativa_encerrar(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Apaga a iniciativa do canal atual.
        """

        chave = self.obter_chave(ctx)

        if chave is None:
            return

        dados = self.iniciativas.get(chave)

        if dados is None:
            await ctx.reply(
                "Não existe uma iniciativa ativa "
                "neste canal.",
                mention_author=False
            )
            return

        titulo = dados["titulo"]

        del self.iniciativas[chave]

        await ctx.send(
            f"🏁 A iniciativa **{titulo}** foi encerrada "
            f"por {ctx.author.mention}."
        )

    # =====================================================
    # ERROS DO SISTEMA DE INICIATIVA
    # =====================================================

    async def cog_command_error(
        self,
        ctx: commands.Context,
        erro: commands.CommandError
    ) -> None:
        erro_original = getattr(
            erro,
            "original",
            erro
        )

        if isinstance(
            erro_original,
            commands.NoPrivateMessage
        ):
            await ctx.reply(
                "Este comando só pode ser usado "
                "dentro de um servidor.",
                mention_author=False
            )
            return

        if isinstance(
            erro_original,
            commands.MissingPermissions
        ):
            await ctx.reply(
                "❌ Você precisa da permissão "
                "**Gerenciar Mensagens** para usar "
                "os comandos de iniciativa.",
                mention_author=False
            )
            return

        if isinstance(
            erro_original,
            commands.CommandNotFound
        ):
            await ctx.reply(
                "Esse comando de iniciativa não existe.\n\n"
                "Use:\n"
                "`!iniciativa iniciar`\n"
                "`!iniciativa ver`\n"
                "`!iniciativa encerrar`",
                mention_author=False
            )
            return

        print(
            "❌ Erro no sistema de iniciativa:",
            repr(erro_original)
        )

        await ctx.reply(
            "❌ Ocorreu um erro ao executar "
            "o comando de iniciativa.",
            mention_author=False
        )


async def setup(
    bot: commands.Bot
) -> None:
    """
    Função obrigatória para carregar a extensão.
    """

    await bot.add_cog(
        Iniciativa(bot)
    )