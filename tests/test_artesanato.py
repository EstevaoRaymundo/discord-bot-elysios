import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from typing import Dict, Optional, Set
from unittest.mock import AsyncMock, patch

import discord

from cogs.artesanato import (
    DIRETORIO_ARTESANATO,
    MENSAGEM_ARTESANATO_INDISPONIVEL,
    MENSAGEM_IMAGEM_ARTESANATO_INDISPONIVEL,
    PESOS_ARTESANATO,
    RESULTADOS_ARTESANATO,
    Artesanato,
)
from cogs.pocoes import CDN_CACHE_FAIL_TTL, Pocoes


BASE_CDN = (
    "https://pub-57a72b7c1133428e9da66f38a6b6bbf4.r2.dev/"
    "artesanato"
)
URLS_ARTESANATO = {
    raridade: f"{BASE_CDN}/{nome_pasta}.gif"
    for raridade, nome_pasta in RESULTADOS_ARTESANATO.items()
}
DESCRICAO_UNICODE = (
    "🔨 Artesanato mítico ﹒だ⸺𝐈\n"
    "**Acentos preservados:** criação, bênção e coração."
)


def criar_payload(
    raridade: str,
    *,
    url_imagem: Optional[str] = None,
) -> Dict:
    nome_pasta = RESULTADOS_ARTESANATO[raridade]
    url = url_imagem or URLS_ARTESANATO[raridade]

    return {
        "embeds": [
            {
                "color": 4069400,
                "title": "Artesanato Mítico ⚒️",
                "description": DESCRICAO_UNICODE,
                "fields": [
                    {
                        "name": "✨ Qualidade",
                        "value": f"**{raridade.title()}**\nLinha seguinte",
                        "inline": False,
                    }
                ],
                "author": {
                    "name": "Artesão",
                    "url": "https://example.com/artesao",
                    "icon_url": "https://example.com/artesao.webp",
                },
                "footer": {
                    "text": "Forjado em Elysios com ç e ã",
                    "icon_url": "https://example.com/rodape.webp",
                },
                "thumbnail": {
                    "url": "https://example.com/miniatura.webp",
                },
                "image": {"url": url},
            }
        ],
        "attachments": [
            {
                "filename": f"{nome_pasta}.gif",
                "url": "blob:https://discohook.app/nao-utilizar",
            }
        ],
    }


class DiretorioArtesanatoTemporarioMixin:
    def setUp(self) -> None:
        super().setUp()
        self._temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporario.cleanup)
        self.diretorio = Path(self._temporario.name)
        self.provedor = Pocoes(
            bot=None,
            diretorio_resultados=self.diretorio / "pocoes",
        )
        self.cog = Artesanato(
            bot=None,
            diretorio_artesanato=self.diretorio,
            provedor_cdn=self.provedor,
        )

    def criar_resultado(
        self,
        raridade: str,
        *,
        payload: Optional[Dict] = None,
        criar_backup: bool = False,
    ) -> Path:
        nome_pasta = RESULTADOS_ARTESANATO[raridade]
        pasta = self.diretorio / nome_pasta
        pasta.mkdir(parents=True)
        conteudo = payload or criar_payload(raridade)
        (pasta / "resultado.json").write_text(
            json.dumps(conteudo, ensure_ascii=False),
            encoding="utf-8",
        )

        if criar_backup:
            (pasta / f"{nome_pasta}.gif").write_bytes(
                b"gif-de-backup-do-artesanato"
            )

        return pasta

    def criar_resultados_obrigatorios(
        self,
        *,
        omitir: Optional[str] = None,
        backups: Optional[Set[str]] = None,
    ) -> None:
        raridades_com_backup = backups or set()

        for raridade in RESULTADOS_ARTESANATO:
            if raridade == omitir:
                continue

            self.criar_resultado(
                raridade,
                criar_backup=raridade in raridades_com_backup,
            )

    @staticmethod
    def criar_interaction() -> SimpleNamespace:
        return SimpleNamespace(
            channel="canal-teste",
            response=SimpleNamespace(send_message=AsyncMock()),
            edit_original_response=AsyncMock(),
        )


