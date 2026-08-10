"""Grupo de manuais acessíveis por /iniciar."""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from utils.discohook import (
    extrair_embed,
    preparar_envio_embed,
    resolver_imagem,
    validar_embed,
)


logger = logging.getLogger(__name__)

DIRETORIO_MANUAIS = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "manuais"
)
NOME_ARQUIVO_MANUAL = "manual.json"
MENSAGEM_MANUAL_INDISPONIVEL = (
    "❌ O manual de poções não está disponível no momento."
)


@dataclass(frozen=True)
class Manual:
    """Dados validados de um manual armazenado localmente."""

    nome: str
    pasta: Path
    embed_data: Dict[str, Any]
    attachment: Optional[Path] = None
    nome_attachment: Optional[str] = None


class Iniciar(
    commands.GroupCog,
    group_name="iniciar",
    group_description="Manuais e instruções para iniciar atividades.",
):
    """Agrupa os manuais de atividades do bot."""

    def __init__(
        self,
        bot: Optional[commands.Bot],
        diretorio_manuais: Optional[Path] = None,
    ) -> None:
        self.bot = bot
        self.diretorio_manuais = Path(
            diretorio_manuais or DIRETORIO_MANUAIS
        )

    def carregar_manual(
        self,
        nome: str,
        nome_arquivo: str = NOME_ARQUIVO_MANUAL,
    ) -> Optional[Manual]:
        """Carrega e valida um manual sem afetar os demais sistemas."""

        pasta = self.diretorio_manuais
        caminho_json = pasta / nome_arquivo

        if not caminho_json.is_file():
            logger.warning("[INICIAR] Manual não encontrado: %s", nome)
            return None

        try:
            with caminho_json.open("r", encoding="utf-8") as arquivo_json:
                dados = json.load(arquivo_json)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning(
                "[INICIAR] JSON inválido: %s",
                nome,
                exc_info=True,
            )
            return None
        except OSError:
            logger.exception(
                "[INICIAR] Erro ao ler manual.json: %s",
                nome,
            )
            return None

        embed_data = extrair_embed(dados)

        if embed_data is None:
            logger.warning("[INICIAR] Embed inválida: %s", nome)
            return None

        if not validar_embed(
            embed_data,
            nome,
            registrador=logger,
            prefixo="[INICIAR]",
        ):
            return None

        imagem_resolvida = resolver_imagem(
            pasta,
            embed_data,
            nome_base_envio=f"iniciar_{nome}",
            registrador=logger,
            prefixo="[INICIAR]",
        )

        if imagem_resolvida is None:
            return None

        attachment, nome_attachment = imagem_resolvida

        return Manual(
            nome=nome,
            pasta=pasta,
            embed_data=embed_data,
            attachment=attachment,
            nome_attachment=nome_attachment,
        )

    @staticmethod
    def preparar_envio(
        manual: Manual,
    ) -> Tuple[discord.Embed, Optional[discord.File]]:
        """Reconstrói a embed e abre o attachment somente para o envio."""

        return preparar_envio_embed(
            manual.embed_data,
            manual.attachment,
            manual.nome_attachment,
        )

    @staticmethod
    async def _responder_indisponivel(
        interaction: discord.Interaction,
        mensagem: str,
    ) -> None:
        try:
            await interaction.response.send_message(mensagem)
        except discord.Forbidden:
            logger.warning(
                "[INICIAR] Sem permissão para responder no canal %s.",
                interaction.channel,
            )
        except discord.HTTPException:
            logger.exception(
                "[INICIAR] Não foi possível enviar a mensagem de erro."
            )

    async def enviar_manual(
        self,
        interaction: discord.Interaction,
        nome: str,
        mensagem_indisponivel: str,
        nome_arquivo: str = NOME_ARQUIVO_MANUAL,
    ) -> None:
        """Executa o fluxo comum dos subcomandos do grupo /iniciar."""

        try:
            manual = self.carregar_manual(nome, nome_arquivo)
        except Exception:
            logger.exception(
                "[INICIAR] Erro inesperado ao carregar o manual: %s",
                nome,
            )
            await self._responder_indisponivel(
                interaction,
                mensagem_indisponivel,
            )
            return

        if manual is None:
            await self._responder_indisponivel(
                interaction,
                mensagem_indisponivel,
            )
            return

        arquivo = None

        try:
            embed, arquivo = self.preparar_envio(manual)
        except Exception:
            logger.exception(
                "[INICIAR] Não foi possível preparar o manual: %s",
                manual.nome,
            )
            await self._responder_indisponivel(
                interaction,
                mensagem_indisponivel,
            )
            return

        try:
            if arquivo is None:
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(
                    embed=embed,
                    file=arquivo,
                )
        except discord.Forbidden:
            logger.warning(
                "[INICIAR] Sem permissão para enviar o manual no canal %s.",
                interaction.channel,
            )
        except discord.HTTPException:
            logger.exception(
                "[INICIAR] Erro do Discord ao enviar o manual: %s",
                manual.nome,
            )
            resposta_concluida = getattr(
                interaction.response,
                "is_done",
                None,
            )

            if callable(resposta_concluida) and not resposta_concluida():
                await self._responder_indisponivel(
                    interaction,
                    mensagem_indisponivel,
                )
        except Exception:
            logger.exception(
                "[INICIAR] Erro inesperado ao executar /iniciar poção."
            )
        finally:
            if arquivo is not None:
                arquivo.close()

    @app_commands.command(
        name="poção",
        description="Mostra as instruções para preparar uma poção.",
    )
    async def iniciar_pocao(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Envia o manual fixo de poções, sem realizar sorteio."""

        await self.enviar_manual(
            interaction,
            "pocao",
            MENSAGEM_MANUAL_INDISPONIVEL,
        )


async def setup(bot: commands.Bot) -> None:
    """Adiciona o grupo /iniciar à CommandTree existente."""

    await bot.add_cog(Iniciar(bot))
