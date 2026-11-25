# Mensagens do MyFoodLink — catálogo v2 (reescrita de tom e gancho)

> Substitui o catálogo gerado em 2026-11-25. Mesma estrutura, mesmos arquivos, mesmos IDs de variante. Mudou o texto das mensagens e as regras de escrita.
> O sistema **não envia nada**: ele sugere o texto e monta o link do WhatsApp Web; quem envia é o João.

---

## 0. Instruções para a IA que vai alterar o código

**Tarefa:** atualizar os textos em `cfg/mensagens/*.md` com os blocos `text` deste arquivo, sem mexer na lógica de escolha.

1. Cada bloco de código `text` vira uma variante do arquivo indicado no título da seção. A ordem das variantes define o índice (`<arquivo>:0`, `:1`, `:2`). Variantes separadas por `---`, como já é hoje.
2. Não renomear arquivos, não mudar a quantidade de variantes por arquivo e não mudar `arquivo_d0` em `src/mfl/mensagens.py`.
3. Manter os campos exatamente como estão: `{nome}`, `{bairro}`, `{sinal}`, `{horario}`. A linha `{sinal}` continua onde está (hoje some, por ser sempre vazia).
4. Toda mensagem de prospecção (D0, concorrente, ifood, D3, D7) mantém a expressão literal `responde SAIR` (LGPD). As respostas prontas (`interesse`, `preco`, `ja_tenho`) não levam.
5. Nenhuma mensagem de D0 leva link, preço ou oferta de teste grátis. O link só aparece em `interesse`, depois que o lead respondeu.
6. Rodar os testes existentes depois de trocar os textos. Se algum teste compara texto fixo, atualizar o teste para o novo texto.
7. Sem emoji, sem negrito/markdown dentro das mensagens (WhatsApp mostra asteriscos literais), sem travessão longo. Tratamento por `tu`, como o João fala.

**Recomendação de código (opcional, pequena):** as variantes `:0` e `:1` citam `{nome}` e `{bairro}`. Se algum desses campos vier vazio, a frase quebra ("Vi a  aí no"). Duas saídas: (a) nesse caso o sistema usa só a variante `:2`, que não cita nenhum dos dois; ou (b) fallback `{nome}` = "tua casa" e `{bairro}` = "por aí" (ajustando o texto). A opção (a) é a mais simples.

---

## 0.1 Por que a versão anterior não funcionava

- Abria com "pessoal da {nome}": parece lista de transmissão, não alguém falando com um dono.
- Falava do produto antes de dar um motivo para a pessoa responder.
- "30 dias grátis" na primeira linha de contato é o gatilho clássico de promoção de operadora. O dono lê como venda e para de ler.
- As variantes `:1` eram perguntas de sondagem ("quanto tempo leva...", "quem responde..."). Soam como vendedor tentando fazer o dono admitir um problema.
- Pedia compromisso grande (testar um sistema por 30 dias) logo no primeiro contato.

## 0.2 Princípios da nova escrita

1. **Dono para dono.** João se apresenta pela história (15 anos de salão em POA), não pela empresa.
2. **Cena antes de produto.** Cada mensagem abre com uma situação que o dono de tal tipo de casa reconhece na hora (sexta à noite na pizzaria, meio-dia no restaurante). Reconhecimento gera atenção; lista de funções não.
3. **Afirmação, não interrogatório.** A cena é contada como observação de quem viveu, sem perguntar sobre a operação do lead.
4. **Curiosidade com pedido pequeno.** O único pedido é "posso te mandar o Instagram / como ficou?". Um sim leva dois segundos. O teste grátis só entra depois, na resposta `interesse`.
5. **Pedido de opinião.** A variante `:2` pede a opinião de quem vive a operação. Elogia sem bajular e dá um motivo para responder mesmo sem interesse imediato.
6. **Curta.** De 4 a 6 linhas, até cerca de 400 caracteres. Uma ideia por linha, linguagem de WhatsApp.
7. **Lembretes que dão algo.** D3 entrega uma dica útil de graça (reciprocidade). D7 fecha com despedida honesta (perda: "vou parar de te chamar").

## 0.3 Como medir qual texto funciona

O sistema já grava o ID da variante enviada (`<arquivo>:<índice>`). Depois de umas 30 a 40 abordagens por tipo, compare por variante: taxa de resposta, taxa de resposta positiva (`interesse`/`preco`) e taxa de `SAIR`. Corte a pior e reescreva. Hipóteses para testar: variante `:0` (cena + produto) contra `:1` (insight de quem viveu) contra `:2` (pedido de opinião). Outro teste: enviar fora do pico, de terça a quinta entre 14h30 e 17h, para pegar o dono longe do serviço (hipótese, medir antes de tratar como regra).

