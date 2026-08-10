# Dados locais do bot

Este diretório armazena os resultados usados por `/poção` e os manuais fixos
do grupo `/iniciar`. O bot não consulta o Discohook, mensagens antigas ou
serviços externos para carregar esses conteúdos.

## Resultados de poções (`/poção`)

### Estrutura dos resultados

Crie uma pasta sem acentos, espaços ou caracteres especiais para cada
resultado:

```text
data/
├── pocao_comum/
│   ├── resultado.json
│   └── pocao_comum.gif
├── pocao_mitica/
│   └── resultado.json
└── manuais/
    ├── README.md
    ├── manual.json
    └── iniciar_pocao.gif
```

O nome `resultado.json` é obrigatório. A imagem local só é necessária quando
a embed usa `attachment://`. Formatos locais aceitos: `.png`, `.jpg`, `.jpeg`,
`.gif` e `.webp`.

Cada pasta válida participa do sorteio com a mesma chance. Pastas novas são
descobertas automaticamente a cada uso do comando: não é preciso alterar uma
lista Python nem sincronizar `/poção` novamente.

### Exportação pelo Discohook

1. Monte visualmente uma única embed no Discohook.
2. Exporte o payload JSON completo.
3. Salve-o como `resultado.json`, em UTF-8, dentro da pasta do resultado.
4. Se a embed usar um attachment, baixe também o GIF, PNG, JPG ou WEBP e
   salve-o manualmente na mesma pasta.
5. Preserve o conteúdo exportado. Títulos, descrições, campos, cores, emojis,
   Unicode, Markdown, links, author, footer, thumbnail e imagem são lidos da
   primeira entrada de `embeds`.

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

O bot reconstrói `embeds[0]` com `discord.Embed.from_dict()`. O array
`attachments` pode permanecer no JSON como foi exportado, mas seus endereços
`blob:https://discohook.app/...` são temporários e são ignorados. A mídia deve
existir localmente.

### Associação da imagem local

Para `attachment://pocao_comum.gif`, a procura segue esta ordem:

1. um arquivo local com o nome exato `pocao_comum.gif`;
2. se não houver correspondência exata, o único arquivo de imagem compatível
   existente na pasta.

O segundo caso permite usar um nome local simples quando o Discohook exporta
acentos, espaços ou outro nome inconveniente. Ao enviar, o bot associa o
arquivo local à embed usando um nome seguro. Se não houver imagem ou se houver
mais de uma alternativa sem correspondência exata, a pasta é ignorada para
evitar uma associação incorreta.

Uma imagem com URL permanente `http://` ou `https://` não precisa de arquivo
local e continua apontando para essa URL.

### Adicionar outra poção

Crie, por exemplo:

```text
data/pocao_divina/
├── resultado.json
└── pocao_divina.webp
```

Não altere o código nem uma lista de resultados. No próximo uso de `/poção`,
a nova pasta válida já participará do sorteio com a mesma probabilidade das
demais.

JSON ausente, inválido ou sem uma primeira embed válida é registrado no
console e ignorado sem afetar as outras pastas. O mesmo ocorre quando um
`attachment://` não pode ser associado a uma imagem local.

## Manuais de início (`/iniciar`)

Os manuais ficam dentro de `data/manuais/` e são independentes do sorteio. O
subcomando `/iniciar poção` sempre carrega:

```text
data/manuais/manual.json
```

O arquivo deve ser o payload completo exportado pelo Discohook, salvo em
UTF-8. O bot reconstrói `embeds[0]`, quando essa primeira entrada é válida, e
envia somente a embed do manual no mesmo canal, sem sortear um resultado. Não use
`resultado.json` nessa pasta: esse nome pertence ao sistema de `/poção`.

Quando a embed apontar para `attachment://`, coloque o GIF, PNG, JPG, JPEG ou
WEBP na mesma pasta do `manual.json`. A procura prioriza o nome referenciado,
depois uma correspondência equivalente após normalizar o nome e, por fim, a
única imagem compatível da pasta. Se houver várias imagens ambíguas, o manual é
considerado indisponível para evitar uma associação incorreta.

URLs permanentes `http://` e `https://` não precisam de arquivo local. O array
`attachments` exportado pode permanecer no JSON, mas URLs
`blob:https://discohook.app/...` são temporárias e nunca são usadas em runtime.
O bot também não depende de webhooks, mensagens ou IDs do Discord para
reconstruir o manual.

O passo a passo específico está no
[guia do manual de poções](manuais/README.md).

### Adicionar outro manual

Para adicionar futuramente `/iniciar mineração`:

1. crie `data/manuais/manual_mineracao.json` e coloque a mídia opcional na
   pasta `data/manuais/`;
2. adicione em `cogs/iniciar.py` um novo método decorado como subcomando do
   grupo `iniciar`, fazendo-o carregar `manual_mineracao.json`;
3. reinicie o bot para carregar e sincronizar a nova estrutura do comando.

Reutilize o grupo `/iniciar`; cada atividade deve ser um subcomando e um JSON
próprio dentro da mesma pasta `data/manuais/`.

## Sincronização dos comandos

`/poção` e o grupo `/iniciar` são sincronizados globalmente com o Discord
quando o bot inicia. Essa propagação pode levar algum tempo depois que um novo
comando ou subcomando é criado. A sincronização registra a estrutura dos
comandos; ela não envia JSONs ou imagens.

Adicionar ou alterar apenas o `manual.json` ou a mídia de um manual já
existente não exige nova sincronização. Uma nova sincronização é necessária
quando um novo subcomando, como `/iniciar mineração`, é acrescentado ao código.
