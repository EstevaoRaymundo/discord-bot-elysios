from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from cogs.rolagem import Rolagem


class RolagemCogTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = Rolagem(bot=None)
        self.message = SimpleNamespace(
            author=SimpleNamespace(bot=False),
            content="1d30",
            channel="canal-teste",
            reply=AsyncMock(),
        )

    async def test_ignora_mensagens_de_bots(self):
        self.message.author.bot = True

        await self.cog.on_message(self.message)

        self.message.reply.assert_not_awaited()

    async def test_ignora_mensagens_de_comando(self):
        self.message.content = "!ping"

        await self.cog.on_message(self.message)

        self.message.reply.assert_not_awaited()

    async def test_primeira_parte_menciona_autor_e_demais_nao(self):
        globais_listener = Rolagem.on_message.__globals__

        with patch.dict(
            globais_listener,
            {
                "calcular_rolagem": (
                    lambda expressao: "primeira\nsegunda\nterceira"
                ),
                "dividir_mensagem": (
                    lambda resultado: [
                        "primeira",
                        "segunda",
                        "terceira",
                    ]
                ),
            }
        ):
            await self.cog.on_message(self.message)

        self.assertEqual(
            self.message.reply.await_args_list,
            [
                unittest.mock.call("primeira", mention_author=True),
                unittest.mock.call("segunda", mention_author=False),
                unittest.mock.call("terceira", mention_author=False),
            ]
        )


if __name__ == "__main__":
    unittest.main()
