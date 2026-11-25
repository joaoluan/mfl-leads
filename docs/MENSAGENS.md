# Mensagens do MyFoodLink

O João aborda e responde pelo WhatsApp Web. A fila sugere os textos conforme o tipo de casa e a etapa da conversa.

O primeiro contato parte da experiência do João na gestão de restaurantes em Porto Alegre. Toda variante D0 apresenta o atendimento automático no WhatsApp e completa com o que faz sentido pro tipo de casa: cardápio digital, reservas, pedido online, encomendas, fidelidade ou fila de espera. Peça permissão pra mostrar. Traga preço e teste grátis depois que a pessoa responder. Use o jeito do João de falar: “opa”, “tu”, “tua casa” e frases curtas.

A essência do MyFoodLink é começar o atendimento sem depender de alguém pegar o celular, registrar o contato e o histórico e avisar a equipe quando precisa de uma pessoa. O bot pausa quando a equipe assume; se o cliente continua esperando atendimento humano, há lembrete pra equipe. As dúvidas não resolvidas alimentam a revisão de respostas, que podem ser publicadas para uso automático depois de aprovadas pelo restaurante. O objetivo comercial é ajudar a evitar oportunidades perdidas por demora na resposta.

As variantes distribuem esse ciclo sem listar todos os recursos em cada abordagem. D3 aprofunda alertas, contatos e aprendizado; D7 encerra a rodada; as respostas prontas explicam o conjunto e os planos. “Contato registrado” não significa venda concluída nem autorização para marketing. Aprendizado tem revisão humana. Evite prometer “nunca perde venda”, “responde qualquer pergunta” ou “aprende sozinho”. A disponibilidade depende do plano, da configuração e da conexão do WhatsApp.

Os blocos de texto abaixo correspondem, na mesma ordem, às variantes em `cfg/mensagens/`. Preserve os IDs existentes ao editar, sincronize as duas cópias e rode `uv run pytest`. Pra comparar a reação aos textos novos, filtre os envios pela data da troca, pois versões anteriores usaram os mesmos IDs. Conte respostas humanas, interesse e pedidos de saída separadamente.

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

**Rodízio de variantes:** cada arquivo tem várias variantes (separadas por `---`). O sistema parte da próxima variante da rodada e pula as que pedem nome ou bairro ausentes, quando há uma alternativa. O ID salvo tem o formato `<arquivo>:<índice>`.

**Respostas prontas** (`interesse`, `preco`, `ja_tenho`): sempre a variante 0, sugerida na tela da conversa conforme a classificação da resposta do lead.

### Campos preenchidos

| Campo | Valor |
|---|---|
| `{nome}` | Nome fantasia; se não tiver, razão social. Se for nome provisório ("CNPJ 123…"), usa `@instagram`; se nem isso, fica vazio |
| `{bairro}` | Bairro do lead |
| `{sinal}` | Hoje sempre vazio — a linha some do texto |

Toda abordagem e todo lembrete devem incluir “responde SAIR”. Adapte as respostas prontas à pergunta que chegou.

---

## 1. Primeira mensagem (D0) — por tipo de lugar

As duas primeiras variantes usam o nome da casa. A segunda usa também o bairro. A terceira serve mesmo quando esses dados faltam.

### Pizzaria (`cfg/mensagens/pizzaria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Pizzaria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `pizzaria:0`

```text
Opa, tudo bem? Aqui é o João. Trabalhei 15 anos na gestão de restaurantes em Porto Alegre e vi a {nome}.
{sinal}
No pico da noite, o MyFoodLink responde automaticamente no WhatsApp e leva o cliente ao cardápio digital e ao pedido pelo site. Se precisa da equipe, avisa pra alguém assumir. Ajuda a não deixar uma venda esfriar esperando resposta.
Posso te mostrar como funciona?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `pizzaria:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
Criei o MyFoodLink depois de 15 anos tocando restaurante. Ele começa o atendimento sozinho no WhatsApp e registra o contato e a conversa. A pizzaria também pode receber pedidos de delivery e retirada pelo próprio site, com pagamento online.
Posso te mostrar esse caminho, da conversa ao pedido?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `pizzaria:2`

