// Gestos das mãos com pontos inventados (sem câmera): node tests/maos_gestos_node.js
const assert = require('assert');
const G = require('../friday/static/maos/maos_gestos.js');

// uma mão em pé: pulso embaixo, dedos para cima. `dedos` = quais estão esticados ('i','m','a','p'); `pinca` junta o polegar na ponta do indicador.
function mao({ dedos = '', pinca = false, gira = 0, cx = 0.5 } = {}) {
  const p = new Array(21);
  const pulso = { x: cx, y: 0.9, z: 0 };
  p[0] = pulso;
  const base = { i: 5, m: 9, a: 13, p: 17 }, dx = { i: -0.06, m: -0.02, a: 0.02, p: 0.06 };
  for (const f of 'imap') {
    const b = base[f], x = cx + dx[f], est = dedos.includes(f);
    p[b] = { x, y: 0.72, z: 0 };                      // articulação da base
    p[b + 1] = { x, y: 0.6, z: 0 };                   // articulação do meio
    p[b + 2] = { x, y: est ? 0.4 : 0.74, z: 0 };      // ponta: esticada vai longe do pulso, dobrada volta perto da palma
    p[b + 3] = p[b + 2];
  }
  p[1] = { x: cx - 0.08, y: 0.85, z: 0 }; p[2] = { x: cx - 0.1, y: 0.78, z: 0 }; p[3] = { x: cx - 0.1, y: 0.7, z: 0 };
  p[4] = pinca ? { x: p[8].x + 0.01, y: p[8].y + 0.01, z: 0 } : { x: cx - 0.2, y: 0.7, z: 0 };
  if (!gira) return p;
  return p.map((q) => {                               // gira a mão inteira em volta do pulso (mão de lado ou inclinada)
    const x = q.x - pulso.x, y = q.y - pulso.y, c = Math.cos(gira), s = Math.sin(gira);
    return { x: pulso.x + x * c - y * s, y: pulso.y + x * s + y * c, z: 0 };
  });
}

const punho = (o) => mao({ dedos: '', ...o }), palma = (o) => mao({ dedos: 'imap', ...o }), aponta = (o) => mao({ dedos: 'i', ...o }), pinca = (o) => mao({ dedos: 'i', pinca: true, ...o });

// leitura de uma mão
assert.deepStrictEqual(G.mao(punho()), { fechada: true, aberta: false, pinca: false, apontar: false });
assert.strictEqual(G.mao(palma()).aberta, true);
assert.strictEqual(G.mao(palma()).fechada, false);
assert.strictEqual(G.mao(aponta()).apontar, true);
assert.strictEqual(G.mao(aponta()).aberta, false);
assert.strictEqual(G.mao(pinca()).pinca, true);
assert.strictEqual(G.mao(aponta()).pinca, false);

// as seis ações (mão esquerda, direita)
const casos = [
  [punho(), punho(), 'reiniciar'],            // dois punhos
  [palma(), palma(), 'girar'],                // duas palmas
  [pinca(), aponta(), 'apagar'],              // pinça da esquerda + indicador da direita
  [null, pinca(), 'construir'],               // pinça da direita
  [palma(), pinca(), 'construir'],            // com a esquerda aberta também constrói
  [punho(), pinca(), 'agarrar'],              // esquerda fechada segura o mundo: construir fica desligado (como no original)
  [punho(), null, 'agarrar'],
  [null, palma(), 'fixar'],                   // palma da direita
  [null, null, 'nenhum'],
  [aponta(), null, 'nenhum'],
];
for (const [e, d, esperado] of casos) assert.strictEqual(G.modo(e, d), esperado, `esperava ${esperado}`);

// a mão de lado ou de cabeça para baixo faz o mesmo gesto (melhoria sobre o original, que comparava alturas na imagem)
for (const ang of [Math.PI / 2, -Math.PI / 2, Math.PI, 0.6, -0.6]) {
  assert.strictEqual(G.mao(punho({ gira: ang })).fechada, true, `punho girado ${ang}`);
  assert.strictEqual(G.mao(palma({ gira: ang })).aberta, true, `palma girada ${ang}`);
  assert.strictEqual(G.modo(punho({ gira: ang }), punho({ gira: ang })), 'reiniciar');
  assert.strictEqual(G.modo(palma({ gira: ang }), palma({ gira: ang })), 'girar');
}

// entrada ruim nunca quebra
for (const ruim of [undefined, null, [], new Array(20).fill({ x: 0, y: 0 }), 'x', 7, {}, Array.from({ length: 21 }, () => ({ x: NaN, y: 0 })), Array.from({ length: 21 }, () => null)]) {
  assert.strictEqual(G.mao(ruim), null);
  assert.strictEqual(G.modo(ruim, ruim), 'nenhum');
}
assert.strictEqual(G.valida(palma()), true);
console.log('gestos ok:', casos.length, 'combinações,', 5 * 4, 'giros');
