import os
import re
import secrets
from decimal import Decimal, ROUND_DOWN, getcontext
from typing import Any, Dict, List

import discord
from dotenv import load_dotenv


# =========================================================
# CONFIGURAÇÕES GERAIS
# =========================================================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# O bot responde somente a este prefixo
PREFIX = "!roll"

# Máximo de dados em uma rolagem:
# !roll 10000d30
MAX_DICE = 10_000

# Máximo de faces:
# !roll 1d10000
MAX_SIDES = 10_000

# Máximo de porcentagens em uma expressão
MAX_PERCENTAGES = 15

# Máximo total de modificadores:
# +10, -5, +20%, *3 etc.
MAX_MODIFIERS = 30

# Maior número aceito em cada modificador
MAX_MODIFIER_VALUE = 1_000_000

# Quantos resultados individuais aparecem na mensagem.
# Todos os dados ainda são rolados e somados.
MAX_DISPLAYED_ROLLS = 100

# Máximo de repetições com #
# Exemplo: !roll 250#d30
MAX_REPEAT_ROLLS = 250

# Limite de caracteres de uma mensagem do Discord
DISCORD_MESSAGE_LIMIT = 2_000

# Aumenta a precisão para operações com várias
# porcentagens e multiplicações.
getcontext().prec = 300


# =========================================================
# EXPRESSÕES REGULARES
# =========================================================

# Formatos aceitos:
#
# d30
# 1d30
# 10d30
# 10000d30
# 1d10000
# 1d30+10
# 1d30-5
# 1d30+20%
# 1d30+40%+40%
# 1d30*3
# 1d30+20%*3
# 1d30+20%+20%+20%+5+1+10%
#
DICE_PATTERN = re.compile(
    r"^(?P<quantity>\d*)"
    r"d"
    r"(?P<sides>\d+)"
    r"(?P<modifiers>(?:[+*-]\d+%?)*)$",
    re.IGNORECASE,
)

# Identifica cada modificador individual:
#
# +20%
# -10%
# +5
# -3
# *2
MODIFIER_PATTERN = re.compile(
    r"(?P<operator>[+*-])"
    r"(?P<value>\d+)"
    r"(?P<percentage>%?)"
)

# Formatos de repetição:
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

    Exemplo com resultado inicial 13:

        1d30+40%+40%

        13 + 40% = 18.20
        18.20 + 40% = 25.48

    Exemplo com multiplicação:

        1d30+20%*3

        10 + 20% = 12
        12 * 3 = 36
    """

    # Remove todos os espaços.
    #
    # Assim, estas duas formas funcionam:
    # !roll 1d30+20%
    # !roll 1d30 + 20%
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

    # Faz "d30" aparecer como "1d30" nos resultados.
    display_expression = (
        f"{quantity}d{sides}{modifiers_text}"
    )

    # Valida a quantidade de dados
    if not 1 <= quantity <= MAX_DICE:
        raise ValueError(
            f"A quantidade de dados deve estar entre "
            f"1 e {MAX_DICE:,}."
        )

    # Valida a quantidade de faces
    if not 2 <= sides <= MAX_SIDES:
        raise ValueError(
            f"O dado deve ter entre 2 e "
            f"{MAX_SIDES:,} faces."
        )

    modifier_matches = list(
        MODIFIER_PATTERN.finditer(modifiers_text)
    )

    # Valida o número total de modificadores
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

    # Valida a quantidade de porcentagens
    if percentage_count > MAX_PERCENTAGES:
        raise ValueError(
            f"Você pode utilizar no máximo "
            f"{MAX_PERCENTAGES} porcentagens."
        )

    # Realiza as rolagens
    rolls = [
        secrets.randbelow(sides) + 1
        for _ in range(quantity)
    ]

    subtotal = sum(rolls)

    # Decimal evita erros comuns de precisão de float
    current_total = Decimal(subtotal)

    applied_modifiers = []

    # Aplica cada modificador na ordem digitada
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
            # Não aceita algo como *20%
            if operator == "*":
                raise ValueError(
                    "Não é possível multiplicar diretamente "
                    "por uma porcentagem. Use `+20%`, `-20%` "
                    "ou uma multiplicação como `*3`."
                )

            percentage = (
                Decimal(value) / Decimal(100)
            )

            # A porcentagem usa o total acumulado
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
                # Multiplicação
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
    Formata o resultado final.

    Números inteiros não recebem casas decimais:

        30.0000 -> 30

    Números decimais recebem exatamente duas casas,
    cortando as casas excedentes sem arredondar:

        21.8064 -> 21.80
        25.4899 -> 25.48
        18.2000 -> 18.20
    """

    decimal_number = Decimal(number)

    # Mantém números inteiros sem .00
    if (
        decimal_number
        == decimal_number.to_integral_value()
    ):
        return format(decimal_number, ".0f")

    # Corta depois da segunda casa decimal
    truncated_number = decimal_number.quantize(
        Decimal("0.00"),
        rounding=ROUND_DOWN,
    )

    # Evita exibir -0.00
    if truncated_number == Decimal("-0.00"):
        truncated_number = Decimal("0.00")

    return format(truncated_number, ".2f")


