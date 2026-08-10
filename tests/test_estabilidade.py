import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from typing import Dict, Optional, Tuple
from unittest.mock import AsyncMock, call, patch

import discord

from cogs.iniciar import Iniciar
from cogs.pocoes import (
    DIRETORIO_ESTABILIDADE,
    MENSAGEM_ESTABILIDADE_INDISPONIVEL,
    RESULTADOS_ESTABILIDADE,
    Estabilidade,
    Pocoes,
    ResultadoEstabilidade,
)


DESCRICAO_ESTAVEL = (
    "⚗️ Poção ESTÁVEL ﹒だ⸺𝐈\n"
    "**Acentos preservados:** ação, bênção e coração."
)
DESCRICAO_INSTAVEL = "💥 Poção INSTÁVEL — reação imprevisível."


def criar_payload(
    *,
    descricao: str,
    url_imagem: Optional[str] = None,
    url_thumbnail: Optional[str] = None,
) -> Dict:
    embed = {
        "color": 4069400,
        "title": "Resultado da Estabilidade 🧪",
        "description": descricao,
        "fields": [
            {
                "name": "✨ Estado",
                "value": "**Análise concluída**\nLinha seguinte",
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
                "filename": "arquivo-exportado.gif",
                "url": "blob:https://discohook.app/nao-utilizar",
            }
        ],
    }


