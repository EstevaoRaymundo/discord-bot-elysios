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

## Dados locais e Discohook

O diretório `data/` armazena os resultados usados por `/poção` e
`/estabilidade`, além dos manuais fixos do grupo `/iniciar`. O bot não consulta
o Discohook, mensagens antigas, webhooks ou serviços externos para carregar
esses conteúdos.

### Estrutura completa

```text
data/
├── pocao_comum/
│   ├── resultado.json
│   └── pocao_comum.gif        Opcional; necessário para attachment://
├── pocao_mitica/
│   └── resultado.json
├── estabilidade/
│   ├── estavel/
│   │   ├── resultado.json
│   │   └── estavel.gif        Opcional; necessário para attachment://
│   └── instavel/
│       ├── resultado.json
│       └── instavel.gif       Opcional; necessário para attachment://
└── manuais/
    ├── manual.json
    └── iniciar_pocao.gif      Opcional; necessário para attachment://
```

### Exportação de uma embed

1. Monte visualmente uma única embed no Discohook.
2. Exporte o payload JSON completo.
3. Salve o arquivo em UTF-8 no diretório e com o nome indicado para o comando.
4. Preserve `embeds`, `attachments` e todo o conteúdo exportado. O bot
   reconstrói `embeds[0]` com `discord.Embed.from_dict()`, preservando títulos,
   descrições, campos, cores, emojis, Unicode, Markdown, links, author, footer,
   thumbnail e imagem.
5. Se a embed usar `attachment://`, baixe também o GIF, PNG, JPG, JPEG ou WEBP
   e salve-o na mesma pasta do JSON.

Exemplo completo com attachment:

```json
{
  "embeds": [
    {
      "color": 4069400,
      "title": "Poção Comum",
      "description": "⚗️ **Resultado:** você recupera energia.",
      "fields": [
        {
          "name": "Efeito",
          "value": "+10 pontos",
          "inline": true
        }
      ],
      "image": {
        "url": "attachment://pocao_comum.gif"
      },
      "footer": {
        "text": "Preparada em Elysios"
      }
    }
  ],
  "attachments": [
    {
      "id": "387115164678754",
      "filename": "pocao_comum.gif",
      "content_type": "image/gif",
      "size": 1473383,
      "url": "blob:https://discohook.app/exemplo",
      "proxy_url": "http://localhost",
      "placement_count": 0
    }
  ]
}
```

O array `attachments` pode permanecer no JSON, mas os endereços
`blob:https://discohook.app/...` são temporários e nunca são usados pelo bot.
O arquivo correspondente precisa ser baixado manualmente e armazenado ao lado
do JSON. Imagens com uma URL permanente `http://` ou `https://` continuam
remotas e não exigem um arquivo local.

Para `attachment://arquivo.gif`, o bot procura uma imagem local nesta ordem:

1. o nome exato referenciado pela embed;
2. um nome equivalente depois da normalização;
3. a única imagem compatível existente na pasta.

Se não encontrar a imagem ou houver várias alternativas ambíguas, o conteúdo
é considerado inválido para evitar uma associação incorreta. Os formatos
locais aceitos são `.png`, `.jpg`, `.jpeg`, `.gif` e `.webp`.

## Sistema de poções (`/poção`)

`/poção` é exclusivamente um slash command; não existem versões ou aliases
com o prefixo `!`. Ao usá-lo, o bot escolhe com chances iguais um dos
resultados válidos e responde no mesmo canal.

Crie uma pasta sem acentos, espaços ou caracteres especiais para cada
resultado. Dentro dela, o nome `resultado.json` é obrigatório:

```text
data/pocao_divina/
├── resultado.json
└── pocao_divina.webp          Opcional; necessário para attachment://
```

Cada pasta válida participa do sorteio com a mesma chance. Pastas novas são
descobertas automaticamente a cada uso, portanto não é preciso alterar uma
lista Python nem sincronizar `/poção` novamente.

