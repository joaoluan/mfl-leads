# Spec — Esteira de leads MyFoodLink

Parte A = decisões tomadas com o operador em 24/11/2026 (prevalecem).
Parte B = especificação original, mantida como base. Onde a Parte A contradiz a B, vale a A.

---

## Parte A — Decisões v2

### Infra
- Tudo roda no **PC desktop** (x86, IP residencial, Tailscale). Sem VPS: IP de datacenter (EUA) queima Maps e Instagram.
- Orange Pi One (armv7, 1 GB) não roda Playwright, Camoufox, DuckDB nem Polars. Papel dele: cópia semanal do backup. Ideia futura: exit node do Tailscale para uma VPS sair pelo IP de casa.
- Backup diário de `db/leads.db` e `data/parquet/` no SSD `backup-ssd` (sdd1, ext4) e cópia semanal no Orange Pi.
- Fuso de tudo: America/Sao_Paulo.
- Custo previsto: zero (sem proxy, IP residencial).

### WhatsApp
- Chip: o **WhatsApp pessoal** (antigo, número comercial 5551985711759, o do site e do Instagram do MFL). O operador aceitou o risco.
- Envio **manual pelo WhatsApp Web** no PC. Deep link: `https://web.whatsapp.com/send?phone=<e164 sem +>&text=<texto codificado>`.
- **Evolution API** em Docker no PC, pareada no pessoal, **só leitura** (revoga "não integre Baileys" da seção 4 só para leitura; nunca envia).
  - Mensagem `fromMe` para um lead vira `touch` automático. O botão "Enviado" fica como reserva (Evolution caída, DM do Instagram).
  - Mensagem recebida de um lead vira `reply`.
  - **Só grava mensagens de números que já são lead.** O resto é descartado sem persistir. Sem sincronizar histórico antigo.
  - UI avisa "Evolution desconectada".
- Classificação de resposta por palavra-chave, com revisão de um clique. "SAIR" vira opt_out automático.
- Bloqueio estimado = mensagem parada em 1 tique por mais de 24h + opt-outs. Alerta se > 3% por 3 dias.
- Validador público de WhatsApp **removido**. Validação = telefone vindo de Maps ou Instagram (inclusive fixo com link de WhatsApp), celular, E.164, e botão "sem WhatsApp" na UI.

### Volume e cadência
- **30 mensagens por dia no total**, follow-ups primeiro e o resto para leads novos. Rampa: semana 1 = 20, semana 2+ = 30, sempre com bloqueio < 5%. Ao atingir o teto a UI avisa.
- Sem teto de trials (o operador aguenta mais de 15 por mês). Foco em Start e Pro.
- Janela de envio: **segunda-feira o dia todo** (9h–18h; restaurante fechado, dono com tempo) e de terça a sexta das 9h às 11h e das 14h30 às 17h30. Fora da janela a UI avisa e não bloqueia. D3 e D7 podem cair na segunda.
- Trial e cliente são marcados à mão na ficha.

### Fontes
- **Telefone** vem de Maps e Instagram (bio, `wa.me`). Telefone só do CNPJ (costuma ser o do contador) leva a `enriquecimento`.
- **CNPJ**: filtro (ativa, CNAE, unidade única, porte) e sinal (abertura). Atualização mensal.
- **Maps**: binário `gosom/google-maps-scraper` com versão fixa e SHA conferido. Só as avaliações que vêm por padrão. Cada bairro é raspado de novo a cada 60 dias.
- **Instagram**: via o **camofox-browser já instalado** (`127.0.0.1:9377`, conta secundária), não a biblioteca `camoufox`. Até ~30 perfis por dia. O @ vem só do Maps ou do site; sem busca dentro do Instagram. Não fica restrito a score >= 55.
- **iFood** (revoga "não raspe iFood" da seção 4): sinal "vende no iFood" (texto próprio: pedido direto sem comissão) e também fonte de leads novos. Casamento por endereço.
- **Grupo de donos: removido em 24/11** por decisão do operador (não importa participantes, sem texto nem peso no score). Os 12 leads já contatados ficaram, sem a marca; os cruzados com CNPJ/Maps voltaram a essas fontes; os demais foram apagados. Opt-outs continuam bloqueados.