```text
Opa, aqui é o João, do MyFoodLink. Trabalhei 15 anos com restaurante aqui em Porto Alegre.
{sinal}
O MyFoodLink responde automaticamente às dúvidas de rotina no WhatsApp. As que precisam da equipe ficam registradas e podem virar respostas automáticas depois da tua aprovação. A pizzaria ainda tem fidelidade por selos pra quem volta.
Posso te mostrar como fica pro cliente?
Se não quiser receber mais mensagens, responde SAIR.
```

### Hamburgueria (`cfg/mensagens/hamburgueria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Hamburgueria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `hamburgueria:0`

```text
Opa, tudo bem? Aqui é o João. Vi a {nome}. Trabalhei 15 anos com restaurante em Porto Alegre.
{sinal}
No pico dos pedidos, o MyFoodLink responde automaticamente no WhatsApp e mostra o cardápio digital. Se o cliente precisa de alguém, avisa a equipe pra assumir. A ideia é evitar que ele desista enquanto espera uma resposta.
Posso te mostrar como fica?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `hamburgueria:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
Criei o MyFoodLink pra começar o atendimento sozinho no WhatsApp e guardar o contato e o histórico da conversa. O cliente também pode pedir delivery ou retirada pelo site da hamburgueria e pagar online.
Posso te mostrar como funciona, do WhatsApp ao pedido?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `hamburgueria:2`

```text
Opa, tudo bem? João aqui, do MyFoodLink. Passei 15 anos tocando restaurante.
{sinal}
O MyFoodLink atende automaticamente no WhatsApp e reúne as dúvidas que a equipe precisou resolver. Depois de aprovadas, as respostas podem ser usadas pelo bot. E a casa tem fidelidade por selos no celular pra incentivar o cliente a voltar.
Posso te mostrar como isso fica na hamburgueria?
Se não quiser receber mais mensagens, responde SAIR.
```

### Churrascaria (`cfg/mensagens/churrascaria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Churrascaria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `churrascaria:0`

```text
Opa, aqui é o João. Vi a {nome}. Trabalhei 15 anos com gestão de restaurantes em Porto Alegre.
{sinal}
O MyFoodLink responde automaticamente no WhatsApp, informa horários e leva o cliente à reserva, com confirmação conforme as vagas e as regras da casa. Se precisa da equipe, manda um alerta pra ela assumir.
Posso te mostrar esse atendimento e a reserva?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `churrascaria:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
Domingo com salão cheio já dá trabalho. No MyFoodLink, o atendimento começa sozinho no WhatsApp, o contato fica registrado e as reservas vão pra agenda. A casa também tem cardápio digital no QR Code, sem a equipe mandar o mesmo link toda hora.
Posso te mostrar como fica essa rotina?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `churrascaria:2`

```text
Opa, aqui é o João, do MyFoodLink. Trabalhei 15 anos com restaurante em Porto Alegre.
{sinal}
O MyFoodLink responde automaticamente às perguntas de rotina no WhatsApp e avisa quando a equipe precisa assumir. As respostas da equipe podem ser usadas pelo bot depois de aprovadas. Pra casa cheia, também tem fila de espera por QR Code e aviso de mesa pelo WhatsApp.
Posso te mostrar como funciona?
Se não quiser receber mais mensagens, responde SAIR.
```

### Japonês (`cfg/mensagens/japones.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Japonês** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `japones:0`

```text
Opa, aqui é o João. Vi a {nome}. Trabalhei 15 anos com restaurante aqui em Porto Alegre.
{sinal}
O MyFoodLink responde automaticamente no WhatsApp e mostra o cardápio digital com fotos dos pratos e combinados. Quando precisa de uma pessoa, avisa a equipe. Ajuda a não deixar o cliente esperando enquanto o salão e os pedidos estão no pico.
Posso te mostrar como fica?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `japones:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
O MyFoodLink começa o atendimento sozinho no WhatsApp e registra o contato e a conversa. O cliente também pode escolher os itens no cardápio, pedir delivery ou retirada pelo site da casa e pagar online.
Posso te mostrar esse caminho, da conversa ao pedido?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `japones:2`

