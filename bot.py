import os
import re
import secrets
from decimal import Decimal, ROUND_DOWN, getcontext
from typing import Any, Dict, List

import discord
from dotenv import load_dotenv


# =========================================================
# CONFIGURAÇÕES
# =========================================================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# O bot responde somente a esse comando.
PREFIX = "!roll"

# Limites para rolagens normais.
MAX_DICE = 10_000
MAX_SIDES = 10_000

# Limites de modificadores.
MAX_PERCENTAGES = 15
MAX_MODIFIERS = 30
MAX_MODIFIER_VALUE = 1_000_000

# Quantidade máxima de dados exibidos na mensagem.
# Todos os dados ainda são rolados e somados.
MAX_DISPLAYED_ROLLS = 100

# Limite para comandos como:
# !roll 250#d30
MAX_REPEAT_ROLLS = 250

# Limite de caracteres de uma mensagem do Discord.
DISCORD_MESSAGE_LIMIT = 2_000

# Precisão para cálculos com várias porcentagens.
getcontext().prec = 300


# =========================================================
# EXPRESSÕES REGULARES
# =========================================================

# Exemplos aceitos:
#
# d30
# 1d30
# 10d30
# 10000d30
# 1d10000
# 1d30+10
# 1d30-5
# 1d30+20%
# 1d30-35%
# 1d30+40%+40%
# 1d30*3
# 1d30+20%*3
DICE_PATTERN = re.compile(
    r"^(?P<quantity>\d*)"
    r"d"
    r"(?P<sides>\d+)"
    r"(?P<modifiers>(?:[+*-]\d+%?)*)$",
    re.IGNORECASE,
)

# Identifica modificadores como:
#
# +20%
# -35%
# +10
# -5
# *3
MODIFIER_PATTERN = re.compile(
    r"(?P<operator>[+*-])"
    r"(?P<value>\d+)"
    r"(?P<percentage>%?)"
)

# Exemplos:
#
# 10#d30
# 5#1d100+20%
# 8#2d20+5
# 10#d30*3
REPEAT_PATTERN = re.compile(
    r"^(?P<repetitions>\d+)#(?P<expression>.+)$",
    re.IGNORECASE,
)


# =========================================================
# FUNÇÕES DAS ROLAGENS
# =========================================================

def roll_expression(expression: str) -> Dict[str, Any]:
    """
    Analisa uma expressão e realiza a rolagem.

    Os modificadores são aplicados na ordem em que aparecem.

    Exemplo:

        Resultado inicial: 13
        +40%: 18.2
        +40%: 25.48

    Multiplicação:

        Resultado inicial: 10
        +20%: 12
        *3: 36
    """

    # Remove espaços e transforma em letras minúsculas.
    cleaned = "".join(expression.split()).lower()

    match = DICE_PATTERN.fullmatch(cleaned)

    if not match:
        raise ValueError(
            "Formato inválido. Use, por exemplo: "
            "`!roll 1d30`, `!roll 1d30+20%`, "
            "`!roll 1d30*3` ou `!roll 10#d30`."
        )

    quantity = int(match.group("quantity") or 1)
    sides = int(match.group("sides"))
    modifiers_text = match.group("modifiers")

    # Faz "d30" aparecer como "1d30".
    display_expression = (
        f"{quantity}d{sides}{modifiers_text}"
    )

    if not 1 <= quantity <= MAX_DICE:
        raise ValueError(
            f"A quantidade de dados deve estar entre "
            f"1 e {MAX_DICE:,}."
        )

    if not 2 <= sides <= MAX_SIDES:
        raise ValueError(
            f"O dado deve ter entre 2 e "
            f"{MAX_SIDES:,} faces."
        )

    modifier_matches = list(
        MODIFIER_PATTERN.finditer(modifiers_text)
    )

    if len(modifier_matches) > MAX_MODIFIERS:
        raise ValueError(
            f"Você pode utilizar no máximo "
            f"{MAX_MODIFIERS} modificadores."
        )

    percentage_count = sum(
        1
        for modifier in modifier_matches
        if modifier.group("percentage") == "%"
    )

    if percentage_count > MAX_PERCENTAGES:
        raise ValueError(
            f"Você pode utilizar no máximo "
            f"{MAX_PERCENTAGES} porcentagens."
        )

    # Realiza todos os dados da expressão.
    rolls = [
        secrets.randbelow(sides) + 1
        for _ in range(quantity)
    ]

    subtotal = sum(rolls)
    current_total = Decimal(subtotal)

    applied_modifiers = []

    for modifier_match in modifier_matches:
        operator = modifier_match.group("operator")
        value = int(modifier_match.group("value"))

        is_percentage = (
            modifier_match.group("percentage") == "%"
        )

        if value > MAX_MODIFIER_VALUE:
            raise ValueError(
                f"Cada modificador pode ter no máximo "
                f"{MAX_MODIFIER_VALUE:,}."
            )

        previous_total = current_total

        if is_percentage:
            # Impede expressões como *20%.
            if operator == "*":
                raise ValueError(
                    "Não é possível multiplicar diretamente "
                    "por uma porcentagem. Use `+20%`, `-20%` "
                    "ou uma multiplicação como `*3`."
                )

            percentage = (
                Decimal(value) / Decimal(100)
            )

            percentage_amount = (
                current_total * percentage
            )

            if operator == "+":
                current_total += percentage_amount
                applied_value = percentage_amount
            else:
                current_total -= percentage_amount
                applied_value = -percentage_amount

        else:
            fixed_value = Decimal(value)

            if operator == "+":
                current_total += fixed_value
                applied_value = fixed_value

            elif operator == "-":
                current_total -= fixed_value
                applied_value = -fixed_value

            else:
                # Multiplicação.
                current_total *= fixed_value

                applied_value = (
                    current_total - previous_total
                )

        applied_modifiers.append(
            {
                "operator": operator,
                "value": value,
                "is_percentage": is_percentage,
                "previous_total": previous_total,
                "applied_value": applied_value,
                "new_total": current_total,
            }
        )

    return {
        "expression": cleaned,
        "display_expression": display_expression,
        "quantity": quantity,
        "sides": sides,
        "rolls": rolls,
        "subtotal": subtotal,
        "applied_modifiers": applied_modifiers,
        "total": current_total,
    }