---

## Como o texto é escolhido

**1ª mensagem (D0)** — ordem de decisão (`arquivo_d0` em `src/mfl/mensagens.py`):

1. Lead com sinal **Usa concorrente** → `concorrente`
2. Lead com sinal **Vende no iFood** → `ifood`
3. Senão, pela categoria do lugar (normalizada, primeira regra que casar vence):

| Tipo de lugar | Arquivo | Palavras que casam na categoria |
|---|---|---|
| Pizzaria | `pizzaria` | pizz |
| Hamburgueria | `hamburgueria` | hamburg, burger |
| Churrascaria | `churrascaria` | churrasc, grill, parrilla, espeto |
| Japonês | `japones` | japon, sushi, temaki, oriental |
| Padaria e doceria | `padaria` | padaria, confeitaria, doce, bolo, torta, panific |
| Bar | `bar` | bar, pub, boteco, choperia, cervejaria (palavra inteira) |
| Lanchonete e café | `lanchonete` | lanch, cafe, pastel, acai, sanduich, salgad |
| Restaurante e marmita | `restaurante` | qualquer outra coisa (padrão) |

**Lembretes:** D3 (3º dia sem resposta) → `d3`; D7 (7º dia sem resposta) → `d7`.

**Rodízio de variantes:** cada arquivo tem várias variantes (separadas por `---`). O sistema pega a próxima depois da última usada daquele arquivo, nunca repete a do último envio. ID gravado: `<arquivo>:<índice>`.

**Respostas prontas** (`interesse`, `preco`, `ja_tenho`): sempre a variante 0, sugerida na tela da conversa conforme a classificação da resposta do lead.

### Campos preenchidos

| Campo | Valor |
|---|---|
| `{nome}` | Nome fantasia; se não tiver, razão social. Se for nome provisório ("CNPJ 123…"), usa `@instagram`; se nem isso, fica vazio |
| `{bairro}` | Bairro do lead |
| `{sinal}` | Hoje sempre vazio — a linha some do texto |
| `{horario}` | Próximo dia útil às 15h: "amanhã às 15h" ou "segunda às 15h" (pula domingo) |

Campo vazio some, e a linha que só tinha ele também. Toda mensagem de prospecção precisa ter "responde SAIR" (LGPD); respostas prontas não.

---

## 1. Primeira mensagem (D0) — por tipo de lugar

Padrão das três variantes de cada tipo:

- `:0` — apresentação curta + cena do tipo de casa + o que o MyFoodLink resolve.
- `:1` — "vi a {nome} aí no {bairro}" + algo que o João aprendeu em 15 anos de salão.
- `:2` — pedido de opinião, sem citar nome nem bairro (serve de reserva quando faltar dado).

### Pizzaria (`cfg/mensagens/pizzaria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Pizzaria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `pizzaria:0`

```text
Opa, tudo bem? João aqui. Toquei restaurante 15 anos em POA e hoje crio sistema pra casas como a {nome}.
{sinal}
Sexta à noite: forno cheio, telefone tocando e o WhatsApp acumulando pedido. Quem já viveu isso sabe que pizzaria não perde cliente por falta de pizza boa.
Montei uma coisa pra essa hora. Posso te mandar o Instagram do projeto pra tu ver?
Se não for o momento, responde SAIR que eu não chamo mais.
```

#### Variante 1 — `pizzaria:1`

```text
Oi! João aqui, vi a {nome} aí no {bairro} e resolvi te chamar.
{sinal}
Aprendi uma coisa em 15 anos de restaurante: pizzaria não perde venda na cozinha, perde no WhatsApp, no minuto em que ninguém consegue responder.
Fiz um sistema que cuida dessa parte e delivery sem comissão de app. Posso te mandar como ficou?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `pizzaria:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos dentro de restaurante em POA.
{sinal}
Tô mostrando pra donos de pizzaria da região, porque a opinião de quem vive o delivery vale mais que a minha. Ele atende o WhatsApp, monta o pedido, manda pra cozinha e não cobra comissão por pedido.
Posso te mandar o Instagram pra tu dar uma olhada e me dizer o que achou?
Se não quiser mais mensagens, responde SAIR.
```

### Hamburgueria (`cfg/mensagens/hamburgueria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Hamburgueria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `hamburgueria:0`

