# Diagnóstico do iFood — 24/11/2026

## Relato do operador

O operador trouxe as seguintes observações de uma investigação anterior. Elas
orientam o diagnóstico, mas não foram confirmadas pelo experimento abaixo:

- A proteção de `merchant-info` foi identificada como PerimeterX (HUMAN).
- A listagem continuou disponível porque, após `bm/home` responder 403, o site
  usou `home:fallback`, que respondeu 200.
- Endereço e CNPJ não apareceram no JSON-LD nem no painel Sobre. Segundo o relato,
  esses dados dependiam da API protegida, sem uma alternativa equivalente.

A hipótese a testar é se cliques e digitação enviados pelos comandos do navegador,
em lugar de eventos sintéticos via JavaScript, mudam o resultado da leitura.
A atribuição a uma nota comportamental e a exclusão de influência do IP ainda
precisam de evidência; sessão nova, sozinha, não resolveu no teste relatado.

## Experimento executado

Foi executado uma vez o `diag6.py` fornecido pelo operador, pelo ambiente `uv`,
com limite externo de 180 segundos. O script usou uma sessão temporária do
camofox e os comandos `/click`, `/type` e `/mouse-wheel`. O gancho observou
requisições feitas pelo próprio site, sem chamar diretamente a API do iFood.

O script verifica CAPTCHA durante as esperas e encerra sem resolvê-lo. Essa
verificação não é contínua: não ocorre durante todas as pausas e comandos.

Antes da execução, `/health` respondeu 503 com `browser_rss_pressure`. Mesmo
assim, a execução conseguiu abrir uma aba e avançar até a lista. Saída relevante:

```text
TYPE: {'ok': True}
LISTA_OK
SEGMENTOS_URL: 2
TITULO_TEM_NOME: True
CAPTURAS: []
PERF: []
```

O processo terminou com código 0. A abertura da página de uma loja não foi
confirmada: uma URL de loja esperada tem o caminho
`/delivery/<cidade>/<nome>/<uuid>`, enquanto a contagem observada foi de apenas
dois segmentos ao dividir o caminho por `/`. Não foram capturadas chamadas de
`merchant-info` ou `catalog`, nem pelo gancho nem por Resource Timing.
`TITULO_TEM_NOME` verifica apenas a ausência de `undefined` no título; não
comprova que o nome de uma loja apareceu.

**Resultado inconclusivo:** o teste não demonstrou sucesso nem novo 403 na
leitura dos detalhes. Nenhum lead foi importado, e a rotina de produção e o
estado de suspensão no banco não foram alterados por este diagnóstico.

Se o experimento for retomado, primeiro será necessário confirmar a navegação
para uma URL de loja e a presença do botão Sobre. Só então será possível avaliar
o status da requisição e a presença de endereço/CNPJ, sem registrar seus valores.
Interromper diante de CAPTCHA ou bloqueio, sem repetir tentativas.

## Investigação do camofox

O teste corrigido selecionou e salvou o endereço com cliques e teclado nativos.
O registro de eventos confirmou `isTrusted=true`. A seleção da sugestão precisa
apontar explicitamente para o primeiro resultado, pois há vários botões com a
classe `.btn-address--full-size`. Cliques por coordenadas atingiram um placeholder
durante a atualização da lista; o seletor nativo acompanha o elemento.

A abertura da loja continuou sem navegação. Uma captura temporária revelou um
modal HUMAN com “Before we continue...” e “Press & Hold to confirm you are a
human”. O detector antigo procurava somente `#px-captcha`, iframe com `captcha`
na URL e título de acesso negado. Ele não identificou esse modal, e o clique no
cartão foi interceptado. Os testes externos foram encerrados após identificar
o CAPTCHA, sem resolvê-lo. Não houve confirmação de acesso a endereço ou CNPJ.

