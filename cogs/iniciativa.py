import random
import re
from typing import Dict, List, Optional, Tuple

import discord
from discord.ext import commands


# A chave identifica uma ordem de turnos pelo servidor e canal.
ChaveTurnos = Tuple[int, int]


class Turnos(commands.Cog):
    """
    Sistema de sorteio da ordem dos turnos.

    Cada canal pode possuir uma ordem de turnos diferente.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Estrutura:
        #
        # {
        #     (servidor_id, canal_id): {
        #         "titulo": "Ataque ao Castelo",
        #         "participantes": ["Deki", "Finn"],
        #         "criador_id": 123456789
        #     }
        # }
        self.ordens: Dict[ChaveTurnos, dict] = {}

    # =====================================================
    # PERMISSÕES
    # =====================================================

    async def cog_check(
        self,
        ctx: commands.Context
    ) -> bool:
        """
        Todos os comandos deste arquivo exigem a permissão
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
    ) -> Optional[ChaveTurnos]:
        """
        Retorna uma chave formada pelo ID do servidor
        e pelo ID do canal.
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
        Separa os participantes por:

        - vírgula;
        - ponto e vírgula;
        - quebra de linha.

        Nomes repetidos são removidos.
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

            # Finn, finn e FINN serão considerados
            # o mesmo participante.
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
        Cria o painel com o título e a ordem sorteada.
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
            if numero == 1:
                nome_campo = "🎲 Ordem dos turnos"
            else:
                nome_campo = "🎲 Continuação"

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
                "Use !turnos ver para mostrar "
                "a ordem novamente."
            )
        )

        return embed

    # =====================================================
    # !TURNOS
    # =====================================================

    @commands.group(
        name="turnos",
        invoke_without_command=True
    )
    async def turnos(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Mostra a ajuda quando alguém usa apenas !turnos.
        """

        embed = discord.Embed(
            title="⚔️ Sistema de turnos",
            description=(
                "**Iniciar uma ordem de turnos**\n"
                "`!turnos iniciar Título / "
                "Jogador 1, Jogador 2`\n\n"

                "**Ver a ordem atual**\n"
                "`!turnos ver`\n\n"

                "**Encerrar a ordem atual**\n"
                "`!turnos encerrar`"
            ),
            color=discord.Color.dark_red()
        )

        await ctx.reply(
            embed=embed,
            mention_author=False
        )

    # =====================================================
    # !TURNOS INICIAR
    # =====================================================

    @turnos.command(name="iniciar")
    async def turnos_iniciar(
        self,
        ctx: commands.Context,
        *,
        conteudo: str = ""
    ) -> None:
        """
        Exemplo:

        !turnos iniciar Ataque ao Castelo /
        Deki, Finn, Christian, Annaliz
        """

        chave = self.obter_chave(ctx)

        if chave is None:
            return

        if chave in self.ordens:
            await ctx.reply(
                "Já existe uma ordem de turnos ativa "
                "neste canal.\n"
                "Use `!turnos encerrar` antes de "
                "iniciar outra.",
                mention_author=False
            )
            return

        conteudo = conteudo.strip()

        if not conteudo:
            await ctx.reply(
                "Informe o título e os participantes.\n\n"
                "**Exemplo:**\n"
                "`!turnos iniciar Ataque ao Castelo / "
                "Deki, Finn, Christian, Annaliz`",
                mention_author=False
            )
            return

        # Divide o título e os participantes
        # na primeira barra encontrada.
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
                "`!turnos iniciar Ataque ao Castelo / "
                "Deki, Finn, Christian`",
                mention_author=False
            )
            return

        if not titulo:
            await ctx.reply(
                "Informe o título antes da `/`.",
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
                "`!turnos iniciar Missão da Floresta / "
                "Deki, Finn`",
                mention_author=False
            )
            return

        if len(participantes) > 50:
            await ctx.reply(
                "Uma ordem pode ter no máximo "
                "50 participantes.",
                mention_author=False
            )
            return

        # Sorteia todos os participantes sem repetir.
        ordem_sorteada = random.sample(
            participantes,
            k=len(participantes)
        )

        dados = {
            "titulo": titulo,
            "participantes": ordem_sorteada,
            "criador_id": ctx.author.id
        }

        self.ordens[chave] = dados

        embed = self.criar_embed(dados)

        await ctx.send(
            content=(
                f"{ctx.author.mention} iniciou uma "
                "nova ordem de turnos!"
            ),
            embed=embed
        )

    # =====================================================
    # !TURNOS VER
    # =====================================================

    @turnos.command(name="ver")
    async def turnos_ver(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Mostra novamente a ordem salva neste canal.
        """

        chave = self.obter_chave(ctx)

        if chave is None:
            return

        dados = self.ordens.get(chave)

        if dados is None:
            await ctx.reply(
                "Não existe uma ordem de turnos ativa "
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
    # !TURNOS ENCERRAR
    # =====================================================

    @turnos.command(name="encerrar")
    async def turnos_encerrar(
        self,
        ctx: commands.Context
    ) -> None:
        """
        Encerra a ordem de turnos do canal atual.
        """

        chave = self.obter_chave(ctx)

        if chave is None:
            return

        dados = self.ordens.get(chave)

        if dados is None:
            await ctx.reply(
                "Não existe uma ordem de turnos ativa "
                "neste canal.",
                mention_author=False
            )
            return

        titulo = dados["titulo"]

        del self.ordens[chave]

        await ctx.send(
            f"🏁 A ordem de turnos **{titulo}** foi "
            f"encerrada por {ctx.author.mention}."
        )

    # =====================================================
    # ERROS
    # =====================================================

    async def cog_command_error(
        self,
        ctx: commands.Context,
        erro: commands.CommandError
    ) -> None:
        """
        Trata os erros dos comandos de turnos.
        """

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
                "os comandos de turnos.",
                mention_author=False
            )
            return

        if isinstance(
            erro_original,
            commands.CommandNotFound
        ):
            await ctx.reply(
                "Esse comando de turnos não existe.\n\n"
                "Comandos disponíveis:\n"
                "`!turnos iniciar`\n"
                "`!turnos ver`\n"
                "`!turnos encerrar`",
                mention_author=False
            )
            return

        print(
            "❌ Erro no sistema de turnos:",
            repr(erro_original)
        )

        await ctx.reply(
            "❌ Ocorreu um erro ao executar "
            "o comando de turnos.",
            mention_author=False
        )


async def setup(
    bot: commands.Bot
) -> None:
    """
    Função usada pelo bot.py para carregar este arquivo.
    """

    await bot.add_cog(
        Turnos(bot)
    )