```text
Opa, tudo bem? João aqui. 15 anos de restaurante em POA, hoje crio sistema pra casas como a {nome}.
{sinal}
Hamburgueria costuma ter o produto que o cliente adora e uma parte do lucro indo embora em comissão de app. Criei um jeito do cliente fiel pedir direto no WhatsApp da casa, sem comissão.
Posso te mandar o Instagram do projeto pra tu ver como ficou?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `hamburgueria:1`

```text
Oi! João aqui, vi a {nome} aí no {bairro} e resolvi te chamar.
{sinal}
Uma coisa que aprendi: cliente que pede no app é do app. O que pede direto no teu WhatsApp é teu, volta mais e não paga comissão.
Fiz um sistema pra trazer esse pedido pra dentro da casa. Posso te mandar como funciona?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `hamburgueria:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Tô mostrando pra donos de hamburgueria da região e queria a opinião de quem vive isso: cardápio com foto, combo, pedido pelo WhatsApp e pagamento online, sem taxa por pedido.
Posso te mandar o Instagram pra tu dar uma olhada?
Se não quiser mais mensagens, responde SAIR.
```

### Churrascaria (`cfg/mensagens/churrascaria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Churrascaria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `churrascaria:0`

```text
Opa, tudo bem? João aqui. Toquei restaurante 15 anos em POA e hoje crio sistema pra casas como a {nome}.
{sinal}
Churrascaria vive de mesa cheia no fim de semana, e reserva confirmada na mão, por áudio e mensagem solta, é por onde mais escapa mesa.
O MyFoodLink recebe a reserva pelo WhatsApp e ainda traz o cliente de volta com fidelidade. Posso te mandar o Instagram do projeto?
Se não for o momento, responde SAIR que eu não chamo mais.
```

#### Variante 1 — `churrascaria:1`

```text
Oi! João aqui, vi a {nome} aí no {bairro} e resolvi te chamar.
{sinal}
Domingo, mesa de doze, três mensagens de reserva em lugares diferentes e nenhuma anotada no mesmo caderno. Quem já tocou salão conhece a cena.
Fiz um sistema que organiza isso sozinho. Posso te mandar como ficou?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `churrascaria:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Tô mostrando pra donos de churrascaria da região e queria a tua opinião: reserva, cardápio digital, fidelidade e delivery sem comissão, tudo pelo WhatsApp da casa.
Posso te mandar o Instagram pra tu dar uma olhada?
Se não quiser mais mensagens, responde SAIR.
```

### Japonês (`cfg/mensagens/japones.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Japonês** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `japones:0`

```text
Opa, tudo bem? João aqui. 15 anos de restaurante em POA, hoje crio sistema pra casas como a {nome}.
{sinal}
Pedido de japonês tem mais detalhe que qualquer outro: combo, peça, troca, sem cebolinha, molho à parte. Cada detalhe digitado na mão é chance de erro.
O MyFoodLink monta isso pelo WhatsApp com cardápio com foto, e o delivery é sem comissão. Posso te mandar o Instagram do projeto?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `japones:1`

```text
Oi! João aqui, vi a {nome} aí no {bairro} e resolvi te chamar.
{sinal}
Aprendi em 15 anos de restaurante que combo mal anotado vira pedido refeito, e refazer pedido de japonês pesa no bolso e na paciência do cliente.
Montei um sistema que fecha o combo certo direto pelo WhatsApp. Posso te mandar como ficou?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `japones:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Tô mostrando pra donos de restaurante japonês da região e queria a tua opinião: cardápio digital com foto, pedido pelo WhatsApp e pagamento online, sem taxa por pedido.
Posso te mandar o Instagram pra tu dar uma olhada?
Se não quiser mais mensagens, responde SAIR.
```

### Padaria e doceria (`cfg/mensagens/padaria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Padaria e doceria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `padaria:0`

```text
Opa, tudo bem? João aqui. Toquei restaurante 15 anos em POA e hoje crio sistema pra casas como a {nome}.
{sinal}
Encomenda de bolo e torta chega de todo jeito: áudio, foto, mensagem às dez da noite. E alguém precisa anotar sabor, tamanho e data sem errar.
O MyFoodLink recebe a encomenda com cardápio digital e organiza tudo. Posso te mandar o Instagram do projeto?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `padaria:1`

```text
Oi! João aqui, vi a {nome} aí no {bairro} e resolvi te chamar.
{sinal}
Encomenda anotada em caderno e áudio perdido no WhatsApp é o jeito mais fácil de errar um bolo de aniversário. Já vi isso acontecer muito.
Fiz um sistema que organiza essa parte. Posso te mandar como ficou?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `padaria:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Tô mostrando pra donos de padaria e doceria da região e queria a tua opinião: encomendas e pedidos pelo WhatsApp, cardápio digital com foto e fidelidade pro cliente voltar.
Posso te mandar o Instagram pra tu dar uma olhada?
Se não quiser mais mensagens, responde SAIR.
```