### Recorte
- Municípios: Porto Alegre, Canoas, Gravataí, Viamão, São Leopoldo, Novo Hamburgo, Alvorada, Cachoeirinha, Sapucaia do Sul, Esteio, Guaíba, Montenegro, Campo Bom, Estância Velha, Ivoti, Dois Irmãos, Sapiranga, Portão.
- CNAE entra: 5611201, 5611203, 5611204, 5611205, 5612100, 5620104, 1091102, 4721102, 4721104.
- CNAE fora: 5620101, 5620102, 5620103, 1091101, 4721103.
- Correção: padaria/confeitaria com produção própria é **1091102**, não 5611201.
- Quem usa concorrente (Goomer, Saipos, Anota AI, LeadsFood etc.) **não é excluído**: vira alvo de troca, com texto próprio e score menor. Rede (4+ filiais no mesmo CNPJ) continua excluída. Franquia por nome **entra** desde 24/11/2026 (decisão do operador) e só perde pontos (sinal `franquia`).
- Exclusões da fila: clientes atuais (Espaço Grill, Fornello Esteio, as 2 pizzarias, a doceria), tenants de teste (Fat Bull, Donilla, Brasa Burger), opt-outs (hash do telefone, bloqueio permanente), fechados permanente ou temporariamente no Maps. Quem já conversou com o operador no pessoal vai para `revisao`.

### Score (adições)
- `raio` = distância até Novo Hamburgo (base) ou até um cliente atual.
- `aberto_menos_12m`: +15 (data de abertura no CNPJ).
- `vende_ifood`: sinal positivo.
- `usa_concorrente`: negativo (alvo de troca).

### Textos
- 8 grupos com 3 variantes cada: pizzaria, hamburgueria, churrascaria, japonês, restaurante/marmita, lanchonete/café, padaria/doceria, bar. A categoria vem do Maps.
- Mais os textos de troca de concorrente e iFood.
- O inbox mostra a resposta sugerida para "quanto custa" e "já tenho".

### UI e LGPD
- Ficha mostra a fonte e a data da coleta ("de onde tirou meu número?").
- Painel: funil por fonte e por variante de texto.

### Modelo de dados (adições)
- `entity.categoria` (a Parte B usa categoria na UI e nos textos, mas faltava a coluna).

### UI (fase 3)
- Config em TOML (`cfg/tetos.toml`, `cfg/icp.toml`), lido com `tomllib` da biblioteca padrão; a Parte B fala em YAML, que exigiria dependência nova.
- Teto conta leads diferentes abordados no dia (follow-up + novo). A fila some quando bate o teto e o botão "Enviado" recusa (409).
- Fila: follow-ups vencidos (D3 = 3 dias após D0, D7 = 4 dias após D3) primeiro, depois novos por score. "Pular" esconde até amanhã (tabela `queue`, kind `pular`).
- Transições por tempo rodam a cada carga da fila: d7 + 3 dias → frio; objecao + 7 dias → frio; frio + 60 dias → na_fila.
- Classificação no inbox: interesse/preco → respondeu, ja_tenho → objecao, nao → frio, opt_out → opt-out permanente.
- Atalhos: Enter abre o WhatsApp, S pula, F abre a ficha. A variante aberta é guardada e o webhook liga o envio a ela (funil por variante).
- Clientes atuais: `mfl marcar <telefone> cliente` ou botão na ficha; cliente nunca entra na fila.
- "Quem já conversou no pessoal" não é detectável sem sincronizar histórico; ao abrir o WhatsApp Web a conversa anterior aparece e o operador decide.
- A UI escuta só em 127.0.0.1:8000 (sem login). Serviço `ops/mfl-ui.service`.

### CNPJ (fase 4)
- Baixa só Estabelecimentos, Empresas, Cnaes e Municipios pelo WebDAV público do compartilhamento. Sócios e Simples ficam de fora (LGPD; nada usa).
- Razão social não entra no Parquet: em MEI ela traz nome e CPF.
- Os CSVs são convertidos para UTF-8 na extração: o leitor latin-1 do DuckDB recusa bytes de controle presentes nos arquivos da Receita.
- Recorte (municípios, CNAEs, limite de rede) fica em `cfg/icp.toml` [recorte]; franquias em `cfg/franquias.txt` (palavra inteira no nome fantasia; só alimenta o sinal `franquia` do score).
- "Rede" = mesmo CNPJ básico com 4+ estabelecimentos ativos **no RS** (só temos RS).
- Lead do CNPJ entra como `enriquecimento`, telefone da Receita em `tel2` (para cruzar fontes), categoria = descrição do CNAE.
- Primeira carga (2026-11): 1.777.043 estabelecimentos ativos no RS, 39.338 no recorte.

