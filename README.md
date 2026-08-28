# Bot Elysios

Bot de Discord com rolagem de dados por mensagens, gerenciamento de ordens de
turnos, manuais, testes de estabilidade e resultados de poções e artesanato.

## Estrutura

```text
bot.py                 Ponto de entrada e eventos gerais
cogs/artesanato.py     Slash command /artesanato
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

O diretório `data/` armazena os resultados usados por `/poção`,
`/artesanato` e `/estabilidade`, além dos manuais fixos do grupo `/iniciar`. O
bot não consulta o Discohook, mensagens antigas ou webhooks para carregar esses
conteúdos. URLs HTTPS presentes nas embeds podem apontar para uma CDN.

### Estrutura completa

```text
data/
├── artesanato/
│   ├── artesanatocomum/
│   │   ├── resultado.json
│   │   └── artesanatocomum.gif
│   ├── artesanatoincomum/
│   │   ├── resultado.json
│   │   └── artesanatoincomum.gif
│   ├── artesanatoraro/
│   │   ├── resultado.json
│   │   └── artesanatoraro.gif
│   ├── artesanatolendario/
│   │   ├── resultado.json
│   │   └── artesanatolendario.gif
│   └── artesanatomitico/
│       ├── resultado.json
│       └── artesanatomitico.gif
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

Para que os slash commands respondam rapidamente, mantenha as imagens estáticas
com até cerca de 1200 pixels de largura e, de preferência, abaixo de 500 KB.
Use JPEG ou WEBP para artes sem transparência; arquivos maiores precisam ser
reenviados ao Discord a cada comando e aumentam diretamente o tempo de resposta.

## Sistema de poções (`/poção`)

`/poção` é exclusivamente um slash command; não existem versões ou aliases
com o prefixo `!`. A cada uso, o bot valida as cinco raridades obrigatórias,
realiza um novo sorteio ponderado e responde no mesmo canal.

| Pasta | Raridade | Probabilidade |
| --- | --- | ---: |
| `pocao_comum` | Comum | 50% |
| `pocao_incomum` | Incomum | 25% |
| `pocao_rara` | Rara | 15% |
| `pocao_lendaria` | Lendária | 8% |
| `pocao_mitica` | Mítica | 2% |

Cada pasta deve conter obrigatoriamente seu `resultado.json` e, quando a embed
usar `attachment://`, a mídia correspondente:

```text
data/pocao_comum/
├── resultado.json
└── pocao_comum.jpg            Opcional; necessário para attachment://
```

Se qualquer uma das cinco raridades estiver ausente ou inválida, o sorteio não
acontece e o sistema informa indisponibilidade temporária, sem redistribuir sua
probabilidade. Pastas extras não participam automaticamente: uma nova raridade
precisa receber um peso explícito em `PESOS_RARIDADES`, em `cogs/pocoes.py`.
Os pesos devem sempre somar 100. Os diretórios `data/artesanato/`,
`data/estabilidade/` e `data/manuais/` continuam reservados para seus próprios
sistemas.

## Sistema de artesanato (`/artesanato`)

`/artesanato` é um slash command separado de `/poção`. A cada uso, o bot
valida os cinco resultados obrigatórios, sorteia uma raridade com os pesos de
artesanato e envia a primeira embed do `resultado.json` correspondente. O
sorteio de poções e suas probabilidades não são alterados.

| Pasta | Raridade | Probabilidade |
| --- | --- | ---: |
| `artesanatocomum` | Comum | 50% |
| `artesanatoincomum` | Incomum | 25% |
| `artesanatoraro` | Raro | 15% |
| `artesanatolendario` | Lendário | 8% |
| `artesanatomitico` | Mítico | 2% |

Os pesos ficam na configuração explícita de artesanato e somam 100. A
associação entre raridade e pasta também é explícita; ela não depende da
ordem em que o sistema operacional lista os diretórios. Se um dos cinco JSONs
estiver ausente ou inválido, o comando informa indisponibilidade temporária e
não redistribui o peso entre os demais resultados.

As pastas já contêm somente `.gitkeep`. Antes de usar o comando, coloque seus
arquivos definitivos do Discohook e os GIFs de backup exatamente nestes locais:

| Raridade | JSON obrigatório | GIF local de backup |
| --- | --- | --- |
| Comum | `data/artesanato/artesanatocomum/resultado.json` | `data/artesanato/artesanatocomum/artesanatocomum.gif` |
| Incomum | `data/artesanato/artesanatoincomum/resultado.json` | `data/artesanato/artesanatoincomum/artesanatoincomum.gif` |
| Raro | `data/artesanato/artesanatoraro/resultado.json` | `data/artesanato/artesanatoraro/artesanatoraro.gif` |
| Lendário | `data/artesanato/artesanatolendario/resultado.json` | `data/artesanato/artesanatolendario/artesanatolendario.gif` |
| Mítico | `data/artesanato/artesanatomitico/resultado.json` | `data/artesanato/artesanatomitico/artesanatomitico.gif` |

Cada `resultado.json` deve manter na imagem da embed sua URL oficial da CDN:

| Raridade | URL esperada em `embeds[0].image.url` |
| --- | --- |
| Comum | `https://pub-57a72b7c1133428e9da66f38a6b6bbf4.r2.dev/artesanato/artesanatocomum.gif` |
| Incomum | `https://pub-57a72b7c1133428e9da66f38a6b6bbf4.r2.dev/artesanato/artesanatoincomum.gif` |
| Raro | `https://pub-57a72b7c1133428e9da66f38a6b6bbf4.r2.dev/artesanato/artesanatoraro.gif` |
| Lendário | `https://pub-57a72b7c1133428e9da66f38a6b6bbf4.r2.dev/artesanato/artesanatolendario.gif` |
| Mítico | `https://pub-57a72b7c1133428e9da66f38a6b6bbf4.r2.dev/artesanato/artesanatomitico.gif` |

A CDN é a fonte principal. Quando a URL da raridade sorteada está saudável,
o bot envia somente a embed e não faz upload do GIF local. A verificação é
feita sob demanda apenas para essa URL; as outras quatro imagens não são
consultadas.

O verificador, a sessão HTTP e o cache de disponibilidade são compartilhados
com `/poção`. O cache usa a própria URL como chave, conserva resultados
saudáveis por aproximadamente 10 minutos e falhas por aproximadamente 1
minuto. Assim, usos repetidos dentro do TTL não geram uma nova requisição HTTP.
Não há monitoramento periódico em segundo plano.

Se a CDN falhar, a raridade não é sorteada novamente. O bot abre o GIF da mesma
pasta com `discord.File`, troca somente a URL da imagem na embed em memória por
`attachment://` e envia o backup. O `resultado.json` nunca é modificado. Se a
CDN estiver saudável, a ausência do backup local não impede o resultado; se a
CDN e o GIF falharem juntos, o jogador recebe uma mensagem amigável. Os GIFs
permanecem animados e não devem ser convertidos para PNG.

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
árvore de Application Commands. Depois de adicionar `/artesanato`, reinicie o
bot e aguarde a propagação da sincronização pelo Discord. O mesmo vale ao
adicionar `/estabilidade`, `/iniciar poção` ou outro novo subcomando.

Adicionar ou editar somente um JSON ou uma mídia de um resultado/manual já
registrado não muda a estrutura dos comandos e não exige nova sincronização. A
sincronização registra os comandos; ela não envia JSONs nem imagens.

## Testes

```powershell
python -m unittest discover -s tests -v
```

As ordens de turnos ficam em memória e são perdidas quando o bot é
reiniciado.
