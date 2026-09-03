import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from typing import Dict, Optional, Tuple
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import aiohttp
import discord

from cogs.pocoes import (
    CDN_CACHE_FAIL_TTL,
    CDN_CACHE_OK_TTL,
    DIRETORIO_RESULTADOS,
    MENSAGEM_IMAGEM_POCAO_INDISPONIVEL,
    MENSAGEM_POCOES_INDISPONIVEL,
    PESOS_RARIDADES,
    Pocoes,
    extrair_embed,
)
from utils.discohook import preparar_previa_embed


DESCRICAO_UNICODE = (
    "⚗️ Poção mítica ﹒だ⸺𝐈\n"
    "**Acentos preservados:** ação, bênção e coração."
)


class RespostaHTTPFalsa:
    def __init__(self, status: int) -> None:
        self.status = status
        self.content = SimpleNamespace(
            read=AsyncMock(return_value=b"x")
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


def criar_payload(
    *,
    descricao: str = DESCRICAO_UNICODE,
    url_imagem: Optional[str] = None,
) -> Dict:
    embed = {
        "color": 4069400,
        "title": "Poção Mítica 🧪",
        "description": descricao,
        "fields": [
            {
                "name": "✨ Efeito",
                "value": "**Brilho**\nLinha seguinte",
                "inline": False,
            }
        ],
        "footer": {"text": "Rodapé com ç e ã"},
        "author": {
            "name": "Alquimista",
            "url": "https://example.com/alquimista",
        },
    }

    if url_imagem is not None:
        embed["image"] = {"url": url_imagem}

    return {
        "embeds": [embed],
        "attachments": [
            {
                "filename": "nome-exportado.gif",
                "url": "blob:https://discohook.app/nao-utilizar",
            }
        ],
    }


class DiretorioTemporarioMixin:
    def setUp(self) -> None:
        super().setUp()
        self._temporario = tempfile.TemporaryDirectory()
        self.diretorio = Path(self._temporario.name)

    def tearDown(self) -> None:
        self._temporario.cleanup()
        super().tearDown()

    def criar_resultado(
        self,
        nome: str,
        *,
        payload: Optional[Dict] = None,
        json_bruto: Optional[str] = None,
        imagens: Tuple[str, ...] = (),
    ) -> Path:
        pasta = self.diretorio / nome
        pasta.mkdir(parents=True)

        if payload is not None:
            conteudo = json.dumps(payload, ensure_ascii=False)
            (pasta / "resultado.json").write_text(
                conteudo,
                encoding="utf-8",
            )
        elif json_bruto is not None:
            (pasta / "resultado.json").write_text(
                json_bruto,
                encoding="utf-8",
            )

        for nome_imagem in imagens:
            (pasta / nome_imagem).write_bytes(b"imagem-de-teste")

        return pasta

    def criar_raridades_obrigatorias(
        self,
        *,
        url_imagem: Optional[str] = None,
        nome_imagem: Optional[str] = None,
        omitir: Optional[str] = None,
    ) -> None:
        for nome_raridade in PESOS_RARIDADES:
            if nome_raridade == omitir:
                continue

            imagens = (nome_imagem,) if nome_imagem is not None else ()
            self.criar_resultado(
                nome_raridade,
                payload=criar_payload(
                    descricao=nome_raridade,
                    url_imagem=url_imagem,
                ),
                imagens=imagens,
            )


class ExtrairEmbedTests(unittest.TestCase):
    def test_diretorio_padrao_e_a_pasta_data(self):
        raiz_projeto = Path(__file__).resolve().parent.parent

        self.assertEqual(DIRETORIO_RESULTADOS, raiz_projeto / "data")

    def test_retorna_primeira_embed_sem_alterar_unicode(self):
        payload = criar_payload()
        payload["embeds"].append({"description": "segunda embed"})

        embed_data = extrair_embed(payload)

        self.assertEqual(embed_data, payload["embeds"][0])
        self.assertEqual(embed_data["description"], DESCRICAO_UNICODE)

    def test_rejeita_estruturas_sem_primeira_embed_valida(self):
        casos = (
            None,
            [],
            {},
            {"embeds": None},
            {"embeds": "não é uma lista"},
            {"embeds": []},
            {"embeds": [None]},
            {"embeds": [None, {"description": "segunda válida"}]},
            {"embeds": ["não é um objeto"]},
            {"embeds": [{}]},
        )

        for dados in casos:
            with self.subTest(dados=dados):
                self.assertIsNone(extrair_embed(dados))

    def test_previa_remove_attachment_e_preserva_midias_remotas(self):
        embed = discord.Embed.from_dict(
            {
                "description": "Prévia imediata",
                "image": {"url": "attachment://arte.jpg"},
                "thumbnail": {"url": "https://example.com/miniatura.jpg"},
                "author": {
                    "name": "Alquimista",
                    "icon_url": "attachment://arte.jpg",
                },
                "footer": {
                    "text": "Rodapé",
                    "icon_url": "attachment://arte.jpg",
                },
            }
        )

        previa = preparar_previa_embed(embed)

        self.assertFalse(previa.image)
        self.assertEqual(
            previa.thumbnail.url,
            "https://example.com/miniatura.jpg",
        )
        self.assertEqual(previa.author.name, "Alquimista")
        self.assertIsNone(previa.author.icon_url)
        self.assertEqual(previa.footer.text, "Rodapé")
        self.assertIsNone(previa.footer.icon_url)


class CarregamentoPocoesTests(
    DiretorioTemporarioMixin,
    unittest.TestCase,
):
    def criar_cog(self) -> Pocoes:
        return Pocoes(
            bot=None,
            diretorio_resultados=self.diretorio,
        )

    def test_json_utf8_preserva_embed_completa(self):
        self.criar_resultado(
            "pocao_unicode",
            payload=criar_payload(
                url_imagem="https://example.com/pocao.gif"
            ),
        )
        cog = self.criar_cog()

        resultados = cog.carregar_resultados()

        self.assertEqual(len(resultados), 1)
        embed, arquivo = cog.preparar_envio(resultados[0])
        self.assertIsNone(arquivo)
        self.assertEqual(embed.title, "Poção Mítica 🧪")
        self.assertEqual(embed.description, DESCRICAO_UNICODE)
        self.assertEqual(embed.color.value, 4069400)
        self.assertEqual(embed.fields[0].name, "✨ Efeito")
        self.assertEqual(
            embed.fields[0].value,
            "**Brilho**\nLinha seguinte",
        )
        self.assertEqual(embed.footer.text, "Rodapé com ç e ã")
        self.assertEqual(embed.author.name, "Alquimista")
        self.assertEqual(
            embed.image.url,
            "https://example.com/pocao.gif",
        )

    def test_http_e_https_nao_exigem_arquivo_local(self):
        urls = (
            "http://example.com/pocao.png",
            "https://example.com/pocao.webp",
        )

        for indice, url in enumerate(urls):
            self.criar_resultado(
                f"pocao_{indice}",
                payload=criar_payload(url_imagem=url),
            )

        cog = self.criar_cog()
        resultados = cog.carregar_resultados()

        self.assertEqual(len(resultados), 2)
        urls_carregadas = set()

        for resultado in resultados:
            embed, arquivo = cog.preparar_envio(resultado)
            self.assertIsNone(arquivo)
            urls_carregadas.add(embed.image.url)

        self.assertEqual(urls_carregadas, set(urls))

    def test_blob_na_embed_e_ignorado_sem_usar_blob_dos_metadados(self):
        self.criar_resultado(
            "http_valido",
            payload=criar_payload(
                url_imagem="https://example.com/valida.gif"
            ),
        )
        self.criar_resultado(
            "blob_invalido",
            payload=criar_payload(
                url_imagem="blob:https://discohook.app/temporaria"
            ),
        )
        self.criar_resultado(
            "http_incompleto",
            payload=criar_payload(url_imagem="https://"),
        )
        cog = self.criar_cog()

        with self.assertLogs("cogs.pocoes", level="WARNING") as logs:
            resultados = cog.carregar_resultados()

        self.assertEqual(len(resultados), 1)
        embed, arquivo = cog.preparar_envio(resultados[0])
        self.assertIsNone(arquivo)
        self.assertEqual(
            embed.image.url,
            "https://example.com/valida.gif",
        )
        self.assertIn("blob_invalido", "\n".join(logs.output))
        self.assertIn("http_incompleto", "\n".join(logs.output))

    def test_attachment_unico_e_associado_mesmo_com_nome_diferente(self):
        self.criar_resultado(
            "pocao_attachment",
            payload=criar_payload(
                url_imagem="attachment://iniciarpoção.gif"
            ),
            imagens=("pocao_local.gif",),
        )
        cog = self.criar_cog()
        resultados = cog.carregar_resultados()

        self.assertEqual(len(resultados), 1)
        primeira_embed, primeiro_arquivo = cog.preparar_envio(
            resultados[0]
        )

        try:
            self.assertIsInstance(primeiro_arquivo, discord.File)
            self.assertEqual(
                primeira_embed.image.url,
                f"attachment://{primeiro_arquivo.filename}",
            )
            self.assertTrue(primeiro_arquivo.filename.endswith(".gif"))
            self.assertTrue(primeiro_arquivo.filename.isascii())
        finally:
            primeiro_arquivo.close()

        segunda_embed, segundo_arquivo = cog.preparar_envio(
            resultados[0]
        )

        try:
            self.assertIsNot(segunda_embed, primeira_embed)
            self.assertIsNot(segundo_arquivo, primeiro_arquivo)
        finally:
            segundo_arquivo.close()

    def test_attachment_ausente_ou_ambiguo_nao_bloqueia_valido(self):
        self.criar_resultado(
            "pocao_valida",
            payload=criar_payload(),
        )
        self.criar_resultado(
            "attachment_ausente",
            payload=criar_payload(
                url_imagem="attachment://ausente.gif"
            ),
        )
        self.criar_resultado(
            "attachment_ambiguo",
            payload=criar_payload(
                url_imagem="attachment://nome_exportado.gif"
            ),
            imagens=("primeira.gif", "segunda.png"),
        )
        cog = self.criar_cog()

        with self.assertLogs("cogs.pocoes", level="WARNING") as logs:
            resultados = cog.carregar_resultados()

        self.assertEqual(len(resultados), 1)
        mensagens = "\n".join(logs.output)
        self.assertIn("attachment_ausente", mensagens)
        self.assertIn("attachment_ambiguo", mensagens)

    def test_jsons_invalidos_sao_isolados(self):
        self.criar_resultado(
            "resultado_valido",
            payload=criar_payload(),
        )
        self.criar_resultado("json_malformado", json_bruto="{")
        self.criar_resultado("json_vazio", json_bruto="")
        self.criar_resultado(
            "sem_embeds",
            payload={"attachments": []},
        )
        self.criar_resultado(
            "embed_invalida",
            payload={"embeds": [{"color": "azul"}]},
        )
        self.criar_resultado("sem_resultado_json")
        pasta_encoding = self.criar_resultado("encoding_invalido")
        (pasta_encoding / "resultado.json").write_bytes(b"\xff\xfe")
        cog = self.criar_cog()

        with self.assertLogs("cogs.pocoes", level="WARNING") as logs:
            resultados = cog.carregar_resultados()

        self.assertEqual(len(resultados), 1)
        mensagens = "\n".join(logs.output)

        for nome in (
            "json_malformado",
            "json_vazio",
            "sem_embeds",
            "embed_invalida",
            "sem_resultado_json",
            "encoding_invalido",
        ):
            with self.subTest(nome=nome):
                self.assertIn(nome, mensagens)

    def test_descobre_novas_pastas_a_cada_carregamento(self):
        cog = self.criar_cog()
        self.assertEqual(cog.carregar_resultados(), [])

        self.criar_resultado(
            "pocao_comum",
            payload=criar_payload(descricao="Comum"),
        )
        primeira_leitura = cog.carregar_resultados()
        self.assertEqual(len(primeira_leitura), 1)

        self.criar_resultado(
            "pocao_divina",
            payload=criar_payload(descricao="Divina"),
        )
        segunda_leitura = cog.carregar_resultados()

        self.assertEqual(len(segunda_leitura), 2)
        descricoes = {
            cog.preparar_envio(resultado)[0].description
            for resultado in segunda_leitura
        }
        self.assertEqual(descricoes, {"Comum", "Divina"})

    def test_diretorios_reservados_nao_participam_do_sorteio(self):
        self.criar_resultado(
            "pocao_comum",
            payload=criar_payload(descricao="Comum"),
        )
        pasta_manual = self.diretorio / "manuais"
        pasta_manual.mkdir(parents=True)
        (pasta_manual / "manual.json").write_text(
            json.dumps(criar_payload(descricao="Manual")),
            encoding="utf-8",
        )
        pasta_estabilidade = self.diretorio / "estabilidade"
        pasta_estabilidade.mkdir(parents=True)
        (pasta_estabilidade / "resultado.json").write_text(
            json.dumps(criar_payload(descricao="Não é uma raridade")),
            encoding="utf-8",
        )
        (pasta_estabilidade / "estavel").mkdir()
        (pasta_estabilidade / "instavel").mkdir()
        pasta_artesanato = self.diretorio / "artesanato"
        pasta_artesanato.mkdir(parents=True)
        (pasta_artesanato / "resultado.json").write_text(
            json.dumps(criar_payload(descricao="Não é uma poção")),
            encoding="utf-8",
        )
        pasta_ingredientes = self.diretorio / "ingredientes"
        pasta_ingredientes.mkdir(parents=True)
        (pasta_ingredientes / "resultado.json").write_text(
            json.dumps(criar_payload(descricao="Não é uma poção")),
            encoding="utf-8",
        )
        cog = self.criar_cog()

        pastas = cog.encontrar_pastas()
        resultados = cog.carregar_resultados()

        self.assertEqual(
            [pasta.name for pasta in pastas],
            ["pocao_comum"],
        )
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].pasta.name, "pocao_comum")

    def test_diretorio_inexistente_retorna_lista_vazia(self):
        cog = Pocoes(
            bot=None,
            diretorio_resultados=self.diretorio / "nao_existe",
        )

        with self.assertLogs("cogs.pocoes", level="WARNING"):
            self.assertEqual(cog.carregar_resultados(), [])

    def test_pesos_oficiais_somam_cem(self):
        self.assertEqual(
            PESOS_RARIDADES,
            {
                "pocao_comum": 50,
                "pocao_incomum": 25,
                "pocao_rara": 15,
                "pocao_lendaria": 8,
                "pocao_mitica": 2,
            },
        )
        self.assertEqual(sum(PESOS_RARIDADES.values()), 100)

    def test_resultados_obrigatorios_ignoram_pasta_sem_peso(self):
        self.criar_raridades_obrigatorias()
        self.criar_resultado(
            "pocao_divina",
            payload=criar_payload(descricao="Sem peso"),
        )
        cog = self.criar_cog()

        resultados = cog.carregar_resultados_obrigatorios()

        self.assertIsNotNone(resultados)
        self.assertEqual(tuple(resultados), tuple(PESOS_RARIDADES))
        self.assertNotIn("pocao_divina", resultados)

    def test_soma_invalida_impede_carregamento(self):
        cog = self.criar_cog()

        with patch.dict(PESOS_RARIDADES, {"pocao_mitica": 3}):
            with self.assertLogs("cogs.pocoes", level="ERROR") as logs:
                resultados = cog.carregar_resultados_obrigatorios()

        self.assertIsNone(resultados)
        self.assertIn("esperado: 100", "\n".join(logs.output))

    def test_uma_raridade_ausente_invalida_o_conjunto_completo(self):
        self.criar_raridades_obrigatorias(omitir="pocao_mitica")
        cog = self.criar_cog()

        with self.assertLogs("cogs.pocoes", level="ERROR") as logs:
            resultados = cog.carregar_resultados_obrigatorios()

        self.assertIsNone(resultados)
        self.assertIn("pocao_mitica", "\n".join(logs.output))

    def test_sorteio_delega_para_random_choices_com_pesos_oficiais(self):
        self.criar_raridades_obrigatorias()
        cog = self.criar_cog()
        resultados = cog.carregar_resultados_obrigatorios()

        self.assertIsNotNone(resultados)

        with patch(
            "cogs.pocoes.random.choices",
            return_value=["pocao_mitica"],
        ) as choices:
            selecionado = cog.sortear_resultado(resultados)

        self.assertIs(selecionado, resultados["pocao_mitica"])
        choices.assert_called_once_with(
            tuple(PESOS_RARIDADES),
            weights=tuple(PESOS_RARIDADES.values()),
            k=1,
        )


