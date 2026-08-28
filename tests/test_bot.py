import unittest
from unittest.mock import AsyncMock, patch

from discord import app_commands

import bot
from utils.dados import calcular_rolagem


class InicializacaoBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_carrega_cogs_e_preserva_comandos(self):
        arvore_original = bot.bot.tree

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
        self.assertIsNotNone(bot.bot.get_cog("Artesanato"))
        self.assertIsNotNone(bot.bot.get_cog("Estabilidade"))
        self.assertIsNotNone(bot.bot.get_cog("Iniciar"))
        self.assertIs(bot.bot.tree, arvore_original)

        grupo_iniciar = bot.bot.tree.get_command("iniciar")
        self.assertIsInstance(grupo_iniciar, app_commands.Group)
        self.assertEqual(
            [comando.name for comando in grupo_iniciar.commands],
            ["poção"],
        )
        self.assertEqual(
            grupo_iniciar.get_command("poção").qualified_name,
            "iniciar poção",
        )
        self.assertIsNotNone(bot.bot.tree.get_command("poção"))
        comando_artesanato = bot.bot.tree.get_command("artesanato")
        self.assertIsInstance(
            comando_artesanato,
            app_commands.Command,
        )
        self.assertEqual(comando_artesanato.parameters, [])
        self.assertEqual(
            comando_artesanato.to_dict(bot.bot.tree)["options"],
            [],
        )
        comando_estabilidade = bot.bot.tree.get_command("estabilidade")
        self.assertIsInstance(
            comando_estabilidade,
            app_commands.Command,
        )
        self.assertEqual(comando_estabilidade.parameters, [])
        self.assertEqual(
            comando_estabilidade.description,
            "Determina se a poção criada ficou estável ou instável.",
        )
        self.assertEqual(
            comando_estabilidade.to_dict(bot.bot.tree)["options"],
            [],
        )
        self.assertIsNone(bot.bot.tree.get_command("iniciar-poção"))
        self.assertIsNone(bot.bot.tree.get_command("iniciar-estabilidade"))
        self.assertIsNone(bot.bot.get_command("iniciar"))
        self.assertIsNone(bot.bot.get_command("estabilidade"))
        self.assertIsNone(bot.bot.get_command("poção"))
        self.assertIsNone(bot.bot.get_command("pocao"))
        self.assertIsNone(bot.bot.get_command("artesanato"))
        sincronizar.assert_awaited_once_with()

        await bot.bot.close()

    def test_calculo_continua_disponivel_pelo_modulo_bot(self):
        self.assertIs(bot.calcular_rolagem, calcular_rolagem)


if __name__ == "__main__":
    unittest.main()