```text
Opa, tudo bem? João aqui, do MyFoodLink. Vim da gestão de restaurantes aqui em Porto Alegre.
{sinal}
O MyFoodLink atende automaticamente no WhatsApp e leva o cliente ao cardápio ou à reserva. As dúvidas que a equipe resolve ficam registradas e podem virar respostas do bot depois da tua aprovação. O atendimento vai evoluindo com as perguntas reais da casa.
Posso te mostrar como fica?
Se não quiser receber mais mensagens, responde SAIR.
```

### Padaria e doceria (`cfg/mensagens/padaria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Padaria e doceria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `padaria:0`

```text
Opa, aqui é o João. Vi a {nome}. Trabalhei 15 anos com restaurante em Porto Alegre e criei o MyFoodLink.
{sinal}
O MyFoodLink responde automaticamente no WhatsApp e leva o cliente ao cardápio digital e às encomendas pelo site. Se a conversa precisa da equipe, manda um alerta pra ela assumir, mesmo com o balcão cheio.
Posso te mostrar esse atendimento e como o cliente encomenda?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `padaria:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
Quando alguém chama no WhatsApp, o MyFoodLink inicia o atendimento sozinho e registra o contato e a conversa. A casa também pode receber encomendas pelo site, com data agendada e pagamento online.
Posso te mostrar como fica, da conversa à encomenda?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `padaria:2`

```text
Opa, tudo bem? João aqui, do MyFoodLink. Vim da gestão de restaurantes.
{sinal}
O MyFoodLink responde automaticamente às dúvidas de rotina no WhatsApp. O que a equipe precisou explicar pode virar resposta do bot depois de aprovado. E quem passa toda semana no balcão pode ter um cartão de fidelidade por selos no celular.
Posso te mostrar como funciona esse atendimento e a fidelidade?
Se não quiser receber mais mensagens, responde SAIR.
```

### Bar (`cfg/mensagens/bar.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Bar** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `bar:0`

```text
Opa, aqui é o João. Vi {nome}. Passei 15 anos na gestão de restaurantes em Porto Alegre.
{sinal}
O MyFoodLink responde automaticamente no WhatsApp, mostra o cardápio digital e leva o cliente à reserva nos horários da casa. Se precisa de alguém, avisa a equipe pra assumir, mesmo com o balcão cheio.
Posso te mostrar esse atendimento e a reserva?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `bar:1`

```text
Oi, aqui é o João. Vi {nome} no bairro {bairro}.
{sinal}
No MyFoodLink, o atendimento começa sozinho no WhatsApp, o contato fica registrado e as reservas vão pra agenda da equipe. A casa ainda tem fidelidade por selos no celular pra incentivar quem já veio a voltar.
Posso te mostrar como fica?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `bar:2`

```text
Opa, aqui é o João, do MyFoodLink. Trabalhei 15 anos com restaurante.
{sinal}
O MyFoodLink atende automaticamente no WhatsApp. As dúvidas que a equipe resolve podem virar respostas do bot depois de aprovadas. Se forma fila na porta, também dá pra entrar nela pelo QR Code e receber o aviso de mesa pelo WhatsApp.
Posso te mostrar como funciona?
Se não quiser receber mais mensagens, responde SAIR.
```

### Lanchonete e café (`cfg/mensagens/lanchonete.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Lanchonete e café** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `lanchonete:0`

```text
Opa, tudo bem? Aqui é o João. Vi a {nome}. Trabalhei 15 anos com restaurante em Porto Alegre.
{sinal}
O MyFoodLink responde automaticamente no WhatsApp e mostra o cardápio digital enquanto a equipe cuida do balcão. Quando o cliente precisa de uma pessoa, avisa pra alguém assumir. Ajuda a não perder o pedido por demora na resposta.
Posso te mostrar como fica esse atendimento?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `lanchonete:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
O MyFoodLink começa o atendimento sozinho no WhatsApp e registra o contato e a conversa. Se vocês recebem pedidos pra buscar no balcão, o cliente também pode pedir pelo site da casa e pagar online.
Posso te mostrar esse caminho, da conversa à retirada?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `lanchonete:2`

