---
name: friday-pedidos
description: Atender os pedidos de evolução que a FRIDAY abre sozinha (pasta Pedidos do cofre) com o Claude Code. Use no início da sessão quando o resumo mostrar pedidos abertos.
---
# Pedidos de evolução

A FRIDAY abre um pedido quando percebe que lhe falta uma capacidade (por exemplo, visão). Eles ficam em `FRIDAY/Pedidos/` no cofre e aparecem no resumo do início da sessão.
1. Leia o pedido e confirme com o usuário o que ele quer (nada é feito sem aprovação dele).
2. Planeje a mudança respeitando as regras do `CLAUDE.md` (corretor, quarentena, honestidade).
3. Implemente com testes (`friday-testar`); nova ferramenta: `friday-nova-ferramenta`.
4. Quando o usuário aprovar, marque o pedido como atendido (uma linha datada na própria nota) e diga a ele o que mudou e o que ainda não foi testado no celular.
