# Mensagens do MyFoodLink

O João aborda e responde pelo WhatsApp Web. A fila sugere os textos conforme o tipo de casa e a etapa da conversa.

O primeiro contato parte da experiência do João na gestão de restaurantes em Porto Alegre. Apresente um uso do MyFoodLink que faça sentido pra casa e peça permissão pra mostrar. Traga preço e teste grátis depois que a pessoa responder. Use o jeito do João de falar: “opa”, “tu”, “tua casa” e frases curtas.

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
Na sexta à noite, responder cardápio e prazo toma tempo de quem tá cuidando dos pedidos. No MyFoodLink, o WhatsApp já pode mostrar o cardápio pra quem chama.
Posso te mostrar como funciona?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `pizzaria:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
Criei o MyFoodLink depois de 15 anos tocando restaurante. Com ele, quem já conhece a pizzaria pode pedir pelo site da casa, com delivery ou retirada.
Posso te mostrar como fica esse pedido?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `pizzaria:2`

```text
Opa, aqui é o João, do MyFoodLink. Trabalhei 15 anos com restaurante aqui em Porto Alegre.
{sinal}
Se o WhatsApp da pizzaria fica cheio no fim de semana, dá pra deixar o cardápio no menu automático e a equipe assume quando precisa.
Posso te mostrar como fica pro cliente?
Se não quiser receber mais mensagens, responde SAIR.
```

### Hamburgueria (`cfg/mensagens/hamburgueria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Hamburgueria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `hamburgueria:0`

```text
Opa, tudo bem? Aqui é o João. Vi a {nome} e lembrei do corre de atender no pico. Trabalhei 15 anos com restaurante em Porto Alegre.
{sinal}
No MyFoodLink, quem chama no WhatsApp já encontra o cardápio e pode falar com a equipe se precisar.
Posso te mostrar como fica?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `hamburgueria:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
Criei o MyFoodLink pra facilitar a rotina de quem toca restaurante. A hamburgueria pode receber pedido de delivery e retirada pelo próprio site.
Posso te mostrar como o cliente faz o pedido?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `hamburgueria:2`

```text
Opa, tudo bem? João aqui, do MyFoodLink. Passei 15 anos tocando restaurante.
{sinal}
Uma ideia pra quem já compra hambúrguer direto da casa é ter um cartão de fidelidade por selos no celular.
Posso te mostrar como o cliente ganha e usa os selos?
Se não quiser receber mais mensagens, responde SAIR.
```

### Churrascaria (`cfg/mensagens/churrascaria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Churrascaria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `churrascaria:0`

```text
Opa, aqui é o João. Vi a {nome}. Trabalhei 15 anos com gestão de restaurantes em Porto Alegre.
{sinal}
No MyFoodLink, a casa define as regras de reserva e o WhatsApp pode confirmar os horários disponíveis.
Posso te mostrar como fica pra quem quer reservar?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `churrascaria:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
Domingo com salão cheio já dá trabalho. No MyFoodLink, as reservas feitas pelo WhatsApp ficam numa agenda que a equipe pode consultar.
Posso te mostrar essa agenda?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `churrascaria:2`

```text
Opa, aqui é o João, do MyFoodLink. Trabalhei 15 anos com restaurante em Porto Alegre.
{sinal}
Pra casa que enche no fim de semana, dá pra organizar a fila de espera no QR Code e avisar pelo WhatsApp quando a mesa libera.
Posso te mostrar como funciona?
Se não quiser receber mais mensagens, responde SAIR.
```

### Japonês (`cfg/mensagens/japones.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Japonês** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `japones:0`

```text
Opa, aqui é o João. Vi a {nome} e queria te mostrar o MyFoodLink. Trabalhei 15 anos com restaurante aqui em Porto Alegre.
{sinal}
Com o menu do WhatsApp, quem chama já consegue abrir o cardápio com fotos antes de perguntar pelos pratos.
Posso te mostrar como fica?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `japones:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
No MyFoodLink, o cliente pode escolher os itens no cardápio da casa, pedir delivery ou retirada pelo site e pagar online.
Posso te mostrar esse caminho?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `japones:2`

```text
Opa, tudo bem? João aqui, do MyFoodLink. Vim da gestão de restaurantes aqui em Porto Alegre.
{sinal}
Quando alguém chama pra perguntar o que tem no combinado, a equipe pode ter o link do cardápio já no menu do WhatsApp e assumir a conversa quando precisar.
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
Pra quem trabalha com bolo e torta por encomenda, dá pra receber o pedido pelo site da casa, com cardápio e pagamento online.
Posso te mostrar como o cliente encomenda?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `padaria:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
Quando o balcão tá cheio, o menu do WhatsApp pode mostrar o cardápio logo de cara. Se alguém quiser tirar uma dúvida, a equipe assume.
Posso te mostrar como fica no MyFoodLink?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `padaria:2`

