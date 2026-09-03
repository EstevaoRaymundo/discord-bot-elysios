import asyncio
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import tempfile
import unittest
from typing import Dict, Iterable, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.ingredientes import (
    ARQUIVOS_INGREDIENTES,
    CAMINHO_BANCO_COOLDOWNS,
    CANAL_TESTES_ID,
    DIRETORIO_INGREDIENTES,
    DIRETORIOS_INGREDIENTES,
    JANELA_COOLDOWN_SEGUNDOS,
    LIMITE_USOS,
    MENSAGEM_COOLDOWN_INGREDIENTES,
    MENSAGEM_INGREDIENTES_INDISPONIVEL,
    NOME_TABELA_COOLDOWNS,
    PESOS_INGREDIENTES,
    RESULTADOS_INGREDIENTES,
    Ingredientes,
    ResultadoIngrediente,
)
from cogs.pocoes import Pocoes


BASE_CDN = (
    "https://pub-57a72b7c1133428e9da66f38a6b6bbf4.r2.dev/"
    "ingredientes"
)

ESPECIFICACAO_INGREDIENTES = {
    "comum": {
        "cogumelos": "cogumelos.png",
        "lirio": "lirio.png",
        "gengibre": "gengibre.png",
        "salgema": "salgema.png",
        "petalabeladona": "petalabeladona.png",
    },
    "raro": {
        "perolanegra": "perolanegra.jpg",
        "musgoruinas": "musgoruinas.jpg",
        "escamadragao": "escamadragao.jpg",
        "floreterna": "floreterna.jpg",
        "essenciaempatica": "essenciaempatica.jpg",
    },
    "lendario": {
        "cometaarcano": "cometaarcano.jpg",
        "sonhagumelo": "sonhagumelo.jpg",
        "meldarainharubra": "meldarainharubra.png",
        "nogueiradeferro": "nogueiradeferro.png",
        "pedradasestacoes": "pedradasestacoes.png",
    },
    "mitico": {
        "rasgaveus": "rasgaveus.jpg",
        "saisepidote": "saisepidote.jpg",
        "sangueberserk": "sangueberserk.jpg",
        "solaria": "solaria.jpg",
        "nocturnia": "nocturnia.png",
    },
}


def url_oficial(nome_arquivo: str) -> str:
    return f"{BASE_CDN}/{nome_arquivo}"


def criar_payload(
    nome: str,
    nome_arquivo: str,
    *,
    titulo: Optional[str] = None,
    url_imagem: Optional[str] = None,
) -> Dict:
    return {
        "embeds": [
            {
                "color": 4069400,
                "title": titulo or f"Ingrediente: {nome}",
                "description": (
                    f"Descrição de {nome} com acentos, ✨ e quebra\n"
                    "de linha preservada."
                ),
                "fields": [
                    {
                        "name": "🧪 Categoria",
                        "value": nome,
                        "inline": False,
                    }
                ],
                "footer": {"text": "Ingredientes de Elysios"},
                "image": {
                    "url": url_imagem or url_oficial(nome_arquivo),
                },
            }
        ],
        "attachments": [
            {
                "filename": nome_arquivo,
                "url": "blob:https://discohook.app/nao-utilizar",
            }
        ],
    }


class ProvedorCDNFalso:
    def __init__(
        self,
        *,
        estado_cache: Optional[bool] = True,
        disponivel: bool = True,
    ) -> None:
        self.consultar_cache_cdn = MagicMock(return_value=estado_cache)
        self.cdn_disponivel = AsyncMock(return_value=disponivel)