### Maps e resolução (fase 5)
- Binário gosom/google-maps-scraper v1.20.0 em `bin/` (fora do git); SHA256 em `bin/SHA256SUMS`, conferido a cada execução. Telemetria desligada.
- Um bairro por execução (`make maps BAIRRO=<chave>`); bairros e bbox em `cfg/bairros.toml`, gerado uma vez do OpenStreetMap (`mfl bairros-gerar`). Célula de 0,5 km, maior em área grande (máx. ~60 células). `mfl maps-fila` raspa os bairros nunca raspados ou com mais de 60 dias, POA e NH primeiro.
- Consultas em `cfg/maps_consultas.txt`. A v1.20.0 às vezes não sai do processo após terminar: o wrapper encerra 15 s depois de "scrapemate exited"; teto de 1800 s.
- Ingestão idempotente por place_id. Descarta fechado e fora dos municípios do recorte (franquia entra e só perde pontos). Telefone celular válido → `novo` (apto para a fila); fixo ou sem telefone → `enriquecimento`. E-mail só se o domínio tem MX.
- Resolução: regra da spec (0,35 CEP5 + 0,35 telefone + 0,30 nome) com ajustes: telefone igual vincula sozinho, exceto telefone repetido entre CNPJs (contador); CEP completo + nome ≥ 0,85 vincula; palavras genéricas (pizzaria, restaurante…) fora da comparação. 0,55–0,85 vai para a tela Revisão.

### Score (fase 6)
- `src/mfl/score.py`, pesos em `cfg/icp.toml` (editável em /config). Recalcula tudo em ~2 s: `make score`, e sozinho depois de `maps` e `resolver`. Sinais gravados em `entity.sinais` (etiquetas na fila).
- Já calculados: mesma_categoria_de_cliente (categorias em `[score]` + clientes marcados), raio (município em `municipios_perto`: NH, vizinhas e cidades de clientes), aberto_menos_12m e unidade_unica (CNPJ), sem_site (sem site ou só rede social), wa_me_na_bio (link wa.me/WhatsApp no Maps), usa_concorrente (-10, link de LeadsFood, Cardápio Web, Goomer etc.), site_com_pedido_proprio (pedido online no domínio do próprio site), reclamacao_demora (avaliações do Maps), aceita_encomenda (confeitaria/doces/encomenda), franquia.
- Instagram (wa.me na bio, atividade) na fase 7; vende_ifood na fase 8.
- Corte (40) vale só para leads novos; follow-ups seguem. Quem usa concorrente recebe `cfg/mensagens/concorrente.md`.
- shortcut: raio por município, não por distância (CNPJ não tem coordenada); trocar por distância quando houver lat/lon de clientes.

### Instagram (fase 7)
- `mfl ig-handles`: @ dos links do Maps (site, pedido online); se não houver, da página inicial do site da casa, só se o @ lembrar o nome da casa e o site não for de plataforma (rodapé de agência/Partiu Pedido).
- `mfl ig --limite N` (`make ig`): perfis pelo camofox (`127.0.0.1:9377`) na sessão `baixar-insta` (conta secundária já logada; `MFL_CAMOFOX_USER` troca). Só páginas de perfil, sem API. Teto de 30 por dia, pausa de 4 a 9 s, uma aba por vez, fecha a aba e mantém a sessão.
- Grava o mínimo (LGPD): bio, links externos, seguidores, posts, data do último post (tirada do shortcode, sem abrir posts), telefone, e-mail, data de coleta. Sem HTML bruto. Revisita após 60 dias.
- Telefone: wa.me (inclusive `wa.me/c/`) e api.whatsapp.com, depois celular escrito na bio; se não houver, abre até 2 links externos (Linktree etc.) com GET simples. Número de link de WhatsApp é apto mesmo fixo (WhatsApp Business), também no Maps.
- Login/verificação pedido = checkpoint: grava `estado.ig_checkpoint`, para o lote, faixa vermelha na UI. Resolver com `baixar-insta --login` e `mfl ig --retomar`.
- Sinais: wa_me_na_bio, ig_ativo_30d (post nos últimos 30 dias), ig_inativo_6m (último post há mais de 180 dias ou nenhum), usa_concorrente (link de plataforma).
- shortcut: telefone que só aparece no botão "Contato" (exige clique) e links encurtados (wa.link, contate.me) não são lidos.

