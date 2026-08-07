from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import discord

from cogs.iniciativa import Turnos


class ParticipantesTests(unittest.TestCase):
    def test_separa_remove_vazios_e_duplicados(self):
        participantes = Turnos.separar_participantes(
            "Finn, deki; FINN\nAnnaliz"
        )

        self.assertEqual(
            participantes,
            ["Finn", "deki", "Annaliz"]
        )

    def test_divisao_normal_preserva_conteudo(self):
        self.assertEqual(
            Turnos.dividir_lista(["Finn", "Deki"]),
            ["**1.** Finn\n**2.** Deki\n"]
        )

    def test_nome_grande_nao_cria_campo_vazio_ou_excessivo(self):
        campos = Turnos.dividir_lista(["x" * 1001, "Finn"])

        self.assertTrue(all(campos))
        self.assertTrue(all(len(campo) <= 1000 for campo in campos))


class EstadoTurnosTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = Turnos(bot=None)
        self.chave = (1, 2)
        self.dados = {
            "titulo": "Teste",
            "participantes": ["Finn", "Deki"],
            "criador_id": 3,
        }
        self.ctx = SimpleNamespace(
            guild=SimpleNamespace(id=1),
            channel=SimpleNamespace(id=2),
            author=SimpleNamespace(mention="<@3>"),
            reply=AsyncMock(),
            send=AsyncMock(),
        )

    async def test_ver_nao_remove_a_ordem(self):
        self.cog.ordens[self.chave] = self.dados

        await Turnos.turnos_ver.callback(self.cog, self.ctx)

        self.assertIn(self.chave, self.cog.ordens)
        self.ctx.reply.assert_awaited_once()

    async def test_encerrar_remove_a_ordem(self):
        self.cog.ordens[self.chave] = self.dados

        await Turnos.turnos_encerrar.callback(self.cog, self.ctx)

        self.assertNotIn(self.chave, self.cog.ordens)
        self.ctx.send.assert_awaited_once()

    async def test_encerrar_restaura_a_ordem_se_o_envio_falhar(self):
        self.cog.ordens[self.chave] = self.dados
        resposta = SimpleNamespace(status=500, reason="Erro")
        self.ctx.send.side_effect = discord.HTTPException(
            resposta,
            "Falha simulada"
        )

        with self.assertRaises(discord.HTTPException):
            await Turnos.turnos_encerrar.callback(
                self.cog,
                self.ctx
            )

        self.assertEqual(self.cog.ordens[self.chave], self.dados)


if __name__ == "__main__":
    unittest.main()