class ConfiguracaoArtesanatoTests(
    DiretorioArtesanatoTemporarioMixin,
    unittest.TestCase,
):
    def test_constantes_mapeiam_as_cinco_pastas_e_pesos_oficiais(self):
        raiz_projeto = Path(__file__).resolve().parent.parent

        self.assertEqual(
            DIRETORIO_ARTESANATO,
            raiz_projeto / "data" / "artesanato",
        )
        self.assertEqual(
            RESULTADOS_ARTESANATO,
            {
                "comum": "artesanatocomum",
                "incomum": "artesanatoincomum",
                "raro": "artesanatoraro",
                "lendario": "artesanatolendario",
                "mitico": "artesanatomitico",
            },
        )
        self.assertEqual(
            PESOS_ARTESANATO,
            {
                "comum": 50,
                "incomum": 25,
                "raro": 15,
                "lendario": 8,
                "mitico": 2,
            },
        )
        self.assertEqual(tuple(RESULTADOS_ARTESANATO), tuple(PESOS_ARTESANATO))
        self.assertEqual(sum(PESOS_ARTESANATO.values()), 100)

        for nome_pasta in RESULTADOS_ARTESANATO.values():
            with self.subTest(nome_pasta=nome_pasta):
                self.assertTrue(
                    (DIRETORIO_ARTESANATO / nome_pasta).is_dir()
                )

    def test_cada_escolha_retorna_a_pasta_explicitamente_mapeada(self):
        self.criar_resultados_obrigatorios()
        resultados = self.cog.carregar_resultados_obrigatorios()

        self.assertIsNotNone(resultados)

        for raridade, nome_pasta in RESULTADOS_ARTESANATO.items():
            with self.subTest(raridade=raridade):
                with patch(
                    "cogs.artesanato.random.choices",
                    return_value=[raridade],
                ) as choices:
                    sorteado = self.cog.sortear_resultado(resultados)

                self.assertEqual(sorteado.raridade, raridade)
                self.assertEqual(sorteado.pasta.name, nome_pasta)
                self.assertTrue(
                    (sorteado.pasta / "resultado.json").is_file()
                )
                choices.assert_called_once_with(
                    tuple(PESOS_ARTESANATO),
                    weights=tuple(PESOS_ARTESANATO.values()),
                    k=1,
                )

    def test_uma_raridade_ausente_invalida_o_conjunto_completo(self):
        self.criar_resultados_obrigatorios(omitir="mitico")

        with self.assertLogs("cogs.artesanato", level="ERROR") as logs:
            resultados = self.cog.carregar_resultados_obrigatorios()

        self.assertIsNone(resultados)
        self.assertIn("mitico", "\n".join(logs.output))

    def test_embed_exportada_do_discohook_e_preservada(self):
        payload = criar_payload("raro")
        payload["embeds"].append({"description": "segunda embed ignorada"})
        self.criar_resultado("raro", payload=payload)

        resultado = self.cog.carregar_resultado("raro")

        self.assertIsNotNone(resultado)
        embed, arquivo = self.cog.preparar_envio(resultado)
        self.assertIsNone(arquivo)
        self.assertEqual(embed.title, "Artesanato Mítico ⚒️")
        self.assertEqual(embed.description, DESCRICAO_UNICODE)
        self.assertEqual(embed.color.value, 4069400)
        self.assertEqual(embed.fields[0].name, "✨ Qualidade")
        self.assertEqual(embed.fields[0].value, "**Raro**\nLinha seguinte")
        self.assertFalse(embed.fields[0].inline)
        self.assertEqual(embed.author.name, "Artesão")
        self.assertEqual(embed.author.url, "https://example.com/artesao")
        self.assertEqual(
            embed.author.icon_url,
            "https://example.com/artesao.webp",
        )
        self.assertEqual(embed.footer.text, "Forjado em Elysios com ç e ã")
        self.assertEqual(
            embed.footer.icon_url,
            "https://example.com/rodape.webp",
        )
        self.assertEqual(
            embed.thumbnail.url,
            "https://example.com/miniatura.webp",
        )
        self.assertEqual(embed.image.url, URLS_ARTESANATO["raro"])

    def test_metadados_expoem_slash_command_sem_parametros(self):
        self.assertEqual(Artesanato.artesanato.name, "artesanato")
        self.assertEqual(
            Artesanato.artesanato.description,
            "Cria um item e descobre o resultado do artesanato.",
        )
        self.assertEqual(Artesanato.artesanato.parameters, [])

    def test_resolve_provedor_atual_do_bot_pela_interface_compartilhada(self):
        bot = SimpleNamespace(
            get_cog=lambda nome: self.provedor if nome == "Pocoes" else None
        )
        cog = Artesanato(
            bot=bot,
            diretorio_artesanato=self.diretorio,
        )

        self.assertIs(cog._obter_provedor_cdn(), self.provedor)