### Bar (`cfg/mensagens/bar.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Bar** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `bar:0`

```text
Opa, tudo bem? João aqui. Toquei restaurante 15 anos em POA e hoje crio sistema pra casas como o {nome}.
{sinal}
Bar vive de sexta e sábado, e reserva que chega solta no WhatsApp atrapalha quem tá no balcão com a casa cheia.
O MyFoodLink atende a reserva pelo WhatsApp e tem cardápio no QR code, sem app pra baixar. Posso te mandar o Instagram do projeto?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `bar:1`

```text
Oi! João aqui, vi o {nome} aí no {bairro} e resolvi te chamar.
{sinal}
Sábado à noite, balcão cheio, celular apitando com pedido de mesa. Ninguém merece parar o serviço pra confirmar reserva na mão.
Fiz um sistema que confirma sozinho. Posso te mandar como ficou?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `bar:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Tô mostrando pra donos de bar da região e queria a tua opinião: reserva pelo WhatsApp, cardápio digital no QR e fidelidade, sem taxa por pedido.
Posso te mandar o Instagram pra tu dar uma olhada?
Se não quiser mais mensagens, responde SAIR.
```

### Lanchonete e café (`cfg/mensagens/lanchonete.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Lanchonete e café** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `lanchonete:0`

```text
Opa, tudo bem? João aqui. 15 anos de restaurante em POA, hoje crio sistema pra casas como a {nome}.
{sinal}
Cartão de carimbo some na carteira, e cliente fiel que ninguém lembra de premiar vira cliente comum.
O MyFoodLink recebe pedido pelo WhatsApp com cardápio digital e tem fidelidade no celular do cliente, um cartão de carimbo que não se perde. Posso te mandar o Instagram do projeto?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `lanchonete:1`

```text
Oi! João aqui, vi a {nome} aí no {bairro} e resolvi te chamar.
{sinal}
Lanchonete boa tem cliente que volta toda semana e nunca ganha nada por isso. Foi o que mais me incomodou nos meus anos de restaurante.
Montei uma fidelidade simples, no celular do cliente. Posso te mandar como ficou?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `lanchonete:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Tô mostrando pra donos de lanchonete e café da região e queria a tua opinião: cardápio digital, pedido pelo WhatsApp e fidelidade, sem taxa por pedido.
Posso te mandar o Instagram pra tu dar uma olhada?
Se não quiser mais mensagens, responde SAIR.
```

### Restaurante e marmita (padrão) (`cfg/mensagens/restaurante.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Restaurante e marmita (padrão)** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `restaurante:0`

```text
Opa, tudo bem? João aqui. Toquei restaurante 15 anos em POA e hoje crio sistema pra casas como a {nome}.
{sinal}
Meio-dia, cozinha a mil e o WhatsApp apitando com "tem marmita hoje?". Todo dono de restaurante conhece essa cena.
O MyFoodLink atende o WhatsApp da casa, manda o cardápio do dia e recebe pedido e marmita sem ninguém parar pra digitar. Posso te mandar o Instagram do projeto?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `restaurante:1`

```text
Oi! João aqui, vi a {nome} aí no {bairro} e resolvi te chamar.
{sinal}
Aprendi em 15 anos de salão que a hora do almoço é quando o WhatsApp mais pede atenção e quando menos tem gente livre pra dar.
Fiz um sistema que atende por ti nessa hora. Posso te mandar como ficou?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `restaurante:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Tô mostrando pra donos de restaurante da região e queria a tua opinião: atendimento e pedido pelo WhatsApp, cardápio digital, fidelidade e delivery sem comissão.
Posso te mandar o Instagram pra tu dar uma olhada?
Se não quiser mais mensagens, responde SAIR.
```

---

## 2. Primeira mensagem (D0) — por sinal (tem prioridade sobre o tipo de lugar)

Aqui o sinal vira o gancho: reconhecer o que o lead já faz, sem criticar.

### Quem usa concorrente (`cfg/mensagens/concorrente.md`)