def format_number(number: Any) -> str:
    """
    Mostra no máximo duas casas decimais.

    As casas excedentes são cortadas, sem arredondamento.

    Exemplos:

        21.8064 -> 21.8
        25.4899 -> 25.48
        18.2000 -> 18.2
        30.0000 -> 30
    """

    decimal_number = Decimal(number)

    if (
        decimal_number
        == decimal_number.to_integral_value()
    ):
        return format(decimal_number, ".0f")

    truncated_number = decimal_number.quantize(
        Decimal("0.00"),
        rounding=ROUND_DOWN,
    )

    # Evita mostrar -0.
    if truncated_number == Decimal("-0.00"):
        truncated_number = Decimal("0.00")

    formatted = format(truncated_number, ".2f")

    # Remove zeros desnecessários no final.
    return formatted.rstrip("0").rstrip(".")


def format_rolls(
    rolls: List[int],
    sides: int,
) -> str:
    """
    Formata os resultados individuais.

    O número 1 e o número máximo do dado ficam em negrito,
    pois são considerados críticos.
    """

    formatted_rolls = []

    visible_rolls = rolls[:MAX_DISPLAYED_ROLLS]

    for roll in visible_rolls:
        is_critical = (
            roll == 1
            or roll == sides
        )

        if is_critical:
            formatted_rolls.append(
                f"**{roll}**"
            )
        else:
            formatted_rolls.append(
                str(roll)
            )

    omitted_rolls = (
        len(rolls) - len(visible_rolls)
    )

    if omitted_rolls > 0:
        omitted_text = (
            f"{omitted_rolls:,}".replace(",", ".")
        )

        formatted_rolls.append(
            f"… +{omitted_text} resultados"
        )

    return ", ".join(formatted_rolls)


def build_discord_messages(
    lines: List[str],
) -> List[str]:
    """
    Divide respostas grandes em várias mensagens para não
    ultrapassar o limite de 2.000 caracteres do Discord.
    """

    messages = []
    current_message = ""

    for line in lines:
        if current_message:
            candidate = f"{current_message}\n{line}"
        else:
            candidate = line

        if len(candidate) > DISCORD_MESSAGE_LIMIT:
            if current_message:
                messages.append(current_message)

            current_message = line
        else:
            current_message = candidate

    if current_message:
        messages.append(current_message)

    return messages


# =========================================================
# CONFIGURAÇÃO DO DISCORD
# =========================================================

intents = discord.Intents.default()

# Necessário para ler comandos escritos no chat.
intents.message_content = True

client = discord.Client(
    intents=intents
)