```text
Opa, aqui é o João, do MyFoodLink. Vim da gestão de restaurantes em Porto Alegre.
{sinal}
O MyFoodLink responde automaticamente às dúvidas de rotina no WhatsApp e reúne as que a equipe precisou resolver. Depois de aprovadas, as respostas podem ser usadas pelo bot. Pra quem volta pro café ou lanche toda semana, tem fidelidade por selos no celular.
Posso te mostrar como fica na tua casa?
Se não quiser receber mais mensagens, responde SAIR.
```

### Restaurante e marmita (padrão) (`cfg/mensagens/restaurante.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Restaurante e marmita (padrão)** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `restaurante:0`

```text
Opa, tudo bem? Aqui é o João. Vi a {nome}. Trabalhei 15 anos na gestão de restaurantes em Porto Alegre.
{sinal}
Na hora do almoço, o MyFoodLink responde automaticamente no WhatsApp e mostra o cardápio digital. Se o cliente precisa da equipe, manda um alerta pra ela assumir. Ajuda a não deixar um pedido esfriar esperando alguém pegar o celular.
Posso te mostrar como fica esse atendimento?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `restaurante:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
Criei o MyFoodLink depois de 15 anos tocando restaurante. Ele inicia o atendimento sozinho no WhatsApp e registra o contato e a conversa. Se a casa recebe reservas, o cliente pode reservar com confirmação conforme as vagas e as regras de vocês.
Posso te mostrar esse atendimento e a agenda?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `restaurante:2`

```text
Opa, tudo bem? João aqui, do MyFoodLink. Vim da gestão de restaurantes.
{sinal}
O MyFoodLink atende automaticamente no WhatsApp. As dúvidas resolvidas pela equipe podem virar respostas do bot depois de aprovadas. Pra casa que vende marmita, também tem pedido pelo site, com entrega ou retirada e pagamento online.
Posso te mostrar como fica, da conversa ao pedido?
Se não quiser receber mais mensagens, responde SAIR.
```

---

## 2. Primeira mensagem (D0) — por sinal (tem prioridade sobre o tipo de lugar)

O sinal ajuda a escolher o assunto. A abordagem oferece um recurso complementar ou um canal de pedido direto.

### Quem usa concorrente (`cfg/mensagens/concorrente.md`)

**Quando usa:** lead com sinal **Usa concorrente** (vence tudo).

**Variantes:** 2

#### Variante 0 — `concorrente:0`

```text
Opa, aqui é o João. Trabalhei 15 anos com restaurante em Porto Alegre.
Vi que a {nome} já tem um canal de pedido. Queria te mostrar o atendimento do MyFoodLink: ele responde automaticamente no WhatsApp, registra o contato e avisa quando a equipe precisa assumir. Também tem cardápio digital, reservas e fidelidade.
Posso te mostrar como esse atendimento funciona?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `concorrente:1`

```text
Oi, aqui é o João, do MyFoodLink. Vim da gestão de restaurantes.
Pra quem já tem sistema de pedidos, vale olhar também o atendimento: o MyFoodLink responde sozinho no WhatsApp e guarda a conversa. As dúvidas que a equipe resolve podem virar respostas do bot depois de aprovadas. A casa ainda tem reservas e cardápio digital.
Posso te mostrar essa parte e tu avalia o que faz falta hoje?
Se não quiser receber mais mensagens, responde SAIR.
```

### Quem vende no iFood (`cfg/mensagens/ifood.md`)

**Quando usa:** lead com sinal **Vende no iFood** (se não usa concorrente).

**Variantes:** 2

#### Variante 0 — `ifood:0`

```text
Opa, aqui é o João. Trabalhei 15 anos com restaurante em Porto Alegre e vi a {nome}.
Pra quem já vende no iFood, o MyFoodLink atende automaticamente quem chama no WhatsApp e leva ao cardápio e ao pedido pelo site da casa. O contato fica registrado e a equipe recebe alerta quando precisa assumir. Dá pra manter o iFood e cuidar também do canal direto.
Posso te mostrar como fica, da conversa ao pedido?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `ifood:1`

