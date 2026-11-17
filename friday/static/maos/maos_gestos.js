/* Gestos das mãos da FRIDAY — funções puras, sem câmera e sem DOM (por isso dá para testar com pontos inventados).
 * Entrada: 21 pontos de uma mão no formato do MediaPipe Hands ({x, y, z} entre 0 e 1; y cresce para baixo).
 * Baseado na linguagem de gestos do Voxel Architect (github.com/DEVNEPTUNE/potential-palm-tree), com uma mudança: o dedo
 * "esticado" é medido pela distância até o pulso, e não pela altura na imagem, então a mão funciona de lado ou inclinada. */
(function (raiz) {
  'use strict';
  var PULSO = 0, POLEGAR = 4, INDICE = [5, 6, 8], MEDIO = [9, 10, 12], ANELAR = [13, 14, 16], MINDINHO = [17, 18, 20];
  var LIMIAR_PINCA = 0.05;                       // polegar e indicador tão perto quanto o repositório original

  function dist(a, b) {
    var dz = (a.z !== undefined && b.z !== undefined) ? (a.z - b.z) : 0;
    return Math.sqrt((a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y) + dz * dz);
  }
  function valida(lm) {
    if (!lm || lm.length !== 21) return false;
    for (var i = 0; i < 21; i++) { var p = lm[i]; if (!p || !isFinite(p.x) || !isFinite(p.y)) return false; }
    return true;
  }
  // dedo esticado: a ponta está mais longe do pulso do que a articulação do meio do dedo
  function esticado(lm, dedo) { return dist(lm[PULSO], lm[dedo[2]]) > dist(lm[PULSO], lm[dedo[1]]) * 1.05; }

  function mao(lm) {
    if (!valida(lm)) return null;
    var i = esticado(lm, INDICE), m = esticado(lm, MEDIO), a = esticado(lm, ANELAR), p = esticado(lm, MINDINHO);
    return {
      fechada: !i && !m && !a,                   // punho (indicador, médio e anelar dobrados)
      aberta: i && m && p,                       // palma aberta
      pinca: dist(lm[POLEGAR], lm[8]) < LIMIAR_PINCA,
      apontar: i && !m                           // só o indicador
    };
  }

  // a mão esquerda e a direita juntas -> o que o Voxel Architect chama de modo
  function modo(esq, dir) {
    var e = mao(esq), d = mao(dir);
    if (e && d && e.fechada && d.fechada) return 'reiniciar';     // dois punhos (segura para valer)
    if (e && d && e.aberta && d.aberta) return 'girar';           // duas palmas
    if (e && e.pinca && d && d.apontar && !d.aberta) return 'apagar';
    if (d && d.pinca && !(e && e.fechada) && !d.aberta) return 'construir';
    if (e && e.fechada) return 'agarrar';
    if (d && d.aberta) return 'fixar';                            // palma direita: transforma o esboço em blocos
    return 'nenhum';
  }

  var api = { dist: dist, mao: mao, modo: modo, valida: valida, LIMIAR_PINCA: LIMIAR_PINCA };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else raiz.MaosGestos = api;
})(typeof self !== 'undefined' ? self : this);