class FluxoArtesanatoTests(
    DiretorioArtesanatoTemporarioMixin,
    unittest.IsolatedAsyncioTestCase,
):
    async def test_resultado_ausente_impede_sorteio_e_informa_jogador(self):
        self.criar_resultados_obrigatorios(omitir="mitico")
        interaction = self.criar_interaction()

        with patch("cogs.artesanato.random.choices") as choices:
            with self.assertLogs("cogs.artesanato", level="ERROR"):
                await Artesanato.artesanato.callback(
                    self.cog,
                    interaction,
                )

        choices.assert_not_called()
        interaction.response.send_message.assert_awaited_once_with(
            MENSAGEM_ARTESANATO_INDISPONIVEL
        )
        interaction.edit_original_response.assert_not_awaited()

    async def test_provedor_ausente_responde_sem_deixar_interacao_aberta(self):
        self.criar_resultados_obrigatorios()
        interaction = self.criar_interaction()
        cog = Artesanato(
            bot=SimpleNamespace(get_cog=lambda _nome: None),
            diretorio_artesanato=self.diretorio,
        )

        with patch(
            "cogs.artesanato.random.choices",
            return_value=["comum"],
        ):
            with self.assertLogs("cogs.artesanato", level="ERROR"):
                await Artesanato.artesanato.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once_with(
            MENSAGEM_IMAGEM_ARTESANATO_INDISPONIVEL
        )
        interaction.edit_original_response.assert_not_awaited()

    async def test_cdn_saudavel_envia_url_sem_discord_file(self):
        self.criar_resultados_obrigatorios()
        interaction = self.criar_interaction()
        url = URLS_ARTESANATO["comum"]
        verificador = AsyncMock(return_value=True)

        with patch(
            "cogs.artesanato.random.choices",
            return_value=["comum"],
        ) as choices:
            with patch.object(
                self.provedor,
                "_verificar_url_cdn",
                verificador,
            ):
                await Artesanato.artesanato.callback(self.cog, interaction)

        choices.assert_called_once_with(
            tuple(PESOS_ARTESANATO),
            weights=tuple(PESOS_ARTESANATO.values()),
            k=1,
        )
        verificador.assert_awaited_once_with(url)
        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once()
        chamada_inicial = interaction.response.send_message.await_args
        chamada_final = interaction.edit_original_response.await_args
        self.assertFalse(chamada_inicial.kwargs["embed"].image)
        self.assertNotIn("file", chamada_inicial.kwargs)
        self.assertNotIn("attachments", chamada_inicial.kwargs)
        self.assertEqual(chamada_final.kwargs["embed"].image.url, url)
        self.assertNotIn("file", chamada_final.kwargs)
        self.assertNotIn("attachments", chamada_final.kwargs)

    async def test_reutiliza_cache_da_instancia_pocoes_sem_novo_http(self):
        self.criar_resultados_obrigatorios()
        interaction = self.criar_interaction()
        url = URLS_ARTESANATO["incomum"]
        verificador = AsyncMock(return_value=True)

        self.assertIs(self.cog._obter_provedor_cdn(), self.provedor)

        with patch("cogs.pocoes.time.monotonic", return_value=100.0):
            with patch.object(
                self.provedor,
                "_verificar_url_cdn",
                verificador,
            ):
                self.assertTrue(
                    await self.provedor.cdn_disponivel(
                        url,
                        "artesanatoincomum",
                    )
                )

                with patch(
                    "cogs.artesanato.random.choices",
                    return_value=["incomum"],
                ):
                    await Artesanato.artesanato.callback(
                        self.cog,
                        interaction,
                    )

                self.assertTrue(self.provedor.consultar_cache_cdn(url))

        verificador.assert_awaited_once_with(url)
        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_not_awaited()
        chamada = interaction.response.send_message.await_args
        self.assertEqual(chamada.kwargs["embed"].image.url, url)
        self.assertNotIn("file", chamada.kwargs)
        self.assertNotIn("attachments", chamada.kwargs)

    async def test_fallback_usa_gif_exato_sem_resortear_ou_alterar_json(self):
        self.criar_resultados_obrigatorios(backups={"comum"})
        pasta = self.diretorio / RESULTADOS_ARTESANATO["comum"]
        (pasta / "nao_usar.gif").write_bytes(b"gif-incorreto")
        caminho_json = pasta / "resultado.json"
        json_antes = caminho_json.read_bytes()
        interaction = self.criar_interaction()
        verificador = AsyncMock(return_value=False)

        with patch(
            "cogs.artesanato.random.choices",
            return_value=["comum"],
        ) as choices:
            with patch.object(
                self.provedor,
                "_verificar_url_cdn",
                verificador,
            ):
                await Artesanato.artesanato.callback(self.cog, interaction)

        choices.assert_called_once_with(
            tuple(PESOS_ARTESANATO),
            weights=tuple(PESOS_ARTESANATO.values()),
            k=1,
        )
        verificador.assert_awaited_once_with(URLS_ARTESANATO["comum"])
        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once()
        chamada_inicial = interaction.response.send_message.await_args
        chamada_final = interaction.edit_original_response.await_args
        arquivo = chamada_final.kwargs["attachments"][0]
        self.assertFalse(chamada_inicial.kwargs["embed"].image)
        self.assertIsInstance(arquivo, discord.File)
        self.assertEqual(arquivo.filename, "artesanatocomum.gif")
        self.assertEqual(
            chamada_final.kwargs["embed"].image.url,
            "attachment://artesanatocomum.gif",
        )
        self.assertEqual(caminho_json.read_bytes(), json_antes)

    async def test_cdn_e_backup_ausentes_respondem_amigavelmente(self):
        self.criar_resultados_obrigatorios()
        interaction = self.criar_interaction()
        verificador = AsyncMock(return_value=False)

        with patch(
            "cogs.artesanato.random.choices",
            return_value=["raro"],
        ) as choices:
            with patch.object(
                self.provedor,
                "_verificar_url_cdn",
                verificador,
            ):
                with self.assertLogs(
                    "cogs.artesanato",
                    level="ERROR",
                ) as logs:
                    await Artesanato.artesanato.callback(
                        self.cog,
                        interaction,
                    )

        choices.assert_called_once()
        verificador.assert_awaited_once_with(URLS_ARTESANATO["raro"])
        interaction.response.send_message.assert_awaited_once()
        interaction.edit_original_response.assert_awaited_once_with(
            content=MENSAGEM_IMAGEM_ARTESANATO_INDISPONIVEL,
            embed=None,
            attachments=[],
        )
        self.assertIn("Backup local não encontrado", "\n".join(logs.output))

    async def test_cache_negativo_expira_e_recupera_via_provedor(self):
        url = URLS_ARTESANATO["mitico"]
        nome = RESULTADOS_ARTESANATO["mitico"]
        verificador = AsyncMock(side_effect=(False, True))

        with patch(
            "cogs.pocoes.time.monotonic",
            return_value=100.0,
        ) as relogio:
            with patch.object(
                self.provedor,
                "_verificar_url_cdn",
                verificador,
            ):
                with self.assertLogs("cogs.pocoes", level="INFO") as logs:
                    primeira = await self.cog._cdn_disponivel(url, nome)

                    relogio.return_value = 159.0
                    segunda = await self.cog._cdn_disponivel(url, nome)

                    relogio.return_value = 161.0
                    terceira = await self.cog._cdn_disponivel(url, nome)

                    self.assertTrue(
                        self.provedor.consultar_cache_cdn(url)
                    )

        self.assertFalse(primeira)
        self.assertFalse(segunda)
        self.assertTrue(terceira)
        self.assertEqual(CDN_CACHE_FAIL_TTL, 60.0)
        self.assertEqual(verificador.await_count, 2)
        self.assertIn("CDN voltou a responder", "\n".join(logs.output))

    async def test_verifica_somente_a_url_da_raridade_sorteada(self):
        self.criar_resultados_obrigatorios()
        interaction = self.criar_interaction()
        verificador = AsyncMock(return_value=True)

        with patch(
            "cogs.artesanato.random.choices",
            return_value=["lendario"],
        ) as choices:
            with patch.object(
                self.provedor,
                "_verificar_url_cdn",
                verificador,
            ):
                await Artesanato.artesanato.callback(self.cog, interaction)

        choices.assert_called_once()
        verificador.assert_awaited_once_with(
            URLS_ARTESANATO["lendario"]
        )
        self.assertEqual(verificador.await_count, 1)


if __name__ == "__main__":
    unittest.main()
