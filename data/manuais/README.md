# Manual de poções

Esta pasta armazena o conteúdo fixo exibido por `/iniciar poção`. Ela não faz
parte do sorteio executado por `/poção`.

## Estrutura

```text
data/manuais/
├── README.md
├── manual.json
└── iniciar_pocao.gif    Opcional; necessário para attachment://
```

Crie `manual.json` quando o conteúdo visual definitivo estiver pronto. Este
diretório não inclui um payload de exemplo para não substituir nem inventar a
embed criada no Discohook.

## Preparar o manual no Discohook

1. Monte visualmente uma única embed com o conteúdo completo do manual.
2. Exporte o payload JSON completo pelo Discohook.
3. Salve o arquivo em UTF-8 com o nome exato `manual.json` nesta pasta.
4. Preserve `embeds`, `attachments` e o conteúdo da embed como foram
   exportados. O bot usa `embeds[0]` quando essa primeira entrada é válida.
5. Se a imagem usar `attachment://`, baixe o arquivo original e salve-o nesta
   mesma pasta.

O Discohook é apenas a ferramenta de criação. O bot não o consulta em runtime
e não depende de webhooks, mensagens antigas, canais ou IDs de mensagens.

## Imagens e attachments

São aceitos arquivos `.png`, `.jpg`, `.jpeg`, `.gif` e `.webp`. Para uma URL
como `attachment://iniciar_pocao.gif`, mantenha o GIF ao lado de `manual.json`.
O bot procura primeiro o nome correspondente, depois um nome equivalente após
normalização e, se necessário, pode usar a única imagem compatível existente
na pasta. Com várias opções ambíguas, o manual não é enviado.

Uma URL permanente `http://` ou `https://` pode permanecer na embed e não
exige mídia local. Já uma URL `blob:https://discohook.app/...` é temporária e
é ignorada: o arquivo correspondente deve ser baixado manualmente. O array
`attachments` pode permanecer no JSON, mas não é usado para baixar arquivos.

## Testar e sincronizar

Inicie o bot e execute `/iniciar poção` no canal desejado. A resposta deve
conter somente a embed do manual, além do arquivo necessário para resolver um
eventual `attachment://`. O comando não sorteia raridade ou resultado.

A criação do subcomando exige que a árvore de Application Commands seja
sincronizada pelo bot. Depois disso, alterações apenas em `manual.json` ou na
mídia não exigem nova sincronização.

Para outro manual, crie outro JSON no mesmo diretório, como
`data/manuais/manual_mineracao.json`, e adicione em `cogs/iniciar.py` um novo
método/subcomando no mesmo grupo `/iniciar`, apontando para esse arquivo. Como
isso altera a estrutura dos slash commands, reinicie o bot para sincronizá-la.
