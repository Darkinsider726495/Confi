/* Mãos da FRIDAY — modelagem 3D com gestos, no navegador.
 * Adaptado do Voxel Architect v4.1 (github.com/DEVNEPTUNE/potential-palm-tree): MediaPipe Hands + Three.js.
 * O que mudou para a FRIDAY: tudo roda offline (bibliotecas em /static/maos), o relógio dos tempos de segurar usa o tempo real,
 * a câmera é fechada ao sair da página, os gestos viram só NOMES numa lista fixa (nunca imagem nem pontos) e o que você
 * constrói pode ser salvo como modelo 3D (nada é apagado: reiniciar a cena salva antes um rascunho). */
(function () {
  'use strict';
  var G = window.MaosGestos;
  var $ = function (id) { return document.getElementById(id); };
  var T = '';
  try { T = localStorage.getItem('friday_t') || ''; } catch (_) {}

  var GRADE = 1.2;                               // tamanho do bloco (gridSize do original)
  var SEGURAR = { agarrar: 500, construir: 500, apagar: 500, reiniciar: 1000, girar: 1000 };   // ms, como o original
  var MAX_BLOCOS = 20000;

  var estado = { pronto: false, erro: '', camera: false, modo: 'nenhum', maos: 0, quadros: 0, blocos: 0, gestos: [], salvo: 0 };
  window.__maos = estado;                        // só leitura: usado pelos testes e pelo painel de diagnóstico

  // ------------------------------------------------------------------ cena 3D
  var video = $('video'), cv3 = $('tres'), bio = $('bio'), bctx = bio.getContext('2d');
  var cena = new THREE.Scene();
  var cam = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.1, 1000);
  var rend = new THREE.WebGLRenderer({ canvas: cv3, antialias: true, alpha: true });
  rend.setSize(innerWidth, innerHeight);
  var grupo = new THREE.Group(); cena.add(grupo);
  var esboco = new THREE.Group(); grupo.add(esboco);
  var colocados = new Map();
  var mira = new THREE.Mesh(new THREE.BoxGeometry(GRADE, GRADE, GRADE), new THREE.MeshBasicMaterial({ color: 0x00f0ff, wireframe: true, transparent: true, opacity: 0.5 }));
  cena.add(mira);
  cena.add(new THREE.AmbientLight(0xffffff, 0.5));
  var sol = new THREE.DirectionalLight(0x00f0ff, 1.0); sol.position.set(5, 5, 5); cena.add(sol);
  cam.position.z = 20;
  addEventListener('resize', function () { cam.aspect = innerWidth / innerHeight; cam.updateProjectionMatrix(); rend.setSize(innerWidth, innerHeight); });

  var geoFinal = new THREE.BoxGeometry(GRADE * 0.95, GRADE * 0.95, GRADE * 0.95);
  var geoBorda = new THREE.EdgesGeometry(geoFinal);
  var matFinal = new THREE.MeshPhongMaterial({ color: 0x001122, emissive: 0x00f0ff, emissiveIntensity: 0.4, transparent: true, opacity: 0.8 });
  var matBorda = new THREE.LineBasicMaterial({ color: 0x00f0ff });
  var geoEsboco = new THREE.BoxGeometry(GRADE * 0.98, GRADE * 0.98, GRADE * 0.98);
  var matEsboco = new THREE.MeshBasicMaterial({ color: 0x00f0ff, wireframe: true });

  function chave(x, y, z) { return x.toFixed(1) + ',' + y.toFixed(1) + ',' + z.toFixed(1); }
  function bloco(x, y, z) {
    var m = new THREE.Mesh(geoFinal, matFinal); m.position.set(x, y, z);
    m.add(new THREE.LineSegments(geoBorda, matBorda)); return m;
  }
  var chavesEsboco = new Set();
  function addEsboco(x, y, z) {
    var k = chave(x, y, z);
    if (chavesEsboco.has(k) || colocados.has(k)) return;
    var m = new THREE.Mesh(geoEsboco, matEsboco); m.position.set(x, y, z);
    esboco.add(m); chavesEsboco.add(k);
  }
  function fixar() {
    var n = 0;
    while (esboco.children.length > 0) {
      var f = esboco.children[0];
      var k = chave(f.position.x, f.position.y, f.position.z);
      if (colocados.size < MAX_BLOCOS) { var c = bloco(f.position.x, f.position.y, f.position.z); grupo.add(c); colocados.set(k, c); n++; }
      esboco.remove(f);
    }
    chavesEsboco.clear();
    estado.blocos = colocados.size; $('blocos').textContent = colocados.size;
    if (n) mudou();
    return n;
  }
  function apagarEm(k) {
    if (!colocados.has(k)) return false;
    grupo.remove(colocados.get(k)); colocados.delete(k);
    estado.blocos = colocados.size; $('blocos').textContent = colocados.size; mudou(); return true;
  }
  function limparCena() {                        // só a cena do navegador: o rascunho já foi salvo antes
    colocados.forEach(function (c) { grupo.remove(c); }); colocados.clear();
    while (esboco.children.length) esboco.remove(esboco.children[0]);
    chavesEsboco.clear();
    grupo.position.set(0, 0, 0); grupo.rotation.set(0, 0, 0);
    estado.blocos = 0; $('blocos').textContent = 0;
  }
  function lista() {                             // coordenadas inteiras da grade
    var r = [];
    colocados.forEach(function (c) { r.push([Math.round(c.position.x / GRADE), Math.round(c.position.y / GRADE), Math.round(c.position.z / GRADE)]); });
    return r;
  }
  function colocarLista(vs) {
    limparCena();
    for (var i = 0; i < vs.length && i < MAX_BLOCOS; i++) {
      var v = vs[i]; if (!Array.isArray(v) || v.length !== 3) continue;
      var x = v[0] * GRADE, y = v[1] * GRADE, z = v[2] * GRADE;
      var k = chave(x, y, z); if (colocados.has(k)) continue;
      var c = bloco(x, y, z); grupo.add(c); colocados.set(k, c);
    }
    estado.blocos = colocados.size; $('blocos').textContent = colocados.size;
    sujo = false;
  }

  // ------------------------------------------------------------------ servidor (só nomes de gestos e modelos que VOCÊ salva)
  function chamar(url, corpo) {
    var o = corpo === undefined ? { headers: { 'X-Friday-Token': T } }
      : { method: 'POST', headers: { 'X-Friday-Token': T, 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) };
    return fetch(url, o).then(function (r) { return r.json(); }).catch(function () { return { ok: false, msg: 'sem conexão com a FRIDAY' }; });
  }
  var ultimoEnvio = {};
  function gesto(nome, agora) {
    if (agora - (ultimoEnvio[nome] || -1e9) < 3000) return;
    ultimoEnvio[nome] = agora;
    estado.gestos.push(nome);
    if (T) chamar('/gesto', { gesto: nome });
  }
  var sujo = false, temporizador = 0;
  function mudou() {
    sujo = true; clearTimeout(temporizador);
    temporizador = setTimeout(function () { if (sujo && colocados.size) salvar('rascunho', true); }, 20000);   // 20 s sem mexer: guarda um rascunho
  }
  function salvar(nome, rascunho) {
    var vs = lista(); if (!vs.length) { aviso('Nada para salvar ainda.'); return Promise.resolve({ ok: false }); }
    if (!T) { aviso('Abra primeiro o painel principal da FRIDAY neste navegador (ele guarda a chave).'); return Promise.resolve({ ok: false }); }
    return chamar('/modelo3d', { nome: nome || 'modelo', voxels: vs, rascunho: !!rascunho }).then(function (j) {
      if (j.ok) { sujo = false; estado.salvo++; aviso((rascunho ? 'Rascunho guardado: ' : 'Modelo guardado: ') + (j.nome || nome)); listar(); }
      else aviso('Não guardei: ' + (j.msg || 'erro'));
      return j;
    });
  }
  function listar() {
    return chamar('/modelos3d').then(function (j) {
      var s = $('lista'); if (!s) return; s.textContent = '';
      var o0 = document.createElement('option'); o0.value = ''; o0.textContent = 'modelos guardados…'; s.appendChild(o0);
      (j.modelos || []).forEach(function (m) { var o = document.createElement('option'); o.value = m; o.textContent = m; s.appendChild(o); });
    });
  }
  function carregar(nome) {
    if (!nome) return;
    chamar('/modelo3d?nome=' + encodeURIComponent(nome)).then(function (j) {
      if (j.ok && Array.isArray(j.voxels)) { colocarLista(j.voxels); aviso('Carreguei «' + nome + '» (' + j.voxels.length + ' blocos).'); }
      else aviso('Não achei esse modelo.');
    });
  }
  function aviso(t) { $('aviso').textContent = t; }

  // ------------------------------------------------------------------ desenho da mão e do relógio de segurar
  var suave = { Left: [], Right: [] };
  var LIGACOES = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [9, 10], [10, 11], [11, 12], [13, 14], [14, 15], [15, 16], [0, 17], [17, 18], [18, 19], [19, 20], [5, 9], [9, 13], [13, 17]];
  function circulo(x, y, prog, cor) {
    bctx.beginPath(); bctx.arc(x, y, 35, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * prog);
    bctx.lineWidth = 5; bctx.strokeStyle = cor; bctx.stroke();
    bctx.setLineDash([3, 5]); bctx.beginPath(); bctx.arc(x, y, 30, 0, Math.PI * 2); bctx.lineWidth = 1; bctx.stroke(); bctx.setLineDash([]);
  }
  function suavizar(rotulo, lm) {
    var s = suave[rotulo];
    if (!s || s.length !== lm.length) suave[rotulo] = lm.map(function (p) { return { x: p.x, y: p.y, z: p.z || 0 }; });
    else lm.forEach(function (p, i) { s[i].x += (p.x - s[i].x) * 0.45; s[i].y += (p.y - s[i].y) * 0.45; s[i].z += ((p.z || 0) - s[i].z) * 0.1; });
    return suave[rotulo];
  }
  function desenharMao(pts) {
    bctx.shadowBlur = 10; bctx.shadowColor = '#00f0ff';
    bctx.beginPath(); bctx.strokeStyle = 'rgba(0,240,255,.6)'; bctx.lineWidth = 2;
    LIGACOES.forEach(function (c) { bctx.moveTo(pts[c[0]].x * bio.width, pts[c[0]].y * bio.height); bctx.lineTo(pts[c[1]].x * bio.width, pts[c[1]].y * bio.height); });
    bctx.stroke();
    pts.forEach(function (p, i) {
      var x = p.x * bio.width, y = p.y * bio.height;
      if (i === 4 || i === 8 || i === 12 || i === 16 || i === 20) { bctx.strokeStyle = '#00f0ff'; bctx.strokeRect(x - 6, y - 6, 12, 12); }
      else { bctx.fillStyle = '#fff'; bctx.fillRect(x - 2, y - 2, 4, 4); }
    });
    bctx.shadowBlur = 0;
  }

  // ------------------------------------------------------------------ o laço dos gestos (uma vez por quadro de mão)
  var rel = { agarrar: 0, construir: 0, apagar: 0, reiniciar: 0, girar: 0 };
  var agarrando = false, construindo = false, apagando = false, deslocamento = new THREE.Vector3(), inicio = null, eixo = null, ultimoT = 0;
  var TEXTO = { nenhum: 'procurando suas mãos', agarrar: 'segurando o mundo', construir: 'construindo', apagar: 'apagando', girar: 'girando', reiniciar: 'reiniciando a cena', fixar: 'fixando o esboço' };

  function zerar() { for (var k in rel) rel[k] = 0; agarrando = construindo = apagando = false; }
  function acumular(nome, ativo, dt) { if (ativo) rel[nome] = Math.min(SEGURAR[nome], rel[nome] + dt); else rel[nome] = 0; return rel[nome] >= SEGURAR[nome]; }

  function resultados(r, agora) {
    agora = agora === undefined ? performance.now() : agora;
    var dt = ultimoT ? Math.min(100, Math.max(1, agora - ultimoT)) : 16; ultimoT = agora;
    bio.width = bio.width; mira.visible = false;     // limpa o desenho
    estado.quadros++;
    var lms = r && r.multiHandLandmarks, lado = r && r.multiHandedness;
    if (!lms || !lms.length || !lado) { zerar(); estado.maos = 0; estado.modo = 'nenhum'; $('modo').textContent = TEXTO.nenhum; return; }
    estado.maos = lms.length;
    var esq = null, dir = null;
    lado.forEach(function (h, i) {
      var lm = lms[i]; if (!G.valida(lm)) return;
      var p = suavizar(h.label, lm); desenharMao(p);
      if (h.label === 'Left') esq = p; if (h.label === 'Right') dir = p;
    });
    var modo = G.modo(esq, dir), e = G.mao(esq), d = G.mao(dir), W = bio.width, H = bio.height;
    estado.modo = modo;

    // dois punhos / duas palmas: ações globais, só depois de segurar
    var reinicia = acumular('reiniciar', modo === 'reiniciar', dt);
    if (modo === 'reiniciar') {
      rel.girar = 0;
      if (!reinicia) { circulo(W / 2, H / 2, rel.reiniciar / SEGURAR.reiniciar, '#ff0055'); $('modo').textContent = 'segure para reiniciar…'; }
      else { if (colocados.size) salvar('rascunho', true); limparCena(); $('modo').textContent = 'cena reiniciada (guardei um rascunho)'; gesto('reiniciar', agora); rel.reiniciar = 0; }
      return;
    }
    var gira = acumular('girar', modo === 'girar', dt);
    if (modo === 'girar') {
      if (!gira) { circulo(W / 2, H / 2, rel.girar / SEGURAR.girar, '#00f0ff'); $('modo').textContent = 'segure para girar…'; }
      else { $('modo').textContent = TEXTO.girar; grupo.rotation.y += (dir[9].x - esq[9].x - 0.5) * 0.05; grupo.rotation.x += (dir[9].y - esq[9].y) * 0.05; gesto('girar', agora); }
      return;
    }

    if (esq && e) {                              // mão esquerda: agarrar o mundo
      var pos = new THREE.Vector3((0.5 - esq[9].x) * 25, (0.5 - esq[9].y) * 18, 0);
      if (e.fechada) {
        if (!acumular('agarrar', true, dt)) circulo(esq[0].x * W, esq[0].y * H, rel.agarrar / SEGURAR.agarrar, '#ffbb00');
        else { if (!agarrando) { deslocamento.copy(grupo.position).sub(pos); agarrando = true; gesto('agarrar', agora); } grupo.position.copy(pos).add(deslocamento); $('modo').textContent = TEXTO.agarrar; }
      } else { agarrando = false; rel.agarrar = 0; }
    }

    if (dir && d) {                              // mão direita: construir, apagar, fixar
      var ponta = dir[8], px = ponta.x * W, py = ponta.y * H;
      var mundo = new THREE.Vector3((0.5 - ponta.x) * 25, (0.5 - ponta.y) * 18, -ponta.z * 25);
      var loc = grupo.worldToLocal(mundo.clone());
      var gx = Math.round(loc.x / GRADE) * GRADE, gy = Math.round(loc.y / GRADE) * GRADE, gz = Math.round(loc.z / GRADE) * GRADE;
      if (modo === 'apagar') {
        rel.construir = 0;
        if (!acumular('apagar', true, dt)) { circulo(px, py, rel.apagar / SEGURAR.apagar, '#ff3333'); $('modo').textContent = 'apagador travando…'; }
        else { if (!apagando) gesto('apagar', agora); apagando = true; apagarEm(chave(gx, gy, gz)); $('modo').textContent = TEXTO.apagar; }
      } else if (modo === 'construir' && !agarrando) {
        rel.apagar = 0;
        if (!acumular('construir', true, dt)) { circulo(px, py, rel.construir / SEGURAR.construir, '#00ffcc'); $('modo').textContent = 'construção sincronizando…'; }
        else {
          if (!construindo) { inicio = { x: gx, y: gy, z: gz }; chavesEsboco.clear(); construindo = true; eixo = null; gesto('construir', agora); }
          else {
            var dx = Math.abs(gx - inicio.x), dy = Math.abs(gy - inicio.y), dz = Math.abs(gz - inicio.z);
            if (!eixo && (dx > 0.4 || dy > 0.4 || dz > 0.4)) eixo = (dx >= dy && dx >= dz) ? 'x' : (dy >= dx && dy >= dz) ? 'y' : 'z';   // linha reta no eixo que mais andou
            var tx = inicio.x, ty = inicio.y, tz = inicio.z;
            if (eixo === 'x') tx = gx; else if (eixo === 'y') ty = gy; else if (eixo === 'z') tz = gz;
            if (colocados.size + esboco.children.length < MAX_BLOCOS) addEsboco(tx, ty, tz);
          }
          $('modo').textContent = TEXTO.construir;
        }
      } else {
        if (d.aberta) {
          if (construindo) { var n = fixar(); if (n) gesto('fixar', agora); }
          construindo = false; apagando = false; rel.construir = 0; rel.apagar = 0;
          $('modo').textContent = TEXTO.fixar;
        } else { rel.construir = 0; rel.apagar = 0; }
      }
      if (construindo || rel.construir > 0 || apagando || rel.apagar > 0) {
        mira.visible = true; mira.position.copy(grupo.localToWorld(new THREE.Vector3(gx, gy, gz)));
        mira.material.color.set((apagando || rel.apagar > 0) ? 0xff3333 : 0x00f0ff);
      }
    }
  }

  // ------------------------------------------------------------------ câmera e MediaPipe
  var hands = null, fluxo = null, rodando = false, ocupado = false;
  function falha(t) { estado.erro = t; $('modo').textContent = t; $('camaviso').textContent = t; $('camaviso').style.display = 'block'; }
  function iniciarMao() {
    if (typeof Hands === 'undefined') { falha('Não consegui carregar o rastreador de mãos (arquivos em /static/maos).'); return false; }
    var cheio = /[?&]modelo=cheio\b/.test(location.search);
    hands = new Hands({ locateFile: function (f) { return '/static/maos/' + f; } });
    hands.setOptions({ maxNumHands: 2, modelComplexity: cheio ? 1 : 0, minDetectionConfidence: 0.8, minTrackingConfidence: 0.8 });
    hands.onResults(function (r) { resultados(r); });
    return true;
  }
  function abrirCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      falha('Este endereço não deixa o navegador usar a câmera. No celular (Termux) abra http://127.0.0.1:8080; de outro aparelho, só com HTTPS.'); return Promise.resolve(false);
    }
    return navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' }, audio: false }).then(function (s) {
      fluxo = s; video.srcObject = s; return video.play().then(function () { estado.camera = true; return true; });
    }).catch(function (e) { falha(e && e.name === 'NotAllowedError' ? 'A câmera foi negada. Libere a câmera para este site e recarregue.' : 'Não consegui abrir a câmera (' + ((e && e.name) || 'erro') + ').'); return false; });
  }
  function fecharCamera() {                      // câmera só enquanto a página está aberta e visível
    rodando = false; estado.camera = false;
    if (fluxo) { fluxo.getTracks().forEach(function (t) { t.stop(); }); fluxo = null; }
    try { video.srcObject = null; } catch (_) {}
  }
  function laco() {
    if (!rodando) return;
    if (!ocupado && video.readyState >= 2 && video.videoWidth) {
      ocupado = true; bio.width = video.videoWidth; bio.height = video.videoHeight;
      hands.send({ image: video }).catch(function () {}).then(function () { ocupado = false; });
    }
    requestAnimationFrame(laco);
  }
  function animar() { requestAnimationFrame(animar); rend.render(cena, cam); }

  function iniciar() {
    animar();
    if (!iniciarMao()) return;
    var p = hands.initialize ? hands.initialize() : Promise.resolve();
    $('modo').textContent = 'carregando o rastreador de mãos…';
    p.then(function () { estado.pronto = true; return abrirCamera(); }).then(function (ok) {
      if (ok) { rodando = true; $('modo').textContent = TEXTO.nenhum; laco(); }
    }).catch(function (e) { falha('O rastreador de mãos não iniciou (' + ((e && e.message) || 'erro') + ').'); });
  }
  addEventListener('pagehide', function () { fecharCamera(); });
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { if (sujo && colocados.size) salvar('rascunho', true); fecharCamera(); }
    else if (!rodando && hands) { abrirCamera().then(function (ok) { if (ok) { rodando = true; laco(); } }); }
  });

  $('salvar').onclick = function () { salvar(($('nome').value || '').trim() || 'modelo', false); };
  $('lista').onchange = function () { carregar(this.value); };
  $('nome').value = 'modelo';

  // gancho de teste (sem câmera): passa pontos inventados pelo mesmo caminho que a câmera usa
  estado.injetar = function (r, agora) { resultados(r, agora); };
  estado.cena = { colocados: function () { return colocados.size; }, esboco: function () { return esboco.children.length; }, lista: lista, colocarLista: colocarLista, salvar: salvar, carregar: carregar, fixar: fixar };
  listar();
  if (!/[?&]semcamera\b/.test(location.search)) iniciar(); else { animar(); estado.pronto = true; }
})();
