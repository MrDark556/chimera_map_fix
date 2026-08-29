[English](README.md) | [Español](README.es.md) | **Português (Brasil)**

# Chimera Hybrid Map Downloader

Um downloader e lançador leve de mapas para **Halo Custom Edition + Chimera**.

Esta ferramenta é voltada principalmente para jogadores que têm problemas com o downloader normal de mapas do HaloNet no Chimera, embora qualquer pessoa possa usá-la.

Quando o Chimera solicita um mapa personalizado que você não tem, o downloader tenta automaticamente várias fontes de mapas do Halo CE até encontrar uma cópia funcional.

## Instalação

### 1. Baixe o lançador


Você pode colocar o arquivo EXE onde for mais conveniente.

### 2. Edite `chimera.ini`

Abra seu arquivo de configuração do Chimera:

```text
chimera.ini
```

Procure a seção:

```ini
[memory]
```

Adicione ou habilite esta linha:

```ini
download_template=http://127.0.0.1:8765/{map}
```

Se você já tiver outra linha `download_template` ativa, comente-a colocando um ponto e vírgula (`;`) no início.

Por exemplo:

```ini
[memory]

;download_template=http://maps.halonet.net/halonet/locator.php?format=inv&map={map}&type={game}
download_template=http://127.0.0.1:8765/{map}
```

> **Importante:** Deve haver apenas uma linha `download_template` ativa.

---

## Fontes de download

O downloader tenta as fontes nesta ordem:

1. **Localizador normal do HaloNet**
2. **Arquivo ZIP estático do HaloNet**
3. **CE3**
4. **HaloMaps.org**

Se o downloader normal do HaloNet funcionar para você, o Chimera continuará usando seu comportamento e progresso normais de download.

Se o HaloNet falhar e o programa precisar usar uma das fontes alternativas, uma pequena janela de progresso aparecerá mostrando informações como:

- Nome do mapa
- Fonte de download atual
- Porcentagem baixada
- MB baixados
- Velocidade de download
- Tempo restante estimado
- Status de busca / extração

---

## Iniciando o Halo

Depois de configurar o Chimera, inicie o Halo Custom Edition usando:

```text
ChimeraMapDownloader.exe
```

Se quiser que o downloader inicie automaticamente, **não abra o `haloce.exe` diretamente**.

O lançador fará o seguinte:

1. Inicia silenciosamente o downloader de mapas em segundo plano.
2. Inicia o Halo Custom Edition.
3. Mantém o downloader ativo enquanto o Halo estiver aberto.
4. Fecha automaticamente o downloader quando o Halo for fechado.

Nenhuma janela de Prompt de Comando ou BAT é exibida.

---

## Primeira inicialização

O lançador tentará encontrar o `haloce.exe` automaticamente.

Se o Halo Custom Edition estiver instalado em um local não padrão, será solicitado que você selecione:

```text
haloce.exe
```

uma única vez.

O local será salvo para as próximas inicializações.

---

## Como cada fonte funciona

### HaloNet — Localizador normal

Este é o método normal de download de mapas do Chimera/HaloNet.

Se funcionar para você, a janela personalizada de progresso alternativo **não** aparecerá, já que o Chimera cuida do download normalmente.

### HaloNet — ZIP estático alternativo

Se o localizador normal do HaloNet falhar, o downloader tentará obter o mapa diretamente do arquivo ZIP estático do HaloNet.

O arquivo é baixado, o `.map` é extraído e validado, e então entregue ao Chimera.

### CE3

O downloader busca no arquivo do Halo Custom Edition do CE3.

As entradas do CE3 mostram o nome interno do mapa, então o downloader verifica o nome do arquivo `.map` solicitado antes de aceitar um resultado.

### HaloMaps.org

O HaloMaps.org é usado como uma fonte alternativa adicional caso as fontes anteriores não consigam fornecer o mapa solicitado.

O downloader busca no arquivo, resolve a entrada correspondente, baixa o arquivo, extrai o mapa, valida e entrega ao Chimera.

---

## Progresso do download

Quando o localizador normal do HaloNet funciona, o Chimera usa seu indicador normal de progresso.

A janela de progresso personalizada só é usada para downloads alternativos, onde o Halo ficaria preso mostrando:

```text
Connecting to map server...
```

A janela alternativa pode mostrar:

```text
Map: example_map
Source: CE3
Downloading...

102.4 MB / 150.6 MB
7.3 MB/s
~7s remaining
```

Durante etapas que não são de download, pode mostrar, por exemplo:

```text
Searching CE3...
Extracting map...
Validating map...
```

A janela se fecha automaticamente quando o mapa estiver pronto.

---

## Proteção contra travamentos

Para evitar que o Halo fique indefinidamente em **Connecting to map server...**:

| Limite | Tempo |
|---|---:|
| Tempo máximo sem atividade de rede | 15 segundos |
| Tempo máximo por transferência de mapa/arquivo | 5 minutos |
| Limite absoluto por solicitação | 6 minutos |

Mapas grandes podem demorar um pouco para baixar e extrair antes que o Halo comece a carregá-los.

---

## Logs e solução de problemas

Os arquivos de execução são salvos em:

```text
%LOCALAPPDATA%\ChimeraHybridMapDownloader
```

Os arquivos de log úteis incluem:

```text
chimera_downloader.log
launcher.log
```

Se um mapa não for baixado, inclua o seguinte ao relatar o problema:

- Nome do mapa
- Qual servidor/fonte estava sendo tentado
- `chimera_downloader.log`
- `launcher.log` se o problema foi com o lançador

---

## Requisitos

- Windows
- Halo Custom Edition
- Chimera

A versão pública do `ChimeraMapDownloader.exe` **não** exige que o Python esteja instalado.

---

## Windows SmartScreen

O executável pode exibir um aviso de **Editor Desconhecido** ou do Windows SmartScreen porque não está assinado digitalmente.

Isso é normal para executáveis de comunidade sem assinatura digital.

---

## Configuração rápida

1. [Baixe](https://github.com/MrDark556/chimera_map_fix/releases/download/v3.5/haloce_chimera_mpdlr.exe) `ChimeraMapDownloader.exe`
2. Abra o `chimera.ini`.
3. Em `[memory]`, configure:

```ini
download_template=http://127.0.0.1:8765/{map}
```

4. Comente qualquer outra linha `download_template` ativa.
5. Inicie o Halo usando:

```text
haloce_chimera_mpdlr.exe
```

6. Entre nos servidores normalmente.

---

## Prioridade atual das fontes

```text
Localizador normal do HaloNet
        ↓
ZIP estático do HaloNet
        ↓
CE3
        ↓
HaloMaps.org
```

---

Aproveite o Halo Custom Edition!
