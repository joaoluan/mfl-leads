# mfl-leads — regras para agentes

Esteira local de leads B2B do MyFoodLink. Spec viva: `docs/SPEC.md` (Parte A prevalece sobre a Parte B). Ler antes de mexer.

- Construção em fases (SPEC, Parte A, "Fases"). Parar ao fim de cada fase, abrir PR e esperar o usuário testar e mesclar.
- O sistema **nunca envia mensagem**. Quem envia é o usuário, pelo WhatsApp Web. A Evolution só lê.
- Conversas do WhatsApp pessoal: só gravar mensagens de números que já são lead. O resto é descartado sem persistir.
- Python 3.12 com `uv`. Sem `print` (usar structlog). Escrita em SQLite em lote de 100 e com `busy_timeout=5000`.
- Dependência entra só na fase que precisa dela.
- Testes: `uv run pytest`. Nunca usar dado real de lead em teste ou fixture.
- pode sempre abrir pr e fazer o merge na main
