"""Sistema independente do slash command /ingredientes."""

import asyncio
from copy import deepcopy
from dataclasses import dataclass
import json
import logging
import math
from pathlib import Path
import random
import time
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Tuple, cast

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from utils.discohook import (
    EXTENSOES_IMAGEM,
    extrair_embed,
    preparar_envio_embed,
    resolver_imagem,
    validar_embed,
)


logger = logging.getLogger(__name__)

DIRETORIO_INGREDIENTES = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "ingredientes"
)
CAMINHO_BANCO_COOLDOWNS = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "database"
    / "cooldowns.db"
)
NOME_ARQUIVO_RESULTADO = "resultado.json"
NOME_TABELA_COOLDOWNS = "ingredientes_cooldowns"

BASE_CDN_INGREDIENTES = (
    "https://pub-57a72b7c1133428e9da66f38a6b6bbf4.r2.dev/ingredientes"
)

DIRETORIOS_INGREDIENTES = {
    "comum": "ingredientecomum",
    "raro": "ingredienteraro",
    "lendario": "ingredientelendario",
    "mitico": "ingredientemitico",
}

RESULTADOS_INGREDIENTES = {
    "comum": (
        "cogumelos",
        "lirio",
        "gengibre",
        "salgema",
        "petalabeladona",
    ),
    "raro": (
        "perolanegra",
        "musgoruinas",
        "escamadragao",
        "floreterna",
        "essenciaempatica",
    ),
    "lendario": (
        "cometaarcano",
        "sonhagumelo",
        "meldarainharubra",
        "nogueiradeferro",
        "pedradasestacoes",
    ),
    "mitico": (
        "rasgaveus",
        "saisepidote",
        "sangueberserk",
        "solaria",
        "nocturnia",
    ),
}

ARQUIVOS_INGREDIENTES = {
    "cogumelos": "cogumelos.png",
    "lirio": "lirio.png",
    "gengibre": "gengibre.png",
    "salgema": "salgema.png",
    "petalabeladona": "petalabeladona.png",
    "perolanegra": "perolanegra.jpg",
    "musgoruinas": "musgoruinas.jpg",
    "escamadragao": "escamadragao.jpg",
    "floreterna": "floreterna.jpg",
    "essenciaempatica": "essenciaempatica.jpg",
    "cometaarcano": "cometaarcano.jpg",
    "sonhagumelo": "sonhagumelo.jpg",
    "meldarainharubra": "meldarainharubra.png",
    "nogueiradeferro": "nogueiradeferro.png",
    "pedradasestacoes": "pedradasestacoes.png",
    "rasgaveus": "rasgaveus.jpg",
    "saisepidote": "saisepidote.jpg",
    "sangueberserk": "sangueberserk.jpg",
    "solaria": "solaria.jpg",
    "nocturnia": "nocturnia.png",
}

PESOS_INGREDIENTES = {
    "comum": 62,
    "raro": 32,
    "lendario": 4,
    "mitico": 2,
}

CANAL_TESTES_ID = 1469573136604205149
JANELA_COOLDOWN_SEGUNDOS = 24 * 60 * 60
LIMITE_USOS = 2

MENSAGEM_INGREDIENTES_INDISPONIVEL = (
    "❌ O sistema de ingredientes não está disponível no momento."
)
MENSAGEM_IMAGEM_INGREDIENTE_INDISPONIVEL = (
    "❌ Não foi possível carregar o resultado do ingrediente no momento."
)
MENSAGEM_COOLDOWN_INGREDIENTES = (
    "⏳ Você já utilizou seus 2 rolls de ingredientes nas últimas "
    "24 horas.\n"
    "Seu próximo uso estará disponível em aproximadamente {tempo}."
)


class ProvedorCDN(Protocol):
    """Interface pública da infraestrutura de CDN do Cog de poções."""

    def consultar_cache_cdn(self, url: str) -> Optional[bool]: ...

    async def cdn_disponivel(
        self,
        url: str,
        nome_resultado: str,
    ) -> bool: ...