class ConfiguracaoCDNProjetoTests(unittest.TestCase):
    URLS_OFICIAIS = {
        "pocao_comum": (
            "https://pub-57a72b7c1133428e9da66f38a6b6bbf4.r2.dev/"
            "pocoes/pocao_comum.png"
        ),
        "pocao_incomum": (
            "https://pub-57a72b7c1133428e9da66f38a6b6bbf4.r2.dev/"
            "pocoes/pocao_incomum.jpg"
        ),
        "pocao_rara": (
            "https://pub-57a72b7c1133428e9da66f38a6b6bbf4.r2.dev/"
            "pocoes/pocao_rara.jpg"
        ),
        "pocao_lendaria": (
            "https://pub-57a72b7c1133428e9da66f38a6b6bbf4.r2.dev/"
            "pocoes/pocao_lendaria.jpg"
        ),
        "pocao_mitica": (
            "https://pub-57a72b7c1133428e9da66f38a6b6bbf4.r2.dev/"
            "pocoes/pocao_mitica.jpg"
        ),
    }

    def test_jsons_usam_cdn_e_backups_locais_permanecem(self):
        for nome, url_esperada in self.URLS_OFICIAIS.items():
            with self.subTest(nome=nome):
                pasta = DIRETORIO_RESULTADOS / nome
                dados = json.loads(
                    (pasta / "resultado.json").read_text(
                        encoding="utf-8"
                    )
                )

                self.assertEqual(
                    dados["embeds"][0]["image"]["url"],
                    url_esperada,
                )
                self.assertTrue((pasta / f"{nome}.jpg").is_file())

    def test_todos_os_backups_reais_sao_localizados(self):
        cog = Pocoes(bot=None)

        for nome, url in self.URLS_OFICIAIS.items():
            with self.subTest(nome=nome):
                resultado = cog.carregar_resultado(
                    DIRETORIO_RESULTADOS / nome
                )

                self.assertIsNotNone(resultado)
                preparado = cog._preparar_backup_cdn(resultado, url)
                self.assertIsNotNone(preparado)
                embed, arquivo = preparado

                try:
                    self.assertEqual(
                        embed.image.url,
                        f"attachment://{arquivo.filename}",
                    )
                    self.assertTrue(arquivo.filename.endswith(".jpg"))
                finally:
                    arquivo.close()


