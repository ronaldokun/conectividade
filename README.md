# Verificador de disponibilidade de URLs

Verifica cada URL em um navegador Chrome/Chromium real, usando abas paralelas, e gera um relatório HTML com captura de tela da página inteira e cópia do HTML renderizado de cada URL.

## Executar a partir do código-fonte

Instale o [uv](https://docs.astral.sh/uv/) e o Chrome ou Chromium; depois execute:

```console
uv sync
uv run url-availability-checker
```

Adicione um URL HTTP(S) por linha em `urls.txt`. Linhas vazias e comentários iniciados por `#` são ignorados. O navegador é exibido por padrão; use `--headless` para executá-lo sem janela.

```console
uv run url-availability-checker [urls.txt] --output report --concurrency 4 --timeout 30 --settle 1 --browser "C:\\caminho\\chrome.exe"
```

Opções:

- `--output`: pasta do relatório (padrão: `report`)
- `--concurrency`: número de abas simultâneas (padrão: `4`)
- `--timeout`: tempo limite de carregamento por página, em segundos (padrão: `30`)
- `--settle`: espera após o carregamento, em segundos (padrão: `1`)
- `--browser`: caminho do executável Chrome/Chromium, caso a detecção automática não funcione
- `--headless`: executa sem exibir a janela do navegador

O nome do relatório é derivado do nome do arquivo de entrada, aparece no título HTML e prefixa os snapshots. O programa cria `report/index.html` com data e hora da execução e `report/snapshots/`, cujos arquivos recebem o nome e o carimbo de data e hora no nome. Retorna código de saída `1` se alguma URL falhar ou se a resposta final não for 2xx; retorna `0` se todas forem aprovadas. O código HTTP vem da API Navigation Timing do Chrome; se não estiver disponível, a verificação considera o resultado do carregamento no navegador. A localização aproximada da conexão é consultada uma vez por execução em `ipapi.co`, usando o IP público de saída. Isso compartilha esse IP com o serviço; se a consulta falhar, o relatório indica localização indisponível.

## Gerar o executável para Windows

Faça a compilação em Windows (PyInstaller não gera executáveis Windows a partir de Linux/macOS):

```bat
build.bat
```

O executável será `dist\url-checker.exe`. Execute-o em uma pasta com `urls.txt` ou informe o caminho do arquivo como primeiro argumento. Chrome/Chromium precisa estar instalado no computador de destino; o navegador não é incluído no executável.
