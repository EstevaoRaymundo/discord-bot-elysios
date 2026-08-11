import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from typing import Dict, Optional, Tuple
from unittest.mock import AsyncMock, patch

import discord

from cogs.pocoes import DIRETORIO_RESULTADOS, Pocoes, extrair_embed
from utils.discohook import preparar_previa_embed


DESCRICAO_UNICODE = (
    "⚗️ Poção mítica ﹒だ⸺𝐈\n"
    "**Acentos preservados:** ação, bênção e coração."
)


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

    def test_sorteio_delega_para_random_choice(self):
        self.criar_resultado(
            "pocao_a",
            payload=criar_payload(descricao="A"),
        )
        self.criar_resultado(
            "pocao_b",
            payload=criar_payload(descricao="B"),
        )
        cog = self.criar_cog()
        resultados = cog.carregar_resultados()

        with patch(
            "cogs.pocoes.random.choice",
            return_value=resultados[1],
        ) as choice:
            selecionado = cog.sortear_resultado(resultados)

        self.assertIs(selecionado, resultados[1])
        choice.assert_called_once_with(resultados)


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

        await Pocoes.pocao.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_not_awaited()
        chamada = interaction.response.send_message.await_args
        self.assertEqual(
            self.obter_content(chamada),
            "❌ Nenhum resultado de poção está cadastrado no momento.",
        )
        self.assertNotIn("embed", chamada.kwargs)
        self.assertNotIn("attachments", chamada.kwargs)

    async def test_callback_envia_embed_http_diretamente(self):
        self.criar_resultado(
            "pocao_http",
            payload=criar_payload(
                url_imagem="https://example.com/resultado.gif"
            ),
        )
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        await Pocoes.pocao.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_not_awaited()
        chamada = interaction.response.send_message.await_args
        self.assertIsNone(self.obter_content(chamada))
        self.assertIsInstance(chamada.kwargs["embed"], discord.Embed)
        self.assertEqual(
            chamada.kwargs["embed"].image.url,
            "https://example.com/resultado.gif",
        )
        self.assertIsNone(chamada.kwargs.get("attachments"))

    async def test_callback_envia_attachment_com_nome_correspondente(self):
        self.criar_resultado(
            "pocao_attachment",
            payload=criar_payload(
                url_imagem="attachment://nome-do-discohook.gif"
            ),
            imagens=("resultado_local.gif",),
        )
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        await Pocoes.pocao.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once()
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

    async def test_erro_de_envio_e_registrado_sem_propagar(self):
        self.criar_resultado(
            "pocao_attachment",
            payload=criar_payload(
                url_imagem="attachment://resultado.gif"
            ),
            imagens=("resultado.gif",),
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
