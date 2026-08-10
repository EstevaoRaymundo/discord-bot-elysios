# Resultados de estabilidade

Esta pasta armazena as duas embeds locais usadas pelo slash command
`/estabilidade`. O sistema é independente de `/poção` e de `/iniciar poção`.

## Estrutura

```text
data/estabilidade/
├── estavel/
│   ├── resultado.json
│   └── estavel.gif       Opcional; necessário para attachment://
└── instavel/
    ├── resultado.json
    └── instavel.gif      Opcional; necessário para attachment://
```

As pastas `estavel/` e `instavel/` já contêm um `.gitkeep` apenas para que a
estrutura vazia seja versionada. Ele pode permanecer no diretório e não
participa do sorteio.

## Preparar os resultados

1. Crie visualmente a embed Estável no Discohook.
2. Exporte o payload JSON completo e salve-o em UTF-8 como
   `estavel/resultado.json`.
3. Repita o processo para a embed Instável, salvando-a em
   `instavel/resultado.json`.
4. Preserve `embeds`, `attachments` e o conteúdo visual exportado. O bot usa
   a primeira entrada válida de `embeds` e a reconstrói com
   `discord.Embed.from_dict()`.

Não existe `resultado.json` de exemplo neste diretório porque as duas embeds
definitivas serão fornecidas pelo responsável pelo bot.

## Imagens e attachments

Quando uma embed usar `attachment://arquivo.gif`, salve a mídia física na
mesma pasta do `resultado.json` correspondente. São aceitos `.png`, `.jpg`,
`.jpeg`, `.gif` e `.webp`.

O bot procura primeiro o nome referenciado, depois uma correspondência
equivalente após normalização e, por fim, a única imagem compatível da pasta.
Com várias imagens ambíguas, o resultado é considerado inválido. URLs
permanentes `http://` e `https://` não exigem arquivo local.

O array `attachments` exportado pelo Discohook pode permanecer no JSON, mas
endereços `blob:https://discohook.app/...` são temporários e não são usados
em runtime. O arquivo correspondente deve ser baixado e armazenado localmente.

## Validação e probabilidade

Antes do sorteio, o bot valida obrigatoriamente os resultados `estavel` e
`instavel`. Se qualquer JSON, embed ou attachment estiver inválido, nenhum
resultado é sorteado e o jogador recebe uma mensagem amigável de
indisponibilidade.

Com os dois resultados válidos, o sorteio escolhe entre esses dois nomes
fixos. A chance é exatamente 50% Estável e 50% Instável; ela não depende da
quantidade de arquivos existentes.

## Testar e sincronizar

Depois de adicionar os dois `resultado.json`, inicie o bot e execute
`/estabilidade` em um canal onde ele possa enviar mensagens, incorporar links
e, quando necessário, anexar arquivos. A resposta deve conter somente uma das
duas embeds.

A criação do slash command exige a sincronização da CommandTree após reiniciar
o bot. Depois que `/estabilidade` estiver registrado, alterar somente os JSONs
ou suas mídias não exige nova sincronização.