### iFood (fase 8)
- Diagnóstico e validações do navegador: [investigação de 24/11/2026](IFOOD_DIAGNOSTICO.md). O experimento antigo usou camofox; a correção final preserva SeleniumBase/Chrome.
- Decisão atualizada pelo operador: o iFood também é fonte de leads novos e roda junto com o Maps. O timer existente das 00h00 (`mfl maps-noturno`) coleta as duas fontes por bairro. Continuam disponíveis `mfl ifood "Rua, número, cidade - RS" --limite 30` (1–1000) e o formulário manual em Coleta. O máximo vem de `ifood.LIMITE_MAX`, compartilhado por coletor, CLI, validação HTTP e campo da tela.
- Decisão atualizada pelo operador (reverte a regra anterior de não resolver CAPTCHA nem ler API): usa o SeleniumBase em modo UC (Chrome), sessão própria sem conta, para passar pelo Cloudflare — clica no captcha quando aparece. Seleciona endereço pelas telas públicas, lê os cartões e, em cada loja, lê CNPJ/endereço da resposta `merchant-info/graphql` que a própria página recebe (não do DOM). O clique no captcha usa PyAutoGUI e precisa de tela: headed por padrão, Xvfb no timer; `MFL_IFOOD_HEADLESS=1` força headless. Sem cardápio, avaliações ou dados de consumidores.
- Seleção de endereço e rolagem usam cliques e teclas nativos do Selenium. O desafio HUMAN “Press & Hold” é detectado antes de agir e interrompe a etapa. Se surgir durante a listagem, preserva as lojas já lidas. A captura de `merchant-info` mantém o requestId enquanto o corpo ainda não terminou de chegar, sem repetir a requisição. Só recarrega uma vez se a navegação UC não expôs a resposta; HTTP 403/429 confirmado encerra a leitura sem recarregar.
- Guarda só UUID da loja, nome, categoria, município, bairro/endereço/CEP/CNPJ quando disponíveis, URL, data e hash. CNPJ fica sem pontuação, com dígitos verificadores conferidos. Não guarda endereço de entrega, HTML, cardápio, avaliações ou dados de consumidores.
- UUID evita duplicatas entre pontos de entrega. Novas lojas têm prioridade; incompletas só usam vagas restantes quando detalhes estão liberados, com pelo menos 7 dias desde `detalhes_em`. Franquias são filtradas antes de ocupar as vagas. Loja já importada é completada por upsert sem apagar valores conhecidos numa leitura parcial. Atualizar só metadados/data não conta em `atualizados`.
- 403/verificação não resolvida, merchant-info ausente ou tempo esgotado na leitura de detalhes preserva a lista e grava `estado.ifood_detalhes_bloqueados`. A suspensão vale para todos os processos/bairros e sobrevive a reinícios: segue descobrindo lojas novas, sem abrir páginas de loja nem gastar vagas com registros antigos. Não retoma sozinha. Após resolver o acesso, o operador usa `mfl ifood "endereço" --retomar-detalhes`. A Coleta mostra o motivo da suspensão.
- CNPJ exato vincula à Receita mesmo com nome fantasia diferente. Descoberta provisória sem conversa é absorvida pelo dono do CNPJ, preservando fontes. Se já houve conversa, ou os CNPJs conhecidos divergem, não funde nem sobrescreve CNPJ: encaminha para Revisão quando há outro lead identificado e registra o conflito no log.
- Só cidades do recorte e sem franquias. Telefone continua vindo do Maps/Instagram: loja nova fica em `enriquecimento`. Endereço/CEP e nome usam a resolução existente; sem endereço suficiente, nome parecido na mesma cidade vai apenas para Revisão, inclusive quando o Maps chega depois. Não altera telefone nem promove o status de um lead existente.
- Ponto de entrega automático = um endereço comercial com número já coletado por Maps/CNPJ no mesmo bairro/cidade, priorizando Maps. Sem ponto válido, avisa no log e mantém o bairro pendente, sem inventar endereço. Cada fonte controla sua visita: `ifood_bairro:<chave>` só é marcado após sucesso, volta em 60 dias e entra na fila mesmo quando o Maps está em dia. `ifood_tentativa:<chave>` ordena os bairros pendentes para que os sem ponto não prendam a fila nas noites seguintes.
- Depois do iFood, busca no Maps lojas da cidade ainda em enriquecimento e sem place_id, pelo nome/cidade: lotes de até 10 e teto total de 30 nomes por rodada noturna, inclusive reservando orçamento se o processo falhar. Reutiliza o binário conferido por SHA, sem grade, depth 1 e teto de 5 min por lote. Tempo esgotado salva o parcial, registra aviso e agenda o restante para amanhã, sem marcar o job como erro. Outras falhas continuam sendo erro. Tentativas em `queue`, kind `maps_ifood`: reserva antes da rede para amanhã; busca completa sem vínculo volta em 7 dias. Alvos vencidos entram na rodada mesmo quando as duas fontes estão em dia no bairro. Não repete os mesmos alvos em cada bairro da noite.
- Link de loja do iFood no site/pedido online do Maps, com domínio e UUID conferidos, comprova identidade e permite completar o mesmo lead sem depender do endereço bloqueado. Vários UUIDs apontando para entidades diferentes não vinculam. Se o Maps já conhecia o place_id, só absorve o lead provisório do iFood (enriquecimento, sem telefone e sem conversa), preservando o lead conhecido. Nome sozinho continua na Revisão.
- O site pode bloquear detalhes mesmo mostrando cartões: importa a lista, suspende os detalhes no banco e avisa na Coleta. Verificação ou falha antes de obter a lista ainda interrompe o job com erro; falha de detalhes depois da lista preserva as lojas descobertas.
- O sinal `vende_ifood` (+10) sai também da fonte `ifood`. Continuam valendo link `ifood.com.br` no Maps/Instagram ou "iFood" nas avaliações do Maps/bio, sem somar o sinal duas vezes.
- Quem vende no iFood recebe `cfg/mensagens/ifood.md` (pedido direto sem comissão). Ordem do texto D0: concorrente > iFood > categoria.