class DiretorioEstabilidadeMixin:
    def setUp(self) -> None:
        super().setUp()
        self._temporario = tempfile.TemporaryDirectory()
        self.diretorio = Path(self._temporario.name) / "estabilidade"
        self.diretorio.mkdir(parents=True)

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
        raiz: Optional[Path] = None,
    ) -> Path:
        pasta = (raiz or self.diretorio) / nome
        pasta.mkdir(parents=True, exist_ok=True)

        if payload is not None:
            (pasta / "resultado.json").write_text(
                json.dumps(payload, ensure_ascii=False),
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

    def criar_par_valido(self, *, raiz: Optional[Path] = None) -> None:
        self.criar_resultado(
            "estavel",
            payload=criar_payload(descricao=DESCRICAO_ESTAVEL),
            raiz=raiz,
        )
        self.criar_resultado(
            "instavel",
            payload=criar_payload(descricao=DESCRICAO_INSTAVEL),
            raiz=raiz,
        )


class CarregamentoEstabilidadeTests(
    DiretorioEstabilidadeMixin,
    unittest.TestCase,
):
    def criar_cog(self, *, diretorio: Optional[Path] = None) -> Estabilidade:
        return Estabilidade(
            bot=None,
            diretorio_estabilidade=diretorio or self.diretorio,
        )

    @staticmethod
    def criar_objeto_resultado(nome: str) -> ResultadoEstabilidade:
        return ResultadoEstabilidade(
            nome=nome,
            pasta=Path(nome),
            embed_data={"description": nome},
        )

    def test_diretorio_padrao_e_nomes_obrigatorios_sao_fixos(self):
        raiz_projeto = Path(__file__).resolve().parent.parent

        self.assertEqual(
            DIRETORIO_ESTABILIDADE,
            raiz_projeto / "data" / "estabilidade",
        )
        self.assertEqual(
            RESULTADOS_ESTABILIDADE,
            ("estavel", "instavel"),
        )

    def test_carrega_os_dois_resultados_e_preserva_embed_utf8_completa(self):
        payload_estavel = criar_payload(
            descricao=DESCRICAO_ESTAVEL,
            url_imagem="https://example.com/estavel.gif",
            url_thumbnail="http://example.com/miniatura.png",
        )
        payload_estavel["embeds"].append(
            {"description": "segunda embed ignorada"}
        )
        self.criar_resultado("estavel", payload=payload_estavel)
        self.criar_resultado(
            "instavel",
            payload=criar_payload(descricao=DESCRICAO_INSTAVEL),
        )
        cog = self.criar_cog()

        resultados = cog.carregar_resultados_obrigatorios()

        self.assertIsNotNone(resultados)
        self.assertEqual(list(resultados), ["estavel", "instavel"])
        embed, arquivo = cog.preparar_envio(resultados["estavel"])
        self.assertIsNone(arquivo)
        self.assertEqual(embed.title, "Resultado da Estabilidade 🧪")
        self.assertEqual(embed.description, DESCRICAO_ESTAVEL)
        self.assertEqual(embed.color.value, 4069400)
        self.assertEqual(embed.fields[0].name, "✨ Estado")
        self.assertEqual(
            embed.fields[0].value,
            "**Análise concluída**\nLinha seguinte",
        )
        self.assertEqual(embed.footer.text, "Rodapé com ç e ã")
        self.assertEqual(embed.author.name, "Alquimista")
        self.assertEqual(
            embed.author.url,
            "https://example.com/alquimista",
        )
        self.assertEqual(
            embed.image.url,
            "https://example.com/estavel.gif",
        )
        self.assertEqual(
            embed.thumbnail.url,
            "http://example.com/miniatura.png",
        )

    def test_http_e_https_nao_exigem_arquivo_local(self):
        urls = (
            "http://example.com/estavel.png",
            "https://example.com/instavel.webp",
        )

        for nome, url in zip(RESULTADOS_ESTABILIDADE, urls):
            self.criar_resultado(
                nome,
                payload=criar_payload(
                    descricao=nome,
                    url_imagem=url,
                ),
            )

        cog = self.criar_cog()
        resultados = cog.carregar_resultados_obrigatorios()

        self.assertIsNotNone(resultados)

        for nome, url in zip(RESULTADOS_ESTABILIDADE, urls):
            with self.subTest(nome=nome):
                embed, arquivo = cog.preparar_envio(resultados[nome])
                self.assertIsNone(arquivo)
                self.assertEqual(embed.image.url, url)

    def test_attachment_exato_tem_prioridade_entre_varias_imagens(self):
        self.criar_resultado(
            "estavel",
            payload=criar_payload(
                descricao=DESCRICAO_ESTAVEL,
                url_imagem="attachment://estável.gif",
            ),
            imagens=("estável.gif", "outra.png"),
        )
        cog = self.criar_cog()

        resultado = cog.carregar_resultado("estavel")

        self.assertIsNotNone(resultado)
        self.assertEqual(resultado.attachment.name, "estável.gif")
        embed, arquivo = cog.preparar_envio(resultado)

        try:
            self.assertIsInstance(arquivo, discord.File)
            self.assertTrue(arquivo.filename.isascii())
            self.assertEqual(
                embed.image.url,
                f"attachment://{arquivo.filename}",
            )
        finally:
            arquivo.close()

    def test_attachment_normalizado_e_encontrado_entre_varias_imagens(self):
        self.criar_resultado(
            "estavel",
            payload=criar_payload(
                descricao=DESCRICAO_ESTAVEL,
                url_imagem="attachment://estável.gif",
            ),
            imagens=("estavel.gif", "outra.png"),
        )
        cog = self.criar_cog()

        resultado = cog.carregar_resultado("estavel")

        self.assertIsNotNone(resultado)
        self.assertEqual(resultado.attachment.name, "estavel.gif")

    def test_attachment_unico_aceita_nome_diferente(self):
        self.criar_resultado(
            "instavel",
            payload=criar_payload(
                descricao=DESCRICAO_INSTAVEL,
                url_imagem="attachment://nome-exportado.gif",
            ),
            imagens=("resultado local.WEBP",),
        )
        cog = self.criar_cog()

        resultado = cog.carregar_resultado("instavel")

        self.assertIsNotNone(resultado)
        self.assertEqual(resultado.attachment.name, "resultado local.WEBP")
        self.assertEqual(
            resultado.nome_attachment,
            "estabilidade_instavel.webp",
        )

    def test_attachment_ausente_ambiguo_e_blob_invalidam_o_resultado(self):
        casos = self.diretorio.parent

        raiz_ausente = casos / "caso_ausente"
        raiz_ausente.mkdir()
        self.criar_resultado(
            "estavel",
            raiz=raiz_ausente,
            payload=criar_payload(
                descricao=DESCRICAO_ESTAVEL,
                url_imagem="attachment://ausente.gif",
            ),
        )

        raiz_ambiguo = casos / "caso_ambiguo"
        raiz_ambiguo.mkdir()
        self.criar_resultado(
            "estavel",
            raiz=raiz_ambiguo,
            payload=criar_payload(
                descricao=DESCRICAO_ESTAVEL,
                url_imagem="attachment://sem-correspondencia.gif",
            ),
            imagens=("primeira.gif", "segunda.png"),
        )

        raiz_blob = casos / "caso_blob"
        raiz_blob.mkdir()
        self.criar_resultado(
            "estavel",
            raiz=raiz_blob,
            payload=criar_payload(
                descricao=DESCRICAO_ESTAVEL,
                url_imagem="blob:https://discohook.app/temporaria",
            ),
        )

        with self.assertLogs("cogs.pocoes", level="WARNING") as logs:
            self.assertIsNone(
                self.criar_cog(diretorio=raiz_ausente).carregar_resultado(
                    "estavel"
                )
            )
            self.assertIsNone(
                self.criar_cog(diretorio=raiz_ambiguo).carregar_resultado(
                    "estavel"
                )
            )
            self.assertIsNone(
                self.criar_cog(diretorio=raiz_blob).carregar_resultado(
                    "estavel"
                )
            )

        mensagens = "\n".join(logs.output)
        self.assertIn("Attachment local não encontrado", mensagens)
        self.assertIn("Attachment local ambíguo", mensagens)
        self.assertIn("não suportada", mensagens)

    def test_jsons_invalidos_e_erros_de_encoding_sao_rejeitados(self):
        casos = self.diretorio.parent
        configuracoes = (
            ("sem_arquivo", None, None),
            ("malformado", None, "{"),
            ("vazio", None, ""),
            ("sem_embeds", {"attachments": []}, None),
            ("embeds_vazias", {"embeds": []}, None),
            ("embed_invalida", {"embeds": [{"color": "azul"}]}, None),
        )

        for nome_caso, payload, json_bruto in configuracoes:
            raiz = casos / nome_caso
            raiz.mkdir()
            self.criar_resultado(
                "estavel",
                raiz=raiz,
                payload=payload,
                json_bruto=json_bruto,
            )

        raiz_encoding = casos / "encoding"
        raiz_encoding.mkdir()
        pasta_encoding = self.criar_resultado(
            "estavel",
            raiz=raiz_encoding,
        )
        (pasta_encoding / "resultado.json").write_bytes(b"\xff\xfe")

        with self.assertLogs("cogs.pocoes", level="WARNING"):
            for nome_caso, _, _ in configuracoes:
                with self.subTest(nome_caso=nome_caso):
                    self.assertIsNone(
                        self.criar_cog(
                            diretorio=casos / nome_caso
                        ).carregar_resultado("estavel")
                    )

            self.assertIsNone(
                self.criar_cog(
                    diretorio=raiz_encoding
                ).carregar_resultado("estavel")
            )

    def test_valida_ambos_mesmo_quando_o_primeiro_e_invalido(self):
        cog = self.criar_cog()
        instavel = self.criar_objeto_resultado("instavel")

        with patch.object(
            cog,
            "carregar_resultado",
            side_effect=(None, instavel),
        ) as carregar:
            resultados = cog.carregar_resultados_obrigatorios()

        self.assertIsNone(resultados)
        self.assertEqual(
            carregar.call_args_list,
            [call("estavel"), call("instavel")],
        )

    def test_um_resultado_invalido_impede_sorteio_nos_dois_lados(self):
        casos = self.diretorio.parent

        for ausente in RESULTADOS_ESTABILIDADE:
            raiz = casos / f"ausente_{ausente}"
            raiz.mkdir()

            for nome in RESULTADOS_ESTABILIDADE:
                if nome != ausente:
                    self.criar_resultado(
                        nome,
                        raiz=raiz,
                        payload=criar_payload(descricao=nome),
                    )

            cog = self.criar_cog(diretorio=raiz)

            with self.subTest(ausente=ausente):
                with patch(
                    "cogs.pocoes.random.choice"
                ) as escolha, self.assertLogs(
                    "cogs.pocoes",
                    level="WARNING",
                ):
                    resultados = cog.carregar_resultados_obrigatorios()

                self.assertIsNone(resultados)
                escolha.assert_not_called()

    def test_sorteio_delega_para_choice_com_apenas_os_dois_nomes_fixos(self):
        resultados = {
            nome: self.criar_objeto_resultado(nome)
            for nome in RESULTADOS_ESTABILIDADE
        }

        for nome in RESULTADOS_ESTABILIDADE:
            with self.subTest(nome=nome):
                with patch(
                    "cogs.pocoes.random.choice",
                    return_value=nome,
                ) as escolha:
                    selecionado = Estabilidade.sortear_resultado(resultados)

                self.assertIs(selecionado, resultados[nome])
                escolha.assert_called_once_with(("estavel", "instavel"))

    def test_pastas_e_arquivos_extras_nao_alteram_as_opcoes_do_sorteio(self):
        self.criar_par_valido()
        self.criar_resultado(
            "terceiro_resultado",
            payload=criar_payload(descricao="Não deve participar"),
        )
        (self.diretorio / "arquivo_extra.json").write_text(
            "{}",
            encoding="utf-8",
        )
        cog = self.criar_cog()
        resultados = cog.carregar_resultados_obrigatorios()

        self.assertEqual(set(resultados), {"estavel", "instavel"})

        with patch(
            "cogs.pocoes.random.choice",
            return_value="estavel",
        ) as escolha:
            cog.sortear_resultado(resultados)

        escolha.assert_called_once_with(("estavel", "instavel"))

    def test_erro_ao_abrir_resultado_e_registrado_sem_propagar(self):
        self.criar_resultado(
            "estavel",
            payload=criar_payload(descricao=DESCRICAO_ESTAVEL),
        )
        cog = self.criar_cog()

        with patch("pathlib.Path.open", side_effect=OSError("falha")):
            with self.assertLogs("cogs.pocoes", level="ERROR"):
                resultado = cog.carregar_resultado("estavel")

        self.assertIsNone(resultado)


class ComandoEstabilidadeTests(
    DiretorioEstabilidadeMixin,
    unittest.IsolatedAsyncioTestCase,
):
    def criar_cog(self, bot=None) -> Estabilidade:
        return Estabilidade(
            bot=bot,
            diretorio_estabilidade=self.diretorio,
        )

    @staticmethod
    def criar_interaction() -> SimpleNamespace:
        return SimpleNamespace(
            channel=SimpleNamespace(send=AsyncMock()),
            response=SimpleNamespace(send_message=AsyncMock()),
        )

    @staticmethod
    def obter_content(chamada) -> Optional[str]:
        argumentos, nomeados = chamada

        if "content" in nomeados:
            return nomeados["content"]

        return argumentos[0] if argumentos else None

    def test_metadados_identificam_apenas_o_slash_command(self):
        self.assertEqual(Estabilidade.estabilidade.name, "estabilidade")
        self.assertEqual(Estabilidade.estabilidade.parameters, [])
        self.assertEqual(
            Estabilidade.estabilidade.description,
            "Determina se a poção criada ficou estável ou instável.",
        )

    async def test_callback_envia_somente_embed_e_e_independente(self):
        self.criar_par_valido()
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        with patch(
            "cogs.pocoes.random.choice",
            return_value="estavel",
        ) as escolha, patch.object(
            Pocoes,
            "carregar_resultados",
            side_effect=AssertionError("não deve carregar /poção"),
        ) as carregar_pocoes, patch.object(
            Pocoes,
            "sortear_resultado",
            side_effect=AssertionError("não deve sortear /poção"),
        ) as sortear_pocao, patch.object(
            Iniciar,
            "carregar_manual",
            side_effect=AssertionError("não deve carregar /iniciar poção"),
        ) as carregar_manual:
            await Estabilidade.estabilidade.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        chamada = interaction.response.send_message.await_args
        self.assertEqual(chamada.args, ())
        self.assertNotIn("content", chamada.kwargs)
        self.assertNotIn("file", chamada.kwargs)
        self.assertIsInstance(chamada.kwargs["embed"], discord.Embed)
        self.assertEqual(
            chamada.kwargs["embed"].description,
            DESCRICAO_ESTAVEL,
        )
        interaction.channel.send.assert_not_awaited()
        escolha.assert_called_once_with(("estavel", "instavel"))
        carregar_pocoes.assert_not_called()
        sortear_pocao.assert_not_called()
        carregar_manual.assert_not_called()

    async def test_callback_envia_attachment_apenas_do_resultado_sorteado(self):
        self.criar_resultado(
            "estavel",
            payload=criar_payload(
                descricao=DESCRICAO_ESTAVEL,
                url_imagem="attachment://estavel.gif",
            ),
            imagens=("estavel.gif",),
        )
        self.criar_resultado(
            "instavel",
            payload=criar_payload(
                descricao=DESCRICAO_INSTAVEL,
                url_imagem="attachment://instavel.gif",
            ),
            imagens=("instavel.gif",),
        )
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        with patch(
            "cogs.pocoes.random.choice",
            return_value="instavel",
        ):
            await Estabilidade.estabilidade.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once()
        chamada = interaction.response.send_message.await_args
        arquivo = chamada.kwargs["file"]
        self.assertEqual(chamada.args, ())
        self.assertNotIn("content", chamada.kwargs)
        self.assertEqual(
            chamada.kwargs["embed"].description,
            DESCRICAO_INSTAVEL,
        )
        self.assertEqual(
            chamada.kwargs["embed"].image.url,
            f"attachment://{arquivo.filename}",
        )
        self.assertIn("instavel", arquivo.filename)
        self.assertTrue(arquivo.fp.closed)

    async def test_callback_nao_sorteia_se_um_resultado_for_invalido(self):
        self.criar_resultado(
            "estavel",
            payload=criar_payload(descricao=DESCRICAO_ESTAVEL),
        )
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        with patch(
            "cogs.pocoes.random.choice"
        ) as escolha, self.assertLogs(
            "cogs.pocoes",
            level="WARNING",
        ):
            await Estabilidade.estabilidade.callback(cog, interaction)

        escolha.assert_not_called()
        interaction.response.send_message.assert_awaited_once()
        chamada = interaction.response.send_message.await_args
        self.assertEqual(
            self.obter_content(chamada),
            MENSAGEM_ESTABILIDADE_INDISPONIVEL,
        )
        self.assertNotIn("embed", chamada.kwargs)
        self.assertNotIn("file", chamada.kwargs)

    async def test_erro_ao_preparar_resulta_em_resposta_amigavel(self):
        self.criar_par_valido()
        cog = self.criar_cog()
        interaction = self.criar_interaction()

        with patch(
            "cogs.pocoes.random.choice",
            return_value="estavel",
        ), patch.object(
            cog,
            "preparar_envio",
            side_effect=OSError("falha simulada"),
        ):
            with self.assertLogs("cogs.pocoes", level="ERROR"):
                await Estabilidade.estabilidade.callback(cog, interaction)

        interaction.response.send_message.assert_awaited_once_with(
            MENSAGEM_ESTABILIDADE_INDISPONIVEL
        )

    async def test_erros_do_discord_sao_registrados_sem_propagar(self):
        self.criar_par_valido()
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

                with patch(
                    "cogs.pocoes.random.choice",
                    return_value="estavel",
                ), self.assertLogs("cogs.pocoes", level=nivel):
                    await Estabilidade.estabilidade.callback(cog, interaction)

                interaction.response.send_message.assert_awaited_once()

    async def test_rele_json_sem_sincronizar_novamente(self):
        bot = SimpleNamespace(
            tree=SimpleNamespace(sync=AsyncMock()),
        )
        cog = self.criar_cog(bot=bot)
        self.criar_par_valido()
        primeira_interaction = self.criar_interaction()

        with patch(
            "cogs.pocoes.random.choice",
            return_value="estavel",
        ) as escolha:
            await Estabilidade.estabilidade.callback(
                cog,
                primeira_interaction,
            )
            self.criar_resultado(
                "estavel",
                payload=criar_payload(descricao="Versão atualizada"),
            )
            segunda_interaction = self.criar_interaction()
            await Estabilidade.estabilidade.callback(
                cog,
                segunda_interaction,
            )

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
        self.assertEqual(primeira_embed.description, DESCRICAO_ESTAVEL)
        self.assertEqual(segunda_embed.description, "Versão atualizada")
        self.assertEqual(escolha.call_count, 2)
        bot.tree.sync.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