```text
Oi, aqui é o João, do MyFoodLink. Vim da gestão de restaurantes.
O MyFoodLink começa o atendimento sozinho no WhatsApp, registra a conversa e oferece pedido pelo site, com entrega ou retirada e pagamento online. As respostas da equipe podem ser usadas pelo bot depois de aprovadas. A cobrança é por mensalidade, sem comissão do MyFoodLink por pedido; o meio de pagamento tem as próprias taxas.
Posso te mostrar esse atendimento e o pedido direto?
Se não quiser receber mais mensagens, responde SAIR.
```

---

## 3. Lembretes (sem resposta)

O D3 traz uma sugestão prática. O D7 encerra o contato atual e deixa a conversa aberta caso a pessoa procure o João.

### Lembrete D3 (`cfg/mensagens/d3.md`)

**Quando usa:** 3º dia depois da 1ª mensagem, sem resposta. Igual para todos os tipos de lugar.

**Variantes:** 3

#### Variante 0 — `d3:0`

```text
Opa, João aqui de novo. Responder rápido é uma parte; quando o cliente precisa de alguém, a equipe também precisa saber. No MyFoodLink, o bot inicia o atendimento, manda o alerta e lembra a equipe se a conversa continua esperando.
Se quiser ver como fica junto do cardápio e das reservas, me chama.
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `d3:1`

```text
Oi, tudo bem? No MyFoodLink, quem chama no WhatsApp vira um contato com histórico. O atendimento começa automaticamente e a equipe vê o que já foi conversado quando precisa assumir, sem pedir pro cliente contar tudo de novo.
Se quiser ver como isso acompanha o cardápio, a reserva ou o pedido da casa, tô por aqui.
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `d3:2`

```text
Opa, João aqui. As perguntas reais dos clientes ajudam a melhorar o atendimento. No MyFoodLink, a equipe revisa o que o bot não resolveu e aprova respostas pra usar automaticamente nas próximas dúvidas parecidas.
Assim o atendimento vai ficando mais preparado pra rotina da casa. Se quiser ver como funciona, me chama.
Se não quiser receber mais mensagens, responde SAIR.
```

### Lembrete D7 (`cfg/mensagens/d7.md`)

**Quando usa:** 7º dia sem resposta. Última mensagem desta rodada de contato.

**Variantes:** 3

#### Variante 0 — `d7:0`

```text
Opa, João aqui. Vou deixar esse assunto por aqui. Se quiser ver o MyFoodLink atendendo automaticamente no WhatsApp e avisando tua equipe quando precisa de alguém, é só me chamar. Te mostro com o cardápio e a rotina da casa.
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `d7:1`

```text
Oi, tudo bem? Fechando esse contato por aqui. Se mais pra frente tu quiser automatizar o atendimento no WhatsApp e juntar cardápio, reservas e pedido direto, pode falar comigo. A ideia é ajudar a não perder oportunidade por demora na resposta.
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `d7:2`

```text
Valeu, vou encerrar por aqui. Se quiser ver como o MyFoodLink atende sozinho no WhatsApp, registra os contatos e chama a equipe quando precisa, me chama. A gente olha junto o que faz sentido pra tua casa.
Se não quiser receber mais mensagens, responde SAIR.
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

Responda primeiro à dúvida. Se fizer sentido para a casa, convide a testar o Start ou o Pro por 30 dias.

### Quando tem interesse (`cfg/mensagens/interesse.md`)

**Quando usa:** resposta classificada como `interesse`.

**Variantes:** 1

#### Variante 0 — `interesse:0`

```text
Claro! O MyFoodLink começa o atendimento sozinho no WhatsApp da casa, responde perguntas de rotina e leva o cliente ao cardápio, à reserva ou ao pedido. O contato e o histórico ficam registrados.

