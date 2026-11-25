# Mensagens do MyFoodLink — catálogo completo

> Gerado a partir de `cfg/mensagens/*.md` em 2026-11-25. Se editar os textos pelo `/config`, este arquivo fica desatualizado.
> O sistema **não envia nada**: ele sugere o texto e monta o link do WhatsApp Web; quem envia é o João.

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

### Pizzaria (`cfg/mensagens/pizzaria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Pizzaria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `pizzaria:0`

```text
Oi, pessoal da {nome}! Sou o João, toquei restaurante 15 anos aqui em POA.
{sinal}
Pizzaria vive de pedido no WhatsApp na sexta à noite. O MyFoodLink atende, monta o pedido e manda pra cozinha, e o delivery é sem comissão.
Posso liberar 30 dias grátis pra vocês testarem?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `pizzaria:1`

```text
Oi! Vi a {nome} aí no {bairro}.
{sinal}
Pergunta direta: no pico de sexta, vocês conseguem responder todo mundo no WhatsApp a tempo?
Tenho um sistema que faz isso e libero 30 dias grátis. Topa testar?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `pizzaria:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante em POA.
{sinal}
Cardápio digital, pedido pelo WhatsApp e delivery próprio sem taxa de app, pensado pra pizzaria.
Quer usar 30 dias grátis na {nome}?
Se não quiser mais mensagens, responde SAIR.
```

### Hamburgueria (`cfg/mensagens/hamburgueria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Hamburgueria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `hamburgueria:0`

```text
Oi, pessoal da {nome}! Sou o João, 15 anos de restaurante em POA.
{sinal}
Hamburgueria paga caro em comissão de app. Com o MyFoodLink o cliente pede direto pelo WhatsApp e o delivery é sem comissão.
Posso liberar 30 dias grátis pra vocês testarem?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `hamburgueria:1`

```text
Oi! Vi a {nome} aí no {bairro}.
{sinal}
Pergunta rápida: quanto do delivery de vocês hoje passa por app com comissão?
Tenho um jeito de trazer esse pedido pro WhatsApp de vocês, e libero 30 dias grátis pra testar. Topa?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `hamburgueria:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Cardápio com foto, combos, pedido pelo WhatsApp e pagamento online, sem taxa por pedido.
Quer usar 30 dias grátis na {nome}?
Se não quiser mais mensagens, responde SAIR.
```

### Churrascaria (`cfg/mensagens/churrascaria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Churrascaria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `churrascaria:0`

```text
Oi, pessoal da {nome}! Sou o João, toquei restaurante 15 anos em POA.
{sinal}
Churrascaria vive de reserva e de cliente que volta. O MyFoodLink atende reserva pelo WhatsApp e tem fidelidade pra trazer o cliente de novo.
Posso liberar 30 dias grátis pra vocês testarem?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `churrascaria:1`

```text
Oi! Vi a {nome} aí no {bairro}.
{sinal}
Pergunta direta: as reservas de fim de semana chegam pelo WhatsApp e alguém confirma na mão?
Tenho um sistema que faz isso sozinho e libero 30 dias grátis. Topa testar?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `churrascaria:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Reserva, cardápio digital, fidelidade e delivery sem comissão, tudo pelo WhatsApp da casa.
Quer usar 30 dias grátis na {nome}?
Se não quiser mais mensagens, responde SAIR.
```

### Japonês (`cfg/mensagens/japones.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Japonês** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `japones:0`

```text
Oi, pessoal da {nome}! Sou o João, 15 anos de restaurante em POA.
{sinal}
Pedido de japonês é cheio de detalhe: combo, peça, troca. O MyFoodLink monta isso pelo WhatsApp com cardápio com foto, e o delivery é sem comissão.
Posso liberar 30 dias grátis pra vocês testarem?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `japones:1`

```text
Oi! Vi a {nome} aí no {bairro}.
{sinal}
Pergunta rápida: quanto tempo leva hoje pra fechar um pedido de combo pelo WhatsApp?
Tenho um sistema que encurta isso e libero 30 dias grátis. Topa testar?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `japones:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Cardápio digital com foto, pedido pelo WhatsApp e pagamento online, sem taxa por pedido.
Quer usar 30 dias grátis na {nome}?
Se não quiser mais mensagens, responde SAIR.
```

### Padaria e doceria (`cfg/mensagens/padaria.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Padaria e doceria** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `padaria:0`

```text
Oi, pessoal da {nome}! Sou o João, toquei restaurante 15 anos em POA.
{sinal}
Encomenda de bolo e torta pelo WhatsApp dá trabalho de anotar. O MyFoodLink recebe a encomenda com cardápio digital e organiza tudo.
Posso liberar 30 dias grátis pra vocês testarem?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `padaria:1`

```text
Oi! Vi a {nome} aí no {bairro}.
{sinal}
Pergunta direta: as encomendas de vocês ainda são anotadas na mão a partir do WhatsApp?
Tenho um sistema que organiza isso e libero 30 dias grátis. Topa testar?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `padaria:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Encomendas e pedidos pelo WhatsApp, cardápio digital com foto e fidelidade pro cliente voltar.
Quer usar 30 dias grátis na {nome}?
Se não quiser mais mensagens, responde SAIR.
```