# =========================================================
# EVENTOS
# =========================================================

@client.event
async def on_ready() -> None:
    print("=" * 50)
    print(f"Bot conectado como: {client.user}")

    if client.user is not None:
        print(f"ID do bot: {client.user.id}")

    print(f"Prefixo configurado: {PREFIX}")
    print("=" * 50)


@client.event
async def on_message(
    message: discord.Message,
) -> None:
    # Ignora mensagens enviadas por bots.
    if message.author.bot:
        return

    content = message.content.strip()

    if not content:
        return

    parts = content.split(maxsplit=1)
    command = parts[0].lower()

    # O bot responde somente ao comando exato !roll.
    #
    # Uma mensagem contendo apenas "1d30" será ignorada.
    if command != PREFIX:
        return

    # Mostra ajuda quando o jogador envia somente !roll.
    if len(parts) == 1:
        help_message = (
            "**🎲 Como usar o bot de dados**\n\n"
            "`!roll 1d30`\n"
            "`!roll 10d30`\n"
            "`!roll 1d100`\n"
            "`!roll 1d30+10`\n"
            "`!roll 1d30-35%`\n"
            "`!roll 1d30+40%+40%`\n"
            "`!roll 1d30*3`\n"
            "`!roll 1d30+20%*3`\n"
            "`!roll 10#d30`\n"
            "`!roll 5#d100+20%`\n"
            "`!roll 8#2d20+5`\n\n"
            f"Máximo de dados: `{MAX_DICE:,}`\n"
            f"Máximo de faces: `{MAX_SIDES:,}`\n"
            f"Máximo de porcentagens: "
            f"`{MAX_PERCENTAGES}`\n"
            f"Máximo de repetições com #: "
            f"`{MAX_REPEAT_ROLLS}`"
        )

        await message.reply(
            help_message,
            mention_author=True,
        )
        return

    expression = parts[1].strip()

    if not expression:
        return

    cleaned_expression = "".join(
        expression.split()
    ).lower()

    # =====================================================
    # ROLAGENS INDEPENDENTES COM #
    # =====================================================

    repeat_match = REPEAT_PATTERN.fullmatch(
        cleaned_expression
    )

    if repeat_match:
        repetitions = int(
            repeat_match.group("repetitions")
        )

        base_expression = repeat_match.group(
            "expression"
        )

        # Valores acima de 250 são ignorados.
        #
        # Portanto, estes comandos não recebem resposta:
        #
        # !roll 251#d30
        # !roll 10000#d10000
        if not 1 <= repetitions <= MAX_REPEAT_ROLLS:
            return

        result_lines = []

        try:
            for _ in range(repetitions):
                result = roll_expression(
                    base_expression
                )

                formatted_total = format_number(
                    result["total"]
                )

                rolls_text = format_rolls(
                    result["rolls"],
                    result["sides"],
                )

                result_line = (
                    f"`{formatted_total}` "
                    f"⟵ [{rolls_text}] "
                    f"{result['display_expression']}"
                )

                result_lines.append(
                    result_line
                )

        except ValueError as error:
            await message.reply(
                f"❌ {error}",
                mention_author=True,
            )
            return

        responses = build_discord_messages(
            result_lines
        )

        # A primeira mensagem responde diretamente ao
        # jogador que utilizou o comando.
        for index, response in enumerate(responses):
            if index == 0:
                await message.reply(
                    response,
                    mention_author=True,
                )
            else:
                await message.channel.send(
                    response
                )

        return

    # =====================================================
    # ROLAGEM NORMAL
    # =====================================================

    try:
        result = roll_expression(
            cleaned_expression
        )

    except ValueError as error:
        await message.reply(
            f"❌ {error}",
            mention_author=True,
        )
        return

    formatted_total = format_number(
        result["total"]
    )

    rolls_text = format_rolls(
        result["rolls"],
        result["sides"],
    )

    response = (
        f"`{formatted_total}` "
        f"⟵ [{rolls_text}] "
        f"{result['display_expression']}"
    )

    # Responde diretamente à mensagem do jogador.
    await message.reply(
        response,
        mention_author=True,
    )


# =========================================================
# INICIALIZAÇÃO
# =========================================================

if not TOKEN:
    raise RuntimeError(
        "O token do bot não foi encontrado.\n"
        "Crie o arquivo .env e adicione:\n"
        "DISCORD_TOKEN=SEU_TOKEN"
    )

client.run(TOKEN)