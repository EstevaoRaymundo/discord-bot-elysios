# Bot Elysios

Bot de Discord com rolagem de dados por mensagens e gerenciamento de
ordens de turnos.

## Estrutura

```text
bot.py                 Ponto de entrada e eventos gerais
cogs/iniciativa.py     Comandos !turnos
cogs/pocoes.py         Slash command /poção
cogs/rolagem.py        Listener de mensagens de rolagem
data/                  Resultados e mídias locais das poções
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

## Sistema de poções

`/poção` é exclusivamente um slash command; não existem versões ou aliases
com o prefixo `!`. Ao usá-lo, o bot escolhe com chances iguais um dos
resultados válidos e responde no mesmo canal.

Cada resultado fica em uma subpasta própria:

```text
data/
└── pocao_comum/
    ├── resultado.json
    └── pocao_comum.gif       Opcional; necessário para attachment://
```

`resultado.json` deve ser o JSON completo exportado pelo Discohook, salvo em
UTF-8. A primeira entrada de `embeds` é reconstruída sem reescrever seus
textos, preservando acentos, emojis, Unicode e Markdown. Exemplo mínimo:

```json
{
  "embeds": [
    {
      "color": 4069400,
      "description": "⚗️ Uma poção foi preparada!",
      "image": {
        "url": "attachment://pocao_comum.gif"
      }
    }
  ],
  "attachments": []
}
```

Imagens com URL `http://` ou `https://` permanecem remotas. Para uma URL
`attachment://arquivo.gif`, salve também a mídia correspondente na mesma
pasta. O bot procura primeiro o nome exato; se ele não existir, aceita o único
arquivo de imagem compatível da pasta. Sem arquivo, ou com vários arquivos
ambíguos, o resultado é ignorado. São aceitos `.png`, `.jpg`, `.jpeg`, `.gif`
e `.webp`.

URLs `blob:https://discohook.app/...` são temporárias e nunca são acessadas
pelo bot. Baixe o attachment manualmente no Discohook e guarde o arquivo
localmente ao lado de `resultado.json`.

Para adicionar outra poção, basta criar uma nova subpasta com seu
`resultado.json` e, quando necessário, sua mídia. As pastas são descobertas
automaticamente, sem lista Python. Consulte o
[guia dos resultados](data/README.md) para o processo de
exportação e um exemplo completo.

Na inicialização, o bot carrega os Cogs e sincroniza globalmente sua árvore de
Application Commands. A propagação de `/poção` pelo Discord pode levar algum
tempo; alterações apenas nos JSONs ou nas imagens não exigem nova
sincronização.

## Testes

```powershell
python -m unittest discover -s tests -v
```

As ordens de turnos ficam em memória e são perdidas quando o bot é
reiniciado.
