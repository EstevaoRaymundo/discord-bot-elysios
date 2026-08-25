"""Interpretação e cálculo das expressões de rolagem do bot."""

from dataclasses import dataclass
from decimal import Decimal, DecimalException, ROUND_HALF_UP
import random
import re
from typing import Callable, Optional


MAX_REPETICOES = 250
MAX_DADOS = 10000
MAX_FACES = 10000
MAX_PERCENTUAIS = 15
LIMITE_MENSAGEM_DISCORD = 2000

MENSAGEM_REPETICOES_INVALIDAS = (
    "❌ A quantidade de rolagens individuais "
    "precisa estar entre 1 e 250."
)
MENSAGEM_DADOS_INVALIDOS = (
    "❌ A quantidade de dados precisa estar entre 1 e 10000."
)
MENSAGEM_FACES_INVALIDAS = (
    "❌ A quantidade de faces precisa estar entre 2 e 10000."
)
MENSAGEM_MODIFICADOR_INVALIDO = (
    "❌ O modificador da rolagem é inválido."
)

PADRAO_ROLAGEM = re.compile(
    r"^\s*"
    r"(?:(?P<repeticoes>\d+)\s*#\s*)?"
    r"(?P<quantidade>\d*)"
    r"[dD]"
    r"(?P<faces>\d+)"
    r"\s*"
    r"(?P<modificadores>"
    r"(?:(?:[+-]\s*\d+(?:[.,]\d+)?%?"
    r"|\*\s*\d+(?:[.,]\d+)?)\s*)*"
    r")"
    r"\s*$"
)

PADRAO_MODIFICADOR = re.compile(
    r"(?:[+-]\s*\d+(?:[.,]\d+)?%?"
    r"|\*\s*\d+(?:[.,]\d+)?)"
)

GeradorInteiro = Callable[[int, int], int]


class ErroRolagem(ValueError):
    """Erro de validação que pode ser mostrado ao usuário."""


@dataclass(frozen=True)
class Modificador:
    operador: str
    valor: Decimal
    percentual: bool
    texto: str


@dataclass(frozen=True)
class ExpressaoRolagem:
    quantidade: int
    faces: int
    repeticoes: int
    modificadores: tuple[Modificador, ...]
    expressao_exibida: str


def formatar_numero(valor: Decimal) -> str:
    """Formata um decimal com no máximo duas casas."""

    valor = valor.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )

    texto = format(valor, "f")

    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")

    return texto


def _converter_inteiro(
    texto: str,
    padrao: int,
    mensagem_erro: str
) -> int:
    if not texto:
        return padrao

    try:
        return int(texto)
    except ValueError as erro:
        raise ErroRolagem(mensagem_erro) from erro


def _inteiro_excede_limite(texto: str, limite: int) -> bool:
    texto_significativo = texto.lstrip("0") or "0"
    limite_texto = str(limite)

    return (
        len(texto_significativo) > len(limite_texto)
        or (
            len(texto_significativo) == len(limite_texto)
            and texto_significativo > limite_texto
        )
    )


