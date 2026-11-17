/* Cérebro 3D da FRIDAY: neurônios (notas) e sinapses (links), em canvas 2D com projeção em perspectiva. Sem bibliotecas externas.
   Usado pelo painel (hud.html) e pelo arquivo exportado (cerebro.html). API: Cerebro3D.criar(canvas, opcoes) -> controle. */
(function () {
  const COR = {pessoa: [255, 95, 168], projeto: [79, 209, 255], preferencia: [255, 169, 77], fato: [108, 140, 255], decisao: [255, 212, 59],
    tarefa: [91, 227, 160], topico: [178, 139, 255], eu: [226, 240, 255], conversa: [118, 132, 156], pedido: [255, 107, 61], estudo: [64, 224, 208], visao: [255, 196, 87]};
  const NOME = {pessoa: 'Pessoas', projeto: 'Projetos', preferencia: 'Preferências', fato: 'Fatos', decisao: 'Decisões', tarefa: 'Tarefas',
    topico: 'Tópicos (aprendidos)', eu: 'Eu (autoconhecimento)', conversa: 'Dias de conversa', pedido: 'Pedidos de evolução', estudo: 'Estudos (internet)', visao: 'Visão (câmera)'};
  const ORDEM = ['pessoa', 'projeto', 'decisao', 'preferencia', 'fato', 'tarefa', 'topico', 'estudo', 'visao', 'eu', 'conversa', 'pedido'];
  const ORD_REG = ['frontal', 'cortex_motor', 'parietal', 'temporal', 'occipital', 'mesencefalo', 'cerebelo', 'tronco', 'hipocampo', 'limbico'];

  function fold(s) { return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  function rng(seed) { let a = seed >>> 0; return function () { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
  function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }

  const sprites = {};
  function sprite(rgb) {
    const k = rgb.join(',');
    if (sprites[k]) return sprites[k];
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const x = c.getContext('2d'), g = x.createRadialGradient(32, 32, 0, 32, 32, 32);
    const m = k => Math.min(255, k * .8 + 70 | 0);
    g.addColorStop(0, `rgba(${m(rgb[0]) * .35 + 165 | 0},${m(rgb[1]) * .35 + 165 | 0},${m(rgb[2]) * .35 + 165 | 0},1)`); g.addColorStop(.1, `rgba(${m(rgb[0])},${m(rgb[1])},${m(rgb[2])},.98)`);
    g.addColorStop(.3, `rgba(${rgb},.7)`); g.addColorStop(.58, `rgba(${rgb},.16)`); g.addColorStop(1, `rgba(${rgb},0)`);
    x.fillStyle = g; x.fillRect(0, 0, 64, 64);
    return (sprites[k] = c);
  }

  function criar(canvas, opc) {
    opc = opc || {};
    const ctx = canvas.getContext('2d');
    const S = {nos: [], ar: [], lay: [], n: 0, W: 300, H: 300, dpr: 1, R: 100, t: 0, yaw: .6, pitch: -.18, zoom: 1, yawT: .6, pitchT: -.18, zoomT: 1,
      auto: opc.auto !== false, vel: 0, sel: -1, hover: -1, busca: null, rotulos: true, cinema: false, reduzido: !!opc.reduzido, manual: !!opc.manual,
      sparks: [], prox: 0, proxAmb: 0, proxCin: 0, adj: [], bg: opc.fundo || '#02050a', legendaCb: null, entrada: 1,
      modo: 'tipo', mix: 0, mixT: 0, reg: null, temReg: false, casca: null, R0: 100, Rr: 100, Rv: 100, U: 100, modoInit: false, mixIni: false, rotReg: true};
    const cb = opc.cb || {};
    let px, py, pz, ps, ord, raf = 0, ult = 0, vivo = true;

    function dimensionar() {
      const r = canvas.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1);
      S.W = Math.max(120, r.width); S.H = Math.max(120, r.height); S.dpr = dpr;
      canvas.width = Math.round(S.W * dpr); canvas.height = Math.round(S.H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    // ---------- posição dos neurônios: forças em 3D ----------
    // 'tipo': aglomerados por tipo dentro de uma esfera. 'regiao': cada neurônio perto da sua região, num cérebro anatômico com dois hemisférios.
    function simular(iter, R, o) {
      const n = S.n, nos = S.nos, A = Array.from({length: n}, (_, i) => o.alvo(i));
      const X = new Float32Array(n), Y = new Float32Array(n), Z = new Float32Array(n), VX = new Float32Array(n), VY = new Float32Array(n), VZ = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        const r = rng(hash(nos[i].id)), a = o.ini ? o.ini(i) : A[i], s = o.esp(i);
        X[i] = a[0] + (r() - .5) * s * 2; Y[i] = a[1] + (r() - .5) * s * 2; Z[i] = a[2] + (r() - .5) * s * 2;
      }
      const L0 = R * .42;
      for (let it = 0; it < iter; it++) {
        const al = 1 - it / iter, rep = (R * R * .55) * (.4 + .6 * al) * (o.rep || 1);
        for (let i = 0; i < n; i++) {
          for (let j = i + 1; j < n; j++) {
            let dx = X[i] - X[j], dy = Y[i] - Y[j], dz = Z[i] - Z[j]; const d2 = dx * dx + dy * dy + dz * dz + 12;
            if (d2 > R * R * 1.6) continue;
            const f = rep / d2, inv = 1 / Math.sqrt(d2); dx *= inv; dy *= inv; dz *= inv;
            VX[i] += dx * f; VY[i] += dy * f; VZ[i] += dz * f; VX[j] -= dx * f; VY[j] -= dy * f; VZ[j] -= dz * f;
          }
        }
        for (const e of S.lay) {   // o desenho da rede usa as sinapses mais fortes (as fracas quase não mexem no lugar dos neurônios)
          const i = e[0], j = e[1], dx = X[j] - X[i], dy = Y[j] - Y[i], dz = Z[j] - Z[i], d = Math.sqrt(dx * dx + dy * dy + dz * dz) + .01;
          const L = L0 / (1 + .25 * Math.min(e[2], 6)), f = .035 * o.liga * Math.min(2.5, .6 + e[2] * .25) * (d - L) / d;
          VX[i] += dx * f; VY[i] += dy * f; VZ[i] += dz * f; VX[j] -= dx * f; VY[j] -= dy * f; VZ[j] -= dz * f;
        }
        for (let i = 0; i < n; i++) {
          const a = A[i], r = Math.sqrt(X[i] * X[i] + Y[i] * Y[i] + Z[i] * Z[i]) + .01;
          VX[i] += (a[0] - X[i]) * o.k; VY[i] += (a[1] - Y[i]) * o.k; VZ[i] += (a[2] - Z[i]) * o.k;
          if (o.esfera && r > R) { const k = (R - r) * .06 / r; VX[i] += X[i] * k; VY[i] += Y[i] * k; VZ[i] += Z[i] * k; }
          if (o.raio) {  // a região é um lugar: o neurônio não sai da vizinhança dela
            const dx = X[i] - a[0], dy = Y[i] - a[1], dz = Z[i] - a[2], d = Math.sqrt(dx * dx + dy * dy + dz * dz) + .001, rm = o.raio(i);
            if (d > rm) { const k = (rm - d) * .18 / d; VX[i] += dx * k; VY[i] += dy * k; VZ[i] += dz * k; }
          }
          const v = Math.sqrt(VX[i] * VX[i] + VY[i] * VY[i] + VZ[i] * VZ[i]), m = 9 * al + 1.5;
          if (v > m) { VX[i] *= m / v; VY[i] *= m / v; VZ[i] *= m / v; }
          X[i] += VX[i]; Y[i] += VY[i]; Z[i] += VZ[i]; VX[i] *= .72; VY[i] *= .72; VZ[i] *= .72;
        }
      }
      return {X, Y, Z};
    }

    function layout(iter) {
      const n = S.n, nos = S.nos;
      const grupos = ORDEM.filter(g => nos.some(x => x.g === g)), anc = {};
      grupos.forEach((g, i) => {  // espiral de Fibonacci: cada tipo ganha a sua "região" da esfera
        const k = (i + .5) / grupos.length, y = 1 - 2 * k, r = Math.sqrt(Math.max(0, 1 - y * y)), a = i * 2.399963;
        anc[g] = [Math.cos(a) * r, y, Math.sin(a) * r];
      });
      const R = S.R0 = 70 + 5.2 * Math.sqrt(n);
      const au = i => anc[nos[i].g] || [0, 0, 0];
      const t = simular(iter, R, {alvo: i => au(i).map(v => v * R * .6), ini: i => au(i).map(v => v * R * .55), esp: () => R * .45, k: .018, liga: 1, esfera: true});
      const X = t.X, Y = t.Y, Z = t.Z;
      let cx = 0, cy = 0, cz = 0; for (let i = 0; i < n; i++) { cx += X[i]; cy += Y[i]; cz += Z[i]; } cx /= n; cy /= n; cz /= n;
      let mx = 1; for (let i = 0; i < n; i++) { X[i] -= cx; Y[i] -= cy; Z[i] -= cz; mx = Math.max(mx, Math.hypot(X[i], Y[i], Z[i])); }
      S.R = mx;
      for (let i = 0; i < n; i++) { nos[i].x = X[i]; nos[i].y = Y[i]; nos[i].z = Z[i]; }
      // anatômico (só se o servidor mandou as regiões e todo neurônio tem uma)
      S.temReg = !!S.reg && nos.every(x => S.reg[x.rg]);
      if (!S.temReg) { S.Rr = S.R; S.casca = null; nos.forEach(x => { x.rx = x.x; x.ry = x.y; x.rz = x.z; }); return; }
      const U = S.U = R * 1.08, cnt = {}; nos.forEach(x => { cnt[x.rg] = (cnt[x.rg] || 0) + 1; });
      const lado = nos.map(x => (hash(x.id + '#lado') & 1) ? 1 : -1);
      const alvoR = i => { const g = S.reg[nos[i].rg], p = g.pos; return [p[0] * U, p[1] * U, (g.lado ? lado[i] * Math.abs(p[2]) : 0) * U]; };
      const raio = i => Math.min(.21, .07 + .03 * Math.sqrt(cnt[nos[i].rg])) * U;
      const t2 = simular(iter, R, {alvo: alvoR, esp: i => raio(i) * .8, k: .09, liga: .22, rep: .55, raio});
      let m2 = 1;
      for (let i = 0; i < n; i++) { nos[i].rx = t2.X[i]; nos[i].ry = t2.Y[i]; nos[i].rz = t2.Z[i]; m2 = Math.max(m2, Math.hypot(t2.X[i], t2.Y[i], t2.Z[i])); }
      S.Rr = Math.max(m2, U * 1.05);
      S.casca = montarCasca(U);
    }

    // contorno do cérebro: fios (paralelos e meridianos) sobre os dois hemisférios, o cerebelo e o tronco. Só estética: os neurônios ficam dentro.
    function montarCasca(U) {
      const fios = [], gir = (x, y, z) => 1 + .05 * Math.sin(x * 9 + z * 7) * Math.sin(y * 8 + x * 5);  // giros do córtex
      const fecha = (v) => { if (v.length > 9) fios.push(Float32Array.from(v)); return []; };
      for (const s of [-1, 1]) {
        const pt = (x, y, z, v) => {
          const g = gir(x, y, z), zz = s * .33 + z * .36 * g;
          if (s * zz < .05) return fecha(v);  // abre a fissura entre os hemisférios
          v.push(x * .98 * g * U, (-.05 + y * .70 * g) * U, zz * U); return v;
        };
        for (let a = 1; a <= 8; a++) { const y = -1 + a * 2 / 9, q = Math.sqrt(1 - y * y); let v = []; for (let k = 0; k <= 56; k++) { const th = k / 56 * 6.2832; v = pt(Math.cos(th) * q, y, Math.sin(th) * q, v); } fecha(v); }
        for (let m = 0; m < 14; m++) { const th = m / 14 * 6.2832; let v = []; for (let k = 0; k <= 34; k++) { const ph = -1.5708 + k / 34 * 3.14159, q = Math.cos(ph); v = pt(Math.cos(th) * q, Math.sin(ph), Math.sin(th) * q, v); } fecha(v); }
      }
      // cerebelo (atrás e embaixo): anéis e meridianos de um elipsoide estriado
      for (let a = 1; a <= 6; a++) { const y = -1 + a * 2 / 7, q = Math.sqrt(1 - y * y), v = []; for (let k = 0; k <= 40; k++) { const th = k / 40 * 6.2832; v.push((-.58 + Math.cos(th) * q * .26) * U, (.55 + y * .17) * U, Math.sin(th) * q * .30 * U); } fecha(v); }
      for (let m = 0; m < 8; m++) { const th = m / 8 * 6.2832, v = []; for (let k = 0; k <= 20; k++) { const ph = -1.5708 + k / 20 * 3.14159, q = Math.cos(ph); v.push((-.58 + Math.cos(th) * q * .26) * U, (.55 + Math.sin(ph) * .17) * U, Math.sin(th) * q * .30 * U); } fecha(v); }
      // tronco: anéis ao longo de um cilindro que afina, mais quatro fios
      for (let a = 0; a <= 6; a++) { const t = a / 6, rad = .09 * (1 - .25 * t), v = []; for (let k = 0; k <= 20; k++) { const th = k / 20 * 6.2832; v.push((-.05 - .18 * t + Math.cos(th) * rad) * U, (.35 + .60 * t) * U, Math.sin(th) * rad * U); } fecha(v); }
      for (let m = 0; m < 4; m++) { const th = m / 4 * 6.2832, v = []; for (let k = 0; k <= 8; k++) { const t = k / 8, rad = .09 * (1 - .25 * t); v.push((-.05 - .18 * t + Math.cos(th) * rad) * U, (.35 + .60 * t) * U, Math.sin(th) * rad * U); } fecha(v); }
      const caloso = [];
      for (let k = 0; k <= 24; k++) { const t = k / 24, x = -.46 + t * 1.0; caloso.push(x * U, (-.2 - .17 * (1 - Math.pow((x - .02) / .5, 2))) * U, 0); }
      S.caloso = new Float32Array(caloso);
      return fios;
    }

    function carregar(g, o) {
      o = o || {};
      S.nos = (g.nos || []).map((x, i) => Object.assign({}, x, {i, luz: 0, ate: 0, nasc: o.sem_entrada ? 1 : 0, nasce_em: x.nasce_em == null ? null : x.nasce_em, dim: 1}));
      S.ar = (g.arestas || []).filter(e => S.nos[e[0]] && S.nos[e[1]]).map(e => { const a = [e[0], e[1], e[2], e[3]]; a.nasce_em = e[4] == null ? null : e[4]; return a; });
      S.n = S.nos.length; S.adj = S.nos.map(() => []); S.reg = g.regioes || null;
      S.ar.forEach((e, k) => { S.adj[e[0]].push(k); S.adj[e[1]].push(k); });
      // Não há teto de sinapses: todas chegam aqui. O que se limita é só quantas TRAÇAR por quadro (as mais fortes primeiro; sobe e desce conforme o aparelho aguenta).
      S.ordem = S.ar.map((_, k) => k).sort((a, b) => S.ar[b][2] - S.ar[a][2]);
      S.pos_ordem = new Int32Array(S.ar.length); S.ordem.forEach((k, r) => { S.pos_ordem[k] = r; });
      S.lay = S.ordem.slice(0, 4000).map(k => S.ar[k]);
      S.novas = []; S.ar.forEach((e, k) => { if (e.nasce_em != null) S.novas.push(k); });
      S.orc = Math.min(S.ar.length, S.reduzido ? 1200 : 3000);
      S.nos.forEach(x => { x.r = 2.1 + (x.imp || 3) * .55 + Math.log(1 + (x.deg || 0)) * .85 + Math.log(1 + (x.uso || 0)) * .5; x.f = fold(x.t); x.ord = (hash(x.id) % 1000) / 1000; });
      px = new Float32Array(S.n); py = new Float32Array(S.n); pz = new Float32Array(S.n); ps = new Float32Array(S.n); ord = Array.from({length: S.n}, (_, i) => i);
      if (S.n) layout(o.iter || (S.n > 300 ? 150 : 230)); else { S.temReg = !!S.reg; S.casca = null; }
      if (!S.temReg) S.modo = 'tipo';
      else if (!S.modoInit) { S.modo = opc.modo || 'regiao'; S.modoInit = true; }
      S.mixT = S.modo === 'regiao' ? 1 : 0;
      if (!S.mixIni) { S.mix = S.mixT; S.mixIni = true; } else if (!S.temReg) S.mix = 0;
      posicionar();
      S.sparks = []; S.sel = -1; S.busca = null;
      if (!o.sem_entrada) S.entrada = 0; else S.entrada = 1;
      // movimento reduzido não tem laço de animação: sem isto os neurônios ficariam em nasc=0 e a tela, em branco
      if (S.reduzido) { S.entrada = 1; S.nos.forEach(x => { x.nasc = x.nasce_em != null && S.t < x.nasce_em ? 0 : 1; }); }
      if (g.ativos) ativar(g.ativos, 5);
      cb.carregado && cb.carregado(S);
      if (S.manual || S.reduzido) desenhar();
    }

    // posição mostrada = mistura entre o layout por tipo e o anatômico (a troca de modo é animada)
    function posicionar() {
      const m = S.mix;
      for (const n of S.nos) { n.dx = n.x + (n.rx - n.x) * m; n.dy = n.y + (n.ry - n.y) * m; n.dz = n.z + (n.rz - n.z) * m; }
      S.Rv = (S.R + (S.Rr - S.R) * m) * (1 + .16 * m);  // o cérebro anatômico é mais alto e largo: afasta a câmera para caber com a interface
    }
    function modo(m) {
      if (m !== 'tipo' && m !== 'regiao') return S.modo;
      if (m === 'regiao' && !S.temReg) return S.modo;
      S.modo = m; S.mixT = m === 'regiao' ? 1 : 0;
      if (S.manual || S.reduzido) { S.mix = S.mixT; posicionar(); desenhar(); }
      cb.modo && cb.modo(S.modo);
      return S.modo;
    }
    function corDe(n) { return S.mix > .5 && S.reg && S.reg[n.rg] ? S.reg[n.rg].cor : (COR[n.g] || [200, 200, 200]); }
    // legenda do modo atual: [{nome, cor, n, vazio}]
    function legenda() {
      const c = {};
      if (S.mixT > .5 && S.reg) {
        S.nos.forEach(x => { c[x.rg] = (c[x.rg] || 0) + 1; });
        return ORD_REG.filter(k => S.reg[k]).map(k => ({id: k, nome: S.reg[k].nome, cor: S.reg[k].cor, n: c[k] || 0, vazio: !c[k]}));
      }
      S.nos.forEach(x => { c[x.g] = (c[x.g] || 0) + 1; });
      return ORDEM.filter(k => c[k]).map(k => ({id: k, nome: NOME[k] || k, cor: COR[k] || [200, 200, 200], n: c[k], vazio: false}));
    }

    function ativar(idx, dur) {
      for (const i of idx) { const n = S.nos[typeof i === 'string' ? S.nos.findIndex(x => x.id === i) : i]; if (n) { n.ate = S.t + (dur || 6); n.luz = 1; } }
    }

    function buscar(q) {
      q = fold(q || '').trim();
      if (!q) { S.busca = null; return 0; }
      S.busca = new Set(); S.nos.forEach((x, i) => { if (x.f.includes(q)) S.busca.add(i); });
      if (S.busca.size) foco([...S.busca][0], 1.35);
      return S.busca.size;
    }

    function foco(i, z) {
      const n = S.nos[i]; if (!n) return;
      const r = Math.hypot(n.dx, n.dz) + .001;
      S.yawT = S.yaw + ajusteAngulo(S.yaw, Math.atan2(-n.dx, n.dz) + Math.PI);  // leva o neurônio para a frente, pelo caminho mais curto
      S.pitchT = Math.max(-1.1, Math.min(1.1, Math.atan2(-n.dy, r)));
      if (z) S.zoomT = z;
    }
    function ajusteAngulo(a, b) { let d = (b - a) % (2 * Math.PI); if (d > Math.PI) d -= 2 * Math.PI; if (d < -Math.PI) d += 2 * Math.PI; return d; }

    // ---------- tempo ----------
    function disparo(i, amb, prof) {
      const adj = S.adj[i]; if (!adj || !adj.length || S.sparks.length > 110) return;
      let tot = 0; for (const k of adj) tot += .4 + S.ar[k][2]; let r = Math.random() * tot, k0 = adj[0];
      for (const k of adj) { r -= .4 + S.ar[k][2]; if (r <= 0) { k0 = k; break; } }
      S.sparks.push({k: k0, dir: S.ar[k0][0] === i ? 1 : -1, p: 0, v: .8 + Math.random() * .5, amb: !!amb, prof: prof || 0});
    }

    function passo(dt) {
      dt = Math.min(dt, .1); S.t += dt;
      if (Math.abs(S.mix - S.mixT) > .001) { S.mix += (S.mixT - S.mix) * Math.min(1, dt * 2.6); posicionar(); } else if (S.mix !== S.mixT) { S.mix = S.mixT; posicionar(); }
      if (S.entrada < 1) S.entrada = Math.min(1, S.entrada + dt / (S.reduzido ? .01 : 4.4));
      const ent = S.entrada;
      S.nos.forEach((x, i) => {
        const alvo = x.nasce_em != null ? (S.t >= x.nasce_em ? Math.min(1, (S.t - x.nasce_em) / 1.4) : 0) : Math.min(1, Math.max(0, ent - x.ord * .72) / .28);
        x.nasc = S.reduzido ? (x.nasce_em != null && S.t < x.nasce_em ? 0 : 1) : alvo;
        if (S.t < x.ate) x.luz = 1; else x.luz *= Math.exp(-dt * 1.3);
      });
      if (S.cinema) {
        S.auto = true; S.proxCin -= dt;
        S.pitchT = -.2 + Math.sin(S.t * .11) * .35; S.zoomT = 1.05 + Math.sin(S.t * .07) * .22;
        if (S.proxCin <= 0 && S.n) { S.proxCin = 5.5; const cand = S.nos.map((x, i) => [x.deg + x.imp, i]).sort((a, b) => b[0] - a[0]).slice(0, 14); const i = cand[Math.floor(Math.random() * cand.length)][1]; ativar([i], 4.5); S.sel = i; }
      }
      if (S.auto && !S.reduzido) S.yawT += (S.cinema ? .2 : .1) * dt;
      S.yaw += ajusteAngulo(S.yaw, S.yawT) * Math.min(1, dt * 3.2); S.pitch += (S.pitchT - S.pitch) * Math.min(1, dt * 3.2); S.zoom += (S.zoomT - S.zoom) * Math.min(1, dt * 3.2);
      if (!S.reduzido) {
        S.prox -= dt; S.proxAmb -= dt;
        if (S.prox <= 0) { S.prox = .22; S.nos.forEach((x, i) => { if (S.t < x.ate && Math.random() < .8) disparo(i, false, 0); }); }
        if (S.proxAmb <= 0 && S.n) { S.proxAmb = .45; const i = Math.floor(Math.random() * S.n); if (S.nos[i].nasc > .9) { S.nos[i].luz = Math.max(S.nos[i].luz, .55); disparo(i, true, 0); } }
        for (let q = S.sparks.length - 1; q >= 0; q--) {
          const s = S.sparks[q], e = S.ar[s.k]; s.p += dt * s.v;
          if (s.p >= 1) {
            const alvo = S.nos[s.dir === 1 ? e[1] : e[0]]; alvo.luz = Math.max(alvo.luz, s.amb ? .5 : .9);
            if (s.prof < (s.amb ? 1 : 3) && Math.random() < (s.amb ? .5 : .6)) disparo(alvo.i, s.amb, s.prof + 1);
            S.sparks.splice(q, 1);
          }
        }
      }
    }

    // ---------- desenho ----------
    function desenhar() {
      const W = S.W, H = S.H; ctx.globalCompositeOperation = 'source-over'; ctx.fillStyle = S.bg; ctx.fillRect(0, 0, W, H);
      const vg = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * .7); vg.addColorStop(0, 'rgba(30,60,110,.16)'); vg.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = vg; ctx.fillRect(0, 0, W, H);
      if (!S.n) return;
      const R = S.Rv, cam = R * 3.4, esc = Math.min(W, H) / (1.85 * R) * S.zoom, cx = W / 2, cy = H / 2;
      const cyaw = Math.cos(S.yaw), syaw = Math.sin(S.yaw), cp = Math.cos(S.pitch), sp = Math.sin(S.pitch);
      for (let i = 0; i < S.n; i++) {
        const n = S.nos[i], x1 = n.dx * cyaw + n.dz * syaw, z1 = -n.dx * syaw + n.dz * cyaw, y1 = n.dy * cp - z1 * sp, z2 = n.dy * sp + z1 * cp;
        const p = cam / (cam + z2); px[i] = cx + x1 * p * esc; py[i] = cy + y1 * p * esc; pz[i] = z2; ps[i] = p * esc;
      }
      if (S.casca && S.mix > .02) contorno(cyaw, syaw, cp, sp, cam, esc, cx, cy, R);
      ord.sort((a, b) => pz[b] - pz[a]);
      const busca = S.busca, selv = S.sel >= 0 ? S.sel : -1;
      const viz = new Set(); if (selv >= 0) { S.adj[selv].forEach(k => { viz.add(S.ar[k][0]); viz.add(S.ar[k][1]); }); }
      const dimDe = i => busca ? (busca.has(i) ? 1 : .18) : (selv >= 0 ? (i === selv || viz.has(i) ? 1 : .22) : 1);
      const prof = z => Math.max(.22, Math.min(1, .62 - z / (R * 2.2)));
      // sinapses
      ctx.lineCap = 'round';
      const traco = e => {
        const a = e[0], b = e[1], na = S.nos[a], nb = S.nos[b], nasc = Math.min(na.nasc, nb.nasc);
        if (nasc <= 0 || (e.nasce_em != null && S.t < e.nasce_em)) return;
        let al = (.085 + .06 * Math.min(e[2], 5)) * prof((pz[a] + pz[b]) / 2) * nasc * Math.min(dimDe(a), dimDe(b));
        if (e.nasce_em != null && S.t < e.nasce_em + 1.2) al += .6 * (1 - (S.t - e.nasce_em) / 1.2);
        const quente = Math.max(na.luz, nb.luz); al += quente * .25;
        if (al < .02) return;
        const c1 = corDe(na), c2 = corDe(nb), r = (c1[0] + c2[0]) * .42 + 40 | 0, g = (c1[1] + c2[1]) * .42 + 40 | 0, bb = (c1[2] + c2[2]) * .42 + 40 | 0;
        ctx.strokeStyle = `rgba(${r},${g},${bb},${Math.min(.9, al)})`; ctx.lineWidth = (.45 + Math.min(e[2], 5) * .22) * Math.min(1.6, (ps[a] + ps[b]) / (2 * esc) * 1.0) * (e[3] ? .8 : 1);
        if (e[3]) ctx.setLineDash([2, 3]); else ctx.setLineDash([]);
        ctx.beginPath(); ctx.moveTo(px[a], py[a]); ctx.lineTo(px[b], py[b]); ctx.stroke();
      };
      if (S.ordem) {
        const ate = Math.min(S.orc || S.ar.length, S.ar.length);
        for (let r = 0; r < ate; r++) traco(S.ar[S.ordem[r]]);
        if (ate < S.ar.length) {   // fora do orçamento só entram as que acabaram de nascer e as do neurônio selecionado
          for (const k of S.novas) if (S.pos_ordem[k] >= ate) traco(S.ar[k]);
          if (selv >= 0) for (const k of S.adj[selv]) if (S.pos_ordem[k] >= ate) traco(S.ar[k]);
        }
      }
      ctx.setLineDash([]);
      // pulsos viajando pelas sinapses
      ctx.globalCompositeOperation = 'lighter';
      for (const s of S.sparks) {
        const e = S.ar[s.k], A = s.dir === 1 ? e[0] : e[1], B = s.dir === 1 ? e[1] : e[0], t = s.p, t0 = Math.max(0, t - .12);
        const ax = px[A], ay = py[A], bx = px[B], by = py[B], x = ax + (bx - ax) * t, y = ay + (by - ay) * t, x0 = ax + (bx - ax) * t0, y0 = ay + (by - ay) * t0;
        const c = corDe(S.nos[A]), f = s.amb ? .45 : 1;
        ctx.strokeStyle = `rgba(${c[0] * .5 + 127},${c[1] * .5 + 127},${c[2] * .5 + 127},${.55 * f})`; ctx.lineWidth = 1.6; ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x, y); ctx.stroke();
        ctx.globalAlpha = .95 * f; const q = 6 * Math.max(.6, ps[A] / esc); ctx.drawImage(sprite([c[0] * .5 + 127 | 0, c[1] * .5 + 127 | 0, c[2] * .5 + 127 | 0]), x - q, y - q, q * 2, q * 2); ctx.globalAlpha = 1;
      }
      // neurônios
      for (const i of ord) {
        const n = S.nos[i], nasc = n.nasc; if (nasc <= 0) continue;
        const c = corDe(n), sc = ps[i] / esc, pf = prof(pz[i]), d = dimDe(i), crescer = nasc < 1 ? (1 - Math.pow(1 - nasc, 3)) * (1 + (1 - nasc) * .6) : 1;
        const q = n.r * ps[i] * .8 * (1 + n.luz * .55) * crescer * (1 - .32 * S.mix);
        ctx.globalAlpha = Math.min(1, (.5 + .5 * pf) * d * (nasc < 1 ? nasc : 1) * (.72 + .28 * n.luz + (n.g === 'conversa' ? -.12 : 0)));
        ctx.drawImage(sprite(c), px[i] - q * 2, py[i] - q * 2, q * 4, q * 4);
        if ((S.t < n.ate) || n.pend) {
          const pul = n.pend ? .5 + .5 * Math.sin(S.t * 2.4 + i) : .5 + .5 * Math.sin(S.t * 5);
          ctx.globalAlpha = Math.min(1, (n.pend ? .35 + .3 * pul : (.55 + .4 * pul)) * d);
          ctx.strokeStyle = n.pend ? 'rgb(255,120,70)' : 'rgb(255,226,150)'; ctx.lineWidth = 1.2;
          ctx.beginPath(); ctx.arc(px[i], py[i], q * (1.15 + .5 * pul + (1 - n.luz) * 1.2), 0, 6.2832); ctx.stroke();
        }
        if (i === selv) { ctx.globalAlpha = 1; ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.arc(px[i], py[i], q * 1.5, 0, 6.2832); ctx.stroke(); }
      }
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
      // rótulos
      const rot = [], vis = new Set();
      if (selv >= 0) rot.push(selv);
      if (S.hover >= 0) rot.push(S.hover);
      if (busca) [...busca].slice(0, 14).forEach(i => rot.push(i));
      S.nos.forEach((n, i) => { if (S.t < n.ate && n.nasc > .8) rot.push(i); });
      if (S.rotulos && !busca) {
        const top = S.nos.map((x, i) => [x.deg * 1.2 + x.imp + Math.log(1 + x.uso) * 2 + (x.g === 'conversa' ? -9 : 0), i]).sort((a, b) => b[0] - a[0]).slice(0, S.zoom > 1.3 ? 26 : 11);
        top.forEach(t => { if (pz[t[1]] < R * .25 && S.nos[t[1]].nasc > .95) rot.push(t[1]); });
      }
      ctx.font = '600 11px ui-monospace,Menlo,Consolas,monospace'; ctx.textBaseline = 'middle'; const caixas = [];
      for (const i of rot) {
        if (vis.has(i)) continue; vis.add(i);
        const t = S.nos[i].t.length > 30 ? S.nos[i].t.slice(0, 29) + '…' : S.nos[i].t, w = ctx.measureText(t).width, x = px[i] + 9 * Math.max(.7, ps[i] / esc), y = py[i] - 9 * Math.max(.7, ps[i] / esc);
        const bx = x < W - w - 8 ? x : px[i] - w - 9, r = [bx - 3, y - 8, w + 6, 16];
        if (r[0] < 2 || r[1] < 2 || r[0] + r[2] > W - 2 || r[1] + r[3] > H - 2) continue;
        if (caixas.some(o => r[0] < o[0] + o[2] && r[0] + r[2] > o[0] && r[1] < o[1] + o[3] && r[1] + r[3] > o[1])) continue;
        caixas.push(r);
        ctx.fillStyle = 'rgba(2,5,10,.62)'; ctx.fillRect(r[0], r[1], r[2], r[3]);
        const c = corDe(S.nos[i]); ctx.fillStyle = `rgb(${c[0] * .4 + 150},${c[1] * .4 + 150},${c[2] * .4 + 150})`; ctx.fillText(t, bx, y);
      }
      if (S.mix > .6 && S.rotReg && S.reg) rotulosRegioes(caixas, cyaw, syaw, cp, sp, cam, esc, cx, cy, W, H);
    }

    // o contorno do cérebro e o corpo caloso: pontos discretos, bem fracos, só para o olho reconhecer a forma
    function proj(x, y, z, cyaw, syaw, cp, sp, cam, esc, cx, cy) {
      const x1 = x * cyaw + z * syaw, z1 = -x * syaw + z * cyaw, y1 = y * cp - z1 * sp, z2 = y * sp + z1 * cp, p = cam / (cam + z2);
      return [cx + x1 * p * esc, cy + y1 * p * esc, z2, p * esc];
    }
    function contorno(cyaw, syaw, cp, sp, cam, esc, cx, cy, R) {
      const m = Math.min(1, S.mix), busca = S.busca || S.sel >= 0 ? .45 : 1;
      ctx.lineWidth = .8; ctx.lineJoin = 'round';
      for (const f of S.casca) {
        const meio = f.length / 6 | 0, qm = proj(f[meio * 3], f[meio * 3 + 1], f[meio * 3 + 2], cyaw, syaw, cp, sp, cam, esc, cx, cy), pf = Math.max(.12, Math.min(1, .62 - qm[2] / (R * 2.2)));
        ctx.strokeStyle = `rgba(120,175,235,${.34 * pf * m * busca})`; ctx.beginPath();
        for (let k = 0; k < f.length; k += 3) { const q = proj(f[k], f[k + 1], f[k + 2], cyaw, syaw, cp, sp, cam, esc, cx, cy); if (k) ctx.lineTo(q[0], q[1]); else ctx.moveTo(q[0], q[1]); }
        ctx.stroke();
      }
      const K = S.caloso;
      if (K) {
        ctx.strokeStyle = `rgba(255,236,190,${.5 * m * busca})`; ctx.lineWidth = 1.8; ctx.beginPath();
        for (let k = 0; k < K.length; k += 3) { const q = proj(K[k], K[k + 1], K[k + 2], cyaw, syaw, cp, sp, cam, esc, cx, cy); if (k) ctx.lineTo(q[0], q[1]); else ctx.moveTo(q[0], q[1]); }
        ctx.stroke();
      }
    }
    function rotulosRegioes(caixas, cyaw, syaw, cp, sp, cam, esc, cx, cy, W, H) {
      ctx.font = '600 9px ui-monospace,Menlo,Consolas,monospace'; ctx.textBaseline = 'middle';
      const cnt = {}; S.nos.forEach(x => { cnt[x.rg] = (cnt[x.rg] || 0) + 1; });
      const alvo = ORD_REG.filter(k => S.reg[k]).map(k => {
        const g = S.reg[k], p = g.pos, U = S.U, lados = g.lado ? [-1, 1] : [0];
        let melhor = null;
        for (const l of lados) { const q = proj(p[0] * U, p[1] * U, l * Math.abs(p[2]) * U, cyaw, syaw, cp, sp, cam, esc, cx, cy); if (!melhor || q[2] < melhor[2]) melhor = q; }
        return {k, g, q: melhor};
      }).sort((a, b) => a.q[2] - b.q[2]);
      for (const a of alvo) {
        const n = cnt[a.k] || 0, t = (a.g.nome + (n ? ' ' + n : ' · vazio')).toUpperCase(), w = ctx.measureText(t).width, x = a.q[0] - w / 2, y = a.q[1] - 15 * Math.max(.8, a.q[3] / esc);
        const r = [x - 3, y - 7, w + 6, 14];
        if (r[0] < 2 || r[1] < 2 || r[0] + r[2] > W - 2 || r[1] + r[3] > H - 2) continue;
        if (caixas.some(o => r[0] < o[0] + o[2] && r[0] + r[2] > o[0] && r[1] < o[1] + o[3] && r[1] + r[3] > o[1])) continue;
        caixas.push(r);
        const c = a.g.cor, al = Math.min(1, (S.mix - .6) / .4) * (n ? .92 : .5);
        ctx.fillStyle = `rgba(2,5,10,${.5 * al})`; ctx.fillRect(r[0], r[1], r[2], r[3]);
        ctx.fillStyle = `rgba(${c[0] * .5 + 120 | 0},${c[1] * .5 + 120 | 0},${c[2] * .5 + 120 | 0},${al})`; ctx.fillText(t, x, y);
      }
    }

    // ---------- interação ----------
    function achar(x, y) {
      let melhor = -1, md = 1e9;
      for (let i = 0; i < S.n; i++) { if (S.nos[i].nasc < .5) continue; const d = Math.hypot(px[i] - x, py[i] - y), lim = Math.max(14, S.nos[i].r * ps[i] * .8 * 1.4); if (d < lim && d - pz[i] * .01 < md) { md = d - pz[i] * .01; melhor = i; } }
      return melhor;
    }
    const ptr = new Map(); let arrasto = null, pinca = 0, tap = null;
    function pos(e) { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
    canvas.style.touchAction = 'none';
    canvas.addEventListener('pointerdown', e => { canvas.setPointerCapture(e.pointerId); ptr.set(e.pointerId, pos(e)); const p = pos(e); arrasto = {x: p[0], y: p[1], mov: 0, t: performance.now()}; S.auto = false; if (ptr.size === 2) { const v = [...ptr.values()]; pinca = Math.hypot(v[0][0] - v[1][0], v[0][1] - v[1][1]); } });
    canvas.addEventListener('pointermove', e => {
      const p = pos(e); if (!ptr.has(e.pointerId)) { if (!S.reduzido && !arrasto) { const h = achar(p[0], p[1]); if (h !== S.hover) { S.hover = h; canvas.style.cursor = h >= 0 ? 'pointer' : 'grab'; if (S.manual || S.reduzido) desenhar(); } } return; }
      ptr.set(e.pointerId, p);
      if (ptr.size === 2) { const v = [...ptr.values()], d = Math.hypot(v[0][0] - v[1][0], v[0][1] - v[1][1]); if (pinca) S.zoomT = S.zoom = Math.max(.5, Math.min(4, S.zoom * d / pinca)); pinca = d; if (S.reduzido) desenhar(); return; }
      if (!arrasto) return; const dx = p[0] - arrasto.x, dy = p[1] - arrasto.y; arrasto.mov += Math.abs(dx) + Math.abs(dy); arrasto.x = p[0]; arrasto.y = p[1];
      S.yaw = S.yawT = S.yaw + dx * .0065; S.pitch = S.pitchT = Math.max(-1.3, Math.min(1.3, S.pitch + dy * .0065)); if (S.reduzido) desenhar();
    });
    function soltar(e) {
      const p = ptr.get(e.pointerId); ptr.delete(e.pointerId); if (ptr.size < 2) pinca = 0;
      if (arrasto && arrasto.mov < 6 && performance.now() - arrasto.t < 500 && p) {
        const i = achar(p[0], p[1]); const agora = performance.now();
        if (tap && agora - tap < 320 && i < 0) { S.yawT = .6; S.pitchT = -.18; S.zoomT = 1; S.sel = -1; cb.selecionar && cb.selecionar(null); } else { S.sel = i === S.sel ? -1 : i; cb.selecionar && cb.selecionar(S.sel >= 0 ? S.nos[S.sel] : null); if (S.sel >= 0) foco(S.sel); }
        tap = agora; if (S.reduzido) desenhar();
      }
      arrasto = null;
    }
    canvas.addEventListener('pointerup', soltar); canvas.addEventListener('pointercancel', soltar);
    canvas.addEventListener('wheel', e => { e.preventDefault(); S.zoomT = Math.max(.5, Math.min(4, S.zoomT * (e.deltaY < 0 ? 1.1 : .91))); if (S.reduzido) { S.zoom = S.zoomT; desenhar(); } }, {passive: false});

    function laco(t) {
      if (!vivo) return; raf = requestAnimationFrame(laco);
      if (document.hidden) { ult = t; return; }
      const dt = ult ? (t - ult) / 1000 : .016; ult = t; if (dt < .012 && !S.manual) return;  // ~60 fps no máximo
      passo(dt); desenhar();
      if (S.ordem && S.ar.length > 400) {   // orçamento de traços: cai se o aparelho engasga, sobe se sobra fôlego
        if (dt > .04 && S.orc > 400) S.orc = Math.max(400, S.orc * .85 | 0);
        else if (dt < .02 && S.orc < S.ar.length) S.orc = Math.min(S.ar.length, (S.orc * 1.06 + 8) | 0);
      }
    }
    function iniciar() { dimensionar(); if (!S.manual && !S.reduzido) raf = requestAnimationFrame(laco); else desenhar(); }
    function parar() { vivo = false; cancelAnimationFrame(raf); }
    function retomar() { if (!vivo) { vivo = true; ult = 0; if (!S.manual && !S.reduzido) raf = requestAnimationFrame(laco); } }
    addEventListener('resize', () => { dimensionar(); if (S.manual || S.reduzido) desenhar(); });
    iniciar();
    return {S, carregar, ativar, buscar, foco, passo, desenhar, dimensionar, parar, retomar, modo, legenda,
      rotulosRegioes(on) { S.rotReg = !!on; if (S.manual || S.reduzido) desenhar(); },
      cinema(on) { S.cinema = !!on; S.auto = true; if (!on) { S.zoomT = 1; } },
      auto(on) { S.auto = !!on; }, rotulos(on) { S.rotulos = !!on; if (S.manual || S.reduzido) desenhar(); },
      selecionar(i) { S.sel = i; if (i >= 0) foco(i); if (S.manual || S.reduzido) desenhar(); },
      camera(o) { if (o.yaw != null) S.yaw = S.yawT = o.yaw; if (o.pitch != null) S.pitch = S.pitchT = o.pitch; if (o.zoom != null) S.zoom = S.zoomT = o.zoom; },
      acender() { return S.nos.filter(x => S.t < x.ate).map(x => x.t); }};
  }
  window.Cerebro3D = {criar, COR, NOME, ORDEM, ORD_REG};
})();