### Operação (fase 9)
- Timers systemd --user (`ops/mfl-*.timer`, `Persistent=true`: o que perdeu com o PC desligado roda ao ligar). Serviços `oneshot` com `Nice=10` e `IOSchedulingClass=idle`:
  - `mfl-maps` 00:00 (+ até 10 min, depois do CNPJ): `mfl maps-noturno`, Maps + iFood. Até 20 bairros, sem iniciar etapa nova depois das 04:00. Em cada bairro: Maps geral, iFood e busca das descobertas no Maps. Cada fonte roda só se estiver pendente. `-depth 3` com as 11 consultas (medido no Moinhos em 24/11/2026: 87 → 119 lugares; cortar para 4 consultas caiu para 59). Revisita do Maps: 45 dias se rendeu ≥ 10 lugares, 120 se não. Dois bairros seguidos vazios suspendem só o Google naquela rodada, com erro; o iFood segue pelos endereços já coletados. Falha da lista suspende só o iFood naquela rodada. Bloqueio dos detalhes persiste até retomada explícita; a lista segue. Tempo esgotado do Maps geral (60 min) ingere o parcial e deixa o bairro pendente. Falhas não marcam a fonte como feita.
  - `mfl-cnpj` 23:00 (no dia da carga mensal leva ~50 min): `mfl cnpj-mensal`, baixa e processa o mês quando a Receita publicar; uma vez por mês (`estado.cnpj_mes`).
  - `mfl-diario` 05:00 (+ até 10 min): cadência, score, backup.
  - `mfl-ig` 04:00 (+ até 20 min, ~30 min com pausas de 15–45 s e 3–5 min a cada 8 perfis): `mfl ig-diario` (@ novos e até 30 perfis).
- Cada job tem trava (`flock -n` em `data/travas/`) e grava ok/erro em `estado.job:<nome>`: o Painel mostra as rotinas e uma faixa vermelha avisa quando alguma falhou.
- Backup diário: banco (API de backup do SQLite, seguro com o webhook gravando) + `cfg/` em `data/backup/diario` (7 dias), espelhado com o Parquet no SSD `backup-ssd` montado em `/mnt/backup-ssd` (30 dias). Domingo: cópia para o Orange Pi (`orangepi:backup/mfl-leads`, 60 dias). SSD desmontado ou Pi fora do ar não derrubam o backup local. `.env` fica fora (segredos).
- Log JSONL rotaciona aos 20 MB (`logs/<job>.jsonl.1`).
- Precisa de sudo do operador (uma vez): montar o SSD (fstab com `nofail`) e `loginctl enable-linger` para os serviços rodarem sem login.

### Fases (parar em cada uma, um PR por fase)
1. Esqueleto, schema, seed por CSV, export.
2. Evolution: envios e respostas, participantes do grupo, palavra-chave, opt-out.
3. UI com as 5 telas (a partir daqui dá para prospectar com os contatos do grupo).
4. ETL do CNPJ e recorte de ICP.
5. Maps, resolução de entidade, telefone.
6. Score.
7. Instagram.
8. iFood.
9. Operação: timers, backup, logs.

Dependências entram na fase que precisa delas. `pymysql` saiu (nada usa MySQL).

---

## Parte B — Especificação original

### 0. Papel

Você é engenheiro de dados e backend sênior. Construa um sistema local de geração de leads
para prospecção B2B, em fases, com código simples e verificável. Pare ao fim de cada fase e
espere revisão antes de continuar. Não invente escopo.

### 1. Contexto de negócio

Produto: MyFoodLink (www.myfoodlink.com.br) — sistema para restaurantes com atendimento e
reservas no WhatsApp, cardápio digital, fidelidade, delivery com pagamento online (plano Pro)
e PDV com salão, comanda, cozinha, estoque e financeiro (plano Gestor, com servidor local
Windows, em implantação assistida).

Planos: Start R$149, Pro R$299, Gestor R$499. Sem contrato mínimo, sem taxa de implantação.
Fundador tem 15 anos de gestão de restaurantes em Porto Alegre. WhatsApp comercial:
+55 51 98571-1759.

Oferta de entrada: 30 dias grátis. O CTA é trial, não demonstração.
Empurrar Start e Pro. Gestor é upsell e exige hardware no cliente.