Quando precisa de uma pessoa, avisa a equipe e lembra se o cliente continua esperando. As dúvidas que o bot não resolveu podem virar respostas automáticas depois de revisadas e aprovadas por vocês.

Junto disso, tem cardápio digital com QR Code, reservas, avaliações, fidelidade e fila de espera. No Pro, também tem delivery, retirada e encomendas pelo site, com pagamento online.
Aqui dá pra conhecer melhor: https://www.myfoodlink.com.br

O que tu quer ver primeiro na rotina da tua casa? Se fizer sentido, te ajudo a configurar e tu pode testar por 30 dias grátis, sem contrato mínimo.
```

### Quando pergunta preço (`cfg/mensagens/preco.md`)

**Quando usa:** resposta classificada como `preco`. Para uma pergunta sobre PDV, apresente o Gestor separadamente.

**Variantes:** 1

#### Variante 0 — `preco:0`

```text
O Start fica R$ 149 por mês. Inclui atendimento automático no teu WhatsApp, contatos com histórico e alertas pra equipe, além de cardápio digital com QR Code, reservas, avaliações, fidelidade e fila de espera. As respostas da equipe podem ser usadas pelo bot depois de aprovadas.
O Pro fica R$ 299 por mês. Tem tudo do Start e também delivery, retirada e encomendas pelo site, com pagamento online.

São 30 dias grátis pra testar, sem taxa de implantação e sem contrato mínimo. Tu quer começar automatizando o atendimento ou receber pedidos pelo site também?
```

### Quando já tem sistema (`cfg/mensagens/ja_tenho.md`)

**Quando usa:** resposta classificada como `ja_tenho`.

**Variantes:** 1

#### Variante 0 — `ja_tenho:0`

```text
Boa! Qual sistema vocês usam hoje e como fica o atendimento no WhatsApp? No MyFoodLink, o bot responde automaticamente às dúvidas de rotina, registra os contatos e avisa quando a equipe precisa assumir. As respostas que vocês revisam e aprovam podem ser usadas pelo bot nas próximas dúvidas parecidas. Também tem cardápio digital, reservas e fidelidade; te mostro o que fizer sentido pra tua casa.
```

---

## 5. Como continuar a conversa

Use estes exemplos manualmente, conforme o que a pessoa respondeu.

**Quando a pessoa só diz “pode mandar”**

> Claro, aqui tá o site: https://www.myfoodlink.com.br. Te mostro como o cliente chama no WhatsApp, o MyFoodLink começa a atender e a equipe é avisada quando precisa assumir. Junto disso, a gente olha o cardápio, a reserva ou o pedido que faz sentido pra tua casa.

**Quando a pessoa quer testar**

> Fechou. A gente configura o atendimento no teu WhatsApp, as informações da casa e quem recebe os alertas. Depois junta o cardápio, as reservas e, se tu precisa, o pedido online. Qual parte da rotina tu quer resolver primeiro?

**Quando pergunta como o bot aprende**

> As dúvidas que ele não resolveu ficam pra revisão junto do que a equipe respondeu. Vocês ajustam e aprovam uma resposta, e o bot pode usar nas próximas perguntas parecidas. Assim ele vai ficando mais preparado pras dúvidas da tua casa, com vocês no controle.

**Quando a pessoa pergunta por PDV**

> Aí tem o Gestor, que fica R$ 499 por mês. Ele mantém o atendimento automático, os recursos do Pro e acrescenta caixa, salão, comandas, cozinha, estoque e financeiro. A implantação é assistida e usa um servidor local na casa. Me conta como vocês usam o caixa e as comandas hoje pra eu entender se encaixa.

Referências do produto: [atendimento, aprendizado, alertas e jornadas](https://github.com/joaoluan/myfoodlink-router/blob/main/docs/OPERACAO.md), [CRM e registro de contatos](https://github.com/joaoluan/myfoodlink-router/blob/main/contacts-store.js) e [recursos por plano](https://github.com/joaoluan/frontend-platform/blob/main/apps/public-web/app/%28marketing%29/plans.ts). Revisão de código e documentação em 25/11/2026; não é verificação de ativação em cada restaurante.
