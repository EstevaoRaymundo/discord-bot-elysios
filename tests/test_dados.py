from decimal import Decimal
import unittest

from utils.dados import (
    calcular_rolagem,
    dividir_mensagem,
    formatar_numero,
)


class GeradorSequencial:
    def __init__(self, *valores: int):
        self._valores = iter(valores)
        self.chamadas = []

    def __call__(self, minimo: int, maximo: int) -> int:
        self.chamadas.append((minimo, maximo))
        return next(self._valores)


class CalculoRolagemTests(unittest.TestCase):
    def calcular(self, expressao: str, *resultados: int):
        gerador = GeradorSequencial(*resultados)
        resposta = calcular_rolagem(
            expressao,
            sortear_inteiro=gerador
        )
        return resposta, gerador

    def test_quantidade_implicita_e_grafia_original(self):
        resposta, _ = self.calcular("  d30  ", 10)

        self.assertEqual(
            resposta,
            "`  10  ` ⟵ [10] d30"
        )

    def test_varios_dados_sao_somados_e_exibidos(self):
        resposta, gerador = self.calcular("2D20", 3, 8)

        self.assertEqual(
            resposta,
            "`  11  ` ⟵ [3, 8] 2D20"
        )
        self.assertEqual(
            gerador.chamadas,
            [(1, 20), (1, 20)]
        )

    def test_modificadores_sao_aplicados_da_esquerda_para_direita(self):
        resposta, _ = self.calcular(
            "1d30 + 10 + 20%",
            10
        )

        self.assertEqual(
            resposta,
            "`  24  ` ⟵ [10] 1d30 + 10 + 20%"
        )

        resposta, _ = self.calcular(
            "1d30 + 20% + 10",
            10
        )

        self.assertEqual(
            resposta,
            "`  22  ` ⟵ [10] 1d30 + 20% + 10"
        )

    def test_decimais_virgula_percentual_e_arredondamento(self):
        resposta, _ = self.calcular(
            "0001d00030 + 01,50%",
            10
        )

        self.assertEqual(
            resposta,
            "`  10.15  ` ⟵ [10] 0001d00030 + 01,50%"
        )
        self.assertEqual(formatar_numero(Decimal("1.005")), "1.01")

    def test_repeticoes_sao_independentes_e_normalizadas(self):
        resposta, gerador = self.calcular(
            "3 # 2d20 + 1,5",
            1, 2,
            3, 4,
            5, 6
        )

        self.assertEqual(
            resposta,
            "\n".join([
                "`  4.5  ` ⟵ [1, 2] 2d20+1,5",
                "`  8.5  ` ⟵ [3, 4] 2d20+1,5",
                "`  12.5  ` ⟵ [5, 6] 2d20+1,5",
            ])
        )
        self.assertEqual(
            gerador.chamadas,
            [(1, 20)] * 6
        )

    def test_limites_preservam_mensagens_e_ordem(self):
        casos = {
            "0#0d1": (
                "❌ A quantidade de rolagens individuais "
                "precisa estar entre 1 e 50."
            ),
            "1#0d1": (
                "❌ A quantidade de dados precisa estar "
                "entre 1 e 100."
            ),
            "1#1d1": (
                "❌ A quantidade de faces precisa estar "
                "entre 2 e 100000."
            ),
        }

        for expressao, mensagem in casos.items():
            with self.subTest(expressao=expressao):
                self.assertEqual(
                    calcular_rolagem(expressao),
                    mensagem
                )

    def test_sintaxes_invalidas_continuam_ignoradas(self):
        invalidas = [
            "texto",
            "1 d30",
            "1d 30",
            "1d30 + 20 %",
            "1d30++1",
            "1d30 +.5",
            "1d30 + 1.",
            "1d30 * 2",
            "(1d30)",
            "5##d30",
        ]

        for expressao in invalidas:
            with self.subTest(expressao=expressao):
                self.assertIsNone(calcular_rolagem(expressao))

    def test_numeros_extremos_retornam_erro_sem_excecao(self):
        numero_enorme = "9" * 5000

        self.assertIn(
            "entre 1 e 100",
            calcular_rolagem(f"{numero_enorme}d6")
        )
        self.assertEqual(
            calcular_rolagem(
                f"1d6+{numero_enorme}",
                sortear_inteiro=lambda minimo, maximo: 1
            ),
            "❌ O modificador da rolagem é inválido."
        )


class DivisaoMensagemTests(unittest.TestCase):
    def test_mensagem_curta_nao_e_alterada(self):
        self.assertEqual(dividir_mensagem("resultado"), ["resultado"])

    def test_prefere_quebras_de_linha_e_respeita_limite(self):
        texto = "linha 1\nlinha 2\nlinha 3"
        partes = dividir_mensagem(texto, limite=15)

        self.assertEqual(partes, ["linha 1\nlinha 2", "linha 3"])
        self.assertTrue(all(len(parte) <= 15 for parte in partes))

    def test_linha_grande_tambem_e_dividida(self):
        partes = dividir_mensagem("x" * 25, limite=10)

        self.assertEqual([len(parte) for parte in partes], [10, 10, 5])


if __name__ == "__main__":
    unittest.main()