**Quando usa:** lead com sinal **Usa concorrente** (vence tudo).

**Variantes:** 2

#### Variante 0 — `concorrente:0`

```text
Oi, tudo bem? João aqui, 15 anos tocando restaurante em POA.
Vi que a {nome} já trabalha com sistema de pedido, e isso diz muito: casa que leva o digital a sério. Não tô te chamando pra largar o que funciona.
Criei o MyFoodLink e queria a opinião de quem já usa algo parecido. Posso te mandar o Instagram pra tu ver e me dizer o que achou?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `concorrente:1`

```text
Oi! João aqui, vi a {nome} aí no {bairro}.
Dono que já usa sistema sabe melhor que ninguém o que falta nele. Fiz o MyFoodLink com o olhar de quem tocou restaurante e queria te mostrar sem compromisso, até pra rodar junto do que tu já tem.
Posso te mandar como ficou?
Se preferir não receber, responde SAIR.
```

### Quem vende no iFood (`cfg/mensagens/ifood.md`)

**Quando usa:** lead com sinal **Vende no iFood** (se não usa concorrente).

**Variantes:** 2

#### Variante 0 — `ifood:0`

```text
Oi, tudo bem? João aqui, 15 anos tocando restaurante em POA.
Vi que a {nome} vende no iFood, ótima vitrine pra ser achado. Só que o cliente que já conhece a casa e pede pelo app deixa uma comissão que podia ficar no teu caixa.
Criei o MyFoodLink pra esse cliente fiel pedir direto pelo WhatsApp, sem comissão por pedido. Posso te mandar o Instagram do projeto?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `ifood:1`

```text
Oi! João aqui, vi a {nome} aí no {bairro}.
O app é vitrine, mas o cliente que pede toda semana devia pedir direto com a casa. Foi isso que me fez criar o MyFoodLink, depois de anos vendo comissão pesar no caixa de restaurante.
Posso te mandar como funciona?
Se preferir não receber, responde SAIR.
```

---

## 3. Lembretes (sem resposta)

Regra: o lembrete não repete o pitch. D3 dá uma dica útil de graça. D7 é uma despedida honesta com convite concreto.

### Lembrete D3 (`cfg/mensagens/d3.md`)

**Quando usa:** 3º dia depois da 1ª mensagem, sem resposta. Igual para todos os tipos de lugar.

**Variantes:** 3

#### Variante 0 — `d3:0`

```text
Sem pressa, só uma dica de graça de quem viveu isso: põe o link do cardápio na bio do Instagram e no status do WhatsApp. Cliente pede o que está a um toque.
Se um dia quiser ver como o MyFoodLink faz isso no automático, é só me chamar. Se não quiser receber, responde SAIR.
```

#### Variante 1 — `d3:1`

```text
Dica de quem passou 15 anos no salão: anota por uma semana quantos pedidos entram pelo app e quantos entram direto. Muita gente se surpreende com a conta.
Se quiser ajuda pra levar mais gente pro pedido direto, tô por aqui. Se não quiser receber, responde SAIR.
```

#### Variante 2 — `d3:2`

```text
Uma coisa que ajuda no pico: mensagem automática no WhatsApp com cardápio e horário. O cliente sente que foi atendido na hora, mesmo com a casa lotada.
O MyFoodLink faz isso e vai além. Se quiser ver, é só falar. Se não quiser receber, responde SAIR.
```

### Lembrete D7 (`cfg/mensagens/d7.md`)

**Quando usa:** 7º dia sem resposta. Última mensagem da cadência; propõe conversa de 15 min.

**Variantes:** 3

#### Variante 0 — `d7:0`

