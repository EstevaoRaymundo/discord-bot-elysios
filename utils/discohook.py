"""Utilitários locais para embeds exportadas pelo Discohook."""

from copy import deepcopy
import logging
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple
import unicodedata
from urllib.parse import unquote, urlparse

import discord


EXTENSOES_IMAGEM = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
CAMPOS_URL_MIDIA = (
    ("image", "url", True),
    ("thumbnail", "url", True),
    ("author", "icon_url", False),
    ("footer", "icon_url", False),
)


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


def normalizar_nome(nome: str) -> str:
    """Cria uma chave somente para comparar nomes de arquivos locais."""

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


def nome_referenciado(url: str) -> str:
    """Obtém somente o basename seguro de uma URL ``attachment://``."""

    esquema, separador, restante = url.partition("://")

    if not separador or esquema.casefold() != "attachment":
        return ""

    nome = unquote(restante)
    return PurePosixPath(nome).name


def listar_imagens(pasta: Path) -> List[Path]:
    """Lista imagens locais suportadas, legíveis e não vazias."""

    imagens = []

    for caminho in pasta.iterdir():
        if (
            caminho.is_file()
            and caminho.suffix.casefold() in EXTENSOES_IMAGEM
            and caminho.stat().st_size > 0
        ):
            imagens.append(caminho)

    return sorted(imagens, key=lambda caminho: caminho.name.casefold())


def localizar_attachment(
    pasta: Path,
    url: str,
    *,
    registrador: logging.Logger,
    prefixo: str,
) -> Optional[Path]:
    """Associa uma referência da embed a uma imagem da mesma pasta."""

    try:
        imagens = listar_imagens(pasta)
    except OSError:
        registrador.exception(
            "%s Não foi possível ler os attachments: %s",
            prefixo,
            pasta.name,
        )
        return None

    if not imagens:
        registrador.warning(
            "%s Attachment local não encontrado: %s",
            prefixo,
            pasta.name,
        )
        return None

    nome_esperado = nome_referenciado(url)
    correspondencias = [
        caminho
        for caminho in imagens
        if caminho.name.casefold() == nome_esperado.casefold()
    ]

    if len(correspondencias) == 1:
        return correspondencias[0]

    nome_normalizado = normalizar_nome(nome_esperado)
    correspondencias = [
        caminho
        for caminho in imagens
        if normalizar_nome(caminho.name) == nome_normalizado
    ]

    if len(correspondencias) == 1:
        return correspondencias[0]

    if len(imagens) == 1:
        return imagens[0]

    registrador.warning(
        "%s Attachment local ambíguo: %s",
        prefixo,
        pasta.name,
    )
    return None


def validar_embed(
    embed_data: Dict[str, Any],
    identificador: str,
    *,
    registrador: logging.Logger,
    prefixo: str,
) -> bool:
    """Confirma que o discord.py reconstrói uma embed não vazia."""

    try:
        embed = discord.Embed.from_dict(embed_data)
    except Exception:
        registrador.warning(
            "%s Embed inválida: %s",
            prefixo,
            identificador,
            exc_info=True,
        )
        return False

    if not embed:
        registrador.warning(
            "%s Embed vazia ignorada: %s",
            prefixo,
            identificador,
        )
        return False

    return True


def resolver_imagem(
    pasta: Path,
    embed_data: Dict[str, Any],
    *,
    nome_base_envio: str,
    registrador: logging.Logger,
    prefixo: str,
) -> Optional[Tuple[Optional[Path], Optional[str]]]:
    """Valida URLs de mídia e resolve um attachment local, se houver."""

    referencias_attachment = []

    for nome_secao, nome_url, url_obrigatoria in CAMPOS_URL_MIDIA:
        secao = embed_data.get(nome_secao)

        if secao is None:
            continue

        if not isinstance(secao, dict):
            registrador.warning(
                "%s Mídia inválida: %s",
                prefixo,
                pasta.name,
            )
            return None

        url = secao.get(nome_url)

        if url is None and not url_obrigatoria:
            continue

        if not isinstance(url, str) or not url:
            registrador.warning(
                "%s URL de mídia inválida: %s",
                prefixo,
                pasta.name,
            )
            return None

        url_analisada = urlparse(url)
        esquema = url_analisada.scheme.casefold()

        if esquema in {"http", "https"}:
            if not url_analisada.netloc:
                registrador.warning(
                    "%s URL de mídia inválida: %s",
                    prefixo,
                    pasta.name,
                )
                return None

            continue

        if esquema != "attachment":
            registrador.warning(
                "%s URL de mídia não suportada ignorada: %s",
                prefixo,
                pasta.name,
            )
            return None

        if not nome_referenciado(url):
            registrador.warning(
                "%s Nome de attachment inválido: %s",
                prefixo,
                pasta.name,
            )
            return None

        referencias_attachment.append(url)

    referencias_unicas = list(dict.fromkeys(referencias_attachment))

    if not referencias_unicas:
        return None, None

    if len(referencias_unicas) > 1:
        registrador.warning(
            "%s Mais de um attachment de mídia encontrado: %s",
            prefixo,
            pasta.name,
        )
        return None

    attachment = localizar_attachment(
        pasta,
        referencias_unicas[0],
        registrador=registrador,
        prefixo=prefixo,
    )

    if attachment is None:
        return None

    nome_envio = f"{nome_base_envio}{attachment.suffix.casefold()}"
    return attachment, nome_envio


def preparar_envio_embed(
    embed_data_original: Dict[str, Any],
    attachment: Optional[Path] = None,
    nome_attachment: Optional[str] = None,
) -> Tuple[discord.Embed, Optional[discord.File]]:
    """Reconstrói uma embed e abre um novo arquivo para este envio."""

    embed_data = deepcopy(embed_data_original)
    arquivo = None

    if attachment is not None:
        if nome_attachment is None:
            raise ValueError("Attachment sem nome de envio.")

        for nome_secao, nome_url, _ in CAMPOS_URL_MIDIA:
            secao = embed_data.get(nome_secao)

            if not isinstance(secao, dict):
                continue

            url = secao.get(nome_url)

            if (
                isinstance(url, str)
                and urlparse(url).scheme.casefold() == "attachment"
            ):
                secao[nome_url] = f"attachment://{nome_attachment}"

        arquivo = discord.File(attachment, filename=nome_attachment)

    try:
        embed = discord.Embed.from_dict(embed_data)
    except Exception:
        if arquivo is not None:
            arquivo.close()
        raise

    return embed, arquivo


def preparar_previa_embed(embed_original: discord.Embed) -> discord.Embed:
    """Remove URLs locais para permitir uma resposta inicial sem upload."""

    embed_data = deepcopy(embed_original.to_dict())

    for nome_secao, nome_url, url_obrigatoria in CAMPOS_URL_MIDIA:
        secao = embed_data.get(nome_secao)

        if not isinstance(secao, dict):
            continue

        url = secao.get(nome_url)

        if not (
            isinstance(url, str)
            and urlparse(url).scheme.casefold() == "attachment"
        ):
            continue

        if url_obrigatoria:
            embed_data.pop(nome_secao, None)
        else:
            secao.pop(nome_url, None)

    return discord.Embed.from_dict(embed_data)
