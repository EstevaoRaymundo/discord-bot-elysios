"""Sistemas locais dos slash commands /poção e /estabilidade."""

import asyncio
from copy import deepcopy
from dataclasses import dataclass
import json
import logging
from pathlib import Path, PurePosixPath
import random
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import unquote, urlparse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from utils.discohook import (
    EXTENSOES_IMAGEM,
    extrair_embed,
    listar_imagens,
    localizar_attachment,
    preparar_previa_embed,
    preparar_envio_embed,
    resolver_imagem,
    validar_embed,
)


logger = logging.getLogger(__name__)

DIRETORIO_RESULTADOS = (
    Path(__file__).resolve().parent.parent
    / "data"
)
DIRETORIO_ESTABILIDADE = DIRETORIO_RESULTADOS / "estabilidade"
NOME_ARQUIVO_RESULTADO = "resultado.json"
DIRETORIOS_RESERVADOS = frozenset(
    {"artesanato", "estabilidade", "manuais"}
)
PESOS_RARIDADES = {
    "pocao_comum": 50,
    "pocao_incomum": 25,
    "pocao_rara": 15,
    "pocao_lendaria": 8,
    "pocao_mitica": 2,
}
CDN_CACHE_OK_TTL = 600.0
CDN_CACHE_FAIL_TTL = 60.0
CDN_HTTP_TIMEOUT = 2.0
STATUS_HEAD_NAO_SUPORTADO = frozenset({405, 501})
MENSAGEM_POCOES_INDISPONIVEL = (
    "❌ O sistema de poções não está disponível no momento."
)
MENSAGEM_IMAGEM_POCAO_INDISPONIVEL = (
    "❌ Não foi possível carregar o resultado da poção no momento."
)
RESULTADOS_ESTABILIDADE = ("estavel", "instavel")
MENSAGEM_ESTABILIDADE_INDISPONIVEL = (
    "❌ O sistema de estabilidade não está disponível no momento."
)


@dataclass(frozen=True)
class ResultadoPocao:
    """Dados validados de uma pasta que pode participar do sorteio."""

    pasta: Path
    embed_data: Dict[str, Any]
    attachment: Optional[Path] = None
    nome_attachment: Optional[str] = None


@dataclass(frozen=True)
class EstadoCacheCDN:
    """Disponibilidade temporária de uma URL remota."""

    disponivel: bool
    verificado_em: float