JSON ausente, inválido ou sem uma primeira embed válida é registrado no
console e ignorado sem afetar as outras pastas. O mesmo ocorre quando um
`attachment://` não pode ser associado a uma imagem local. Os diretórios
`data/estabilidade/` e `data/manuais/` são reservados para seus próprios
sistemas e não participam do pool de `/poção`.

## Manuais de início (`/iniciar`)

`/iniciar` é um grupo de Application Commands. Ele organiza os manuais como
subcomandos e não é usado sozinho. O primeiro manual é `/iniciar poção`.

Os dois comandos de poção têm responsabilidades diferentes:

- `/iniciar poção` sempre mostra a embed fixa com as instruções de preparo;
- `/poção` sorteia um resultado entre as poções válidas.

O manual não realiza sorteio, não altera raridades ou probabilidades e não
participa dos resultados de `/poção`. Salve o payload exportado em:

```text
data/manuais/manual.json
```

Não use `resultado.json` nessa pasta. Se houver um `attachment://`, coloque a
mídia ao lado de `manual.json`, seguindo as regras da seção de dados locais.
Quando o conteúdo definitivo ainda não estiver pronto, não é necessário criar
um payload de exemplo que substitua ou invente a embed do Discohook.

Para testar, inicie o bot e execute `/iniciar poção` em um canal no qual ele
possa enviar mensagens, incorporar links e anexar arquivos. A resposta deve
conter somente a embed do manual e, quando necessário, seu attachment.

Para criar futuramente `/iniciar mineração`:

1. adicione `data/manuais/manual_mineracao.json` e sua mídia opcional;
2. crie em `cogs/iniciar.py` um novo método/subcomando no grupo `iniciar`,
   apontando para esse arquivo;
3. reinicie o bot para sincronizar a nova estrutura do comando.

Reutilize o grupo existente; não crie um comando solto como
`/iniciar-mineração`.

## Estabilidade das poções (`/estabilidade`)

`/estabilidade` é um slash command independente que determina se a poção ficou
estável ou instável. Ele envia somente a embed do resultado sorteado, sem
alterar o manual de `/iniciar poção` nem o sorteio de raridade de `/poção`.

O fluxo recomendado é separado em três etapas:

1. `/iniciar poção` mostra o manual de criação;
2. `/estabilidade` sorteia Estável ou Instável;
3. `/poção` realiza o sistema de resultado e raridade.

Os dois resultados são obrigatórios e ficam nestes caminhos:

```text
data/estabilidade/estavel/resultado.json
data/estabilidade/instavel/resultado.json
```

Salve a embed Estável no primeiro arquivo e a Instável no segundo. Os arquivos
`.gitkeep` podem permanecer nos diretórios e não participam do sorteio. Não é
necessário criar resultados de exemplo antes de as duas embeds definitivas
estarem disponíveis.

Antes de sortear, o bot valida os dois JSONs, suas primeiras embeds e suas
mídias. Se qualquer um estiver ausente ou inválido, nenhum resultado é
sorteado e o jogador recebe uma mensagem amigável de indisponibilidade. Com os
dois válidos, a escolha ocorre entre os nomes fixos `estavel` e `instavel`,
garantindo exatamente 50% de chance para cada um, independentemente da
quantidade de arquivos ou pastas.

Para testar, execute `/estabilidade` em um canal no qual o bot possa enviar
mensagens, incorporar links e anexar arquivos. A resposta deve conter somente
uma das duas embeds.

## Sincronização dos slash commands

Na inicialização, o bot carrega os Cogs e sincroniza globalmente uma única
árvore de Application Commands. Ao adicionar `/estabilidade`, `/iniciar poção`
ou outro novo subcomando, reinicie o bot e aguarde a propagação da
sincronização pelo Discord.

Adicionar ou editar somente um JSON ou uma mídia de um resultado/manual já
registrado não muda a estrutura dos comandos e não exige nova sincronização. A
sincronização registra os comandos; ela não envia JSONs nem imagens.

## Testes

```powershell
python -m unittest discover -s tests -v
```

As ordens de turnos ficam em memória e são perdidas quando o bot é
reiniciado.