Objetivo do sistema: produzir, toda semana, uma fila de 40 a 60 donos de estabelecimentos de
alimentação em Porto Alegre e região metropolitana, com telefone validado, que ainda não usam
sistema concorrente, para abordagem manual de 30 por dia.

### 2. Operador (restrições reais)

- Uma pessoa, sozinha. Sem time.
- Capacidade: 30 abordagens/dia, 20 a 40 por semana com follow-up.
- Teto de 3 trials por mês (cada trial consome configuração manual).
- Orçamento total do projeto: R$ 300/mês.
- Já tem 4 clientes ativos (2 pizzarias, 1 churrascaria, 1 doceria), vindos de um grupo de
  WhatsApp de donos de restaurantes. O operador está nesse grupo e tem chip dedicado.

Consequência de projeto: PRECISÃO acima de volume. O sistema nunca deve priorizar quantidade
sobre qualidade do lead.

### 3. Stack obrigatória

- Python 3.12, ambiente com `uv`. Uma linguagem só.
- Linux nativo ou WSL2. Roda na máquina do operador, IP residencial.
- SQLite em WAL como banco OPERACIONAL (fila, estado, dedupe, toques, respostas).
- DuckDB em modo read-only + Parquet como camada ANALÍTICA (gold). Nunca escritor concorrente.
- `bin/google-maps-scraper` — binário Go open source (github.com/gosom/google-maps-scraper),
  pinado por versão, chamado via subprocess com timeout. Nunca reimplementar.
- Camoufox (`camoufox[geoip]`) para Instagram, isolado em módulo próprio.
- UI local em Flask, `localhost:8000`, sem build step, sem framework JS.
- Dependências: duckdb, polars, pymysql, camoufox[geoip], playwright, seleniumbase (iFood, modo UC), typer, pydantic,
  tenacity, structlog, phonenumbers, rapidfuzz, unidecode, python-dotenv, flask.
- Sem Docker, sem Celery/Redis, sem Postgres, sem autenticação, sem deploy.

### 4. NÃO faça

- Não envie mensagem automaticamente. O envio é manual, via deep link.
- Não integre Cloud API oficial, Baileys ou whatsapp-web.js.
- Não use Apify, Scrap.io, Outscraper nem qualquer SaaS pago.
- Não raspe iFood, SERP do Google ou marketplaces.
- Não baixe o dump de CNPJ do Brasil inteiro: só UF=RS e só municípios da região metropolitana.
- Não rode Instagram em massa: só score >= 55 e só anel 1 ou 2.
- Não crie dashboard, Kanban, multiusuário, autenticação ou API pública.
- Não invente CNAE, campo ou endpoint fora desta especificação.

### 5. Fonte de dados 1 — CNPJ (dados abertos)

Origem: https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9
Layout: https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf
Formato: CSV, separador `;`, aspas duplas, encoding latin-1, sem cabeçalho.
Tabelas usadas: EMPRESAS, ESTABELECIMENTOS, CNAE, MUNICIPIOS, SOCIOS.

`ESTABELECIMENTOS` traz: cnpj_basico, cnpj_ordem, cnpj_dv, matriz_filial, nome_fantasia,
situacao_cadastral, data_situacao, motivo, cidade_exterior, pais, data_inicio_atividade,
cnae_fiscal_principal, cnae_secundaria, tipo_logradouro, logradouro, numero, complemento,
bairro, cep, uf, municipio, ddd1, telefone1, ddd2, telefone2, ddd_fax, fax,
correio_eletronico, situacao_especial, data_situacao_especial.

#### 5.1 ETL

`src/mfl/cnpj_etl.py` converte para Parquet já filtrado, uma partição por UF:

1. Lê com `delim=';'`, `quote='"'`, `encoding='latin-1'`, `all_varchar=true`, colunas nomeadas.
2. Filtra `situacao_cadastral = '02'` (ativa) e `uf = 'RS'`.
3. Escreve `data/parquet/estab/uf=RS/*.parquet`.
4. Idem para EMPRESAS (só porte, capital_social, natureza_juridica), CNAE, MUNICIPIOS, SOCIOS.
5. Valida a contagem de colunas de cada arquivo antes do COPY; aborta com erro claro se o
   layout mudar.

#### 5.2 Recorte de ICP

Municípios alvo: Porto Alegre, Canoas, Gravataí, Viamão, São Leopoldo, Novo Hamburgo,
Alvorada, Cachoeirinha, Sapucaia do Sul, Esteio, Guaíba, Montenegro.

CNAE núcleo: 5611201, 5611203, 5620104
CNAE incluir (peso menor): 4721102, 4721104, 5611204
CNAE fora: 5620102, 5620103, 4721103, 1091101, 5611205