@dataclass(frozen=True)
class ResultadoEstabilidade:
    """Dados validados de um resultado obrigatório de estabilidade."""

    nome: str
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
        self._sessao_http: Optional[aiohttp.ClientSession] = None
        self._lock_sessao_http = asyncio.Lock()
        self._sessao_http_encerrada = False
        self._cache_cdn: Dict[str, EstadoCacheCDN] = {}
        self._locks_cdn: Dict[str, asyncio.Lock] = {}

    async def cog_load(self) -> None:
        """Cria a sessão HTTP única usada enquanto o Cog estiver ativo."""

        async with self._lock_sessao_http:
            self._sessao_http_encerrada = False

        await self._obter_sessao_http()

    async def cog_unload(self) -> None:
        """Fecha a sessão HTTP quando o Cog for descarregado."""

        async with self._lock_sessao_http:
            self._sessao_http_encerrada = True
            sessao = self._sessao_http
            self._sessao_http = None

        if sessao is not None and not sessao.closed:
            await sessao.close()

    async def _obter_sessao_http(self) -> aiohttp.ClientSession:
        """Retorna a sessão compartilhada, com criação lazy defensiva."""

        if self._sessao_http_encerrada:
            raise RuntimeError("A sessão HTTP do Cog já foi encerrada.")

        sessao = self._sessao_http

        if sessao is not None and not sessao.closed:
            return sessao

        async with self._lock_sessao_http:
            if self._sessao_http_encerrada:
                raise RuntimeError("A sessão HTTP do Cog já foi encerrada.")

            sessao = self._sessao_http

            if sessao is None or sessao.closed:
                sessao = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(
                        total=CDN_HTTP_TIMEOUT
                    )
                )
                self._sessao_http = sessao

        return sessao

    @staticmethod
    def _status_http_disponivel(status: int) -> bool:
        return 200 <= status < 400

    @classmethod
    async def _requisitar_url_cdn(
        cls,
        sessao: aiohttp.ClientSession,
        url: str,
    ) -> bool:
        """Executa HEAD e usa um GET mínimo se HEAD não for aceito."""

        async with sessao.head(
            url,
            allow_redirects=True,
        ) as resposta:
            status_head = resposta.status

        if status_head not in STATUS_HEAD_NAO_SUPORTADO:
            return cls._status_http_disponivel(status_head)

        async with sessao.get(
            url,
            allow_redirects=True,
            headers={"Range": "bytes=0-0"},
        ) as resposta:
            disponivel = cls._status_http_disponivel(resposta.status)

            if disponivel:
                await resposta.content.read(1)

            return disponivel

    async def _verificar_url_cdn(self, url: str) -> bool:
        """Verifica uma URL sem bloquear o event loop nem baixar a imagem."""

        try:
            sessao = await self._obter_sessao_http()
            return await asyncio.wait_for(
                self._requisitar_url_cdn(sessao, url),
                timeout=CDN_HTTP_TIMEOUT,
            )
        except (TimeoutError, aiohttp.ClientError, RuntimeError):
            return False

    def _consultar_cache_cdn(self, url: str) -> Optional[bool]:
        """Retorna um estado ainda válido sem realizar I/O HTTP."""

        estado = self._cache_cdn.get(url)

        if estado is None:
            return None

        ttl = (
            CDN_CACHE_OK_TTL
            if estado.disponivel
            else CDN_CACHE_FAIL_TTL
        )

        if time.monotonic() - estado.verificado_em < ttl:
            return estado.disponivel

        return None

    def consultar_cache_cdn(self, url: str) -> Optional[bool]:
        """Expõe o cache por URL para outros sistemas do mesmo bot."""

        return self._consultar_cache_cdn(url)

    async def _cdn_disponivel(
        self,
        url: str,
        nome_resultado: str,
    ) -> bool:
        """Consulta o cache e verifica somente a URL exigida pelo sorteio."""

        estado_em_cache = self._consultar_cache_cdn(url)

        if estado_em_cache is not None:
            return estado_em_cache

        lock = self._locks_cdn.setdefault(url, asyncio.Lock())

        async with lock:
            estado_em_cache = self._consultar_cache_cdn(url)

            if estado_em_cache is not None:
                return estado_em_cache

            estado_anterior = self._cache_cdn.get(url)
            logger.info("[CDN] Verificando: %s", nome_resultado)

            try:
                disponivel = await self._verificar_url_cdn(url)
            except Exception:
                logger.exception(
                    "[CDN] Erro inesperado ao verificar: %s",
                    nome_resultado,
                )
                disponivel = False

            self._cache_cdn[url] = EstadoCacheCDN(
                disponivel=disponivel,
                verificado_em=time.monotonic(),
            )

            if disponivel:
                if (
                    estado_anterior is not None
                    and not estado_anterior.disponivel
                ):
                    logger.info(
                        "[CDN] CDN voltou a responder: %s",
                        nome_resultado,
                    )
                else:
                    logger.info(
                        "[CDN] Disponível: %s",
                        nome_resultado,
                    )
            else:
                logger.warning(
                    "[CDN] Indisponível: %s (%s)",
                    nome_resultado,
                    url,
                )

            return disponivel

    async def cdn_disponivel(
        self,
        url: str,
        nome_resultado: str,
    ) -> bool:
        """Compartilha a sessão, o cache e os TTLs ativos do Cog."""

        return await self._cdn_disponivel(url, nome_resultado)

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

    def carregar_resultados_obrigatorios(
        self,
    ) -> Optional[Dict[str, ResultadoPocao]]:
        """Valida as cinco raridades sem redistribuir pesos ausentes."""

        total_pesos = sum(PESOS_RARIDADES.values())

        if total_pesos != 100:
            logger.error(
                "[POÇÕES] Soma dos pesos inválida: %s; esperado: 100.",
                total_pesos,
            )
            return None

        resultados: Dict[str, ResultadoPocao] = {}

        for nome_raridade in PESOS_RARIDADES:
            pasta = self.diretorio_resultados / nome_raridade

            try:
                resultado = self.carregar_resultado(pasta)
            except Exception:
                logger.exception(
                    "[POÇÕES] Erro inesperado na raridade obrigatória: %s",
                    nome_raridade,
                )
                continue

            if resultado is None:
                logger.error(
                    "[POÇÕES] Raridade obrigatória indisponível: %s",
                    nome_raridade,
                )
                continue

            resultados[nome_raridade] = resultado

        if len(resultados) != len(PESOS_RARIDADES):
            return None

        return resultados

    @staticmethod
    def sortear_resultado(
        resultados: Mapping[str, ResultadoPocao],
    ) -> ResultadoPocao:
        """Sorteia uma das cinco raridades usando os pesos oficiais."""

        raridades = tuple(PESOS_RARIDADES)
        pesos = tuple(PESOS_RARIDADES.values())
        raridade_sorteada = random.choices(
            raridades,
            weights=pesos,
            k=1,
        )[0]
        return resultados[raridade_sorteada]

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

    @staticmethod
    def _obter_url_cdn(resultado: ResultadoPocao) -> Optional[str]:
        """Obtém a URL HTTP(S) da imagem principal, quando houver."""

        imagem = resultado.embed_data.get("image")

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
    def _preparar_previa_cdn(
        embed: discord.Embed,
    ) -> discord.Embed:
        """Preserva o texto e remove a imagem até a primeira checagem."""

        previa_sem_attachments = preparar_previa_embed(embed)
        embed_data = deepcopy(previa_sem_attachments.to_dict())
        embed_data.pop("image", None)
        return discord.Embed.from_dict(embed_data)

    @staticmethod
    def _localizar_backup_cdn(
        resultado: ResultadoPocao,
        url: str,
    ) -> Optional[Path]:
        """Reutiliza a associação local exata/normalizada/única."""

        nome_esperado = PurePosixPath(
            unquote(urlparse(url).path)
        ).name

        if not nome_esperado:
            logger.error(
                "[CDN] Backup local não encontrado para: %s",
                resultado.pasta.name,
            )
            return None

        backup = localizar_attachment(
            resultado.pasta,
            f"attachment://{nome_esperado}",
            registrador=logger,
            prefixo="[CDN]",
        )

        if backup is None:
            logger.error(
                "[CDN] Backup local não encontrado para: %s",
                resultado.pasta.name,
            )

        return backup

    @classmethod
    def _preparar_backup_cdn(
        cls,
        resultado: ResultadoPocao,
        url: str,
    ) -> Optional[Tuple[discord.Embed, discord.File]]:
        """Troca somente a cópia em memória por ``attachment://``."""

        backup = cls._localizar_backup_cdn(resultado, url)

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

        nome_attachment = f"imagem_pocao{backup.suffix.casefold()}"
        imagem["url"] = f"attachment://{backup.name}"

        try:
            embed, arquivo = preparar_envio_embed(
                embed_data,
                backup,
                nome_attachment,
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
    async def _responder_imagem_indisponivel(
        interaction: discord.Interaction,
        *,
        resposta_inicial_enviada: bool,
    ) -> None:
        if resposta_inicial_enviada:
            await interaction.edit_original_response(
                content=MENSAGEM_IMAGEM_POCAO_INDISPONIVEL,
                embed=None,
                attachments=[],
            )
        else:
            await interaction.response.send_message(
                MENSAGEM_IMAGEM_POCAO_INDISPONIVEL
            )

    async def _enviar_backup_cdn(
        self,
        interaction: discord.Interaction,
        resultado: ResultadoPocao,
        url: str,
        *,
        resposta_inicial_enviada: bool,
    ) -> None:
        try:
            preparado = self._preparar_backup_cdn(resultado, url)
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
        resultado: ResultadoPocao,
        url: str,
    ) -> None:
        """Usa a CDN como fonte principal e o arquivo local como backup."""

        estado_em_cache = self._consultar_cache_cdn(url)

        if estado_em_cache is False:
            await self._enviar_backup_cdn(
                interaction,
                resultado,
                url,
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

            if await self._cdn_disponivel(url, resultado.pasta.name):
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
                url,
                resposta_inicial_enviada=True,
            )
        finally:
            if arquivo is not None:
                arquivo.close()

    @app_commands.command(
        name="poção",
        description="Prepara uma poção e descobre o resultado.",
    )
    async def pocao(self, interaction: discord.Interaction) -> None:
        """Sorteia e envia um dos resultados válidos no canal atual."""

        resultados = self.carregar_resultados_obrigatorios()

        if resultados is None:
            try:
                await interaction.response.send_message(
                    MENSAGEM_POCOES_INDISPONIVEL
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
            url_cdn = self._obter_url_cdn(resultado)

            if url_cdn is not None:
                await self._enviar_resultado_cdn(
                    interaction,
                    resultado,
                    url_cdn,
                )
                return

            embed, arquivo = self.preparar_envio(resultado)

            if arquivo is None:
                await interaction.response.send_message(embed=embed)
            else:
                previa = preparar_previa_embed(embed)
                await interaction.response.send_message(embed=previa)

                await interaction.edit_original_response(
                    embed=embed,
                    attachments=[arquivo],
                )
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


class Estabilidade(commands.Cog):
    """Determina a estabilidade com uma escolha binária uniforme."""

    def __init__(
        self,
        bot: Optional[commands.Bot],
        diretorio_estabilidade: Optional[Path] = None,
    ) -> None:
        self.bot = bot
        self.diretorio_estabilidade = Path(
            diretorio_estabilidade or DIRETORIO_ESTABILIDADE
        )

    def carregar_resultado(
        self,
        nome: str,
    ) -> Optional[ResultadoEstabilidade]:
        """Carrega um dos dois resultados fixos de estabilidade."""

        if nome not in RESULTADOS_ESTABILIDADE:
            raise ValueError(
                f"Resultado de estabilidade desconhecido: {nome}"
            )

        pasta = self.diretorio_estabilidade / nome
        caminho_json = pasta / NOME_ARQUIVO_RESULTADO

        if not caminho_json.is_file():
            logger.warning(
                "[ESTABILIDADE] resultado.json não encontrado: %s",
                nome,
            )
            return None

        try:
            with caminho_json.open("r", encoding="utf-8") as arquivo_json:
                dados = json.load(arquivo_json)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning(
                "[ESTABILIDADE] JSON inválido: %s",
                nome,
                exc_info=True,
            )
            return None
        except OSError:
            logger.exception(
                "[ESTABILIDADE] Erro ao ler resultado.json: %s",
                nome,
            )
            return None

        embed_data = extrair_embed(dados)

        if embed_data is None:
            logger.warning(
                "[ESTABILIDADE] Embed inválida: %s",
                nome,
            )
            return None

        if not validar_embed(
            embed_data,
            nome,
            registrador=logger,
            prefixo="[ESTABILIDADE]",
        ):
            return None

        imagem_resolvida = resolver_imagem(
            pasta,
            embed_data,
            nome_base_envio=f"estabilidade_{nome}",
            registrador=logger,
            prefixo="[ESTABILIDADE]",
        )

        if imagem_resolvida is None:
            return None

        attachment, nome_attachment = imagem_resolvida

        return ResultadoEstabilidade(
            nome=nome,
            pasta=pasta,
            embed_data=embed_data,
            attachment=attachment,
            nome_attachment=nome_attachment,
        )

    def carregar_resultados_obrigatorios(
        self,
    ) -> Optional[Dict[str, ResultadoEstabilidade]]:
        """Valida estável e instável antes de permitir qualquer sorteio."""

        resultados: Dict[str, ResultadoEstabilidade] = {}

        for nome in RESULTADOS_ESTABILIDADE:
            try:
                resultado = self.carregar_resultado(nome)
            except Exception:
                logger.exception(
                    "[ESTABILIDADE] Erro inesperado ao carregar: %s",
                    nome,
                )
                continue

            if resultado is not None:
                resultados[nome] = resultado

        if len(resultados) != len(RESULTADOS_ESTABILIDADE):
            return None

        return resultados

    @staticmethod
    def sortear_resultado(
        resultados: Mapping[str, ResultadoEstabilidade],
    ) -> ResultadoEstabilidade:
        """Escolhe entre dois nomes fixos, sem consultar arquivos ou pastas."""

        nome_sorteado = random.choice(RESULTADOS_ESTABILIDADE)
        return resultados[nome_sorteado]

    @staticmethod
    def preparar_envio(
        resultado: ResultadoEstabilidade,
    ) -> Tuple[discord.Embed, Optional[discord.File]]:
        """Reconstrói a embed e abre somente o attachment sorteado."""

        return preparar_envio_embed(
            resultado.embed_data,
            resultado.attachment,
            resultado.nome_attachment,
        )

    @staticmethod
    async def _responder_indisponivel(
        interaction: discord.Interaction,
    ) -> None:
        try:
            await interaction.response.send_message(
                MENSAGEM_ESTABILIDADE_INDISPONIVEL
            )
        except discord.Forbidden:
            logger.warning(
                "[ESTABILIDADE] Sem permissão para responder no canal %s.",
                interaction.channel,
            )
        except discord.HTTPException:
            logger.exception(
                "[ESTABILIDADE] Não foi possível informar a indisponibilidade."
            )
        except Exception:
            logger.exception(
                "[ESTABILIDADE] Erro inesperado ao informar a indisponibilidade."
            )

    @app_commands.command(
        name="estabilidade",
        description="Determina se a poção criada ficou estável ou instável.",
    )
    async def estabilidade(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Valida o par obrigatório, sorteia 50/50 e envia sua embed."""

        try:
            resultados = self.carregar_resultados_obrigatorios()
        except Exception:
            logger.exception(
                "[ESTABILIDADE] Não foi possível validar os resultados."
            )
            await self._responder_indisponivel(interaction)
            return

        if resultados is None:
            await self._responder_indisponivel(interaction)
            return

        arquivo = None

        try:
            resultado = self.sortear_resultado(resultados)
            embed, arquivo = self.preparar_envio(resultado)
        except Exception:
            logger.exception(
                "[ESTABILIDADE] Não foi possível preparar o resultado."
            )
            await self._responder_indisponivel(interaction)
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
                "[ESTABILIDADE] Sem permissão para enviar no canal %s.",
                interaction.channel,
            )
        except discord.HTTPException:
            logger.exception(
                "[ESTABILIDADE] Erro do Discord ao enviar o resultado: %s",
                resultado.nome,
            )

            resposta_concluida = getattr(
                interaction.response,
                "is_done",
                None,
            )

            if callable(resposta_concluida) and not resposta_concluida():
                await self._responder_indisponivel(interaction)
        except Exception:
            logger.exception(
                "[ESTABILIDADE] Erro inesperado ao executar /estabilidade."
            )

            resposta_concluida = getattr(
                interaction.response,
                "is_done",
                None,
            )

            if callable(resposta_concluida) and not resposta_concluida():
                await self._responder_indisponivel(interaction)
        finally:
            if arquivo is not None:
                arquivo.close()


async def setup(bot: commands.Bot) -> None:
    """Carrega os Cogs na CommandTree já pertencente ao bot."""

    await bot.add_cog(Pocoes(bot))
    await bot.add_cog(Estabilidade(bot))