def format_rolls(
    rolls: List[int],
    sides: int,
) -> str:
    """
    Formata os resultados individuais.

    O número 1 e o número máximo do dado ficam em negrito,
    pois são considerados resultados críticos.
    """

    formatted_rolls = []

    # Em rolagens enormes, mostra apenas uma parte
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
    header: str,
    lines: List[str],
) -> List[str]:
    """
    Divide resultados grandes em várias mensagens para
    não ultrapassar o limite de caracteres do Discord.
    """

    messages = []
    current_message = header

    for line in lines:
        candidate = (
            f"{current_message}\n{line}"
        )

        if len(candidate) > DISCORD_MESSAGE_LIMIT:
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

# Necessário para ler o texto de comandos como:
# !roll 1d30
intents.message_content = True

client = discord.Client(
    intents=intents
)


# =========================================================
# EVENTOS DO DISCORD
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
    # Ignora mensagens de bots
    if message.author.bot:
        return

    content = message.content.strip()

    if not content:
        return

    # Divide o comando da expressão.
    #
    # !roll 1d30
    #
    # command = !roll
    # expression = 1d30
    parts = content.split(maxsplit=1)
    command = parts[0].lower()

    # O bot responde somente ao comando exato !roll.
    #
    # Uma mensagem contendo apenas "1d30"
    # será completamente ignorada.
    if command != PREFIX:
        return

    # Caso a pessoa envie apenas !roll,
    # mostra os exemplos.
    if len(parts) == 1:
        help_message = (
            "**🎲 Como usar o bot de dados**\n\n"
            "`!roll 1d30`\n"
            "`!roll 10d30`\n"
            "`!roll 1d100`\n"
            "`!roll 1d30+10`\n"
            "`!roll 1d30-5`\n"
            "`!roll 1d30+20%`\n"
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

        await message.channel.send(
            help_message,
            allowed_mentions=(
                discord.AllowedMentions.none()
            ),
        )
        return

    expression = parts[1].strip()

    if not expression:
        return

    # Remove espaços e padroniza as letras
    cleaned_expression = "".join(
        expression.split()
    ).lower()

    # Pega o apelido do jogador no servidor.
    # Caso não tenha apelido, usa o nome de exibição.
    player_name = discord.utils.escape_markdown(
        message.author.global_name
    )

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

        # Somente valores entre 1 e 250 são aceitos.
        #
        # Acima de 250, o bot não responde.
        # Portanto, 10000#d10000 será ignorado.
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
            await message.channel.send(
                f"❌ {error}",
                allowed_mentions=(
                    discord.AllowedMentions.none()
                ),
            )
            return

        header = (
            f"🎲 **{player_name} rolou** "
            f"{cleaned_expression}"
        )

        responses = build_discord_messages(
            header,
            result_lines,
        )

        for response in responses:
            await message.channel.send(
                response,
                allowed_mentions=(
                    discord.AllowedMentions.none()
                ),
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
        await message.channel.send(
            f"❌ {error}",
            allowed_mentions=(
                discord.AllowedMentions.none()
            ),
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
        f"🎲 **{player_name} rolou** "
        f"{result['display_expression']}\n\n"
        f"`  {formatted_total}  ` "
        f"⟵ [{rolls_text}] "
        f"{result['display_expression']}"
    )

    await message.channel.send(
        response,
        allowed_mentions=(
            discord.AllowedMentions.none()
        ),
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