class DiretorioIngredientesTemporarioMixin:
    def setUp(self) -> None:
        super().setUp()
        self._temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporario.cleanup)
        self.raiz_temporaria = Path(self._temporario.name)
        self.diretorio = self.raiz_temporaria / "ingredientes"
        self.caminho_banco = (
            self.raiz_temporaria
            / "estado"
            / "database"
            / "cooldowns.db"
        )
        self.agora = 1_800_000_000.0
        self.provedor = ProvedorCDNFalso()
        self.cog = self.criar_cog()
        self._cog_principal_encerrado = False

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.addAsyncCleanup(self._encerrar_cog_principal)

    async def _encerrar_cog_principal(self) -> None:
        if not self._cog_principal_encerrado:
            await self.cog.cog_unload()
            self._cog_principal_encerrado = True

    def criar_cog(
        self,
        *,
        provedor=None,
        caminho_banco: Optional[Path] = None,
    ) -> Ingredientes:
        return Ingredientes(
            bot=None,
            diretorio_ingredientes=self.diretorio,
            caminho_banco=caminho_banco or self.caminho_banco,
            provedor_cdn=provedor or self.provedor,
            relogio=lambda: self.agora,
        )

    def criar_resultado(
        self,
        raridade: str,
        nome: str,
        *,
        payload: Optional[Dict] = None,
        criar_backup: bool = True,
    ) -> Path:
        nome_arquivo = ESPECIFICACAO_INGREDIENTES[raridade][nome]
        pasta = (
            self.diretorio
            / DIRETORIOS_INGREDIENTES[raridade]
            / nome
        )
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "resultado.json").write_text(
            json.dumps(
                payload or criar_payload(nome, nome_arquivo),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        if criar_backup:
            (pasta / nome_arquivo).write_bytes(
                f"imagem-local-{nome}".encode("utf-8")
            )

        return pasta

    def criar_todos_resultados(
        self,
        *,
        omitir: Optional[Tuple[str, str]] = None,
    ) -> None:
        for raridade, ingredientes in ESPECIFICACAO_INGREDIENTES.items():
            for nome in ingredientes:
                if omitir == (raridade, nome):
                    continue

                self.criar_resultado(raridade, nome)

    @staticmethod
    def criar_interaction(
        *,
        user_id: int = 123456,
        channel_id: int = 987654,
    ) -> SimpleNamespace:
        estado = {"concluida": False}

        async def diferir(**_kwargs) -> None:
            estado["concluida"] = True

        async def enviar_resposta(*_args, **_kwargs) -> None:
            estado["concluida"] = True

        response = SimpleNamespace(
            defer=AsyncMock(side_effect=diferir),
            send_message=AsyncMock(side_effect=enviar_resposta),
            is_done=MagicMock(side_effect=lambda: estado["concluida"]),
        )
        return SimpleNamespace(
            user=SimpleNamespace(id=user_id, mention=f"<@{user_id}>"),
            channel_id=channel_id,
            channel=f"canal-{channel_id}",
            response=response,
            edit_original_response=AsyncMock(),
            followup=SimpleNamespace(send=AsyncMock()),
        )

    @staticmethod
    def _conteudo_chamada(chamada) -> Optional[str]:
        if "content" in chamada.kwargs:
            return chamada.kwargs["content"]

        return chamada.args[0] if chamada.args else None

    @classmethod
    def conteudos_enviados(cls, interaction: SimpleNamespace) -> Tuple[str, ...]:
        chamadas = (
            interaction.response.send_message.await_args_list
            + interaction.edit_original_response.await_args_list
            + interaction.followup.send.await_args_list
        )
        return tuple(
            conteudo
            for chamada in chamadas
            if (conteudo := cls._conteudo_chamada(chamada)) is not None
        )

    @staticmethod
    def embeds_enviadas(interaction: SimpleNamespace) -> Tuple[discord.Embed, ...]:
        chamadas = (
            interaction.response.send_message.await_args_list
            + interaction.edit_original_response.await_args_list
            + interaction.followup.send.await_args_list
        )
        return tuple(
            chamada.kwargs["embed"]
            for chamada in chamadas
            if isinstance(chamada.kwargs.get("embed"), discord.Embed)
        )

    def linhas_cooldown(self) -> Tuple[Tuple[int, float], ...]:
        with closing(sqlite3.connect(self.caminho_banco)) as conexao:
            linhas = conexao.execute(
                f"SELECT user_id, used_at FROM {NOME_TABELA_COOLDOWNS} "
                "ORDER BY used_at, rowid"
            ).fetchall()

        return tuple((int(user_id), float(used_at)) for user_id, used_at in linhas)

    def contar_usos(self, user_id: Optional[int] = None) -> int:
        linhas = self.linhas_cooldown()

        if user_id is None:
            return len(linhas)

        return sum(id_registrado == user_id for id_registrado, _ in linhas)

    @staticmethod
    def selecionar_nome(nome: str):
        def selecionar(resultados: Iterable[ResultadoIngrediente]):
            return next(resultado for resultado in resultados if resultado.nome == nome)

        return selecionar


class ConfiguracaoIngredientesTests(unittest.TestCase):
    def test_configuracao_oficial_contem_quatro_raridades_e_vinte_itens(self):
        self.assertEqual(
            DIRETORIOS_INGREDIENTES,
            {
                "comum": "ingredientecomum",
                "raro": "ingredienteraro",
                "lendario": "ingredientelendario",
                "mitico": "ingredientemitico",
            },
        )
        self.assertEqual(
            PESOS_INGREDIENTES,
            {"comum": 62, "raro": 32, "lendario": 4, "mitico": 2},
        )
        self.assertEqual(sum(PESOS_INGREDIENTES.values()), 100)
        self.assertEqual(tuple(RESULTADOS_INGREDIENTES), tuple(PESOS_INGREDIENTES))

        esperados = {
            raridade: tuple(ingredientes)
            for raridade, ingredientes in ESPECIFICACAO_INGREDIENTES.items()
        }
        self.assertEqual(RESULTADOS_INGREDIENTES, esperados)
        self.assertEqual(
            ARQUIVOS_INGREDIENTES,
            {
                nome: arquivo
                for ingredientes in ESPECIFICACAO_INGREDIENTES.values()
                for nome, arquivo in ingredientes.items()
            },
        )
        self.assertEqual(
            sum(map(len, RESULTADOS_INGREDIENTES.values())),
            20,
        )
        self.assertTrue(
            all(
                len(nomes) == 5
                for nomes in RESULTADOS_INGREDIENTES.values()
            )
        )

    def test_diretorios_padrao_e_as_vinte_subpastas_existem(self):
        raiz_projeto = Path(__file__).resolve().parent.parent

        self.assertEqual(
            DIRETORIO_INGREDIENTES,
            raiz_projeto / "data" / "ingredientes",
        )
        self.assertEqual(
            CAMINHO_BANCO_COOLDOWNS,
            raiz_projeto / "data" / "database" / "cooldowns.db",
        )

        for raridade, ingredientes in ESPECIFICACAO_INGREDIENTES.items():
            for nome in ingredientes:
                with self.subTest(raridade=raridade, nome=nome):
                    self.assertTrue(
                        (
                            DIRETORIO_INGREDIENTES
                            / DIRETORIOS_INGREDIENTES[raridade]
                            / nome
                        ).is_dir()
                    )

    def test_metadados_expoem_slash_command_sem_parametros(self):
        self.assertEqual(Ingredientes.ingredientes.name, "ingredientes")
        self.assertEqual(Ingredientes.ingredientes.parameters, [])


class CarregamentoIngredientesTests(
    DiretorioIngredientesTemporarioMixin,
    unittest.TestCase,
):
    def test_carrega_as_urls_oficiais_exatas_dos_vinte_resultados(self):
        self.criar_todos_resultados()

        resultados = self.cog.carregar_resultados_obrigatorios()

        self.assertIsNotNone(resultados)
        self.assertEqual(set(resultados), set(ESPECIFICACAO_INGREDIENTES))

        for raridade, ingredientes in ESPECIFICACAO_INGREDIENTES.items():
            self.assertEqual(len(resultados[raridade]), 5)

            for resultado in resultados[raridade]:
                with self.subTest(raridade=raridade, nome=resultado.nome):
                    nome_arquivo = ingredientes[resultado.nome]
                    self.assertEqual(resultado.raridade, raridade)
                    self.assertEqual(resultado.arquivo_imagem, nome_arquivo)
                    self.assertEqual(resultado.url_cdn, url_oficial(nome_arquivo))
                    self.assertEqual(
                        resultado.caminho_backup,
                        (
                            self.diretorio
                            / DIRETORIOS_INGREDIENTES[raridade]
                            / resultado.nome
                            / nome_arquivo
                        ),
                    )

    def test_url_com_mesmo_nome_mas_origem_incorreta_e_rejeitada(self):
        nome = "cogumelos"
        nome_arquivo = ESPECIFICACAO_INGREDIENTES["comum"][nome]
        self.criar_resultado(
            "comum",
            nome,
            payload=criar_payload(
                nome,
                nome_arquivo,
                url_imagem=f"https://example.com/ingredientes/{nome_arquivo}",
            ),
        )

        with self.assertLogs("cogs.ingredientes", level="ERROR") as logs:
            resultado = self.cog.carregar_resultado("comum", nome)

        self.assertIsNone(resultado)
        self.assertIn("URL CDN inválida", "\n".join(logs.output))

    def test_resultado_json_e_relido_sem_reiniciar_o_cog(self):
        pasta = self.criar_resultado(
            "raro",
            "perolanegra",
            payload=criar_payload(
                "perolanegra",
                "perolanegra.jpg",
                titulo="Versão inicial",
            ),
        )

        primeiro = self.cog.carregar_resultado("raro", "perolanegra")
        payload_atualizado = criar_payload(
            "perolanegra",
            "perolanegra.jpg",
            titulo="Versão atualizada",
        )
        (pasta / "resultado.json").write_text(
            json.dumps(payload_atualizado, ensure_ascii=False),
            encoding="utf-8",
        )
        segundo = self.cog.carregar_resultado("raro", "perolanegra")

        self.assertIsNotNone(primeiro)
        self.assertIsNotNone(segundo)
        self.assertEqual(primeiro.embed_data["title"], "Versão inicial")
        self.assertEqual(segundo.embed_data["title"], "Versão atualizada")

    def test_sorteio_ocorre_em_duas_etapas_e_item_e_uniforme_na_categoria(self):
        self.criar_todos_resultados()
        resultados = self.cog.carregar_resultados_obrigatorios()
        self.assertIsNotNone(resultados)

        for raridade, nomes in RESULTADOS_INGREDIENTES.items():
            escolhido = nomes[3]

            with self.subTest(raridade=raridade, escolhido=escolhido):
                with patch(
                    "cogs.ingredientes.random.choices",
                    return_value=[raridade],
                ) as escolher_raridade:
                    with patch(
                        "cogs.ingredientes.random.choice",
                        side_effect=self.selecionar_nome(escolhido),
                    ) as escolher_item:
                        resultado = self.cog.sortear_resultado(resultados)

                escolher_raridade.assert_called_once_with(
                    tuple(PESOS_INGREDIENTES),
                    weights=tuple(PESOS_INGREDIENTES.values()),
                    k=1,
                )
                escolher_item.assert_called_once_with(resultados[raridade])
                self.assertEqual(len(escolher_item.call_args.args[0]), 5)
                self.assertEqual(resultado.raridade, raridade)
                self.assertEqual(resultado.nome, escolhido)


class FluxoIngredientesTests(
    DiretorioIngredientesTemporarioMixin,
    unittest.IsolatedAsyncioTestCase,
):
    async def test_conjunto_incompleto_impede_qualquer_sorteio(self):
        self.criar_todos_resultados(omitir=("mitico", "nocturnia"))
        interaction = self.criar_interaction()

        with patch("cogs.ingredientes.random.choices") as escolher_raridade:
            with patch("cogs.ingredientes.random.choice") as escolher_item:
                with self.assertLogs("cogs.ingredientes", level="WARNING") as logs:
                    await Ingredientes.ingredientes.callback(self.cog, interaction)

        escolher_raridade.assert_not_called()
        escolher_item.assert_not_called()
        self.provedor.consultar_cache_cdn.assert_not_called()
        self.provedor.cdn_disponivel.assert_not_awaited()
        interaction.response.defer.assert_awaited_once_with(thinking=True)
        interaction.response.send_message.assert_not_awaited()
        interaction.edit_original_response.assert_awaited_once_with(
            content=MENSAGEM_INGREDIENTES_INDISPONIVEL,
            embed=None,
            attachments=[],
        )
        self.assertIn("nocturnia", "\n".join(logs.output))
        self.assertEqual(self.contar_usos(), 0)

    async def test_defer_acontece_antes_da_consulta_ao_provedor(self):
        self.criar_todos_resultados()
        interaction = self.criar_interaction(channel_id=CANAL_TESTES_ID)

        def consultar_cache(_url: str) -> bool:
            self.assertEqual(interaction.response.defer.await_count, 1)
            return True

        self.provedor.consultar_cache_cdn.side_effect = consultar_cache

        with patch("cogs.ingredientes.random.choices", return_value=["comum"]):
            with patch(
                "cogs.ingredientes.random.choice",
                side_effect=self.selecionar_nome("lirio"),
            ):
                await Ingredientes.ingredientes.callback(self.cog, interaction)

        interaction.response.defer.assert_awaited_once_with(thinking=True)
        interaction.response.send_message.assert_not_awaited()
        interaction.followup.send.assert_not_awaited()
        self.assertEqual(len(self.embeds_enviadas(interaction)), 1)

    async def test_reutiliza_cache_do_provedor_e_verifica_so_url_sorteada(self):
        self.criar_todos_resultados()
        provedor = Pocoes(
            bot=None,
            diretorio_resultados=self.raiz_temporaria / "pocoes",
        )
        self.addAsyncCleanup(provedor.cog_unload)
        cog = self.criar_cog(provedor=provedor)
        self.addAsyncCleanup(cog.cog_unload)
        primeira_interaction = self.criar_interaction(channel_id=CANAL_TESTES_ID)
        segunda_interaction = self.criar_interaction(channel_id=CANAL_TESTES_ID)
        nome = "sangueberserk"
        url = url_oficial("sangueberserk.jpg")
        verificador = AsyncMock(return_value=True)

        with patch("cogs.pocoes.time.monotonic", return_value=100.0):
            with patch.object(provedor, "_verificar_url_cdn", verificador):
                with patch(
                    "cogs.ingredientes.random.choices",
                    return_value=["mitico"],
                ) as escolher_raridade:
                    with patch(
                        "cogs.ingredientes.random.choice",
                        side_effect=self.selecionar_nome(nome),
                    ) as escolher_item:
                        await Ingredientes.ingredientes.callback(
                            cog,
                            primeira_interaction,
                        )
                        await Ingredientes.ingredientes.callback(
                            cog,
                            segunda_interaction,
                        )

                self.assertTrue(provedor.consultar_cache_cdn(url))

        self.assertEqual(escolher_raridade.call_count, 2)
        self.assertEqual(escolher_item.call_count, 2)
        verificador.assert_awaited_once_with(url)

        for interaction in (primeira_interaction, segunda_interaction):
            embeds = self.embeds_enviadas(interaction)
            self.assertEqual(len(embeds), 1)
            self.assertEqual(embeds[0].image.url, url)

    async def test_fallback_usa_arquivo_exato_sem_resortear_ou_mutar_json(self):
        self.criar_todos_resultados()
        pasta = (
            self.diretorio
            / DIRETORIOS_INGREDIENTES["comum"]
            / "cogumelos"
        )
        (pasta / "nao_usar.png").write_bytes(b"imagem-incorreta")
        caminho_json = pasta / "resultado.json"
        json_antes = caminho_json.read_bytes()
        resultados = self.cog.carregar_resultados_obrigatorios()
        self.assertIsNotNone(resultados)
        resultado = next(
            item
            for item in resultados["comum"]
            if item.nome == "cogumelos"
        )
        embed_data_antes = deepcopy(resultado.embed_data)
        interaction = self.criar_interaction(channel_id=CANAL_TESTES_ID)
        self.provedor.consultar_cache_cdn.return_value = None
        self.provedor.cdn_disponivel.return_value = False

        with patch(
            "cogs.ingredientes.random.choices",
            return_value=["comum"],
        ) as escolher_raridade:
            with patch(
                "cogs.ingredientes.random.choice",
                side_effect=self.selecionar_nome("cogumelos"),
            ) as escolher_item:
                with patch.object(
                    self.cog,
                    "carregar_resultados_obrigatorios",
                    return_value=resultados,
                ):
                    await Ingredientes.ingredientes.callback(self.cog, interaction)

        escolher_raridade.assert_called_once()
        escolher_item.assert_called_once()
        self.provedor.cdn_disponivel.assert_awaited_once_with(
            url_oficial("cogumelos.png"),
            "cogumelos",
        )
        interaction.edit_original_response.assert_awaited_once()
        chamada = interaction.edit_original_response.await_args
        arquivo = chamada.kwargs["attachments"][0]
        self.assertIsInstance(arquivo, discord.File)
        self.assertEqual(arquivo.filename, "cogumelos.png")
        self.assertEqual(
            chamada.kwargs["embed"].image.url,
            "attachment://cogumelos.png",
        )
        self.assertEqual(caminho_json.read_bytes(), json_antes)
        self.assertEqual(resultado.embed_data, embed_data_antes)

    async def test_cache_negativo_usa_backup_sem_nova_verificacao(self):
        self.criar_todos_resultados()
        interaction = self.criar_interaction(channel_id=CANAL_TESTES_ID)
        self.provedor.consultar_cache_cdn.return_value = False

        with patch("cogs.ingredientes.random.choices", return_value=["mitico"]):
            with patch(
                "cogs.ingredientes.random.choice",
                side_effect=self.selecionar_nome("nocturnia"),
            ):
                await Ingredientes.ingredientes.callback(self.cog, interaction)

        self.provedor.cdn_disponivel.assert_not_awaited()
        chamada = interaction.edit_original_response.await_args
        self.assertEqual(
            chamada.kwargs["embed"].image.url,
            "attachment://nocturnia.png",
        )
        self.assertEqual(
            chamada.kwargs["attachments"][0].filename,
            "nocturnia.png",
        )

    async def test_erro_ao_consultar_cdn_tambem_usa_backup(self):
        self.criar_todos_resultados()
        interaction = self.criar_interaction(channel_id=CANAL_TESTES_ID)
        self.provedor.consultar_cache_cdn.return_value = None
        self.provedor.cdn_disponivel.side_effect = RuntimeError(
            "provedor indisponível"
        )

        with patch("cogs.ingredientes.random.choices", return_value=["raro"]):
            with patch(
                "cogs.ingredientes.random.choice",
                side_effect=self.selecionar_nome("perolanegra"),
            ):
                with self.assertLogs("cogs.ingredientes", level="ERROR"):
                    await Ingredientes.ingredientes.callback(
                        self.cog,
                        interaction,
                    )

        chamada = interaction.edit_original_response.await_args
        self.assertEqual(
            chamada.kwargs["embed"].image.url,
            "attachment://perolanegra.jpg",
        )
        self.assertEqual(
            chamada.kwargs["attachments"][0].filename,
            "perolanegra.jpg",
        )

    async def test_uso_e_registrado_somente_depois_do_envio_bem_sucedido(self):
        self.criar_todos_resultados()
        interaction = self.criar_interaction(user_id=701)

        async def confirmar_envio(**_kwargs) -> None:
            self.assertEqual(self.contar_usos(701), 0)

        interaction.edit_original_response.side_effect = confirmar_envio

        with patch("cogs.ingredientes.random.choices", return_value=["raro"]):
            with patch(
                "cogs.ingredientes.random.choice",
                side_effect=self.selecionar_nome("floreterna"),
            ):
                await Ingredientes.ingredientes.callback(self.cog, interaction)

        interaction.edit_original_response.assert_awaited_once()
        self.assertEqual(self.contar_usos(701), 1)
        self.assertEqual(self.linhas_cooldown(), ((701, self.agora),))
        self.assertTrue(self.caminho_banco.parent.is_dir())

    async def test_falha_do_discord_nao_consume_uso(self):
        self.criar_todos_resultados()
        interaction = self.criar_interaction(user_id=702)
        resposta = SimpleNamespace(status=500, reason="Erro simulado")
        erro = discord.HTTPException(resposta, "Falha simulada")
        interaction.edit_original_response.side_effect = (erro, None)

        with patch("cogs.ingredientes.random.choices", return_value=["lendario"]):
            with patch(
                "cogs.ingredientes.random.choice",
                side_effect=self.selecionar_nome("cometaarcano"),
            ):
                with self.assertLogs("cogs.ingredientes", level="ERROR"):
                    await Ingredientes.ingredientes.callback(self.cog, interaction)

        self.assertEqual(interaction.edit_original_response.await_count, 2)
        self.assertEqual(self.contar_usos(702), 0)


class CooldownIngredientesTests(
    DiretorioIngredientesTemporarioMixin,
    unittest.IsolatedAsyncioTestCase,
):
    async def _executar(
        self,
        *,
        user_id: int = 9001,
        channel_id: int = 7654321,
    ) -> SimpleNamespace:
        interaction = self.criar_interaction(
            user_id=user_id,
            channel_id=channel_id,
        )
        await Ingredientes.ingredientes.callback(self.cog, interaction)
        return interaction

    async def test_apenas_dois_usos_cabem_na_janela_movel_de_24_horas(self):
        self.criar_todos_resultados()

        with patch(
            "cogs.ingredientes.random.choices",
            return_value=["comum"],
        ) as escolher_raridade:
            with patch(
                "cogs.ingredientes.random.choice",
                side_effect=self.selecionar_nome("gengibre"),
            ) as escolher_item:
                primeira = await self._executar()
                segunda = await self._executar()
                terceira = await self._executar()

        self.assertEqual(escolher_raridade.call_count, LIMITE_USOS)
        self.assertEqual(escolher_item.call_count, LIMITE_USOS)
        self.assertEqual(self.contar_usos(9001), LIMITE_USOS)
        self.assertEqual(len(self.embeds_enviadas(primeira)), 1)
        self.assertEqual(len(self.embeds_enviadas(segunda)), 1)
        self.assertEqual(len(self.embeds_enviadas(terceira)), 0)
        mensagem = "\n".join(self.conteudos_enviados(terceira))
        self.assertIn("2 rolls", mensagem)
        self.assertIn("24h", mensagem)

        for interaction in (primeira, segunda, terceira):
            interaction.response.defer.assert_awaited_once_with(thinking=True)

    async def test_tempo_restante_expiracao_e_limpeza_oportunista(self):
        self.criar_todos_resultados()
        instante_inicial = self.agora

        with patch("cogs.ingredientes.random.choices", return_value=["raro"]):
            with patch(
                "cogs.ingredientes.random.choice",
                side_effect=self.selecionar_nome("perolanegra"),
            ) as escolher_item:
                await self._executar(user_id=42)

                self.agora = instante_inicial + 2 * 60 * 60
                await self._executar(user_id=42)

                self.agora = instante_inicial + 17 * 60 * 60 + 28 * 60
                bloqueada = await self._executar(user_id=42)

                mensagem = "\n".join(self.conteudos_enviados(bloqueada))
                self.assertIn("6h 32min", mensagem)
                self.assertEqual(self.contar_usos(42), 2)

                self.agora = instante_inicial + JANELA_COOLDOWN_SEGUNDOS
                liberada = await self._executar(user_id=42)

        self.assertEqual(len(self.embeds_enviadas(liberada)), 1)
        self.assertEqual(escolher_item.call_count, 3)
        linhas = self.linhas_cooldown()
        self.assertEqual(len(linhas), 2)
        self.assertTrue(
            all(
                used_at > instante_inicial
                for user_id, used_at in linhas
                if user_id == 42
            )
        )

    async def test_cooldown_persiste_apos_fechar_e_recriar_o_cog(self):
        self.criar_todos_resultados()

        with patch("cogs.ingredientes.random.choices", return_value=["mitico"]):
            with patch(
                "cogs.ingredientes.random.choice",
                side_effect=self.selecionar_nome("solaria"),
            ) as escolher_item:
                await self._executar(user_id=8080)
                await self._encerrar_cog_principal()

                novo_cog = self.criar_cog()
                self.addAsyncCleanup(novo_cog.cog_unload)
                segunda = self.criar_interaction(user_id=8080)
                terceira = self.criar_interaction(user_id=8080)
                await Ingredientes.ingredientes.callback(novo_cog, segunda)
                await Ingredientes.ingredientes.callback(novo_cog, terceira)

        self.assertEqual(self.contar_usos(8080), 2)
        self.assertEqual(escolher_item.call_count, 2)
        self.assertEqual(len(self.embeds_enviadas(segunda)), 1)
        self.assertEqual(len(self.embeds_enviadas(terceira)), 0)
        self.assertIn(
            "2 rolls",
            "\n".join(self.conteudos_enviados(terceira)),
        )

    async def test_canal_de_testes_ignora_consulta_e_registro_sem_limite(self):
        self.criar_todos_resultados()

        with patch("cogs.ingredientes.random.choices", return_value=["comum"]):
            with patch(
                "cogs.ingredientes.random.choice",
                side_effect=self.selecionar_nome("salgema"),
            ):
                await self._executar(user_id=55)
                await self._executar(user_id=55)
                linhas_antes = self.linhas_cooldown()

                with patch.object(
                    self.cog,
                    "_consultar_usos_validos",
                    AsyncMock(
                        side_effect=AssertionError(
                            "O bypass não pode consultar o cooldown."
                        )
                    ),
                ) as consultar:
                    with patch.object(
                        self.cog,
                        "_registrar_uso",
                        AsyncMock(
                            side_effect=AssertionError(
                                "O bypass não pode registrar uso."
                            )
                        ),
                    ) as registrar:
                        bypasses = [
                            await self._executar(
                                user_id=55,
                                channel_id=CANAL_TESTES_ID,
                            )
                            for _ in range(3)
                        ]

        consultar.assert_not_awaited()
        registrar.assert_not_awaited()
        self.assertEqual(self.contar_usos(55), 2)
        self.assertEqual(self.linhas_cooldown(), linhas_antes)
        self.assertTrue(
            all(len(self.embeds_enviadas(interaction)) == 1 for interaction in bypasses)
        )

    async def test_canal_de_testes_nao_cria_banco_em_estado_limpo(self):
        self.criar_todos_resultados()

        with patch("cogs.ingredientes.random.choices", return_value=["raro"]):
            with patch(
                "cogs.ingredientes.random.choice",
                side_effect=self.selecionar_nome("musgoruinas"),
            ):
                interactions = [
                    await self._executar(
                        user_id=56,
                        channel_id=CANAL_TESTES_ID,
                    )
                    for _ in range(3)
                ]

        self.assertFalse(self.caminho_banco.exists())
        self.assertIsNone(self.cog._conexao_banco)
        self.assertTrue(
            all(
                len(self.embeds_enviadas(interaction)) == 1
                for interaction in interactions
            )
        )

    async def test_unload_aguarda_roll_ativo_e_persiste_o_uso(self):
        self.criar_todos_resultados()
        interaction = self.criar_interaction(user_id=57)
        envio_iniciado = asyncio.Event()
        liberar_envio = asyncio.Event()

        async def concluir_envio(**_kwargs) -> None:
            envio_iniciado.set()
            await liberar_envio.wait()

        interaction.edit_original_response.side_effect = concluir_envio

        with patch("cogs.ingredientes.random.choices", return_value=["mitico"]):
            with patch(
                "cogs.ingredientes.random.choice",
                side_effect=self.selecionar_nome("nocturnia"),
            ):
                comando = asyncio.create_task(
                    Ingredientes.ingredientes.callback(self.cog, interaction)
                )
                await asyncio.wait_for(envio_iniciado.wait(), timeout=1)
                descarregamento = asyncio.create_task(self.cog.cog_unload())
                await asyncio.sleep(0)

                self.assertFalse(descarregamento.done())
                liberar_envio.set()
                await comando
                await descarregamento

        self._cog_principal_encerrado = True
        self.assertEqual(self.contar_usos(57), 1)

    async def test_tres_execucoes_concorrentes_do_mesmo_usuario_param_em_duas(self):
        self.criar_todos_resultados()

        with patch("cogs.ingredientes.random.choices", return_value=["lendario"]):
            with patch(
                "cogs.ingredientes.random.choice",
                side_effect=self.selecionar_nome("nogueiradeferro"),
            ) as escolher_item:
                interactions = await asyncio.gather(
                    self._executar(user_id=777),
                    self._executar(user_id=777),
                    self._executar(user_id=777),
                )

        self.assertEqual(self.contar_usos(777), LIMITE_USOS)
        self.assertEqual(escolher_item.call_count, LIMITE_USOS)
        self.assertEqual(
            sum(
                bool(self.embeds_enviadas(interaction))
                for interaction in interactions
            ),
            LIMITE_USOS,
        )
        bloqueadas = [
            interaction
            for interaction in interactions
            if "2 rolls" in "\n".join(self.conteudos_enviados(interaction))
        ]
        self.assertEqual(len(bloqueadas), 1)

    def test_formatacao_do_tempo_restante_nao_subestima(self):
        self.assertEqual(Ingredientes.formatar_tempo_restante(1), "1min")
        self.assertEqual(Ingredientes.formatar_tempo_restante(61), "2min")
        self.assertEqual(
            Ingredientes.formatar_tempo_restante(6 * 3600 + 32 * 60),
            "6h 32min",
        )
        self.assertEqual(
            MENSAGEM_COOLDOWN_INGREDIENTES.format(tempo="6h 32min"),
            "⏳ Você já utilizou seus 2 rolls de ingredientes nas últimas "
            "24 horas.\nSeu próximo uso estará disponível em aproximadamente "
            "6h 32min.",
        )


if __name__ == "__main__":
    unittest.main()
