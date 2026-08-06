import random
import re

import discord
from discord.ext import commands


class Iniciativa(commands.Cog):
    """Sistema de sorteio de iniciativa."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Cada canal pode possuir uma iniciativa diferente.
        #
        # Chave:
        # (ID do servidor, ID do canal)
        #
        # Valor:
        # Dados da iniciativa.
        self.iniciativas = {}

    # =====================================================
    # VERIFICAÇÃO DE PERMISSÃO
    # =====================================================

    async def cog_check(self, ctx: commands.Context) -> bool:
        """
        Esta verificação é aplicada em todos os comandos
        existentes neste arquivo.

        Somente membros com Gerenciar Mensagens podem usar
        os comandos de iniciativa.
        """

        if ctx.guild is None:
            raise commands.NoPrivateMessage()

        permissoes = ctx.channel.permissions_for(ctx.author)

        if not permissoes.manage_messages:
            raise commands.MissingPermissions(
                ["manage_messages"]
            )

        return True

    # =====================================================
    # FUNÇÕES AUXILIARES
    # =====================================================

    @staticmethod
    def obter_chave(ctx: commands.Context):
        """
        Retorna uma chave formada pelo servidor e pelo canal.
        """

        if ctx.guild is None:
            return None

        return ctx.guild.id, ctx.channel.id

    @staticmethod
    def separar_jogadores(texto: str) -> list[str]:
        """
        Separa os participantes por:

        - vírgula;
        - ponto e vírgula;
        - quebra de linha.

        Também remove participantes repetidos.
        """

        nomes_separados = re.split(
            r"[,;\n]+",
            texto
        )

        participantes = []
        participantes_adicionados = set()

        for nome in nomes_separados:
            nome = nome.strip()

            if not nome:
                continue

            # Faz Finn, FINN e finn serem considerados
            # o mesmo participante.
            nome_normalizado = nome.casefold()

            if nome_normalizado in participantes_adicionados:
                continue

            participantes_adicionados.add(
                nome_normalizado
            )

            participantes.append(nome)

        return participantes

    @staticmethod
    def dividir_ordem_em_campos(
        participantes: list[str]
    ) -> list[str]:
        """
        Divide listas grandes em vários campos do embed.
        """

        campos = []
        campo_atual = ""

        for posicao, participante in enumerate(
            participantes,
            start=1
        ):
            linha = (
                f"**{posicao}.** {participante}\n"
            )

            # Mantém uma margem antes do limite do Discord.
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
        Cria a mensagem com o título e a ordem sorteada.
        """

        embed = discord.Embed(
            title=f"⚔️ {dados['titulo']}",
            description=(
                "A ordem dos turnos foi sorteada "
                "aleatoriamente."
            ),
            color=discord.Color.dark_red()
        )

        campos = self.dividir_ordem_em_campos(
            dados["participantes"]
        )

        for numero, campo in enumerate(
            campos,
            start=1
        ):
            if numero == 1:
                titulo_campo = "🎲 Ordem dos turnos"
            else:
                titulo_campo = "🎲 Continuação"

            embed.add_field(
                name=titulo_campo,
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
                "Use !iniciativa ver para consultar "
                "novamente."
            )
        )

        return embed

    # =====================================================
    # COMANDO PRINCIPAL
    # =====================================================

    @commands.group(
        name="iniciativa",
        invoke_without_command=True
    )
    async def iniciativa(
        self,
        ctx: commands.Context
    ):
        """
        Mostra como utilizar os comandos.
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

    @iniciativa.command(
        name="iniciar"
    )
    async def iniciativa_iniciar(
        self,
        ctx: commands.Context,
        *,
        conteudo: str = ""
    ):
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
                "Já existe uma iniciativa ativa neste canal.\n"
                "Use `!iniciativa encerrar` antes de "
                "iniciar outra.",
                mention_author=False
            )
            return

        conteudo = conteudo.strip()

        if not conteudo:
            await ctx.reply(
                "Você precisa informar o título e os "
                "participantes.\n\n"
                "**Exemplo:**\n"
                "`!iniciativa iniciar Ataque ao Castelo / "
                "Deki, Finn, Christian, Annaliz`",
                mention_author=False
            )
            return

        # Divide o texto na primeira barra encontrada.
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
                "Informe o título da iniciativa antes "
                "da `/`.",
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

        participantes = self.separar_jogadores(
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

        # Cria uma nova lista em ordem aleatória.
        # Cada participante aparece apenas uma vez.
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

    @iniciativa.command(
        name="ver"
    )
    async def iniciativa_ver(
        self,
        ctx: commands.Context
    ):
        """
        Mostra a iniciativa ativa no canal.
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

    @iniciativa.command(
        name="encerrar"
    )
    async def iniciativa_encerrar(
        self,
        ctx: commands.Context
    ):
        """
        Encerra a iniciativa ativa no canal.
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

        self.iniciativas.pop(chave)

        await ctx.send(
            f"🏁 A iniciativa **{titulo}** foi encerrada "
            f"por {ctx.author.mention}."
        )

    # =====================================================
    # TRATAMENTO DE ERROS
    # =====================================================

    async def cog_command_error(
        self,
        ctx: commands.Context,
        erro: commands.CommandError
    ):
        """
        Mostra mensagens de erro mais fáceis de entender.
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
                "Este comando só pode ser usado dentro "
                "de um servidor.",
                mention_author=False
            )
            return

        if isinstance(
            erro_original,
            commands.MissingPermissions
        ):
            await ctx.reply(
                "❌ Você precisa da permissão "
                "**Gerenciar Mensagens** para usar os "
                "comandos de iniciativa.",
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
            "Erro no sistema de iniciativa:",
            repr(erro_original)
        )

        await ctx.reply(
            "Ocorreu um erro ao executar o comando.",
            mention_author=False
        )


async def setup(bot: commands.Bot):
    """
    Carrega este arquivo no bot.
    """

    await bot.add_cog(
        Iniciativa(bot)
    )