```text
Vou parar de te chamar, prometo. Antes, deixo o convite: 15 minutos {horario}, te mostro na tela como ficaria o atendimento da tua casa. Se for melhor outro horário, me diz qual.
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `d7:1`

```text
Última por aqui, João. Se um dia o WhatsApp apertar ou a comissão do app pesar, lembra que tem alguém que já passou por isso e montou uma saída.
Posso te mostrar em 15 minutos, {horario}? Se não quiser receber, responde SAIR.
```

#### Variante 2 — `d7:2`

```text
Fecho o assunto por aqui pra não encher o teu WhatsApp. Se fizer sentido conversar, tenho um horário {horario}, 15 minutos, sem compromisso.
Se não, sem problema: responde SAIR que eu não mando mais.
```

---

## 4. Respostas prontas (quando o lead responde)

A resposta do lead é classificada por palavra-chave (`src/mfl/classifica.py`, primeira regra que casar vence) e o João confirma na UI. **A classificação não muda.**

| Ordem | Classe | Exemplos que casam | Status do lead | Resposta sugerida |
|---|---|---|---|---|
| 1 | `opt_out` | "não manda mais", "para de mandar", "me tira", "descadastrar", ou só "sair/pare/stop/remover/cancelar" | Pediu SAIR (automático) | nenhuma |
| 2 | `nao` | "não tenho interesse", "não quero", "não preciso", "sem interesse", "dispenso" | Frio | nenhuma |
| 3 | `ja_tenho` | "já tenho/uso/temos", "trabalhamos com", Goomer, Saipos, Anota Aí, LeadsFood, Consumer, Linx, MenuDino, Cardápio Web | Já tem sistema (objeção) | `ja_tenho` |
| 4 | `preco` | "quanto custa/é/sai/fica", "valor", "preço", "mensalidade", "plano(s)" | Respondeu | `preco` |
| 5 | `interesse` | "tenho interesse", "quero", "como funciona", "me explica", "pode ser", "bora", "vamos", "testar", "manda", "sim", "claro" | Respondeu | `interesse` |
| — | `outro` | nada casou | não muda | nenhuma |

Aqui entra o teste grátis, que saiu da primeira mensagem: o lead já mostrou interesse, então a oferta chega como convite, não como isca.

### Quando tem interesse (`cfg/mensagens/interesse.md`)

**Quando usa:** resposta classificada como `interesse`.

**Variantes:** 1

#### Variante 0 — `interesse:0`

```text
Que bom! Dá uma olhada com calma: https://www.myfoodlink.com.br

Se fizer sentido, eu mesmo configuro tudo pra tua casa e tu usa 30 dias sem pagar nada, sem contrato. Com quem eu tô falando, aliás?
```

### Quando pergunta preço (`cfg/mensagens/preco.md`)

**Quando usa:** resposta classificada como `preco`. `{horario}` vira o próximo dia útil às 15h.

**Variantes:** 1

#### Variante 0 — `preco:0`

```text
Boa pergunta. São três planos, sem contrato mínimo e sem taxa de implantação:
- Start, R$149/mês: atendimento e reservas no WhatsApp, cardápio digital e fidelidade
- Pro, R$299/mês: tudo do Start mais delivery com pagamento online
- Gestor, R$499/mês: PDV com salão, comanda, cozinha, estoque e financeiro
Os primeiros 30 dias são por minha conta. Te mostro tudo em 15 minutos {horario}, pra tu ver qual plano faz sentido pra tua casa?
```

### Quando já tem sistema (`cfg/mensagens/ja_tenho.md`)

**Quando usa:** resposta classificada como `ja_tenho`.

**Variantes:** 1

#### Variante 0 — `ja_tenho:0`

```text
Boa, isso mostra que tu leva a casa a sério. Não é pra largar o que funciona.
Qual sistema vocês usam? Pergunto por curiosidade de colega: muita casa me conta que o que mais pesa é comissão ou WhatsApp que ainda é no braço.
Se um dia fizer sentido, eu rodo o MyFoodLink do lado do atual por 30 dias, sem mexer em nada do que tu já tem, e tu compara.
```

---

## 5. Resumo das mudanças

| Item | Antes | Agora |
|---|---|---|
| Abertura | "Oi, pessoal da {nome}!" | "Opa, tudo bem? João aqui." e, nas variantes `:1`, "vi a {nome} aí no {bairro} e resolvi te chamar" |
| Gancho | Produto + função | Cena que o dono do tipo de casa reconhece, ou algo que o João aprendeu em 15 anos |
| Oferta no D0 | "30 dias grátis" na primeira mensagem | Nenhuma. Pedido único: "posso te mandar o Instagram / como ficou?" |
| Variante `:1` | Pergunta de sondagem | Observação de quem viveu (sem interrogar o lead) |
| Variante `:2` | Lista de funções + oferta | Pedido de opinião, sem `{nome}` nem `{bairro}` (serve de reserva) |
| Concorrente e iFood | Pitch direto | Reconhece o que a casa já faz, sem pedir pra largar |
| D3 | Repete o pitch | Dica útil de graça |
| D7 | Repete oferta | Despedida honesta + convite de 15 min |
| Teste grátis | Em toda mensagem | Só nas respostas prontas (`interesse`, `preco`, `ja_tenho`), depois que o lead respondeu |