```text
Opa, tudo bem? João aqui, do MyFoodLink. Vim da gestão de restaurantes.
{sinal}
Pra quem tem cliente que passa toda semana no balcão, dá pra usar um cartão de selos no celular da pessoa.
Posso te mostrar como funciona a fidelidade?
Se não quiser receber mais mensagens, responde SAIR.
```

### Bar (`cfg/mensagens/bar.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Bar** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `bar:0`

```text
Opa, aqui é o João. Vi {nome}. Passei 15 anos na gestão de restaurantes em Porto Alegre.
{sinal}
No MyFoodLink, quem chama no WhatsApp pode consultar o cardápio ou reservar mesa. A casa define quais horários ficam disponíveis.
Posso te mostrar como fica a reserva?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `bar:1`

```text
Oi, aqui é o João. Vi {nome} no bairro {bairro}.
{sinal}
Quando o balcão tá cheio, uma reserva perdida no meio da conversa dá retrabalho. No MyFoodLink, os horários reservados ficam numa agenda pra equipe.
Posso te mostrar como fica?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `bar:2`

```text
Opa, aqui é o João, do MyFoodLink. Trabalhei 15 anos com restaurante.
{sinal}
Se costuma formar fila na porta, dá pra colocar o cliente na fila pelo QR Code e avisar no WhatsApp quando a mesa fica livre.
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
Criei o MyFoodLink pra facilitar coisas simples da rotina. Uma delas é o cartão de selos que fica no celular do cliente.
Posso te mostrar como ele ganha e troca os selos?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `lanchonete:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
Se a equipe vive mandando o mesmo cardápio pelo WhatsApp, dá pra colocar o link no menu automático. A equipe segue atendendo por ali quando precisa.
Posso te mostrar como fica no MyFoodLink?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `lanchonete:2`

```text
Opa, aqui é o João, do MyFoodLink. Vim da gestão de restaurantes em Porto Alegre.
{sinal}
Se tu recebe pedido pra buscar no balcão, dá pra abrir a retirada pelo site da casa e deixar o cliente pagar online.
Posso te mostrar como fica pra quem pede?
Se não quiser receber mais mensagens, responde SAIR.
```

### Restaurante e marmita (padrão) (`cfg/mensagens/restaurante.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Restaurante e marmita (padrão)** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `restaurante:0`

```text
Opa, tudo bem? Aqui é o João. Vi a {nome}. Trabalhei 15 anos na gestão de restaurantes em Porto Alegre.
{sinal}
No almoço, toda pergunta de cardápio tira alguém do que tá fazendo. No MyFoodLink, quem chama no WhatsApp já encontra o link do cardápio.
Posso te mostrar como fica?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `restaurante:1`

```text
Oi, aqui é o João. Vi a {nome} no bairro {bairro}.
{sinal}
Criei o MyFoodLink depois de 15 anos tocando restaurante. Se vocês recebem reservas pelo WhatsApp, dá pra confirmar nos horários que a casa libera e ver tudo numa agenda.
Posso te mostrar como funciona?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `restaurante:2`

```text
Opa, tudo bem? João aqui, do MyFoodLink. Vim da gestão de restaurantes.
{sinal}
Pra casa que vende marmita, dá pra oferecer pedido direto pelo site, com entrega ou retirada e pagamento online.
Posso te mostrar como fica pro cliente?
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
Vi que a {nome} já tem um canal de pedido. Criei o MyFoodLink e pensei que talvez faça sentido mostrar outra parte do que a gente faz, como reservas pelo WhatsApp ou fidelidade por selos.
Alguma dessas duas coisas te interessa?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `concorrente:1`

```text
Oi, aqui é o João, do MyFoodLink. Vim da gestão de restaurantes.
Se vocês já têm um sistema de pedidos, posso te mostrar separadamente como funciona o atendimento pelo WhatsApp no número da casa.
Faz sentido te mostrar essa parte?
Se não quiser receber mais mensagens, responde SAIR.
```

### Quem vende no iFood (`cfg/mensagens/ifood.md`)

**Quando usa:** lead com sinal **Vende no iFood** (se não usa concorrente).

**Variantes:** 2

#### Variante 0 — `ifood:0`

```text
Opa, aqui é o João. Trabalhei 15 anos com restaurante em Porto Alegre e vi a {nome}.
O MyFoodLink ajuda a ter um canal direto pra quem já conhece a casa. A pessoa pode pedir pelo teu site, com entrega ou retirada, enquanto tu mantém o iFood.
Posso te mostrar como fica esse pedido?
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `ifood:1`