class CacheCDNTests(
    DiretorioTemporarioMixin,
    unittest.IsolatedAsyncioTestCase,
):
    def criar_cog(self) -> Pocoes:
        return Pocoes(
            bot=None,
            diretorio_resultados=self.diretorio,
        )

    async def test_cache_positivo_nao_repete_verificacao(self):
        cog = self.criar_cog()
        url = "https://cdn.example/pocao.jpg"
        verificador = AsyncMock(return_value=True)

        with patch(
            "cogs.pocoes.time.monotonic",
            return_value=100.0,
        ):
            with patch.object(
                cog,
                "_verificar_url_cdn",
                verificador,
            ):
                primeira = await cog._cdn_disponivel(url, "pocao_rara")
                segunda = await cog._cdn_disponivel(url, "pocao_rara")

        self.assertTrue(primeira)
        self.assertTrue(segunda)
        self.assertEqual(CDN_CACHE_OK_TTL, 600.0)
        verificador.assert_awaited_once_with(url)

    async def test_chamadas_simultaneas_compartilham_uma_verificacao(self):
        cog = self.criar_cog()
        url = "https://cdn.example/pocao.jpg"

        async def verificar(_url):
            await asyncio.sleep(0)
            return True

        verificador = AsyncMock(side_effect=verificar)

        with patch.object(
            cog,
            "_verificar_url_cdn",
            verificador,
        ):
            resultados = await asyncio.gather(
                *(
                    cog._cdn_disponivel(url, "pocao_comum")
                    for _ in range(5)
                )
            )

        self.assertEqual(resultados, [True] * 5)
        verificador.assert_awaited_once_with(url)

    async def test_cache_negativo_nao_repete_verificacao(self):
        cog = self.criar_cog()
        url = "https://cdn.example/pocao.jpg"
        verificador = AsyncMock(return_value=False)

        with patch(
            "cogs.pocoes.time.monotonic",
            return_value=100.0,
        ):
            with patch.object(
                cog,
                "_verificar_url_cdn",
                verificador,
            ):
                primeira = await cog._cdn_disponivel(url, "pocao_mitica")
                segunda = await cog._cdn_disponivel(url, "pocao_mitica")

        self.assertFalse(primeira)
        self.assertFalse(segunda)
        self.assertEqual(CDN_CACHE_FAIL_TTL, 60.0)
        verificador.assert_awaited_once_with(url)

    async def test_cache_negativo_expira_e_detecta_recuperacao(self):
        cog = self.criar_cog()
        url = "https://cdn.example/pocao.jpg"
        verificador = AsyncMock(side_effect=(False, True))

        with patch(
            "cogs.pocoes.time.monotonic",
            return_value=100.0,
        ) as relogio:
            with patch.object(
                cog,
                "_verificar_url_cdn",
                verificador,
            ):
                with self.assertLogs(
                    "cogs.pocoes",
                    level="INFO",
                ) as logs:
                    self.assertFalse(
                        await cog._cdn_disponivel(url, "pocao_mitica")
                    )

                    relogio.return_value = 159.0
                    self.assertFalse(
                        await cog._cdn_disponivel(url, "pocao_mitica")
                    )

                    relogio.return_value = 161.0
                    self.assertTrue(
                        await cog._cdn_disponivel(url, "pocao_mitica")
                    )

        self.assertEqual(verificador.await_count, 2)
        self.assertIn("CDN voltou a responder", "\n".join(logs.output))

    async def test_head_disponivel_nao_executa_get(self):
        resposta_head = RespostaHTTPFalsa(200)
        sessao = SimpleNamespace(
            head=MagicMock(return_value=resposta_head),
            get=MagicMock(),
        )
        url = "https://cdn.example/pocao.jpg"

        disponivel = await Pocoes._requisitar_url_cdn(sessao, url)

        self.assertTrue(disponivel)
        sessao.head.assert_called_once_with(
            url,
            allow_redirects=True,
        )
        sessao.get.assert_not_called()

    async def test_head_nao_suportado_usa_get_minimo(self):
        resposta_head = RespostaHTTPFalsa(405)
        resposta_get = RespostaHTTPFalsa(206)
        sessao = SimpleNamespace(
            head=MagicMock(return_value=resposta_head),
            get=MagicMock(return_value=resposta_get),
        )
        url = "https://cdn.example/pocao.jpg"

        disponivel = await Pocoes._requisitar_url_cdn(sessao, url)

        self.assertTrue(disponivel)
        sessao.get.assert_called_once_with(
            url,
            allow_redirects=True,
            headers={"Range": "bytes=0-0"},
        )
        resposta_get.content.read.assert_awaited_once_with(1)

    async def test_timeout_e_erro_de_conexao_marcam_indisponivel(self):
        cog = self.criar_cog()
        url = "https://cdn.example/pocao.jpg"

        for erro in (
            asyncio.TimeoutError(),
            aiohttp.ClientConnectionError(),
        ):
            with self.subTest(erro=type(erro).__name__):
                sessao = SimpleNamespace(
                    head=MagicMock(side_effect=erro),
                )

                with patch.object(
                    cog,
                    "_obter_sessao_http",
                    AsyncMock(return_value=sessao),
                ):
                    self.assertFalse(
                        await cog._verificar_url_cdn(url)
                    )

    async def test_sessao_e_criada_uma_vez_e_fechada(self):
        cog = self.criar_cog()
        sessao = SimpleNamespace(
            closed=False,
            close=AsyncMock(),
        )

        with patch(
            "cogs.pocoes.aiohttp.ClientSession",
            return_value=sessao,
        ) as construtor:
            await cog.cog_load()
            await cog.cog_load()
            await cog.cog_unload()

            with self.assertRaises(RuntimeError):
                await cog._obter_sessao_http()

        construtor.assert_called_once()
        timeout = construtor.call_args.kwargs["timeout"]
        self.assertEqual(timeout.total, 2.0)
        sessao.close.assert_awaited_once_with()
        self.assertIsNone(cog._sessao_http)


