"""Sistema independente do slash command /artesanato."""

from copy import deepcopy
from dataclasses import dataclass
import json
import logging
from pathlib import Path, PurePosixPath
import random
from typing import Any, Dict, Mapping, Optional, Protocol, Tuple, cast
from urllib.parse import unquote, urlparse

import discord
from discord import app_commands
from discord.ext import commands

from utils.discohook import (
    extrair_embed,
    preparar_envio_embed,
    preparar_previa_embed,
    resolver_imagem,
    validar_embed,
)


logger = logging.getLogger(__name__)

DIRETORIO_ARTESANATO = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "artesanato"
)
NOME_ARQUIVO_RESULTADO = "resultado.json"
RESULTADOS_ARTESANATO = {
    "comum": "artesanatocomum",
    "incomum": "artesanatoincomum",
    "raro": "artesanatoraro",
    "lendario": "artesanatolendario",
    "mitico": "artesanatomitico",
}
PESOS_ARTESANATO = {
    "comum": 50,
    "incomum": 25,
    "raro": 15,
    "lendario": 8,
    "mitico": 2,
}
MENSAGEM_ARTESANATO_INDISPONIVEL = (
    "❌ O sistema de artesanato não está disponível no momento."
)
MENSAGEM_IMAGEM_ARTESANATO_INDISPONIVEL = (
    "❌ Não foi possível carregar o resultado de artesanato no momento."
)


class ProvedorCDN(Protocol):
    """Interface mínima compartilhada com a infraestrutura de /poção."""

    def consultar_cache_cdn(self, url: str) -> Optional[bool]: ...

    async def cdn_disponivel(
        self,
        url: str,
        nome_resultado: str,
    ) -> bool: ...


@dataclass(frozen=True)
class ResultadoArtesanato:
    """Dados validados de uma raridade obrigatória de artesanato."""

    raridade: str
    pasta: Path
    embed_data: Dict[str, Any]
    url_cdn: str
    attachment: Optional[Path] = None
    nome_attachment: Optional[str] = None

    @property
    def caminho_backup(self) -> Path:
        """Retorna o caminho exato do GIF local desta raridade."""

        return self.pasta / f"{self.pasta.name}.gif"


