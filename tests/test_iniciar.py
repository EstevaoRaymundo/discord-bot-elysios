import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from typing import Dict, Optional, Tuple
from unittest.mock import AsyncMock, patch

import discord
from discord import app_commands

from cogs.iniciar import (
    DIRETORIO_MANUAIS,
    MENSAGEM_MANUAL_INDISPONIVEL,
    Iniciar,
)
from cogs.pocoes import Pocoes


DESCRICAO_UNICODE = (
    "⚗️ Manual de poções ﹒だ⸺𝐈\n"
    "**Acentos preservados:** ação, bênção e coração."
)


def criar_payload(
    *,
    descricao: str = DESCRICAO_UNICODE,
    url_imagem: Optional[str] = None,
    url_thumbnail: Optional[str] = None,
) -> Dict:
    embed = {
        "color": 4069400,
        "title": "Manual de Poções 🧪",
        "description": descricao,
        "fields": [
            {
                "name": "✨ Primeiro passo",
                "value": "**Misture** os ingredientes.\nAguarde dois turnos.",
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

    if url_thumbnail is not None:
        embed["thumbnail"] = {"url": url_thumbnail}

    return {
        "embeds": [embed],
        "attachments": [
            {
                "filename": "iniciar_pocao.gif",
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

    def criar_manual(
        self,
        nome: str = "pocao",
        *,
        payload: Optional[Dict] = None,
        json_bruto: Optional[str] = None,
        imagens: Tuple[str, ...] = (),
    ) -> Path:
        pasta = self.diretorio / nome
        pasta.mkdir(parents=True, exist_ok=True)

        if payload is not None:
            conteudo = json.dumps(payload, ensure_ascii=False)
            (pasta / "manual.json").write_text(
                conteudo,
                encoding="utf-8",
            )
        elif json_bruto is not None:
            (pasta / "manual.json").write_text(
                json_bruto,
                encoding="utf-8",
            )

        for nome_imagem in imagens:
            (pasta / nome_imagem).write_bytes(b"imagem-de-teste")

        return pasta


class CarregamentoManualTests(
    DiretorioTemporarioMixin,
    unittest.TestCase,
):
    def criar_cog(self, bot=None, nome: str = "pocao") -> Iniciar:
        return Iniciar(
            bot=bot,
            diretorio_manuais=self.diretorio / nome,
        )

    def test_diretorio_padrao_aponta_para_data_manuais(self):
        raiz_projeto = Path(__file__).resolve().parent.parent

        self.assertEqual(
            DIRETORIO_MANUAIS,
            raiz_projeto / "data" / "manuais",
        )

    def test_manual_json_fica_diretamente_na_pasta_manuais(self):
        (self.diretorio / "manual.json").write_text(
            json.dumps(criar_payload(), ensure_ascii=False),
            encoding="utf-8",
        )
        cog = Iniciar(bot=None, diretorio_manuais=self.diretorio)

        manual = cog.carregar_manual("pocao")

        self.assertIsNotNone(manual)
        self.assertEqual(manual.pasta, self.diretorio)

    def test_group_cog_expoe_apenas_o_subcomando_pocao(self):
        cog = self.criar_cog()
        grupo = cog.__cog_app_commands_group__

        self.assertIsInstance(grupo, app_commands.Group)
        self.assertEqual(grupo.name, "iniciar")
        self.assertEqual(
            grupo.description,
            "Manuais e instruções para iniciar atividades.",
        )
        self.assertEqual(
            [comando.name for comando in grupo.commands],
            ["poção"],
        )

        subcomando = grupo.get_command("poção")
        self.assertIsNotNone(subcomando)
        self.assertEqual(subcomando.qualified_name, "iniciar poção")
        self.assertEqual(subcomando.parameters, [])
        self.assertEqual(
            subcomando.description,
            "Mostra as instruções para preparar uma poção.",
        )
        self.assertEqual(cog.get_commands(), [])

    def test_json_utf8_preserva_embed_completa_e_primeira_entrada(self):
        payload = criar_payload(
            url_imagem="https://example.com/manual.gif",
            url_thumbnail="https://example.com/miniatura.png",
        )
        payload["embeds"].append({"description": "segunda embed"})
        self.criar_manual(payload=payload)
        cog = self.criar_cog()

        manual = cog.carregar_manual("pocao")

        self.assertIsNotNone(manual)
        embed, arquivo = cog.preparar_envio(manual)
        self.assertIsNone(arquivo)
        self.assertEqual(embed.title, "Manual de Poções 🧪")
        self.assertEqual(embed.description, DESCRICAO_UNICODE)
        self.assertEqual(embed.color.value, 4069400)
        self.assertEqual(embed.fields[0].name, "✨ Primeiro passo")
        self.assertEqual(
            embed.fields[0].value,
            "**Misture** os ingredientes.\nAguarde dois turnos.",
        )
        self.assertEqual(embed.footer.text, "Rodapé com ç e ã")
        self.assertEqual(embed.author.name, "Alquimista")
        self.assertEqual(
            embed.author.url,
            "https://example.com/alquimista",
        )
        self.assertEqual(embed.image.url, "https://example.com/manual.gif")
        self.assertEqual(
            embed.thumbnail.url,
            "https://example.com/miniatura.png",
        )

    def test_http_e_https_nao_exigem_arquivo_local(self):
        urls = (
            "http://example.com/manual.png",
            "https://example.com/manual.webp",
        )

        for indice, url in enumerate(urls):
            self.criar_manual(
                f"manual_{indice}",
                payload=criar_payload(url_imagem=url),
            )

        for indice, url in enumerate(urls):
            with self.subTest(url=url):
                cog = self.criar_cog(nome=f"manual_{indice}")
                manual = cog.carregar_manual(f"manual_{indice}")
                self.assertIsNotNone(manual)
                embed, arquivo = cog.preparar_envio(manual)
                self.assertIsNone(arquivo)
                self.assertEqual(embed.image.url, url)

    def test_blob_dos_metadados_e_ignorado(self):
        self.criar_manual(payload=criar_payload())
        cog = self.criar_cog()

        manual = cog.carregar_manual("pocao")

        self.assertIsNotNone(manual)
        embed, arquivo = cog.preparar_envio(manual)
        self.assertIsNone(arquivo)
        self.assertIsNone(embed.image.url)

    def test_blob_usado_diretamente_na_embed_invalida_o_manual(self):
        self.criar_manual(
            payload=criar_payload(
                url_imagem="blob:https://discohook.app/temporaria"
            )
        )
        cog = self.criar_cog()

        with self.assertLogs("cogs.iniciar", level="WARNING") as logs:
            manual = cog.carregar_manual("pocao")

        self.assertIsNone(manual)
        self.assertIn("pocao", "\n".join(logs.output))

    def test_attachment_exato_tem_prioridade_entre_varias_imagens(self):
        self.criar_manual(
            payload=criar_payload(
                url_imagem="attachment://iniciar_poção.gif"
            ),
            imagens=("iniciar_poção.gif", "outra.png"),
        )
        cog = self.criar_cog()

        manual = cog.carregar_manual("pocao")

        self.assertIsNotNone(manual)
        self.assertEqual(manual.attachment.name, "iniciar_poção.gif")
        embed, arquivo = cog.preparar_envio(manual)

        try:
            self.assertIsInstance(arquivo, discord.File)
            self.assertEqual(arquivo.filename, "iniciar_pocao.gif")
            self.assertEqual(
                embed.image.url,
                "attachment://iniciar_pocao.gif",
            )
        finally:
            arquivo.close()

    def test_attachment_normalizado_e_encontrado_entre_varias_imagens(self):
        self.criar_manual(
            payload=criar_payload(
                url_imagem="attachment://iniciar_poção.gif"
            ),
            imagens=("iniciar_pocao.gif", "outra.png"),
        )
        cog = self.criar_cog()

        manual = cog.carregar_manual("pocao")

        self.assertIsNotNone(manual)
        self.assertEqual(manual.attachment.name, "iniciar_pocao.gif")

    def test_attachment_unico_aceita_nome_diferente_e_nomeia_com_seguranca(self):
        self.criar_manual(
            payload=criar_payload(
                url_imagem="attachment://nome exportado.gif"
            ),
            imagens=("Manual Final.WEBP",),
        )
        cog = self.criar_cog()

        manual = cog.carregar_manual("pocao")

        self.assertIsNotNone(manual)
        self.assertEqual(manual.attachment.name, "Manual Final.WEBP")
        self.assertEqual(manual.nome_attachment, "iniciar_pocao.webp")

    def test_attachment_em_thumbnail_tambem_e_associado(self):
        self.criar_manual(
            payload=criar_payload(
                url_imagem="https://example.com/manual.gif",
                url_thumbnail="attachment://miniatura.png",
            ),
            imagens=("miniatura-local.png",),
        )
        cog = self.criar_cog()

        manual = cog.carregar_manual("pocao")

        self.assertIsNotNone(manual)
        embed, arquivo = cog.preparar_envio(manual)

        try:
            self.assertIsInstance(arquivo, discord.File)
            self.assertEqual(
                embed.thumbnail.url,
                f"attachment://{arquivo.filename}",
            )
            self.assertEqual(
                embed.image.url,
                "https://example.com/manual.gif",
            )
        finally:
            arquivo.close()

    def test_attachment_malformado_e_rejeitado_sem_excecao(self):
        self.criar_manual(
            payload=criar_payload(
                url_imagem="attachment:arquivo.gif"
            ),
            imagens=("arquivo.gif",),
        )
        cog = self.criar_cog()

        with self.assertLogs("cogs.iniciar", level="WARNING"):
            manual = cog.carregar_manual("pocao")

        self.assertIsNone(manual)

    def test_attachment_ausente_ou_ambiguo_e_blob_sao_rejeitados(self):
        self.criar_manual(
            "ausente",
            payload=criar_payload(
                url_imagem="attachment://nao_existe.gif"
            ),
        )
        self.criar_manual(
            "ambiguo",
            payload=criar_payload(
                url_imagem="attachment://nao_existe.gif"
            ),
            imagens=("primeira.gif", "segunda.png"),
        )
        with self.assertLogs("cogs.iniciar", level="WARNING") as logs:
            self.assertIsNone(
                self.criar_cog(nome="ausente").carregar_manual("ausente")
            )
            self.assertIsNone(
                self.criar_cog(nome="ambiguo").carregar_manual("ambiguo")
            )

        mensagens = "\n".join(logs.output)
        self.assertIn("ausente", mensagens)
        self.assertIn("ambiguo", mensagens)

    def test_manual_ausente_e_jsons_invalidos_sao_isolados(self):
        self.criar_manual("malformado", json_bruto="{")
        self.criar_manual("vazio", json_bruto="")
        self.criar_manual("sem_embeds", payload={"attachments": []})
        self.criar_manual("embeds_vazias", payload={"embeds": []})
        self.criar_manual(
            "embed_invalida",
            payload={"embeds": [{"color": "azul"}]},
        )
        self.criar_manual(
            "primeira_invalida",
            payload={
                "embeds": [
                    {"color": "azul"},
                    criar_payload()["embeds"][0],
                ]
            },
        )
        pasta_encoding = self.criar_manual("encoding_invalido")
        (pasta_encoding / "manual.json").write_bytes(b"\xff\xfe")
        nomes = (
            "inexistente",
            "malformado",
            "vazio",
            "sem_embeds",
            "embeds_vazias",
            "embed_invalida",
            "primeira_invalida",
            "encoding_invalido",
        )

        with self.assertLogs("cogs.iniciar", level="WARNING") as logs:
            for nome in nomes:
                with self.subTest(nome=nome):
                    cog = self.criar_cog(nome=nome)
                    self.assertIsNone(cog.carregar_manual(nome))

        mensagens = "\n".join(logs.output)

        for nome in nomes:
            with self.subTest(log=nome):
                self.assertIn(nome, mensagens)

    def test_erro_ao_abrir_manual_e_registrado_sem_propagar(self):
        self.criar_manual(payload=criar_payload())
        cog = self.criar_cog()

        with patch("pathlib.Path.open", side_effect=OSError("falha")):
            with self.assertLogs("cogs.iniciar", level="ERROR"):
                manual = cog.carregar_manual("pocao")

        self.assertIsNone(manual)


class ComandoIniciarTests(
    DiretorioTemporarioMixin,
    unittest.IsolatedAsyncioTestCase,
):
    def criar_cog(self, bot=None) -> Iniciar:
        return Iniciar(
            bot=bot,
            diretorio_manuais=self.diretorio / "pocao",
        )

    @staticmethod
    def criar_interaction() -> SimpleNamespace:
        return SimpleNamespace(
            channel="canal-teste",
            response=SimpleNamespace(send_message=AsyncMock()),
        )

    @staticmethod
    def obter_content(chamada) -> Optional[str]:
        argumentos, nomeados = chamada

        if "content" in nomeados:
            return nomeados["content"]

        return argumentos[0] if argumentos else None

    async def test_callback_envia_somente_embed_sem_sortear_resultado(self):
        self.criar_manual(
            payload=criar_payload(
                url_imagem="https://example.com/manual.gif"
            )
        )
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        with patch.object(
            Pocoes,
            "carregar_resultados",
            side_effect=AssertionError("não deve carregar resultados"),
        ) as carregar_resultados, patch.object(
            Pocoes,
            "sortear_resultado",
            side_effect=AssertionError("não deve sortear resultados"),
        ) as sortear_resultado, patch(
            "random.choice",
            side_effect=AssertionError("não deve usar random.choice"),
        ) as escolha:
            await Iniciar.iniciar_pocao.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        chamada = interaction.response.send_message.await_args
        self.assertEqual(chamada.args, ())
        self.assertNotIn("content", chamada.kwargs)
        self.assertNotIn("file", chamada.kwargs)
        self.assertIsInstance(chamada.kwargs["embed"], discord.Embed)
        self.assertEqual(
            chamada.kwargs["embed"].description,
            DESCRICAO_UNICODE,
        )
        carregar_resultados.assert_not_called()
        sortear_resultado.assert_not_called()
        escolha.assert_not_called()

    async def test_callback_envia_embed_e_attachment_no_mesmo_response(self):
        self.criar_manual(
            payload=criar_payload(
                url_imagem="attachment://arquivo-do-discohook.gif"
            ),
            imagens=("manual-local.gif",),
        )
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        await Iniciar.iniciar_pocao.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        chamada = interaction.response.send_message.await_args
        arquivo = chamada.kwargs["file"]
        self.assertEqual(chamada.args, ())
        self.assertNotIn("content", chamada.kwargs)
        self.assertIsInstance(chamada.kwargs["embed"], discord.Embed)
        self.assertIsInstance(arquivo, discord.File)
        self.assertEqual(
            chamada.kwargs["embed"].image.url,
            f"attachment://{arquivo.filename}",
        )
        self.assertTrue(arquivo.fp.closed)

    async def test_callback_informa_quando_manual_nao_existe(self):
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        with self.assertLogs("cogs.iniciar", level="WARNING"):
            await Iniciar.iniciar_pocao.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        chamada = interaction.response.send_message.await_args
        self.assertEqual(
            self.obter_content(chamada),
            MENSAGEM_MANUAL_INDISPONIVEL,
        )
        self.assertNotIn("embed", chamada.kwargs)
        self.assertNotIn("file", chamada.kwargs)

    async def test_json_invalido_resulta_em_resposta_amigavel(self):
        self.criar_manual(json_bruto="{")
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        with self.assertLogs("cogs.iniciar", level="WARNING"):
            await Iniciar.iniciar_pocao.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once_with(
            MENSAGEM_MANUAL_INDISPONIVEL
        )

    async def test_erro_ao_preparar_resulta_em_resposta_amigavel(self):
        self.criar_manual(payload=criar_payload())
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        with patch.object(
            cog,
            "preparar_envio",
            side_effect=OSError("falha simulada"),
        ):
            with self.assertLogs("cogs.iniciar", level="ERROR"):
                await Iniciar.iniciar_pocao.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once_with(
            MENSAGEM_MANUAL_INDISPONIVEL
        )

    async def test_erros_do_discord_sao_registrados_sem_propagar(self):
        self.criar_manual(payload=criar_payload())
        cog = self.criar_cog()
        resposta_forbidden = SimpleNamespace(status=403, reason="Proibido")
        resposta_http = SimpleNamespace(status=500, reason="Erro")
        casos = (
            (
                discord.Forbidden(resposta_forbidden, "Falha simulada"),
                "WARNING",
            ),
            (
                discord.HTTPException(resposta_http, "Falha simulada"),
                "ERROR",
            ),
        )

        for erro, nivel in casos:
            with self.subTest(tipo=type(erro).__name__):
                interaction = self.criar_interaction()
                interaction.response.send_message.side_effect = erro

                with self.assertLogs("cogs.iniciar", level=nivel):
                    await Iniciar.iniciar_pocao.callback(cog, interaction)

                interaction.response.send_message.assert_awaited_once()

    async def test_erro_http_tenta_resposta_amigavel_se_interacao_esta_aberta(
        self,
    ):
        self.criar_manual(payload=criar_payload())
        cog = self.criar_cog()
        resposta = SimpleNamespace(status=400, reason="Embed rejeitada")
        interaction = self.criar_interaction()
        interaction.response.is_done = lambda: False
        interaction.response.send_message.side_effect = [
            discord.HTTPException(resposta, "Falha simulada"),
            None,
        ]

        with self.assertLogs("cogs.iniciar", level="ERROR"):
            await Iniciar.iniciar_pocao.callback(cog, interaction)

        self.assertEqual(
            interaction.response.send_message.await_count,
            2,
        )
        self.assertEqual(
            interaction.response.send_message.await_args_list[1].args,
            (MENSAGEM_MANUAL_INDISPONIVEL,),
        )

    async def test_rele_manual_alterado_sem_sincronizar_novamente(self):
        bot = SimpleNamespace(
            tree=SimpleNamespace(sync=AsyncMock()),
        )
        cog = self.criar_cog(bot=bot)
        self.criar_manual(
            payload=criar_payload(descricao="Versão inicial")
        )
        primeira_interaction = self.criar_interaction()

        await Iniciar.iniciar_pocao.callback(cog, primeira_interaction)

        self.criar_manual(
            payload=criar_payload(descricao="Versão atualizada")
        )
        segunda_interaction = self.criar_interaction()

        await Iniciar.iniciar_pocao.callback(cog, segunda_interaction)

        primeira_embed = (
            primeira_interaction.response.send_message.await_args.kwargs[
                "embed"
            ]
        )
        segunda_embed = (
            segunda_interaction.response.send_message.await_args.kwargs[
                "embed"
            ]
        )
        self.assertEqual(primeira_embed.description, "Versão inicial")
        self.assertEqual(segunda_embed.description, "Versão atualizada")
        bot.tree.sync.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