class ComandoPocaoTests(
    DiretorioTemporarioMixin,
    unittest.IsolatedAsyncioTestCase,
):
    def criar_cog(self) -> Pocoes:
        return Pocoes(
            bot=None,
            diretorio_resultados=self.diretorio,
        )

    @staticmethod
    def criar_interaction() -> SimpleNamespace:
        return SimpleNamespace(
            user=SimpleNamespace(mention="<@123>"),
            channel="canal-teste",
            response=SimpleNamespace(send_message=AsyncMock()),
            edit_original_response=AsyncMock(),
        )

    @staticmethod
    def obter_content(chamada) -> Optional[str]:
        argumentos, nomeados = chamada

        if "content" in nomeados:
            return nomeados["content"]

        return argumentos[0] if argumentos else None

    def test_metadados_identificam_apenas_o_slash_command_acentuado(self):
        self.assertEqual(Pocoes.pocao.name, "poção")
        self.assertEqual(Pocoes.pocao.parameters, [])

    async def test_callback_informa_quando_nao_ha_resultados(self):
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        with patch("cogs.pocoes.random.choices") as choices:
            with self.assertLogs("cogs.pocoes", level="ERROR"):
                await Pocoes.pocao.callback(cog, interaction)

        choices.assert_not_called()
        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_not_awaited()
        chamada = interaction.response.send_message.await_args
        self.assertEqual(
            self.obter_content(chamada),
            MENSAGEM_POCOES_INDISPONIVEL,
        )
        self.assertNotIn("embed", chamada.kwargs)
        self.assertNotIn("attachments", chamada.kwargs)

    async def test_callback_cdn_disponivel_envia_embed_sem_arquivo(self):
        self.criar_raridades_obrigatorias(
            url_imagem="https://example.com/resultado.gif",
        )
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        with patch.object(
            cog,
            "_cdn_disponivel",
            AsyncMock(return_value=True),
        ) as disponibilidade:
            await Pocoes.pocao.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once()
        disponibilidade.assert_awaited_once_with(
            "https://example.com/resultado.gif",
            ANY,
        )
        chamada_inicial = interaction.response.send_message.await_args
        chamada_final = interaction.edit_original_response.await_args
        self.assertIsNone(self.obter_content(chamada_inicial))
        self.assertFalse(chamada_inicial.kwargs["embed"].image)
        self.assertIsInstance(
            chamada_final.kwargs["embed"],
            discord.Embed,
        )
        self.assertEqual(
            chamada_final.kwargs["embed"].image.url,
            "https://example.com/resultado.gif",
        )
        self.assertNotIn("file", chamada_inicial.kwargs)
        self.assertNotIn("attachments", chamada_inicial.kwargs)
        self.assertNotIn("file", chamada_final.kwargs)
        self.assertNotIn("attachments", chamada_final.kwargs)

    async def test_callback_reutiliza_cache_positivo_sem_novo_http(self):
        url = "https://example.com/resultado.gif"
        self.criar_raridades_obrigatorias(url_imagem=url)
        cog = self.criar_cog()
        interaction = self.criar_interaction()
        verificador = AsyncMock(return_value=True)

        with patch(
            "cogs.pocoes.time.monotonic",
            return_value=100.0,
        ):
            with patch.object(
                cog,
                "_verificar_url_cdn",
                verificador,
            ):
                await cog._cdn_disponivel(url, "pocao_comum")
                await Pocoes.pocao.callback(cog, interaction)

        verificador.assert_awaited_once_with(url)
        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_not_awaited()
        chamada = interaction.response.send_message.await_args
        self.assertEqual(chamada.kwargs["embed"].image.url, url)
        self.assertNotIn("file", chamada.kwargs)
        self.assertNotIn("attachments", chamada.kwargs)

    async def test_callback_envia_attachment_com_nome_correspondente(self):
        self.criar_raridades_obrigatorias(
            url_imagem="attachment://nome-do-discohook.gif",
            nome_imagem="resultado_local.gif",
        )
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        with patch.object(
            cog,
            "_cdn_disponivel",
            AsyncMock(),
        ) as disponibilidade:
            await Pocoes.pocao.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once()
        disponibilidade.assert_not_awaited()
        chamada_inicial = interaction.response.send_message.await_args
        chamada_final = interaction.edit_original_response.await_args
        previa = chamada_inicial.kwargs["embed"]
        arquivo = chamada_final.kwargs["attachments"][0]

        try:
            self.assertFalse(previa.image)
            self.assertIsInstance(arquivo, discord.File)
            self.assertEqual(
                chamada_final.kwargs["embed"].image.url,
                f"attachment://{arquivo.filename}",
            )
        finally:
            arquivo.close()

    async def test_callback_cdn_indisponivel_usa_backup_local(self):
        url = "https://cdn.example/pocao_comum.png"
        self.criar_raridades_obrigatorias(
            url_imagem=url,
            nome_imagem="pocao_comum.jpg",
        )
        cog = self.criar_cog()
        interaction = self.criar_interaction()
        caminho_json = (
            self.diretorio
            / "pocao_comum"
            / "resultado.json"
        )
        json_antes = caminho_json.read_bytes()

        with patch(
            "cogs.pocoes.random.choices",
            return_value=["pocao_comum"],
        ) as choices:
            with patch.object(
                cog,
                "_cdn_disponivel",
                AsyncMock(return_value=False),
            ):
                await Pocoes.pocao.callback(cog, interaction)

        choices.assert_called_once_with(
            tuple(PESOS_RARIDADES),
            weights=tuple(PESOS_RARIDADES.values()),
            k=1,
        )
        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once()
        chamada_inicial = interaction.response.send_message.await_args
        chamada_final = interaction.edit_original_response.await_args
        arquivo = chamada_final.kwargs["attachments"][0]

        self.assertFalse(chamada_inicial.kwargs["embed"].image)
        self.assertIsInstance(arquivo, discord.File)
        self.assertEqual(
            chamada_final.kwargs["embed"].image.url,
            f"attachment://{arquivo.filename}",
        )
        self.assertEqual(caminho_json.read_bytes(), json_antes)

    async def test_callback_sem_cdn_nem_backup_responde_amigavelmente(self):
        url = "https://cdn.example/inexistente.jpg"
        self.criar_raridades_obrigatorias(url_imagem=url)
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        with patch.object(
            cog,
            "_cdn_disponivel",
            AsyncMock(return_value=False),
        ):
            with self.assertLogs(
                "cogs.pocoes",
                level="WARNING",
            ) as logs:
                await Pocoes.pocao.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once()
        chamada_final = interaction.edit_original_response.await_args
        self.assertEqual(
            chamada_final.kwargs["content"],
            MENSAGEM_IMAGEM_POCAO_INDISPONIVEL,
        )
        self.assertIsNone(chamada_final.kwargs["embed"])
        mensagens = "\n".join(logs.output)
        self.assertIn("Backup local não encontrado", mensagens)

    async def test_erro_de_envio_e_registrado_sem_propagar(self):
        self.criar_raridades_obrigatorias(
            url_imagem="attachment://resultado.gif",
            nome_imagem="resultado.gif",
        )
        cog = self.criar_cog()
        interaction = self.criar_interaction()
        resposta = SimpleNamespace(status=500, reason="Erro simulado")
        interaction.edit_original_response.side_effect = (
            discord.HTTPException(resposta, "Falha simulada")
        )

        with self.assertLogs("cogs.pocoes", level="ERROR"):
            await Pocoes.pocao.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