def interpretar_rolagem(
    expressao: str
) -> Optional[ExpressaoRolagem]:
    """Interpreta uma expressão sem realizar nenhum sorteio."""

    correspondencia = PADRAO_ROLAGEM.fullmatch(expressao)

    if correspondencia is None:
        return None

    repeticoes_texto = correspondencia.group("repeticoes")
    quantidade_texto = correspondencia.group("quantidade")
    faces_texto = correspondencia.group("faces")
    modificadores_texto = correspondencia.group("modificadores")

    if (
        repeticoes_texto is not None
        and _inteiro_excede_limite(
            repeticoes_texto,
            MAX_REPETICOES
        )
    ):
        return None

    repeticoes = _converter_inteiro(
        repeticoes_texto or "",
        1,
        MENSAGEM_REPETICOES_INVALIDAS
    )
    quantidade = _converter_inteiro(
        quantidade_texto,
        1,
        MENSAGEM_DADOS_INVALIDOS
    )
    faces = _converter_inteiro(
        faces_texto,
        0,
        MENSAGEM_FACES_INVALIDAS
    )

    if repeticoes < 1:
        raise ErroRolagem(MENSAGEM_REPETICOES_INVALIDAS)

    if quantidade < 1 or quantidade > MAX_DADOS:
        raise ErroRolagem(MENSAGEM_DADOS_INVALIDOS)

    if faces < 2 or faces > MAX_FACES:
        raise ErroRolagem(MENSAGEM_FACES_INVALIDAS)

    modificadores = []

    try:
        for texto in PADRAO_MODIFICADOR.findall(
            modificadores_texto
        ):
            texto_normalizado = re.sub(r"\s+", "", texto)
            percentual = texto_normalizado.endswith("%")
            valor_texto = texto_normalizado[1:]

            if percentual:
                valor_texto = valor_texto[:-1]

            modificadores.append(
                Modificador(
                    operador=texto_normalizado[0],
                    valor=Decimal(
                        valor_texto.replace(",", ".")
                    ),
                    percentual=percentual,
                    texto=texto_normalizado
                )
            )
    except DecimalException as erro:
        raise ErroRolagem(
            MENSAGEM_MODIFICADOR_INVALIDO
        ) from erro

    if sum(
        modificador.percentual
        for modificador in modificadores
    ) > MAX_PERCENTUAIS:
        return None

    if repeticoes_texto is not None:
        expressao_exibida = (
            f"{quantidade}d{faces}"
            + "".join(
                modificador.texto
                for modificador in modificadores
            )
        )
    else:
        expressao_exibida = expressao.strip()

    return ExpressaoRolagem(
        quantidade=quantidade,
        faces=faces,
        repeticoes=repeticoes,
        modificadores=tuple(modificadores),
        expressao_exibida=expressao_exibida
    )


def _aplicar_modificadores(
    resultado: Decimal,
    modificadores: tuple[Modificador, ...]
) -> Decimal:
    for modificador in modificadores:
        if modificador.percentual:
            fator = modificador.valor / Decimal("100")

            if modificador.operador == "+":
                resultado *= Decimal("1") + fator
            else:
                resultado *= Decimal("1") - fator
        elif modificador.operador == "+":
            resultado += modificador.valor
        elif modificador.operador == "-":
            resultado -= modificador.valor
        else:
            resultado *= modificador.valor

    return resultado


def _formatar_resultado_individual(
    resultado: int,
    faces: int
) -> str:
    if resultado == 1 or resultado == faces:
        return f"**{resultado}**"

    return str(resultado)


def _rolar_uma_vez(
    dados: ExpressaoRolagem,
    sortear_inteiro: GeradorInteiro
) -> str:
    resultados = [
        sortear_inteiro(1, dados.faces)
        for _ in range(dados.quantidade)
    ]

    resultado_final = _aplicar_modificadores(
        Decimal(sum(resultados)),
        dados.modificadores
    )
    resultado_formatado = formatar_numero(resultado_final)

    dados_formatados = "[" + ", ".join(
        _formatar_resultado_individual(resultado, dados.faces)
        for resultado in resultados
    ) + "]"

    return (
        f"`  {resultado_formatado}  ` "
        f"⟵ {dados_formatados} "
        f"{dados.expressao_exibida}"
    )


def calcular_rolagem(
    expressao: str,
    *,
    sortear_inteiro: Optional[GeradorInteiro] = None
) -> Optional[str]:
    """Calcula uma expressão e devolve a resposta formatada."""

    try:
        dados = interpretar_rolagem(expressao)

        if dados is None:
            return None

        gerador = sortear_inteiro or random.randint

        return "\n".join(
            _rolar_uma_vez(dados, gerador)
            for _ in range(dados.repeticoes)
        )
    except ErroRolagem as erro:
        return str(erro)
    except DecimalException:
        return MENSAGEM_MODIFICADOR_INVALIDO


def dividir_mensagem(
    texto: str,
    limite: int = LIMITE_MENSAGEM_DISCORD
) -> list[str]:
    """Divide uma resposta sem ultrapassar o limite do Discord."""

    if limite < 1:
        raise ValueError("O limite precisa ser maior que zero.")

    if len(texto) <= limite:
        return [texto]

    partes = []
    restante = texto

    while len(restante) > limite:
        corte = restante.rfind("\n", 0, limite + 1)

        if corte <= 0:
            corte = limite
            partes.append(restante[:corte])
        else:
            partes.append(restante[:corte])
            corte += 1

        restante = restante[corte:]

    if restante:
        partes.append(restante)

    return partes
