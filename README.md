# Bot Elysios

Bot de Discord com rolagem de dados por mensagens, gerenciamento de ordens de
turnos, manuais, testes de estabilidade e resultados de poções.

## Estrutura

```text
bot.py                 Ponto de entrada e eventos gerais
cogs/iniciativa.py     Comandos !turnos
cogs/iniciar.py        Grupo de manuais /iniciar
cogs/pocoes.py         Slash commands /poção e /estabilidade
cogs/rolagem.py        Listener de mensagens de rolagem
data/                  Resultados, manuais e mídias locais
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

## Manuais de início

`/iniciar` é um grupo de Application Commands. Ele organiza os manuais como
subcomandos e não é usado sozinho. O primeiro manual é `/iniciar poção`.

Os dois comandos de poção têm responsabilidades diferentes:

- `/iniciar poção` sempre mostra a embed fixa com as instruções de preparo;
- `/poção` continua sorteando um resultado entre as poções válidas.

O manual não realiza sorteio, não altera raridades ou probabilidades e não
participa dos resultados de `/poção`. Seus arquivos ficam separados:

```text
data/
├── pocao_comum/
│   ├── resultado.json
│   └── pocao_comum.gif
└── manuais/
    ├── manual.json
    └── iniciar_pocao.gif    Opcional; necessário para attachment://
```

Crie a embed visualmente no Discohook, exporte o payload JSON completo e
salve-o em UTF-8 como `data/manuais/manual.json`. O bot lê a primeira
entrada de `embeds` e preserva textos, campos, cores, emojis, Unicode, Markdown
e as demais propriedades compatíveis com `discord.Embed`.

Se a embed usar `attachment://arquivo.gif`, baixe a mídia e coloque-a na mesma
pasta do `manual.json`. Imagens permanentes `http://` ou `https://` continuam
remotas. Endereços `blob:https://discohook.app/...` são temporários, não são
acessados pelo bot e não substituem o arquivo local. Consulte o
[guia do manual de poções](data/manuais/README.md) para preparar esses
arquivos.

Para criar futuramente `/iniciar mineração`, adicione no mesmo diretório um
arquivo como `manual_mineracao.json` e sua mídia opcional. Também é necessário
acrescentar em `cogs/iniciar.py` um novo método/subcomando no grupo `iniciar`,
apontando para esse arquivo. Reutilize o grupo existente; não crie um comando
solto como `/iniciar-mineração`.

## Estabilidade das poções

`/estabilidade` é um slash command independente que determina se a poção ficou
estável ou instável. Ele envia somente a embed do resultado sorteado, sem
alterar o manual de `/iniciar poção` nem o sorteio de raridade de `/poção`.

O fluxo recomendado permanece separado em três etapas:

1. `/iniciar poção` mostra o manual de criação;
2. `/estabilidade` sorteia Estável ou Instável;
3. `/poção` realiza o sistema existente de resultado e raridade.

Os dois resultados obrigatórios ficam separados:

```text
data/estabilidade/
├── estavel/
│   ├── resultado.json
│   └── estavel.gif       Opcional; necessário para attachment://
└── instavel/
    ├── resultado.json
    └── instavel.gif      Opcional; necessário para attachment://
```

Cada `resultado.json` deve conter o payload completo exportado pelo Discohook,
salvo em UTF-8. Antes de sortear, o bot valida os dois resultados e suas mídias.
Se qualquer um estiver indisponível ou inválido, não há sorteio e o jogador
recebe uma mensagem amigável.

Com ambos válidos, a escolha é feita entre os dois nomes fixos `estavel` e
`instavel`. Assim, a chance é sempre exatamente 50% para Estável e 50% para
Instável, independentemente da quantidade de arquivos nas pastas. Consulte o
[guia dos resultados de estabilidade](data/estabilidade/README.md) para
preparar os JSONs e as mídias locais.

## Sincronização dos slash commands

Na inicialização, o bot carrega os Cogs e sincroniza globalmente uma única
árvore de Application Commands. Ao adicionar `/estabilidade`, `/iniciar poção`
ou outro novo subcomando, reinicie o bot e aguarde a propagação da
sincronização pelo Discord.

Adicionar ou editar somente o `manual.json`, GIF, PNG, JPG, JPEG ou WEBP de um
manual já registrado não muda a estrutura dos comandos e não exige nova
sincronização. O mesmo vale para os arquivos de resultados de `/poção` e
`/estabilidade`.

## Testes

```powershell
python -m unittest discover -s tests -v
```

As ordens de turnos ficam em memória e são perdidas quando o bot é
reiniciado.
