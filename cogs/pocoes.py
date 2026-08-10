"""Sistema local de resultados para o slash command /poção."""

from copy import deepcopy
from dataclasses import dataclass
import json
import logging
from pathlib import Path, PurePosixPath
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple
import unicodedata
from urllib.parse import unquote, urlparse

import discord
from discord import app_commands
from discord.ext import commands


logger = logging.getLogger(__name__)

DIRETORIO_RESULTADOS = (
    Path(__file__).resolve().parent.parent
    / "data"
)
NOME_ARQUIVO_RESULTADO = "resultado.json"
EXTENSOES_IMAGEM = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})


@dataclass(frozen=True)
class ResultadoPocao:
    """Dados validados de uma pasta que pode participar do sorteio."""

    pasta: Path
    embed_data: Dict[str, Any]
    attachment: Optional[Path] = None
    nome_attachment: Optional[str] = None


def extrair_embed(dados: object) -> Optional[Dict[str, Any]]:
    """Extrai ``embeds[0]`` do payload principal exportado pelo Discohook."""

    if not isinstance(dados, dict):
        return None

    embeds = dados.get("embeds")

    if not isinstance(embeds, list) or not embeds:
        return None

    primeira_embed = embeds[0]

    if not isinstance(primeira_embed, dict) or not primeira_embed:
        return None

    return primeira_embed


def _normalizar_nome(nome: str) -> str:
    """Cria uma chave apenas para comparar nomes de arquivos locais."""

    sem_acentos = unicodedata.normalize("NFKD", nome)
    sem_acentos = "".join(
        caractere
        for caractere in sem_acentos
        if not unicodedata.combining(caractere)
    )
    return "".join(
        caractere
        for caractere in sem_acentos.casefold()
        if caractere.isalnum()
    )


def _nome_referenciado(url: str) -> str:
    """Obtém somente o basename seguro de uma URL ``attachment://``."""

    nome = unquote(url.split("://", maxsplit=1)[1])
    return PurePosixPath(nome).name


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
                    if caminho.is_dir()
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
        try:
            embed = discord.Embed.from_dict(embed_data)
        except Exception:
            logger.warning(
                "[POÇÕES] Embed inválida: %s",
                nome_resultado,
                exc_info=True,
            )
            return False

        if not embed:
            logger.warning(
                "[POÇÕES] Embed vazia ignorada: %s",
                nome_resultado,
            )
            return False

        return True

    @staticmethod
    def _listar_imagens(pasta: Path) -> List[Path]:
        imagens = []

        for caminho in pasta.iterdir():
            if (
                caminho.is_file()
                and caminho.suffix.casefold() in EXTENSOES_IMAGEM
                and caminho.stat().st_size > 0
            ):
                imagens.append(caminho)

        return sorted(imagens, key=lambda caminho: caminho.name.casefold())

    @classmethod
    def _localizar_attachment(
        cls,
        pasta: Path,
        url: str,
    ) -> Optional[Path]:
        try:
            imagens = cls._listar_imagens(pasta)
        except OSError:
            logger.exception(
                "[POÇÕES] Não foi possível ler os attachments: %s",
                pasta.name,
            )
            return None

        if not imagens:
            logger.warning(
                "[POÇÕES] Attachment local não encontrado: %s",
                pasta.name,
            )
            return None

        nome_esperado = _nome_referenciado(url)
        correspondencias = [
            caminho
            for caminho in imagens
            if caminho.name.casefold() == nome_esperado.casefold()
        ]

        if len(correspondencias) == 1:
            return correspondencias[0]

        nome_normalizado = _normalizar_nome(nome_esperado)
        correspondencias = [
            caminho
            for caminho in imagens
            if _normalizar_nome(caminho.name) == nome_normalizado
        ]

        if len(correspondencias) == 1:
            return correspondencias[0]

        if len(imagens) == 1:
            return imagens[0]

        logger.warning(
            "[POÇÕES] Attachment local ambíguo: %s",
            pasta.name,
        )
        return None

    @classmethod
    def _resolver_imagem(
        cls,
        pasta: Path,
        embed_data: Dict[str, Any],
    ) -> Optional[Tuple[Optional[Path], Optional[str]]]:
        imagem = embed_data.get("image")

        if imagem is None:
            return None, None

        if not isinstance(imagem, dict):
            logger.warning("[POÇÕES] Imagem inválida: %s", pasta.name)
            return None

        url = imagem.get("url")

        if not isinstance(url, str) or not url:
            logger.warning("[POÇÕES] URL de imagem inválida: %s", pasta.name)
            return None

        url_analisada = urlparse(url)
        esquema = url_analisada.scheme.casefold()

        if esquema in {"http", "https"}:
            if not url_analisada.netloc:
                logger.warning(
                    "[POÇÕES] URL de imagem inválida: %s",
                    pasta.name,
                )
                return None

            return None, None

        if esquema != "attachment":
            logger.warning(
                "[POÇÕES] URL de imagem não suportada ignorada: %s",
                pasta.name,
            )
            return None

        nome_referenciado = _nome_referenciado(url)

        if not nome_referenciado:
            logger.warning(
                "[POÇÕES] Nome de attachment inválido: %s",
                pasta.name,
            )
            return None

        attachment = cls._localizar_attachment(pasta, url)

        if attachment is None:
            return None

        nome_envio = f"imagem_pocao{attachment.suffix.casefold()}"
        return attachment, nome_envio

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

        embed_data = deepcopy(resultado.embed_data)
        arquivo = None

        if resultado.attachment is not None:
            nome_attachment = resultado.nome_attachment

            if nome_attachment is None:
                raise ValueError("Attachment sem nome de envio.")

            embed_data["image"]["url"] = (
                f"attachment://{nome_attachment}"
            )
            arquivo = discord.File(
                resultado.attachment,
                filename=nome_attachment,
            )

        try:
            embed = discord.Embed.from_dict(embed_data)
        except Exception:
            if arquivo is not None:
                arquivo.close()
            raise

        return embed, arquivo

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
