# Resultados de poções

Este diretório armazena tudo que o slash command `/poção` usa. O bot não
consulta o Discohook, mensagens antigas ou serviços externos para carregar os
resultados.

## Estrutura

Crie uma pasta sem acentos, espaços ou caracteres especiais para cada
resultado:

```text
data/
├── pocao_comum/
│   ├── resultado.json
│   └── pocao_comum.gif
└── pocao_mitica/
    └── resultado.json
```

O nome `resultado.json` é obrigatório. A imagem local só é necessária quando
a embed usa `attachment://`. Formatos locais aceitos: `.png`, `.jpg`, `.jpeg`,
`.gif` e `.webp`.

Cada pasta válida participa do sorteio com a mesma chance. Pastas novas são
descobertas automaticamente a cada uso do comando: não é preciso alterar uma
lista Python nem sincronizar `/poção` novamente.

## Exportação pelo Discohook

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

## Associação da imagem local

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

## Adicionar outra poção

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

## Sincronização do comando

`/poção` é sincronizado globalmente com o Discord quando o bot inicia. Essa
propagação pode levar algum tempo na primeira execução. A sincronização
registra o comando; ela não envia os JSONs ou as imagens, e não precisa ser
repetida quando uma pasta de resultado é adicionada.