Nota de domínio: padaria e doceria com produção própria são classificadas em 5611-2/01, não
em 47.21-1. Não filtre só por 47.21-1.

#### 5.3 Filtros de exclusão (obrigatórios, em SQL)

- situacao != ativa (já no ETL)
- logradouro vazio ou nulo
- franquia/rede: mesmo cnpj_basico com 4+ filiais, ou nome_fantasia contendo termo da lista
  `cfg/franquias.txt`
- já tem sistema: nome_fantasia, site ou Instagram contendo goomer, saipos, consumer, linx,
  cardapio digital

### 6. Fonte 2 — Google Maps

`src/mfl/maps.py` chama o binário:

    bin/google-maps-scraper -input <q> -results <out> -grid-bbox <bbox> -grid-cell 0.5 \
      -zoom 16 -depth 1 -c 4 -email -lang pt -exit-on-inactivity 3m

- Uma execução por bairro de `cfg/bairros.yml`, com timeout de 1800s.
- Ingestão com `INSERT OR IGNORE` em `source_record`, `source_key = place_id`.
- Nunca combine `-fast-mode` com `-grid-bbox`.
- `-grid-strict` ativo.
- Concorrência máxima 4.

### 7. Resolução de entidade

`src/mfl/resolve.py`

1. Normaliza nome: unidecode, lowercase, remove ltda|me|eireli|sa|mei, colapsa espaço.
2. Bloqueia pares por `substr(cep,1,5)` OU últimos 8 dígitos do telefone.
3. Score: 0.35 CEP5 igual + 0.35 telefone8 igual + 0.30 similaridade rapidfuzz do nome.
4. >= 0.85 vincula automático. Entre 0.55 e 0.85 vai para `revisao`. Abaixo, descarta.
5. Grava `match_score` em `source_record`.

### 8. Normalização e validação

- Telefone: `phonenumbers`, região BR, saída E.164 (`+5551...`). Marca `is_mobile`.
- Sem telefone válido → `status = enriquecimento`, fora da fila.
- E-mail: regex + checagem MX antes de gravar como válido.
- `src/mfl/validate.py` consulta validador público de WhatsApp, com cache em `validacao`
  (telefone, resultado, data) e intervalo de 1,5s entre chamadas.

### 9. Instagram (fase final, opcional)

`src/mfl/ig.py` com `AsyncCamoufox(headless=True, os=["windows"], humanize=True, geoip=True,
proxy=<env>, persistent_context=True, user_data_dir="sess/ig")`.

- Lê só `status IN ('respondeu','na_fila')` e score >= 55.
- Extrai bio, e-mail por regex, telefone por regex, link externo e seguidores.
- Segue o link externo no mesmo browser para procurar e-mail.
- Detecta challenge/login por seletor; grava `Checkpoint` e para o lote.
- Semáforo 2, delay 4 a 9s com jitter, teto 25 por execução.
- Salva HTML bruto em `data/raw/ig/<data>/<hash>.html.gz`.

### 10. Modelo de dados

Ver `db/schema.sql` (fonte de verdade do schema).

`entity_id` é UUID4. Toda linha de toda fonte aponta para uma entity.

### 11. Score

`src/mfl/score.py` lê pesos de `cfg/icp.yml`:

    mesma_categoria_de_cliente: 30
    raio_1500m: 20
    wa_me_na_bio: 20
    reclamacao_demora: 15
    sem_site: 10
    aceita_encomenda: 10
    ig_ativo_30d: 8
    unidade_unica: 8
    franquia: -25
    site_com_pedido_proprio: -30
    ig_inativo_6m: -10
    corte: 40

Corte: score < 40 não entra na fila. Fila sempre ordenada por score desc.

### 12. Máquina de estados

    novo → qualificado → na_fila → enviado_d0
    enviado_d0 → respondeu | d3
    d3 → d7 (sem resposta) | respondeu
    d7 → frio (sem resposta)
    respondeu → trial | objecao | opt_out
    objecao → frio
    trial → cliente | frio
    frio → na_fila após 60 dias
    opt_out → terminal, nunca mais contatado

Toda transição grava `atualizado_em`. `opt_out` é irreversível sem ação manual.

### 13. Cadência

D0: mensagem com o sinal, pergunta fechada, oferta de 30 dias grátis.
D3: dado curto, sem apresentação.
D7: oferta de conversa de 15 min com horário específico.
D10 sem resposta: `frio`, volta em 60 dias.

Templates em `cfg/mensagens/{pizzaria,doceria,lanchonete,marmita}.md`, 3 variantes cada,
placeholders `{bairro}` e `{sinal}`. A primeira linha é sempre personalizada.

Resposta "quanto custa" → faixa de preço + horário proposto na mesma mensagem.
Resposta "já tenho" → perguntar qual sistema e o que falta.

