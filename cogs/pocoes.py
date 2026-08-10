"""Sistema local de resultados para o slash command /poção."""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from utils.discohook import (
    EXTENSOES_IMAGEM,
    extrair_embed,
    listar_imagens,
    localizar_attachment,
    preparar_envio_embed,
    resolver_imagem,
    validar_embed,
)


logger = logging.getLogger(__name__)

DIRETORIO_RESULTADOS = (
    Path(__file__).resolve().parent.parent
    / "data"
)
NOME_ARQUIVO_RESULTADO = "resultado.json"
DIRETORIOS_RESERVADOS = frozenset({"manuais"})


@dataclass(frozen=True)
class ResultadoPocao:
    """Dados validados de uma pasta que pode participar do sorteio."""

    pasta: Path
    embed_data: Dict[str, Any]
    attachment: Optional[Path] = None
    nome_attachment: Optional[str] = None


class Pocoes(commands.Cog):
    """Descobre e sorteia embeds de poções armazenadas localmente."""

    def __init__(
        self,
        bot: Optional[commands.Bot],
        diretorio_resultados: Optional[Path] = None,
    ) -> None:
        self.bot = bot
        self.diretorio_resultados = Path(
            diretorio_resultados or DIRETORIO_RESULTADOS
        )

    def encontrar_pastas(self) -> List[Path]:
        """Lista somente as subpastas imediatas de resultados."""

        try:
            if not self.diretorio_resultados.is_dir():
                logger.warning(
                    "[POÇÕES] Diretório de resultados não encontrado: %s",
                    self.diretorio_resultados,
                )
                return []

            return sorted(
                (
                    caminho
                    for caminho in self.diretorio_resultados.iterdir()
                    if (
                        caminho.is_dir()
                        and caminho.name.casefold()
                        not in DIRETORIOS_RESERVADOS
                    )
                ),
                key=lambda caminho: caminho.name.casefold(),
            )
        except OSError:
            logger.exception(
                "[POÇÕES] Não foi possível ler o diretório de resultados: %s",
                self.diretorio_resultados,
            )
            return []

    @staticmethod
    def _validar_embed(
        embed_data: Dict[str, Any],
        nome_resultado: str,
    ) -> bool:
        return validar_embed(
            embed_data,
            nome_resultado,
            registrador=logger,
            prefixo="[POÇÕES]",
        )

    @staticmethod
    def _listar_imagens(pasta: Path) -> List[Path]:
        return listar_imagens(pasta)

    @classmethod
    def _localizar_attachment(
        cls,
        pasta: Path,
        url: str,
    ) -> Optional[Path]:
        return localizar_attachment(
            pasta,
            url,
            registrador=logger,
            prefixo="[POÇÕES]",
        )

    @classmethod
    def _resolver_imagem(
        cls,
        pasta: Path,
        embed_data: Dict[str, Any],
    ) -> Optional[Tuple[Optional[Path], Optional[str]]]:
        return resolver_imagem(
            pasta,
            embed_data,
            nome_base_envio="imagem_pocao",
            registrador=logger,
            prefixo="[POÇÕES]",
        )

    def carregar_resultado(self, pasta: Path) -> Optional[ResultadoPocao]:
        """Carrega uma pasta, isolando qualquer falha daquele resultado."""

        caminho_json = pasta / NOME_ARQUIVO_RESULTADO

        if not caminho_json.is_file():
            logger.warning(
                "[POÇÕES] resultado.json não encontrado: %s",
                pasta.name,
            )
            return None

        try:
            with caminho_json.open("r", encoding="utf-8") as arquivo_json:
                dados = json.load(arquivo_json)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning(
                "[POÇÕES] JSON inválido ignorado: %s",
                pasta.name,
                exc_info=True,
            )
            return None
        except OSError:
            logger.exception(
                "[POÇÕES] Erro ao ler resultado.json: %s",
                pasta.name,
            )
            return None

        embed_data = extrair_embed(dados)

        if embed_data is None:
            logger.warning(
                "[POÇÕES] Embed inválida: %s",
                pasta.name,
            )
            return None

        if not self._validar_embed(embed_data, pasta.name):
            return None

        imagem_resolvida = self._resolver_imagem(pasta, embed_data)

        if imagem_resolvida is None:
            return None

        attachment, nome_attachment = imagem_resolvida

        return ResultadoPocao(
            pasta=pasta,
            embed_data=embed_data,
            attachment=attachment,
            nome_attachment=nome_attachment,
        )

    def carregar_resultados(self) -> List[ResultadoPocao]:
        """Descobre novamente todos os resultados válidos."""

        resultados = []

        for pasta in self.encontrar_pastas():
            try:
                resultado = self.carregar_resultado(pasta)
            except Exception:
                logger.exception(
                    "[POÇÕES] Resultado ignorado por erro inesperado: %s",
                    pasta.name,
                )
                continue

            if resultado is not None:
                resultados.append(resultado)

        return resultados

    @staticmethod
    def sortear_resultado(
        resultados: Sequence[ResultadoPocao],
    ) -> ResultadoPocao:
        """Mantém o sorteio uniforme isolado para aceitar pesos no futuro."""

        return random.choice(resultados)

    @staticmethod
    def preparar_envio(
        resultado: ResultadoPocao,
    ) -> Tuple[discord.Embed, Optional[discord.File]]:
        """Reconstrói a embed e abre somente o attachment sorteado."""

        return preparar_envio_embed(
            resultado.embed_data,
            resultado.attachment,
            resultado.nome_attachment,
        )

    @app_commands.command(
        name="poção",
        description="Prepara uma poção e descobre o resultado.",
    )
    async def pocao(self, interaction: discord.Interaction) -> None:
        """Sorteia e envia um dos resultados válidos no canal atual."""

        resultados = self.carregar_resultados()

        if not resultados:
            try:
                await interaction.response.send_message(
                    "❌ Nenhum resultado de poção está cadastrado no momento."
                )
            except discord.Forbidden:
                logger.warning(
                    "[POÇÕES] Sem permissão para responder no canal %s.",
                    interaction.channel,
                )
            except discord.HTTPException:
                logger.exception(
                    "[POÇÕES] Não foi possível informar a ausência de resultados."
                )
            return

        resultado = self.sortear_resultado(resultados)
        arquivo = None

        try:
            embed, arquivo = self.preparar_envio(resultado)
            argumentos = {
                "content": (
                    f"⚗️ {interaction.user.mention}, seu resultado foi:"
                ),
                "embed": embed,
            }

            if arquivo is not None:
                argumentos["file"] = arquivo

            await interaction.response.send_message(**argumentos)
        except discord.Forbidden:
            logger.warning(
                "[POÇÕES] Sem permissão para enviar o resultado no canal %s.",
                interaction.channel,
            )
        except discord.HTTPException:
            logger.exception(
                "[POÇÕES] Erro do Discord ao enviar o resultado: %s",
                resultado.pasta.name,
            )
        except (OSError, ValueError, TypeError):
            logger.exception(
                "[POÇÕES] Não foi possível preparar o resultado: %s",
                resultado.pasta.name,
            )
        except Exception:
            logger.exception(
                "[POÇÕES] Erro inesperado ao executar /poção."
            )
        finally:
            if arquivo is not None:
                arquivo.close()


async def setup(bot: commands.Bot) -> None:
    """Carrega o Cog na CommandTree já pertencente ao bot."""

    await bot.add_cog(Pocoes(bot))