### Bar (`cfg/mensagens/bar.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Bar** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `bar:0`

```text
Oi, pessoal do {nome}! Sou o João, toquei restaurante 15 anos em POA.
{sinal}
O MyFoodLink atende reserva de mesa pelo WhatsApp e tem cardápio digital no QR code, sem app pra baixar.
Posso liberar 30 dias grátis pra vocês testarem?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `bar:1`

```text
Oi! Vi o {nome} aí no {bairro}.
{sinal}
Pergunta rápida: as reservas de sexta e sábado chegam pelo WhatsApp e alguém confirma na mão?
Tenho um sistema que faz isso sozinho e libero 30 dias grátis. Topa testar?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `bar:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Reserva pelo WhatsApp, cardápio digital no QR e fidelidade, sem taxa por pedido.
Quer usar 30 dias grátis no {nome}?
Se não quiser mais mensagens, responde SAIR.
```

### Lanchonete e café (`cfg/mensagens/lanchonete.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Lanchonete e café** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `lanchonete:0`

```text
Oi, pessoal da {nome}! Sou o João, 15 anos de restaurante em POA.
{sinal}
O MyFoodLink recebe pedido pelo WhatsApp com cardápio digital e tem fidelidade, tipo cartão de carimbo, só que no celular do cliente.
Posso liberar 30 dias grátis pra vocês testarem?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `lanchonete:1`

```text
Oi! Vi a {nome} aí no {bairro}.
{sinal}
Pergunta rápida: vocês têm algum jeito de fazer o cliente voltar mais vezes, tipo fidelidade?
Tenho um sistema simples pra isso e libero 30 dias grátis. Topa testar?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `lanchonete:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Cardápio digital, pedido pelo WhatsApp e fidelidade, sem taxa por pedido.
Quer usar 30 dias grátis na {nome}?
Se não quiser mais mensagens, responde SAIR.
```

### Restaurante e marmita (padrão) (`cfg/mensagens/restaurante.md`)

**Quando usa:** 1ª mensagem para lead da categoria **Restaurante e marmita (padrão)** sem sinal de concorrente/iFood.

**Variantes:** 3

#### Variante 0 — `restaurante:0`

```text
Oi, pessoal da {nome}! Sou o João, toquei restaurante 15 anos em POA.
{sinal}
O MyFoodLink atende o WhatsApp da casa, manda o cardápio do dia e recebe pedido e marmita sem ninguém parar pra digitar.
Posso liberar 30 dias grátis pra vocês testarem?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `restaurante:1`

```text
Oi! Vi a {nome} aí no {bairro}.
{sinal}
Pergunta direta: no horário do almoço, quem responde o WhatsApp de vocês?
Tenho um sistema que faz isso sozinho e libero 30 dias grátis. Topa testar?
Se preferir não receber, responde SAIR.
```

#### Variante 2 — `restaurante:2`

```text
Oi, tudo bem? João aqui, criei o MyFoodLink depois de 15 anos tocando restaurante.
{sinal}
Atendimento e pedido pelo WhatsApp, cardápio digital, fidelidade e delivery sem comissão.
Quer usar 30 dias grátis na {nome}?
Se não quiser mais mensagens, responde SAIR.
```

---

## 2. Primeira mensagem (D0) — por sinal (tem prioridade sobre o tipo de lugar)

### Quem usa concorrente (`cfg/mensagens/concorrente.md`)

**Quando usa:** lead com sinal **Usa concorrente** (vence tudo).

**Variantes:** 2

#### Variante 0 — `concorrente:0`

```text
Oi, pessoal da {nome}! Sou o João, toquei restaurante 15 anos aqui em POA.
Vi que vocês já recebem pedido por um sistema. Criei o MyFoodLink pra quem quer pedido pelo WhatsApp com atendimento automático e delivery sem comissão.
Se um dia pensarem em trocar, libero 30 dias grátis pra comparar lado a lado. Posso te mostrar?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `concorrente:1`

```text
Oi! Vi a {nome} aí no {bairro}.
Vocês já usam sistema de pedido, né? Pergunta sincera: tá atendendo bem no pico ou ainda escapa pedido no WhatsApp?
Tenho um sistema feito por quem tocou restaurante e libero 30 dias grátis pra testar junto com o atual. Topa?
Se preferir não receber, responde SAIR.
```

### Quem vende no iFood (`cfg/mensagens/ifood.md`)

**Quando usa:** lead com sinal **Vende no iFood** (se não usa concorrente).

**Variantes:** 2

#### Variante 0 — `ifood:0`