### 14. UI (Flask, localhost)

Cinco telas, sem login, sem build:

- `/` Fila: 30 cartões do dia ordenados por score. Nome, categoria, bairro, chips de sinal,
  score, telefone. Botões: Abrir WhatsApp (deep link `wa.me`), Instagram (`ig.me/m/`), Ficha,
  Enviado, Pular. Barra de progresso. Atalhos Enter/S/F.
- `/lead/<id>` Ficha: todos os dados, link da fonte, texto sugerido por categoria com botão
  copiar, linha do tempo, botões de status e opt-out.
- `/respostas` Inbox: só quem respondeu, classificador de um clique.
- `/painel` Métricas: enviados hoje/semana, taxa de resposta, taxa de bloqueio, demos, trials,
  tabela por categoria, tabela por bairro, alerta se bloqueio > 3% por 3 dias.
- `/config` Editor simples de `icp.yml`, templates e tetos.

Estilo: flat, sem sombra, duas espessuras de fonte, sentence case, sem emoji, mínimo 11px.

### 15. Operação

- `Makefile`: etl, maps BAIRRO=, resolve, validate, score, export, ig, seed.
- `seed` importa CSV de leads do grupo de WhatsApp (colunas: nome, telefone, categoria, bairro).
- `systemd timers` + `flock -n` por job, `Nice=10`, `IOSchedulingClass=idle`.
- Log JSONL em `logs/<job>.jsonl`, com job_id, source, url, captured_at.
- `.env` com `chmod 600`, contendo proxy e caminhos. `.gitignore` cobre data/, db/*.db, .env.
- Backup diário de `db/leads.db` e `data/parquet/` para segundo disco.

### 16. Limites operacionais

Teto de envio por dia, controlado na UI: semana 1 = 10, semana 2 = 20, semana 3 = 30,
semana 4+ = 40 a 50, sempre condicionado a bloqueio < 5%. A UI bloqueia o botão Enviado ao
atingir o teto e avisa.

Nunca repetir o mesmo texto em dois envios consecutivos da mesma categoria.

### 17. LGPD

- Guardar sempre `url`, `captured_at` e hash da fonte.
- Só dado necessário ao contato comercial. Nada de CPF de sócio.
- Opt-out em toda mensagem ("responda SAIR").
- Instagram: dado pessoal, manter mínimo e registrar data de coleta.

### 18. Ordem de construção e critérios de aceite (original; a ordem vale a da Parte A)

Fase 1 — esqueleto, schema, seed. Aceite: `make seed` importa CSV e cria entities; `make export` gera CSV.

Fase 2 — ETL CNPJ. Aceite: rodando em 1 arquivo de amostra, gera Parquet com contagem conferida e aborta com mensagem clara se o layout mudar.

Fase 3 — recorte ICP e score. Aceite: query de ICP devolve só ativa, só município alvo, só CNAE permitido, sem franquia; score preenche `sinais` e corta abaixo de 40.

Fase 4 — Maps. Aceite: `make maps BAIRRO=moinhos-de-vento` produz CSV, ingere com place_id único, sem duplicata em duas execuções.

Fase 5 — resolução, telefone, validação. Aceite: telefone sempre em E.164; nenhum lead entra na fila sem validação positiva.

Fase 6 — UI. Aceite: as 5 telas funcionam, deep link abre com texto codificado, teto diário bloqueia.

Fase 7 — Instagram. Aceite: processa 5 perfis, grava bio e link, para sozinho em checkpoint.

### 19. Regras de qualidade de código

- Tipagem em todas as funções públicas. Pydantic no contrato de dados.
- Nenhuma credencial em código. Nenhum `print`, só structlog.
- Toda escrita em SQLite com `PRAGMA busy_timeout=5000` e em lote de 100.
- Toda função de rede com retry exponencial (tenacity) e timeout.
- Docstring curta em português, explicando o porquê, não o quê.
- Se algo da spec for ambíguo, pergunte antes de implementar.

### 20. Instalação de dependências externas

#### gosom/google-maps-scraper
1. Baixe a release (asset linux-amd64), salve em `bin/google-maps-scraper`, `chmod +x`.
2. Grave o SHA256 em `bin/SHA256SUMS` e valide antes de cada execução.
3. Instale o runtime do browser uma vez: `PLAYWRIGHT_INSTALL_ONLY=1 ./bin/google-maps-scraper`.
4. Versão usada: v1.20.0. Não rode `latest` sem registrar o SHA.

#### Camoufox (substituído pelo camofox-browser já instalado; ver Parte A)

#### Verificação antes da fase do Maps
`bin/google-maps-scraper -h` deve imprimir o help. Se falhar, pare e reporte.