Esse experimento foi feito no checkout antigo, que ainda usava camofox. Ao
atualizar a referência remota, verificou-se que a `main` já usava SeleniumBase e
Chrome. A correção final foi portada para esse navegador, preservando a mudança
do operador; o experimento camofox não valida o acesso do Chrome ao iFood.

Havia ainda uma falha local independente: o camofox reiniciava a árvore do
navegador perto de 3 GB porque seu limite padrão era 1.500 MB. No PC de 16 GB,
com aproximadamente 9 GB disponíveis durante o diagnóstico, foi aplicado:

```ini
# ~/.config/systemd/user/camofox.service.d/ifood-memoria.conf
[Service]
Environment=BROWSER_RSS_RESTART_THRESHOLD_MB=4096
```

O serviço `camofox.service` foi reiniciado após `systemctl --user daemon-reload`.
O ajuste foi temporário para o experimento: ao confirmar que o coletor atual usa
Chrome, o arquivo foi removido e o serviço recarregado/reiniciado, restaurando o
limite original de 1.500 MB. Nenhuma configuração permanente do camofox foi alterada.

Validação local, sem acessar o iFood: uma página sintética no navegador confirmou
o detector para modal HUMAN, iframe HUMAN e texto do desafio, sem falso bloqueio
na página normal ou no modal oculto. A mesma página confirmou clique em botão
com texto acentuado e digitação por teclado: os 17 eventos registrados tinham
`isTrusted=true`. Os testes automatizados usam somente dados sintéticos.

O estado de suspensão e os leads do banco operacional não foram alterados nesta
investigação. O desafio externo continua sendo uma limitação de acesso, mesmo
com os defeitos locais corrigidos.

## Correção no coletor atual (SeleniumBase/Chrome)

- Foi corrigida a execução de JavaScript nos dois modos do SeleniumBase. Com
  WebDriver desconectado, o modo CDP recebe uma expressão, sem `return` solto,
  que antes produzia `SyntaxError: Illegal return statement`. Com WebDriver
  conectado, conserva o formato exigido por `execute_script`. O driver é
  reconectado quando necessário para enviar eventos nativos e ler a rede.
- O campo de endereço recebe cliques e teclas nativos do Selenium. A primeira
  sugestão é selecionada explicitamente; os botões são identificados pelo texto,
  marcados no DOM e clicados pelo driver. A rolagem usa a tecla End nativa.
- O detector cobre o modal `px-captcha-modal`, títulos de iframe HUMAN/challenge
  e o texto “Press & Hold”. Ele é consultado antes de comandos e durante as
  esperas, inclusive a espera da resposta da loja. Se o desafio aparecer durante
  a rolagem, a lista já descoberta é preservada.
- Foi corrigida uma perda de resposta: `Network.responseReceived` pode chegar
  antes de o corpo estar disponível. Antes, a tentativa falhava e o evento era
  descartado por `get_log`; não havia nova tentativa para aquele requestId. Agora
  os identificadores pendentes são mantidos até o corpo estar disponível, dentro
  do timeout, sem repetir a requisição ao site.
- Os eventos anteriores são descartados antes de navegar, preservando eventos
  da nova loja. A recarga ocorre uma única vez quando UC não expõe a primeira
  resposta. HTTP 403/429 confirmado interrompe a leitura sem recarregar.
- Erro do driver durante detalhes preserva a listagem. Resposta inválida gera
  erro explícito, sem atribuir 403 quando ele não foi confirmado.

Os testes externos no iFood não foram retomados após o CAPTCHA. Sucesso real na
obtenção de endereço/CNPJ com o coletor corrigido permanece sem confirmação.

A bateria atual `uv run pytest -q` passou com 134 testes. No Chrome/UC, uma página
sintética também validou os cinco cenários do detector e 19 eventos nativos
(`isTrusted=true`), incluindo clique em texto acentuado e digitação. Essa validação
local também capturou uma resposta `merchant-info/graphql` sintética e extraiu
endereço e CNPJ pelo fluxo real de navegação, logs e leitura do corpo. Essas
validações não são evidência de liberação pelo iFood.