class Artesanato(commands.Cog):
    """Sorteia artesanatos e compartilha a CDN ativa de /poção."""

    def __init__(
        self,
        bot: Optional[commands.Bot],
        diretorio_artesanato: Optional[Path] = None,
        provedor_cdn: Optional[ProvedorCDN] = None,
    ) -> None:
        self.bot = bot
        self.diretorio_artesanato = Path(
            diretorio_artesanato or DIRETORIO_ARTESANATO
        )
        self._provedor_cdn_injetado = provedor_cdn

    @staticmethod
    def _provedor_cdn_valido(provedor: object) -> bool:
        return all(
            callable(getattr(provedor, nome_metodo, None))
            for nome_metodo in (
                "consultar_cache_cdn",
                "cdn_disponivel",
            )
        )

    def _obter_provedor_cdn(self) -> ProvedorCDN:
        """Resolve a instância atual de /poção para compartilhar recursos."""

        if self._provedor_cdn_injetado is not None:
            return self._provedor_cdn_injetado

        if self.bot is None:
            raise RuntimeError("Provedor CDN não configurado.")

        provedor = self.bot.get_cog("Pocoes")

        if not self._provedor_cdn_valido(provedor):
            raise RuntimeError("O Cog de poções não está disponível.")

        return cast(ProvedorCDN, provedor)

    def _consultar_cache_cdn(self, url: str) -> Optional[bool]:
        """Consulta o mesmo cache por URL utilizado por /poção."""

        return self._obter_provedor_cdn().consultar_cache_cdn(url)

    async def _cdn_disponivel(
        self,
        url: str,
        nome_resultado: str,
    ) -> bool:
        """Verifica a URL usando a sessão, os locks e TTLs de /poção."""

        return await self._obter_provedor_cdn().cdn_disponivel(
            url,
            nome_resultado,
        )

    @staticmethod
    def _obter_url_cdn(
        embed_data: Mapping[str, Any],
    ) -> Optional[str]:
        """Obtém a URL HTTP(S) da imagem principal da embed."""

        imagem = embed_data.get("image")

        if not isinstance(imagem, dict):
            return None

        url = imagem.get("url")

        if not isinstance(url, str):
            return None

        url_analisada = urlparse(url)

        if (
            url_analisada.scheme.casefold() in {"http", "https"}
            and url_analisada.netloc
        ):
            return url

        return None

    @staticmethod
    def _nome_arquivo_url(url: str) -> str:
        """Extrai o nome decodificado do arquivo indicado pela CDN."""

        return PurePosixPath(unquote(urlparse(url).path)).name

    def carregar_resultado(
        self,
        raridade: str,
    ) -> Optional[ResultadoArtesanato]:
        """Carrega e valida o resultado fixo associado à raridade."""

        nome_pasta = RESULTADOS_ARTESANATO.get(raridade)

        if nome_pasta is None:
            raise ValueError(
                f"Raridade de artesanato desconhecida: {raridade}"
            )

        pasta = self.diretorio_artesanato / nome_pasta
        caminho_json = pasta / NOME_ARQUIVO_RESULTADO

        if not caminho_json.is_file():
            logger.warning(
                "[ARTESANATO] resultado.json não encontrado: %s",
                nome_pasta,
            )
            return None

        try:
            with caminho_json.open("r", encoding="utf-8") as arquivo_json:
                dados = json.load(arquivo_json)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning(
                "[ARTESANATO] JSON inválido: %s",
                nome_pasta,
                exc_info=True,
            )
            return None
        except OSError:
            logger.exception(
                "[ARTESANATO] Erro ao ler resultado.json: %s",
                nome_pasta,
            )
            return None

        embed_data = extrair_embed(dados)

        if embed_data is None:
            logger.warning(
                "[ARTESANATO] Embed inválida: %s",
                nome_pasta,
            )
            return None

        if not validar_embed(
            embed_data,
            nome_pasta,
            registrador=logger,
            prefixo="[ARTESANATO]",
        ):
            return None

        imagem_resolvida = resolver_imagem(
            pasta,
            embed_data,
            nome_base_envio=f"imagem_{nome_pasta}",
            registrador=logger,
            prefixo="[ARTESANATO]",
        )

        if imagem_resolvida is None:
            return None

        url_cdn = self._obter_url_cdn(embed_data)

        if url_cdn is None:
            logger.error(
                "[ARTESANATO] URL CDN da imagem não encontrada: %s",
                nome_pasta,
            )
            return None

        nome_backup = f"{nome_pasta}.gif"

        if self._nome_arquivo_url(url_cdn).casefold() != nome_backup.casefold():
            logger.error(
                "[ARTESANATO] A URL CDN não aponta para %s: %s",
                nome_backup,
                nome_pasta,
            )
            return None

        attachment, nome_attachment = imagem_resolvida

        return ResultadoArtesanato(
            raridade=raridade,
            pasta=pasta,
            embed_data=embed_data,
            url_cdn=url_cdn,
            attachment=attachment,
            nome_attachment=nome_attachment,
        )

    def carregar_resultados_obrigatorios(
        self,
    ) -> Optional[Dict[str, ResultadoArtesanato]]:
        """Valida as cinco raridades sem redistribuir probabilidades."""

        if tuple(RESULTADOS_ARTESANATO) != tuple(PESOS_ARTESANATO):
            logger.error(
                "[ARTESANATO] Mapeamento de raridades incompatível com os pesos."
            )
            return None

        total_pesos = sum(PESOS_ARTESANATO.values())

        if total_pesos != 100:
            logger.error(
                "[ARTESANATO] Soma dos pesos inválida: %s; esperado: 100.",
                total_pesos,
            )
            return None

        resultados: Dict[str, ResultadoArtesanato] = {}

        for raridade in RESULTADOS_ARTESANATO:
            try:
                resultado = self.carregar_resultado(raridade)
            except Exception:
                logger.exception(
                    "[ARTESANATO] Erro inesperado na raridade obrigatória: %s",
                    raridade,
                )
                continue

            if resultado is None:
                logger.error(
                    "[ARTESANATO] Raridade obrigatória indisponível: %s",
                    raridade,
                )
                continue

            resultados[raridade] = resultado

        if len(resultados) != len(RESULTADOS_ARTESANATO):
            return None

        return resultados

    @staticmethod
    def sortear_resultado(
        resultados: Mapping[str, ResultadoArtesanato],
    ) -> ResultadoArtesanato:
        """Sorteia uma raridade com os pesos exclusivos de artesanato."""

        raridades = tuple(PESOS_ARTESANATO)
        pesos = tuple(PESOS_ARTESANATO.values())
        raridade_sorteada = random.choices(
            raridades,
            weights=pesos,
            k=1,
        )[0]
        return resultados[raridade_sorteada]

    @staticmethod
    def preparar_envio(
        resultado: ResultadoArtesanato,
    ) -> Tuple[discord.Embed, Optional[discord.File]]:
        """Reconstrói a embed sem abrir o GIF de backup da CDN."""

        return preparar_envio_embed(
            resultado.embed_data,
            resultado.attachment,
            resultado.nome_attachment,
        )

    @staticmethod
    def _preparar_previa_cdn(
        embed: discord.Embed,
    ) -> discord.Embed:
        """Preserva o texto enquanto a primeira checagem está em curso."""

        previa_sem_attachments = preparar_previa_embed(embed)
        embed_data = deepcopy(previa_sem_attachments.to_dict())
        embed_data.pop("image", None)
        return discord.Embed.from_dict(embed_data)

    @staticmethod
    def _localizar_backup_cdn(
        resultado: ResultadoArtesanato,
    ) -> Optional[Path]:
        """Valida exclusivamente o GIF de backup previsto no mapeamento."""

        backup = resultado.caminho_backup

        try:
            if (
                not backup.is_file()
                or backup.suffix.casefold() != ".gif"
                or backup.stat().st_size <= 0
            ):
                logger.error(
                    "[CDN] Backup local não encontrado: %s",
                    resultado.pasta.name,
                )
                return None
        except OSError:
            logger.exception(
                "[CDN] Não foi possível validar o backup local: %s",
                resultado.pasta.name,
            )
            return None

        return backup

    @classmethod
    def _preparar_backup_cdn(
        cls,
        resultado: ResultadoArtesanato,
    ) -> Optional[Tuple[discord.Embed, discord.File]]:
        """Troca somente a imagem em memória pelo GIF local exato."""

        backup = cls._localizar_backup_cdn(resultado)

        if backup is None:
            return None

        if (
            resultado.attachment is not None
            and resultado.attachment != backup
        ):
            logger.error(
                "[CDN] Fallback exigiria dois attachments distintos: %s",
                resultado.pasta.name,
            )
            return None

        embed_data = deepcopy(resultado.embed_data)
        imagem = embed_data.get("image")

        if not isinstance(imagem, dict):
            logger.error(
                "[CDN] Embed sem imagem para aplicar backup: %s",
                resultado.pasta.name,
            )
            return None

        imagem["url"] = f"attachment://{backup.name}"

        try:
            embed, arquivo = preparar_envio_embed(
                embed_data,
                backup,
                backup.name,
            )
        except (OSError, TypeError, ValueError):
            logger.exception(
                "[CDN] Não foi possível abrir o backup local: %s",
                resultado.pasta.name,
            )
            return None

        if arquivo is None:
            logger.error(
                "[CDN] Backup local não gerou attachment: %s",
                resultado.pasta.name,
            )
            return None

        return embed, arquivo

    @staticmethod
    async def _responder_sistema_indisponivel(
        interaction: discord.Interaction,
    ) -> None:
        try:
            await interaction.response.send_message(
                MENSAGEM_ARTESANATO_INDISPONIVEL
            )
        except discord.Forbidden:
            logger.warning(
                "[ARTESANATO] Sem permissão para responder no canal %s.",
                interaction.channel,
            )
        except discord.HTTPException:
            logger.exception(
                "[ARTESANATO] Não foi possível informar a indisponibilidade."
            )
        except Exception:
            logger.exception(
                "[ARTESANATO] Erro inesperado ao informar a indisponibilidade."
            )

    @staticmethod
    async def _responder_imagem_indisponivel(
        interaction: discord.Interaction,
        *,
        resposta_inicial_enviada: bool,
    ) -> None:
        if resposta_inicial_enviada:
            await interaction.edit_original_response(
                content=MENSAGEM_IMAGEM_ARTESANATO_INDISPONIVEL,
                embed=None,
                attachments=[],
            )
        else:
            await interaction.response.send_message(
                MENSAGEM_IMAGEM_ARTESANATO_INDISPONIVEL
            )

    @classmethod
    async def _responder_erro_inesperado(
        cls,
        interaction: discord.Interaction,
    ) -> None:
        """Evita deixar a interação aberta após uma falha de infraestrutura."""

        resposta_concluida = getattr(
            interaction.response,
            "is_done",
            None,
        )

        try:
            if callable(resposta_concluida) and resposta_concluida():
                await interaction.edit_original_response(
                    content=MENSAGEM_IMAGEM_ARTESANATO_INDISPONIVEL,
                    embed=None,
                    attachments=[],
                )
            else:
                await interaction.response.send_message(
                    MENSAGEM_IMAGEM_ARTESANATO_INDISPONIVEL
                )
        except discord.Forbidden:
            logger.warning(
                "[ARTESANATO] Sem permissão para informar a falha no canal %s.",
                interaction.channel,
            )
        except discord.HTTPException:
            logger.exception(
                "[ARTESANATO] Não foi possível informar a falha do resultado."
            )
        except Exception:
            logger.exception(
                "[ARTESANATO] Erro inesperado ao informar a falha do resultado."
            )

    async def _enviar_backup_cdn(
        self,
        interaction: discord.Interaction,
        resultado: ResultadoArtesanato,
        *,
        resposta_inicial_enviada: bool,
    ) -> None:
        try:
            preparado = self._preparar_backup_cdn(resultado)
        except Exception:
            logger.exception(
                "[CDN] Erro inesperado ao preparar o backup: %s",
                resultado.pasta.name,
            )
            preparado = None

        if preparado is None:
            await self._responder_imagem_indisponivel(
                interaction,
                resposta_inicial_enviada=resposta_inicial_enviada,
            )
            return

        embed, arquivo = preparado

        try:
            logger.info(
                "[CDN] Usando backup local: %s",
                resultado.pasta.name,
            )

            if not resposta_inicial_enviada:
                previa = preparar_previa_embed(embed)
                await interaction.response.send_message(embed=previa)

            await interaction.edit_original_response(
                embed=embed,
                attachments=[arquivo],
            )
        finally:
            arquivo.close()

    async def _enviar_resultado_cdn(
        self,
        interaction: discord.Interaction,
        resultado: ResultadoArtesanato,
    ) -> None:
        """Usa a CDN principal e recorre ao GIF local sem novo sorteio."""

        estado_em_cache = self._consultar_cache_cdn(resultado.url_cdn)

        if estado_em_cache is False:
            await self._enviar_backup_cdn(
                interaction,
                resultado,
                resposta_inicial_enviada=False,
            )
            return

        embed, arquivo = self.preparar_envio(resultado)

        try:
            if estado_em_cache is True:
                if arquivo is None:
                    await interaction.response.send_message(embed=embed)
                else:
                    previa = preparar_previa_embed(embed)
                    await interaction.response.send_message(embed=previa)
                    await interaction.edit_original_response(
                        embed=embed,
                        attachments=[arquivo],
                    )
                return

            previa = self._preparar_previa_cdn(embed)
            await interaction.response.send_message(embed=previa)

            if await self._cdn_disponivel(
                resultado.url_cdn,
                resultado.pasta.name,
            ):
                if arquivo is None:
                    await interaction.edit_original_response(embed=embed)
                else:
                    await interaction.edit_original_response(
                        embed=embed,
                        attachments=[arquivo],
                    )
                return

            if arquivo is not None:
                arquivo.close()
                arquivo = None

            await self._enviar_backup_cdn(
                interaction,
                resultado,
                resposta_inicial_enviada=True,
            )
        finally:
            if arquivo is not None:
                arquivo.close()

    @app_commands.command(
        name="artesanato",
        description="Cria um item e descobre o resultado do artesanato.",
    )
    async def artesanato(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Valida as raridades, sorteia uma vez e envia sua embed."""

        try:
            resultados = self.carregar_resultados_obrigatorios()
        except Exception:
            logger.exception(
                "[ARTESANATO] Não foi possível validar os resultados."
            )
            await self._responder_sistema_indisponivel(interaction)
            return

        if resultados is None:
            await self._responder_sistema_indisponivel(interaction)
            return

        try:
            resultado = self.sortear_resultado(resultados)
            logger.info(
                "[ARTESANATO] Resultado sorteado: %s",
                resultado.raridade,
            )
        except Exception:
            logger.exception(
                "[ARTESANATO] Não foi possível sortear o resultado."
            )
            await self._responder_sistema_indisponivel(interaction)
            return

        try:
            await self._enviar_resultado_cdn(interaction, resultado)
        except discord.Forbidden:
            logger.warning(
                "[ARTESANATO] Sem permissão para enviar no canal %s.",
                interaction.channel,
            )
        except discord.HTTPException:
            logger.exception(
                "[ARTESANATO] Erro do Discord ao enviar o resultado: %s",
                resultado.pasta.name,
            )
        except (OSError, ValueError, TypeError):
            logger.exception(
                "[ARTESANATO] Não foi possível preparar o resultado: %s",
                resultado.pasta.name,
            )
            await self._responder_erro_inesperado(interaction)
        except Exception:
            logger.exception(
                "[ARTESANATO] Erro inesperado ao executar /artesanato."
            )
            await self._responder_erro_inesperado(interaction)


async def setup(bot: commands.Bot) -> None:
    """Adiciona /artesanato à CommandTree já existente."""

    if not Artesanato._provedor_cdn_valido(bot.get_cog("Pocoes")):
        raise RuntimeError(
            "cogs.pocoes deve ser carregado antes de cogs.artesanato."
        )

    await bot.add_cog(Artesanato(bot))