```text
Oi, aqui é o João, do MyFoodLink. Vim da gestão de restaurantes.
Se tu usa iFood e quer receber também pelo site da casa, o MyFoodLink cobra mensalidade, sem comissão do MyFoodLink por pedido. O meio de pagamento tem as próprias taxas.
Posso te mostrar como o cliente pede e paga?
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
Opa, João aqui de novo. Se tu já tem cardápio online, vale deixar o link no perfil do WhatsApp. Quem chama pode achar o cardápio antes de perguntar.
Se quiser ver como isso fica no menu do MyFoodLink, me chama.
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `d3:1`

```text
Oi, tudo bem? No WhatsApp Business, dá pra salvar as respostas que mais se repetem, tipo cardápio, horário e endereço. Ajuda quando tem muita conversa aberta.
Se quiser ver o atendimento do MyFoodLink, tô por aqui.
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `d3:2`

```text
Opa, João aqui. Se vocês pegam reservas no WhatsApp, vale pedir dia, horário e número de pessoas na mesma mensagem. Já economiza algumas idas e vindas.
Se quiser ver como o MyFoodLink organiza as reservas, me chama.
Se não quiser receber mais mensagens, responde SAIR.
```

### Lembrete D7 (`cfg/mensagens/d7.md`)

**Quando usa:** 7º dia sem resposta. Última mensagem desta rodada de contato.

**Variantes:** 3

#### Variante 0 — `d7:0`

```text
Opa, João aqui. Vou deixar esse assunto por aqui. Se tu quiser ver como ficaria o atendimento do MyFoodLink no WhatsApp da casa, é só me chamar.
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 1 — `d7:1`

```text
Oi, tudo bem? Passando só pra fechar esse contato. Se quiser conversar sobre cardápio, reservas ou pedido direto mais pra frente, pode falar comigo por aqui.
Se não quiser receber mais mensagens, responde SAIR.
```

#### Variante 2 — `d7:2`

```text
Valeu, vou encerrar por aqui. Se em outro momento tu quiser experimentar o MyFoodLink, me chama e te explico como começar.
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
Claro! No MyFoodLink, quem chama no WhatsApp da casa pode abrir o cardápio, fazer uma reserva ou falar com a equipe. Se tu quer vender pelo próprio site, o Pro inclui pedidos e pagamento online.
Aqui dá pra conhecer melhor: https://www.myfoodlink.com.br

O que tu quer ver primeiro? Se fizer sentido pra tua casa, te ajudo a configurar e tu pode testar por 30 dias grátis, sem contrato mínimo.
```

### Quando pergunta preço (`cfg/mensagens/preco.md`)

**Quando usa:** resposta classificada como `preco`. Para uma pergunta sobre PDV, apresente o Gestor separadamente.

**Variantes:** 1

#### Variante 0 — `preco:0`

```text
O Start fica R$ 149 por mês e inclui atendimento e reservas no WhatsApp, cardápio digital e fidelidade.
O Pro fica R$ 299 por mês e inclui também delivery, retirada e encomendas pelo site, com pagamento online.

São 30 dias grátis pra testar, sem taxa de implantação e sem contrato mínimo. Tu tá procurando mais ajuda com o atendimento ou quer receber pedidos pelo site também?
```

### Quando já tem sistema (`cfg/mensagens/ja_tenho.md`)

**Quando usa:** resposta classificada como `ja_tenho`.

**Variantes:** 1

#### Variante 0 — `ja_tenho:0`

```text
Boa! Qual sistema vocês usam hoje? Se ele já resolve os pedidos, posso te mostrar só a parte que fizer sentido pra tua casa, como reservas pelo WhatsApp ou fidelidade por selos.
```

---

## 5. Como continuar a conversa

Use estes exemplos manualmente, conforme o que a pessoa respondeu.

**Quando a pessoa só diz “pode mandar”**

> Claro, aqui tá o site: https://www.myfoodlink.com.br. Se tu quiser, te mostro a parte que comentei e como ela ficaria na tua casa.

**Quando a pessoa quer testar**

> Fechou. Por onde tu quer começar? Posso te ajudar a montar o cardápio e o atendimento ou configurar o pedido online, se for o que a tua casa precisa.

**Quando a pessoa pergunta por PDV**

> Aí tem o Gestor, que fica R$ 499 por mês. Ele inclui caixa, salão e cozinha. A implantação é assistida e usa um servidor local na casa. Me conta como vocês usam o caixa e as comandas hoje pra eu entender se encaixa.