@dataclass(frozen=True)
class ResultadoIngrediente:
    """Dados validados de um ingrediente que pode participar do sorteio."""

    raridade: str
    nome: str
    pasta: Path
    arquivo_imagem: str
    embed_data: Dict[str, Any]
    url_cdn: str
    attachment: Optional[Path] = None
    nome_attachment: Optional[str] = None

    @property
    def caminho_backup(self) -> Path:
        """Retorna a imagem local exata exigida para este ingrediente."""

        return self.pasta / self.arquivo_imagem


class Ingredientes(commands.Cog):
    """Sorteia ingredientes e aplica um cooldown persistente por usuário."""

    def __init__(
        self,
        bot: Optional[commands.Bot],
        diretorio_ingredientes: Optional[Path] = None,
        caminho_banco: Optional[Path] = None,
        provedor_cdn: Optional[ProvedorCDN] = None,
        relogio: Optional[Callable[[], float]] = None,
    ) -> None:
        self.bot = bot
        self.diretorio_ingredientes = Path(
            diretorio_ingredientes or DIRETORIO_INGREDIENTES
        )
        self.caminho_banco = Path(
            caminho_banco or CAMINHO_BANCO_COOLDOWNS
        )
        self._provedor_cdn_injetado = provedor_cdn
        self._relogio = relogio or time.time

        self._conexao_banco: Optional[aiosqlite.Connection] = None
        self._lock_banco = asyncio.Lock()
        self._locks_usuarios: Dict[int, asyncio.Lock] = {}
        self._banco_indisponivel = False
        self._encerrando = False
        self._encerrado = False

    async def cog_unload(self) -> None:
        """Espera rolls ativos e fecha a conexão SQLite sob demanda."""

        self._encerrando = True
        locks_ativos = tuple(self._locks_usuarios.values())
        locks_adquiridos = []

        try:
            for lock in locks_ativos:
                await lock.acquire()
                locks_adquiridos.append(lock)

            async with self._lock_banco:
                self._encerrado = True
                conexao = self._conexao_banco
                self._conexao_banco = None

                if conexao is not None:
                    try:
                        await conexao.close()
                    except Exception:
                        logger.exception(
                            "[INGREDIENTES] Não foi possível fechar o banco de "
                            "cooldowns."
                        )
        finally:
            for lock in reversed(locks_adquiridos):
                lock.release()

            self._locks_usuarios.clear()

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
        """Resolve o Cog de poções que mantém sessão, cache e locks CDN."""

        if self._provedor_cdn_injetado is not None:
            return self._provedor_cdn_injetado

        if self.bot is None:
            raise RuntimeError("Provedor CDN não configurado.")

        provedor = self.bot.get_cog("Pocoes")

        if not self._provedor_cdn_valido(provedor):
            raise RuntimeError("O Cog de poções não está disponível.")

        return cast(ProvedorCDN, provedor)

    def _consultar_cache_cdn(self, url: str) -> Optional[bool]:
        """Consulta o cache mantido pelo Cog de poções."""

        return self._obter_provedor_cdn().consultar_cache_cdn(url)

    async def _cdn_disponivel(
        self,
        url: str,
        nome_resultado: str,
    ) -> bool:
        """Verifica somente a URL sorteada usando o provedor compartilhado."""

        return await self._obter_provedor_cdn().cdn_disponivel(
            url,
            nome_resultado,
        )

    @staticmethod
    def _configuracao_valida() -> bool:
        """Confirma a configuração fixa 4 x 5 e os pesos oficiais."""

        raridades = tuple(PESOS_INGREDIENTES)

        if (
            tuple(DIRETORIOS_INGREDIENTES) != raridades
            or tuple(RESULTADOS_INGREDIENTES) != raridades
        ):
            logger.error(
                "[INGREDIENTES] Mapeamentos incompatíveis com os pesos."
            )
            return False

        if sum(PESOS_INGREDIENTES.values()) != 100:
            logger.error(
                "[INGREDIENTES] Soma dos pesos inválida: %s; esperado: 100.",
                sum(PESOS_INGREDIENTES.values()),
            )
            return False

        if any(
            not isinstance(peso, int) or peso <= 0
            for peso in PESOS_INGREDIENTES.values()
        ):
            logger.error("[INGREDIENTES] Os pesos devem ser inteiros positivos.")
            return False

        nomes = tuple(
            nome
            for raridade in raridades
            for nome in RESULTADOS_INGREDIENTES[raridade]
        )

        if (
            any(
                len(RESULTADOS_INGREDIENTES[raridade]) != 5
                for raridade in raridades
            )
            or len(nomes) != 20
            or len(set(nomes)) != 20
            or set(nomes) != set(ARQUIVOS_INGREDIENTES)
        ):
            logger.error(
                "[INGREDIENTES] A configuração deve conter 20 resultados "
                "únicos, cinco por raridade."
            )
            return False

        for nome, arquivo_imagem in ARQUIVOS_INGREDIENTES.items():
            caminho = Path(arquivo_imagem)

            if (
                caminho.name != arquivo_imagem
                or caminho.suffix.casefold() not in EXTENSOES_IMAGEM
            ):
                logger.error(
                    "[INGREDIENTES] Arquivo de imagem inválido para %s: %s",
                    nome,
                    arquivo_imagem,
                )
                return False

        return True

    @staticmethod
    def _url_oficial(nome_arquivo: str) -> str:
        return f"{BASE_CDN_INGREDIENTES}/{nome_arquivo}"

    def carregar_resultado(
        self,
        raridade: str,
        nome: str,
    ) -> Optional[ResultadoIngrediente]:
        """Carrega um ingrediente e valida JSON, URL e backup exatos."""

        nomes_raridade = RESULTADOS_INGREDIENTES.get(raridade)

        if nomes_raridade is None:
            raise ValueError(f"Raridade de ingrediente desconhecida: {raridade}")

        if nome not in nomes_raridade:
            raise ValueError(
                f"Ingrediente desconhecido para a raridade {raridade}: {nome}"
            )

        nome_diretorio = DIRETORIOS_INGREDIENTES[raridade]
        arquivo_imagem = ARQUIVOS_INGREDIENTES[nome]
        pasta = self.diretorio_ingredientes / nome_diretorio / nome
        caminho_json = pasta / NOME_ARQUIVO_RESULTADO

        if not caminho_json.is_file():
            logger.warning(
                "[INGREDIENTES] resultado.json não encontrado: %s/%s",
                nome_diretorio,
                nome,
            )
            return None

        try:
            with caminho_json.open("r", encoding="utf-8") as arquivo_json:
                conteudo_json = arquivo_json.read()

            if not conteudo_json.strip():
                logger.warning(
                    "[INGREDIENTES] resultado.json vazio: %s",
                    nome,
                )
                return None

            dados = json.loads(conteudo_json)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning(
                "[INGREDIENTES] JSON inválido: %s",
                nome,
                exc_info=True,
            )
            return None
        except OSError:
            logger.exception(
                "[INGREDIENTES] Erro ao ler resultado.json: %s",
                nome,
            )
            return None

        embed_data = extrair_embed(dados)

        if embed_data is None:
            logger.warning("[INGREDIENTES] Embed inválida: %s", nome)
            return None

        if not validar_embed(
            embed_data,
            nome,
            registrador=logger,
            prefixo="[INGREDIENTES]",
        ):
            return None

        imagem = embed_data.get("image")
        url_cdn = imagem.get("url") if isinstance(imagem, dict) else None
        url_oficial = self._url_oficial(arquivo_imagem)

        if url_cdn != url_oficial:
            logger.error(
                "[INGREDIENTES] URL CDN inválida para %s; esperado: %s",
                nome,
                url_oficial,
            )
            return None

        imagem_resolvida = resolver_imagem(
            pasta,
            embed_data,
            nome_base_envio=f"imagem_ingrediente_{nome}",
            registrador=logger,
            prefixo="[INGREDIENTES]",
        )

        if imagem_resolvida is None:
            return None

        caminho_backup = pasta / arquivo_imagem

        try:
            if (
                not caminho_backup.is_file()
                or caminho_backup.suffix.casefold()
                != Path(arquivo_imagem).suffix.casefold()
                or caminho_backup.stat().st_size <= 0
            ):
                logger.error(
                    "[INGREDIENTES] Imagem local não encontrada: %s",
                    nome,
                )
                return None
        except OSError:
            logger.exception(
                "[INGREDIENTES] Não foi possível validar a imagem local: %s",
                nome,
            )
            return None

        attachment, nome_attachment = imagem_resolvida

        if attachment is not None and attachment != caminho_backup:
            logger.error(
                "[INGREDIENTES] Embed exigiria dois attachments distintos: %s",
                nome,
            )
            return None

        return ResultadoIngrediente(
            raridade=raridade,
            nome=nome,
            pasta=pasta,
            arquivo_imagem=arquivo_imagem,
            embed_data=embed_data,
            url_cdn=url_cdn,
            attachment=attachment,
            nome_attachment=nome_attachment,
        )

    def carregar_resultados_obrigatorios(
        self,
    ) -> Optional[Dict[str, Tuple[ResultadoIngrediente, ...]]]:
        """Valida os 20 resultados antes de permitir qualquer sorteio."""

        if not self._configuracao_valida():
            return None

        resultados: Dict[str, Tuple[ResultadoIngrediente, ...]] = {}
        houve_falha = False

        for raridade, nomes in RESULTADOS_INGREDIENTES.items():
            resultados_raridade = []

            for nome in nomes:
                try:
                    resultado = self.carregar_resultado(raridade, nome)
                except Exception:
                    logger.exception(
                        "[INGREDIENTES] Erro inesperado ao carregar: %s",
                        nome,
                    )
                    resultado = None

                if resultado is None:
                    houve_falha = True
                    continue

                resultados_raridade.append(resultado)

            resultados[raridade] = tuple(resultados_raridade)

        if houve_falha or any(
            len(resultados.get(raridade, ())) != 5
            for raridade in PESOS_INGREDIENTES
        ):
            logger.error(
                "[INGREDIENTES] Conjunto obrigatório incompleto; o sorteio "
                "foi desativado para preservar as probabilidades."
            )
            return None

        return resultados

    @staticmethod
    def sortear_resultado(
        resultados: Mapping[str, Tuple[ResultadoIngrediente, ...]],
    ) -> ResultadoIngrediente:
        """Sorteia a raridade ponderada e depois um dos cinco itens."""

        if tuple(resultados) != tuple(PESOS_INGREDIENTES) or any(
            len(resultados.get(raridade, ())) != 5
            for raridade in PESOS_INGREDIENTES
        ):
            raise ValueError("Conjunto de ingredientes inválido para sorteio.")

        raridades = tuple(PESOS_INGREDIENTES)
        pesos = tuple(PESOS_INGREDIENTES.values())
        raridade = random.choices(
            raridades,
            weights=pesos,
            k=1,
        )[0]
        return random.choice(resultados[raridade])

    @staticmethod
    def preparar_envio(
        resultado: ResultadoIngrediente,
    ) -> Tuple[discord.Embed, Optional[discord.File]]:
        """Reconstrói a embed sem modificar os dados carregados do JSON."""

        return preparar_envio_embed(
            resultado.embed_data,
            resultado.attachment,
            resultado.nome_attachment,
        )

    @classmethod
    def _preparar_backup_cdn(
        cls,
        resultado: ResultadoIngrediente,
    ) -> Optional[Tuple[discord.Embed, discord.File]]:
        """Troca somente a imagem da cópia em memória pelo backup local."""

        backup = resultado.caminho_backup

        try:
            if (
                not backup.is_file()
                or backup.name != resultado.arquivo_imagem
                or backup.stat().st_size <= 0
            ):
                logger.error(
                    "[CDN] Backup local não encontrado: %s",
                    resultado.nome,
                )
                return None
        except OSError:
            logger.exception(
                "[CDN] Não foi possível validar o backup local: %s",
                resultado.nome,
            )
            return None

        if resultado.attachment is not None and resultado.attachment != backup:
            logger.error(
                "[CDN] Fallback exigiria dois attachments distintos: %s",
                resultado.nome,
            )
            return None

        embed_data = deepcopy(resultado.embed_data)
        imagem = embed_data.get("image")

        if not isinstance(imagem, dict):
            logger.error(
                "[CDN] Embed sem imagem para aplicar backup: %s",
                resultado.nome,
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
                resultado.nome,
            )
            return None

        if arquivo is None:
            logger.error(
                "[CDN] Backup local não gerou attachment: %s",
                resultado.nome,
            )
            return None

        return embed, arquivo

    @staticmethod
    async def _responder_sistema_indisponivel(
        interaction: discord.Interaction,
    ) -> None:
        """Substitui a resposta diferida por uma indisponibilidade amigável."""

        try:
            await interaction.edit_original_response(
                content=MENSAGEM_INGREDIENTES_INDISPONIVEL,
                embed=None,
                attachments=[],
            )
        except discord.Forbidden:
            logger.warning(
                "[INGREDIENTES] Sem permissão para responder no canal %s.",
                interaction.channel,
            )
        except discord.HTTPException:
            logger.exception(
                "[INGREDIENTES] Não foi possível informar a indisponibilidade."
            )
        except Exception:
            logger.exception(
                "[INGREDIENTES] Erro inesperado ao informar a "
                "indisponibilidade."
            )

    @staticmethod
    async def _responder_imagem_indisponivel(
        interaction: discord.Interaction,
    ) -> None:
        try:
            await interaction.edit_original_response(
                content=MENSAGEM_IMAGEM_INGREDIENTE_INDISPONIVEL,
                embed=None,
                attachments=[],
            )
        except discord.Forbidden:
            logger.warning(
                "[INGREDIENTES] Sem permissão para informar falha de imagem "
                "no canal %s.",
                interaction.channel,
            )
        except discord.HTTPException:
            logger.exception(
                "[INGREDIENTES] Não foi possível informar a falha de imagem."
            )
        except Exception:
            logger.exception(
                "[INGREDIENTES] Erro inesperado ao informar a falha de imagem."
            )

    async def _enviar_backup_cdn(
        self,
        interaction: discord.Interaction,
        resultado: ResultadoIngrediente,
    ) -> bool:
        """Envia o backup exato e informa se o resultado final foi aceito."""

        try:
            preparado = self._preparar_backup_cdn(resultado)
        except Exception:
            logger.exception(
                "[CDN] Erro inesperado ao preparar o backup: %s",
                resultado.nome,
            )
            preparado = None

        if preparado is None:
            await self._responder_imagem_indisponivel(interaction)
            return False

        embed, arquivo = preparado

        try:
            logger.info("[CDN] Usando backup local: %s", resultado.nome)
            await interaction.edit_original_response(
                embed=embed,
                attachments=[arquivo],
            )
            return True
        finally:
            arquivo.close()

    async def _enviar_resultado_cdn(
        self,
        interaction: discord.Interaction,
        resultado: ResultadoIngrediente,
    ) -> bool:
        """Usa a CDN principal e retorna ``True`` somente no envio final."""

        try:
            estado_em_cache = self._consultar_cache_cdn(resultado.url_cdn)

            if estado_em_cache is None:
                estado_em_cache = await self._cdn_disponivel(
                    resultado.url_cdn,
                    resultado.nome,
                )
        except Exception:
            logger.exception(
                "[CDN] Falha inesperada ao consultar a CDN: %s",
                resultado.nome,
            )
            estado_em_cache = False

        if not estado_em_cache:
            return await self._enviar_backup_cdn(interaction, resultado)

        embed, arquivo = self.preparar_envio(resultado)

        try:
            if arquivo is None:
                await interaction.edit_original_response(embed=embed)
            else:
                await interaction.edit_original_response(
                    embed=embed,
                    attachments=[arquivo],
                )

            return True
        finally:
            if arquivo is not None:
                arquivo.close()

    async def _executar_sorteio_e_envio(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """Valida tudo, sorteia em duas etapas e envia um resultado final."""

        try:
            resultados = self.carregar_resultados_obrigatorios()
        except Exception:
            logger.exception(
                "[INGREDIENTES] Não foi possível validar os resultados."
            )
            await self._responder_sistema_indisponivel(interaction)
            return False

        if resultados is None:
            await self._responder_sistema_indisponivel(interaction)
            return False

        try:
            resultado = self.sortear_resultado(resultados)
            logger.info(
                "[INGREDIENTES] Raridade sorteada: %s",
                resultado.raridade,
            )
            logger.info(
                "[INGREDIENTES] Resultado sorteado: %s",
                resultado.nome,
            )
        except Exception:
            logger.exception(
                "[INGREDIENTES] Não foi possível sortear o resultado."
            )
            await self._responder_sistema_indisponivel(interaction)
            return False

        try:
            return await self._enviar_resultado_cdn(interaction, resultado)
        except discord.Forbidden:
            logger.warning(
                "[INGREDIENTES] Sem permissão para enviar no canal %s.",
                interaction.channel,
            )
        except discord.HTTPException:
            logger.exception(
                "[INGREDIENTES] Erro do Discord ao enviar o resultado: %s",
                resultado.nome,
            )
        except (OSError, TypeError, ValueError):
            logger.exception(
                "[INGREDIENTES] Não foi possível preparar o resultado: %s",
                resultado.nome,
            )
        except Exception:
            logger.exception(
                "[INGREDIENTES] Erro inesperado ao executar o sorteio."
            )

        await self._responder_imagem_indisponivel(interaction)
        return False

    def _agora_utc(self) -> float:
        """Obtém um epoch UTC finito por meio do relógio injetável."""

        agora = float(self._relogio())

        if not math.isfinite(agora):
            raise ValueError("O relógio retornou um timestamp inválido.")

        return agora

    def _obter_lock_usuario(self, user_id: int) -> asyncio.Lock:
        lock = self._locks_usuarios.get(user_id)

        if lock is None:
            lock = asyncio.Lock()
            self._locks_usuarios[user_id] = lock

        return lock

    async def _obter_conexao_banco_bloqueado(
        self,
    ) -> aiosqlite.Connection:
        """Cria a conexão e o schema; deve ser chamado sob ``_lock_banco``."""

        if self._encerrado:
            raise RuntimeError("O Cog de ingredientes já foi encerrado.")

        if self._banco_indisponivel:
            raise RuntimeError("O banco de cooldowns está indisponível.")

        if self._conexao_banco is not None:
            return self._conexao_banco

        conexao: Optional[aiosqlite.Connection] = None

        try:
            await asyncio.to_thread(
                self.caminho_banco.parent.mkdir,
                parents=True,
                exist_ok=True,
            )
            conexao = await aiosqlite.connect(self.caminho_banco)
            await conexao.execute("PRAGMA journal_mode = WAL")
            await conexao.execute("PRAGMA busy_timeout = 5000")
            await conexao.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {NOME_TABELA_COOLDOWNS} (
                    user_id INTEGER NOT NULL,
                    used_at REAL NOT NULL
                )
                """
            )
            await conexao.execute(
                f"""
                CREATE INDEX IF NOT EXISTS
                    idx_ingredientes_cooldowns_user_used_at
                ON {NOME_TABELA_COOLDOWNS} (user_id, used_at)
                """
            )
            await conexao.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_ingredientes_cooldowns_used_at
                ON {NOME_TABELA_COOLDOWNS} (used_at)
                """
            )
            await conexao.commit()
        except Exception:
            self._banco_indisponivel = True
            logger.exception(
                "[INGREDIENTES] Não foi possível inicializar o banco: %s",
                self.caminho_banco,
            )

            if conexao is not None:
                try:
                    await conexao.close()
                except Exception:
                    logger.exception(
                        "[INGREDIENTES] Não foi possível fechar a conexão "
                        "incompleta."
                    )

            raise

        self._conexao_banco = conexao
        return conexao

    async def _rollback_banco(self, conexao: aiosqlite.Connection) -> None:
        try:
            await conexao.rollback()
        except Exception:
            logger.exception(
                "[INGREDIENTES] Falha adicional ao reverter a transação."
            )

    async def _consultar_usos_validos(
        self,
        user_id: int,
        agora: float,
    ) -> Tuple[float, ...]:
        """Limpa expirados globalmente e retorna os usos válidos do usuário."""

        limite_inferior = agora - JANELA_COOLDOWN_SEGUNDOS

        async with self._lock_banco:
            conexao = await self._obter_conexao_banco_bloqueado()
            cursor: Optional[aiosqlite.Cursor] = None

            try:
                await conexao.execute(
                    f"DELETE FROM {NOME_TABELA_COOLDOWNS} "
                    "WHERE used_at <= ?",
                    (limite_inferior,),
                )
                cursor = await conexao.execute(
                    f"SELECT used_at FROM {NOME_TABELA_COOLDOWNS} "
                    "WHERE user_id = ? AND used_at > ? "
                    "ORDER BY used_at ASC",
                    (user_id, limite_inferior),
                )
                linhas = await cursor.fetchall()
                await conexao.commit()
            except Exception:
                self._banco_indisponivel = True
                await self._rollback_banco(conexao)
                logger.exception(
                    "[INGREDIENTES] Falha ao consultar o cooldown do usuário %s.",
                    user_id,
                )
                raise
            finally:
                if cursor is not None:
                    await cursor.close()

        return tuple(float(linha[0]) for linha in linhas)

    async def _registrar_uso(
        self,
        user_id: int,
        usado_em: float,
    ) -> bool:
        """Persiste um uso concluído e bloqueia o sistema se o commit falhar."""

        async with self._lock_banco:
            try:
                conexao = await self._obter_conexao_banco_bloqueado()
            except Exception:
                return False

            try:
                await conexao.execute(
                    f"INSERT INTO {NOME_TABELA_COOLDOWNS} "
                    "(user_id, used_at) VALUES (?, ?)",
                    (user_id, usado_em),
                )
                await conexao.commit()
                return True
            except Exception:
                self._banco_indisponivel = True
                await self._rollback_banco(conexao)
                logger.critical(
                    "[INGREDIENTES] O resultado foi enviado, mas o uso do "
                    "usuário %s não pôde ser persistido; o cooldown foi "
                    "colocado em modo indisponível.",
                    user_id,
                    exc_info=True,
                )
                return False

    @staticmethod
    def formatar_tempo_restante(segundos: float) -> str:
        """Formata uma duração aproximada sem subestimar a espera."""

        total_minutos = max(1, math.ceil(max(0.0, segundos) / 60.0))
        horas, minutos = divmod(total_minutos, 60)

        if horas and minutos:
            return f"{horas}h {minutos}min"

        if horas:
            return f"{horas}h"

        return f"{minutos}min"

    @classmethod
    async def _responder_cooldown(
        cls,
        interaction: discord.Interaction,
        segundos_restantes: float,
    ) -> None:
        tempo = cls.formatar_tempo_restante(segundos_restantes)
        mensagem = MENSAGEM_COOLDOWN_INGREDIENTES.format(tempo=tempo)

        try:
            await interaction.edit_original_response(
                content=mensagem,
                embed=None,
                attachments=[],
            )
        except discord.Forbidden:
            logger.warning(
                "[INGREDIENTES] Sem permissão para informar cooldown no "
                "canal %s.",
                interaction.channel,
            )
        except discord.HTTPException:
            logger.exception(
                "[INGREDIENTES] Não foi possível informar o cooldown."
            )
        except Exception:
            logger.exception(
                "[INGREDIENTES] Erro inesperado ao informar o cooldown."
            )

    async def _executar_com_cooldown(
        self,
        interaction: discord.Interaction,
        user_id: int,
    ) -> None:
        """Serializa todo o fluxo do mesmo usuário até o commit final."""

        lock_usuario = self._obter_lock_usuario(user_id)

        async with lock_usuario:
            if (
                self._banco_indisponivel
                or self._encerrando
                or self._encerrado
            ):
                await self._responder_sistema_indisponivel(interaction)
                return

            try:
                agora = self._agora_utc()
                usos_validos = await self._consultar_usos_validos(
                    user_id,
                    agora,
                )
            except Exception:
                await self._responder_sistema_indisponivel(interaction)
                return

            if len(usos_validos) >= LIMITE_USOS:
                proximo_uso_em = (
                    usos_validos[0] + JANELA_COOLDOWN_SEGUNDOS
                )
                logger.info(
                    "[INGREDIENTES] Usuário em cooldown: %s",
                    user_id,
                )
                await self._responder_cooldown(
                    interaction,
                    max(0.0, proximo_uso_em - agora),
                )
                return

            enviado = await self._executar_sorteio_e_envio(interaction)

            if not enviado:
                return

            try:
                usado_em = self._agora_utc()
            except Exception:
                self._banco_indisponivel = True
                logger.critical(
                    "[INGREDIENTES] Resultado enviado, mas o relógio falhou; "
                    "o cooldown foi colocado em modo indisponível.",
                    exc_info=True,
                )
                return

            await self._registrar_uso(user_id, usado_em)

    @app_commands.command(
        name="ingredientes",
        description="Coleta um ingrediente alquímico aleatório.",
    )
    async def ingredientes(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """Executa o roll com bypass exato e cooldown persistente."""

        try:
            await interaction.response.defer(thinking=True)
        except discord.Forbidden:
            logger.warning(
                "[INGREDIENTES] Sem permissão para iniciar a resposta no "
                "canal %s.",
                interaction.channel,
            )
            return
        except discord.HTTPException:
            logger.exception(
                "[INGREDIENTES] Não foi possível diferir a resposta."
            )
            return
        except Exception:
            logger.exception(
                "[INGREDIENTES] Erro inesperado ao diferir a resposta."
            )
            return

        if interaction.channel_id == CANAL_TESTES_ID:
            await self._executar_sorteio_e_envio(interaction)
            return

        try:
            user_id = int(interaction.user.id)
        except (AttributeError, TypeError, ValueError):
            logger.error(
                "[INGREDIENTES] Não foi possível identificar o usuário."
            )
            await self._responder_sistema_indisponivel(interaction)
            return

        await self._executar_com_cooldown(interaction, user_id)


async def setup(bot: commands.Bot) -> None:
    """Adiciona /ingredientes à CommandTree já existente."""

    if not Ingredientes._provedor_cdn_valido(bot.get_cog("Pocoes")):
        raise RuntimeError(
            "cogs.pocoes deve ser carregado antes de cogs.ingredientes."
        )

    await bot.add_cog(Ingredientes(bot))
