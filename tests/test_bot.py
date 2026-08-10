import unittest
from unittest.mock import AsyncMock, patch

import bot
from utils.dados import calcular_rolagem


class InicializacaoBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_carrega_cogs_e_preserva_comandos(self):
        with patch.object(
            bot.bot.tree,
            "sync",
            new_callable=AsyncMock,
        ) as sincronizar:
            await bot.bot.setup_hook()

        comandos = sorted(
            comando.qualified_name
            for comando in bot.bot.walk_commands()
        )

        self.assertEqual(
            comandos,
            [
                "ping",
                "turnos",
                "turnos encerrar",
                "turnos iniciar",
                "turnos ver",
            ]
        )
        self.assertIsNotNone(bot.bot.get_cog("Turnos"))
        self.assertIsNotNone(bot.bot.get_cog("Rolagem"))
        self.assertIsNotNone(bot.bot.get_cog("Pocoes"))
        self.assertIsNotNone(bot.bot.tree.get_command("poção"))
        self.assertIsNone(bot.bot.get_command("poção"))
        self.assertIsNone(bot.bot.get_command("pocao"))
        sincronizar.assert_awaited_once_with()

        await bot.bot.close()

    def test_calculo_continua_disponivel_pelo_modulo_bot(self):
        self.assertIs(bot.calcular_rolagem, calcular_rolagem)


if __name__ == "__main__":
    unittest.main()