```text
Oi, pessoal da {nome}! Sou o João, toquei restaurante 15 anos aqui em POA.
Vi que vocês vendem no iFood. Criei o MyFoodLink pra casa ter o próprio canal de pedido pelo WhatsApp, sem comissão por pedido.
O cliente que já conhece vocês pede direto e a taxa fica no caixa. Posso liberar 30 dias grátis pra testarem?
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `ifood:1`

```text
Oi! Vi a {nome} aí no {bairro}.
Pergunta direta: quanto do faturamento vai pra comissão do iFood todo mês?
Tenho um sistema de pedido direto pelo WhatsApp, sem comissão, feito por quem tocou restaurante. Libero 30 dias grátis pra testar. Topa?
Se preferir não receber, responde SAIR.
```

---

## 3. Lembretes (sem resposta)

### Lembrete D3 (`cfg/mensagens/d3.md`)

**Quando usa:** 3º dia depois da 1ª mensagem, sem resposta. Igual para todos os tipos de lugar.

**Variantes:** 3

#### Variante 0 — `d3:0`

```text
Só um dado rápido: cliente que manda mensagem e espera muito pede em outro lugar. Responder na hora é exatamente o que o MyFoodLink automatiza.
Os 30 dias grátis continuam valendo. Se não quiser receber, responde SAIR.
```

#### Variante 1 — `d3:1`

```text
Lembrei de ti: comissão de app come uma boa parte de cada pedido. No MyFoodLink o pedido direto pelo WhatsApp é teu, sem comissão.
Quer testar 30 dias grátis? Se não quiser receber, responde SAIR.
```

#### Variante 2 — `d3:2`

```text
Pergunta curta: quem responde o WhatsApp da casa hoje, tu ou alguém da equipe?
Se for no braço, dá pra automatizar e testar 30 dias grátis. Se não quiser receber, responde SAIR.
```

### Lembrete D7 (`cfg/mensagens/d7.md`)

**Quando usa:** 7º dia sem resposta. Última mensagem da cadência; propõe conversa de 15 min.

**Variantes:** 3

#### Variante 0 — `d7:0`

```text
Última mensagem, prometo. Posso te mostrar o MyFoodLink em 15 minutos, {horario}? Se for melhor outro horário, me diz qual.
Se não quiser receber, responde SAIR.
```

#### Variante 1 — `d7:1`

```text
Que tal 15 minutos {horario}? Te mostro como fica o atendimento da tua casa no WhatsApp e já deixo os 30 dias grátis prontos.
Se não quiser receber, responde SAIR.
```

#### Variante 2 — `d7:2`

```text
Tenho um horário {horario} pra uma conversa de 15 minutos. Serve? Se não, sem problema: responde SAIR que eu não mando mais.
```

---

## 4. Respostas prontas (quando o lead responde)

A resposta do lead é classificada por palavra-chave (`src/mfl/classifica.py`, primeira regra que casar vence) e o João confirma na UI:

| Ordem | Classe | Exemplos que casam | Status do lead | Resposta sugerida |
|---|---|---|---|---|
| 1 | `opt_out` | "não manda mais", "para de mandar", "me tira", "descadastrar", ou só "sair/pare/stop/remover/cancelar" | Pediu SAIR (automático) | nenhuma |
| 2 | `nao` | "não tenho interesse", "não quero", "não preciso", "sem interesse", "dispenso" | Frio | nenhuma |
| 3 | `ja_tenho` | "já tenho/uso/temos", "trabalhamos com", Goomer, Saipos, Anota Aí, LeadsFood, Consumer, Linx, MenuDino, Cardápio Web | Já tem sistema (objeção) | `ja_tenho` |
| 4 | `preco` | "quanto custa/é/sai/fica", "valor", "preço", "mensalidade", "plano(s)" | Respondeu | `preco` |
| 5 | `interesse` | "tenho interesse", "quero", "como funciona", "me explica", "pode ser", "bora", "vamos", "testar", "manda", "sim", "claro" | Respondeu | `interesse` |
| — | `outro` | nada casou | não muda | nenhuma |

### Quando tem interesse (`cfg/mensagens/interesse.md`)

**Quando usa:** resposta classificada como `interesse`.

**Variantes:** 1

#### Variante 0 — `interesse:0`

```text
Show! Dá uma olhada: https://www.myfoodlink.com.br

Se curtir, eu mesmo configuro e te libero 30 dias grátis, sem contrato. Qual o nome da tua casa?
```

### Quando pergunta preço (`cfg/mensagens/preco.md`)

**Quando usa:** resposta classificada como `preco`. `{horario}` vira o próximo dia útil às 15h.

**Variantes:** 1

#### Variante 0 — `preco:0`

```text
São três planos, sem contrato mínimo e sem taxa de implantação:
- Start, R$149/mês: atendimento e reservas no WhatsApp, cardápio digital e fidelidade
- Pro, R$299/mês: tudo do Start mais delivery com pagamento online
- Gestor, R$499/mês: PDV com salão, comanda, cozinha, estoque e financeiro
Os primeiros 30 dias são grátis. Posso te mostrar em 15 minutos {horario}?
```

### Quando já tem sistema (`cfg/mensagens/ja_tenho.md`)

**Quando usa:** resposta classificada como `ja_tenho`.

**Variantes:** 1

#### Variante 0 — `ja_tenho:0`

```text
Legal! Qual sistema vocês usam hoje? E o que mais falta nele, ou o que mais incomoda?
Pergunto porque muita gente troca por causa de comissão ou de atendimento no WhatsApp que não é automático. Se fizer sentido, te libero 30 dias grátis pra comparar.
```
