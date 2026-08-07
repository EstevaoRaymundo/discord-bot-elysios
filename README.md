# Bot Elysios

Bot de Discord com rolagem de dados por mensagens e gerenciamento de
ordens de turnos.

## Estrutura

```text
bot.py                 Ponto de entrada e eventos gerais
cogs/iniciativa.py     Comandos !turnos
cogs/rolagem.py        Listener de mensagens de rolagem
utils/dados.py         Parser e cálculo das rolagens
tests/                 Testes automatizados
```

## Instalação e execução

```powershell
python -m pip install -r requirements.txt
python bot.py
```

O token deve ficar no arquivo `.env`:

```dotenv
DISCORD_TOKEN=seu_token
```

## Rolagens aceitas

```text
1d30
2d20
1d30 + 10
1d30 - 35%
1d30 + 10 + 20%
5#d30
5#d30 + 10 + 20%
```

Os modificadores são aplicados da esquerda para a direita. O formato `N#`
executa `N` rolagens independentes e mostra cada resultado em uma linha.

## Testes

```powershell
python -m unittest discover -s tests -v
```

As ordens de turnos ficam em memória e são perdidas quando o bot é
reiniciado.
