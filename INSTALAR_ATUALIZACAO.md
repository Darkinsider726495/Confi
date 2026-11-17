# FRIDAY — instalar esta atualização no celular (Termux)

Esta versão traz: auditoria da fase 3, núcleo com o sistema distribuído e a autonomia total, neurônios que trabalham sozinhos,
assimilação (cada fala vira sinapse e a frase é descartada), conversa a partir do que ela aprendeu, lembranças de conversas
profundas e a conexão com a LLM grande (Groq).

O que **não** vem no zip e continua o seu: `.env` (chaves), `cofre/` (memória), `android/`, `voz/`. O atualizador não toca nisso.

---

## 1. Pôr o zip no celular
Baixe o `FRIDAY-atualizada.zip` para a pasta **Downloads** do celular.

## 2. Aplicar a atualização (no Termux)
Entre na pasta da FRIDAY (a mesma onde ela já está instalada) e rode:
```bash
termux-setup-storage          # só se o Termux ainda não tiver acesso aos arquivos (aceite o pedido)
bash termux/atualizar.sh ~/storage/downloads/FRIDAY-atualizada.zip
```
O atualizador:
- faz uma **cópia de segurança** do que você tinha (`~/friday-backup-DATA.tar.gz`);
- copia o código novo **sem tocar** em `.env`, `cofre/`, auditoria e tokens;
- instala as dependências, roda o diagnóstico e **reinicia** a FRIDAY.

> Se você usa git na pasta, pode trocar este passo por `git pull`.

## 3. Ligar a LLM grande (Groq, grátis)
1. **Se você já mandou alguma chave no chat, cancele-a** (console.groq.com → ☰ → API Keys → lixeira) e crie uma nova.
2. No Termux, na pasta da FRIDAY:
   ```bash
   python scripts/conectar_groq.py
   ```
3. Cole a chave nova quando pedir (ela **não aparece** na tela — é normal) e aperte Enter.
4. Deve aparecer `✅ Conectada!`. Então:
   ```bash
   bash termux/atualizar.sh --reiniciar
   ```
Se aparecer `❌`, mande um print (o script nunca mostra a chave).

## 3b. Rede neural (significado dos assuntos)
```bash
pkg install -y python-numpy tur-repo
pkg install -y python-onnxruntime python-tokenizers            # o Transformer (o pip não tem onnxruntime para Android)
mkdir -p modelos_ia
unzip ~/storage/downloads/FRIDAY-modelo-significado.zip -d modelos_ia/
python -c "import sys; sys.path.insert(0,'friday'); import significado as S; print(S.motor(), round(S.parecenca('sql','banco de dados'),2))"
```
Esperado: `transformer 0.66`. Sem o zip do modelo, ela usa a rede própria (treine com `python scripts/treinar_significado.py --pretreino`).
Se o `pkg` reclamar de `curl` («CANNOT LINK EXECUTABLE»), rode antes `apt update && apt full-upgrade -y`.
Depois ela se reajusta sozinha a cada 6 h. Pergunte: «o que é parecido com treino?». Corrija: «treino não tem nada a ver com prova».

## 3c. GRU da rotina (atualização 5)
```bash
pkg install -y python-numpy
python scripts/treinar_rotina.py       # nos primeiros dias: «preciso de pelo menos 7 dias»; depois treina sozinha 1x/dia
```
Pergunte: «como é a minha rotina?» ou «o que você acha que eu vou fazer agora?». Detalhes em `docs/ROTINA.md` e no guia em PDF.

## 4. Conferir que está tudo certo (opcional, ~2 min)
```bash
python -m compileall -q friday
python -m unittest discover -s tests -p 'test_*.py'
```
Esperado: **1 falha** só (`test_nunca_apaga`, aceita pelo dono). Qualquer outra falha: mande o print.

## 5. Ligar o que é por voz (só você liga)
| Diga | O que faz |
|---|---|
| **«pode puxar assunto»** | ela conversa sozinha: lembranças do que aprendeu, retoma conversas profundas |
| **«liga a autonomia total»** | os neurônios trabalham sozinhos e ela faz os próprios objetivos de nível 1 sem esperar você (nível 2+ continua pedindo) |
| «como está a autonomia total?» | ela diz se está ligada e o que está rodando |
| «desliga a autonomia total» / «não puxe assunto» | volta ao normal |

## 6. Comandos novos para conversar com ela
| Diga | O que faz |
|---|---|
| «no que você está focada?» | foco + o que o núcleo notou + atividades registradas hoje |
| «o que você percebeu?» | padrões que ela descobriu sozinha (sinapses fortes) |
| «quais são as suas lembranças?» | assuntos de conversas profundas que ela guardou |
| «do que você lembra sobre o projeto?» | a essência que ela guardou daquela conversa |
| «esqueça a lembrança sobre X» | vai para `Arquivo/` (nada é apagado) |

## 7. Parar (sempre seu)
```bash
bash termux/parar.sh          # para agora
bash termux/supervisor.sh     # liga de novo
```

## Configurações novas (opcionais, no `.env`)
| Variável | Padrão | Para quê |
|---|---|---|
| `MEMORIA_DIARIO` | `assuntos` | diário só com assuntos; `completo` = frase inteira; `desligado` |
| `ASSIMILAR` | `1` | `0` desliga a assimilação |
| `ASSIMILAR_IA` | `1` | `0` tira os assuntos sem IA (offline, sem gastar limite) |
| `IA_MODO` | `auto` | `auto` (nuvem com reserva local), `nuvem`, `local` |

## O que não foi testado
Tudo foi testado num Linux na nuvem (1531 testes), não no seu celular: Termux:API, microfone, câmera, a Groq de verdade e o
desempenho no aparelho só dá para conferir aí. Se algo sair diferente, mande o print.
