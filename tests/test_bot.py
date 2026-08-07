import unittest

import bot
from utils.dados import calcular_rolagem


class InicializacaoBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_carrega_cogs_e_preserva_comandos(self):
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

        await bot.bot.close()

    def test_calculo_continua_disponivel_pelo_modulo_bot(self):
        self.assertIs(bot.calcular_rolagem, calcular_rolagem)


if __name__ == "__main__":
    unittest.main()
