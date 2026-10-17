// Etapa 0 — Extração no navegador (o GeoSampa só responde a navegadores comuns).
// Cole cada bloco no Console (F12) da aba indicada. Cada bloco baixa um arquivo .gz.

// ---------------------------------------------------------------------------
// BLOCO A — rodar numa aba aberta em https://novogeosampa.prefeitura.sp.gov.br/
// Baixa o IPTU 2026 (~70 MB), filtra os setores fiscais 001–045 e 196, agrega por
// lote (ou condomínio) e salva sp_iptu_centro.csv.gz.
// ---------------------------------------------------------------------------
(async () => {
  const BASE = "\\\\nas.prodam\\du0110_download\\GEOPORTAL_DOWNLOAD_SEM_INTERACAO\\12_Cadastro\\IPTU_INTER";
  const r = await fetch('/Download/DownloadGeneric', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ IdLayer: 352, RelativePathAndFile: 'XLS_CSV/IPTU_2026.zip', FileName: 'IPTU_2026.zip', BasePath: BASE }) });
  const u8 = new Uint8Array(await r.arrayBuffer()); const dv = new DataView(u8.buffer);
  const lnl = dv.getUint16(26, true), lxl = dv.getUint16(28, true);
  let e = u8.length - 22; while (dv.getUint32(e, true) !== 0x06054b50) e--;
  const csz = dv.getUint32(dv.getUint32(e + 16, true) + 20, true);
  const data = u8.subarray(30 + lnl + lxl, 30 + lnl + lxl + csz);
  const ok = new Set(); for (let i = 1; i <= 45; i++) ok.add(String(i).padStart(3, '0')); ok.add('196');
  const rd = new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate-raw')).pipeThrough(new TextDecoderStream('utf-8')).getReader();
  let buf = '', header = true; const agg = new Map();
  for (;;) { const { value, done } = await rd.read(); if (done) break; buf += value; const lines = buf.split('\n'); buf = lines.pop();
    for (const line of lines) { if (header) { header = false; continue; }
      const setor = line.slice(0, 3); if (!ok.has(setor)) continue; const c = line.split(';');
      const quadra = c[0].slice(3, 6), lote = c[0].slice(6, 10), cond = c[4]; const isCond = cond && cond !== '00-0';
      const key = isCond ? 'C' + setor + quadra + cond : 'L' + setor + quadra + lote;
      const ano = parseInt(c[19]) || 0, pav = parseInt(c[20]) || 0, ac = parseFloat(c[15]) || 0;
      let a = agg.get(key); if (!a) { a = [ano, ano, pav, 0, 0, c[6] + ', ' + c[7], c[22], c[23], c[9]]; agg.set(key, a); }
      if (ano && (ano < a[0] || !a[0])) a[0] = ano; if (ano > a[1]) a[1] = ano; if (pav > a[2]) a[2] = pav; a[3] += ac; a[4]++; } }
  const out = ['key;ano_min;ano_max;pav;area;n;endereco;uso;padrao;bairro'];
  for (const [k, a] of agg) out.push([k, a[0], a[1], a[2], Math.round(a[3]), a[4], a[5], a[6], a[7], a[8]].map(x => String(x).replace(/;/g, ',')).join(';'));
  const gz = await new Response(new Blob([out.join('\n')]).stream().pipeThrough(new CompressionStream('gzip'))).blob();
  const a = document.createElement('a'); a.href = URL.createObjectURL(gz); a.download = 'sp_iptu_centro.csv.gz'; document.body.appendChild(a); a.click();
})();

// ---------------------------------------------------------------------------
// BLOCO B — rodar numa aba aberta em https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/ows
// Baixa via WFS edificações, lotes, distritos, bens tombados, quadras e massas d'água
// no retângulo do centro (EPSG:31983) e salva sp_geometria.json.gz.
// ---------------------------------------------------------------------------
(async () => {
  const B = '328946,7391443,336307,7398298,EPSG:31983';
  const W = '/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&outputFormat=application/json&typeNames=';
  const r1 = v => Math.round(v * 10) / 10;
  const simp = g => { if (!g) return null; const p = g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : null;
    return p ? p.map(q => q.map(ring => ring.map(c => [r1(c[0]), r1(c[1])]))) : null; };
  const get = async u => { for (let t = 0; t < 6; t++) { try { return await fetch(u).then(r => r.json()); } catch (e) { await new Promise(r => setTimeout(r, 4000)); } } throw new Error('falhou: ' + u); };
  const geo = { edif: [], lote: [] };
  const jobs = [['edif', 'geoportal:edificacao', p => [p.qt_altura_edificacao]],
    ['lote', 'geoportal:lote_cidadao', p => [p.cd_setor_fiscal, p.cd_quadra_fiscal, p.cd_lote, p.cd_condominio, p.cd_tipo_lote, p.dc_tipo_uso_imovel, p.qt_area_construida, p.tx_situ_lote]]];
  for (const [k, t, pick] of jobs) for (let s = 0; ; s += 5000) {
    const j = await get(W + t + '&bbox=' + B + '&count=5000&startIndex=' + s + '&sortBy=cd_identificador');
    for (const f of j.features) if (f.geometry) geo[k].push([pick(f.properties), simp(f.geometry)]);
    console.log(k, geo[k].length); if (j.features.length < 5000) break; }
  const d = await get(W + 'geoportal:distrito_municipal');
  const want = ['SE', 'REPUBLICA', 'BELA VISTA', 'CONSOLACAO', 'SANTA CECILIA', 'BOM RETIRO', 'BRAS', 'LIBERDADE', 'CAMBUCI', 'PARI'];
  const norm = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase();
  geo.dist = d.features.filter(f => want.includes(norm(f.properties.nm_distrito_municipal))).map(f => [f.properties.nm_distrito_municipal, simp(f.geometry)]);
  const tb = await get(W + 'geoportal:patrimonio_cultural_bem_tombado&bbox=' + B);
  geo.tomb = tb.features.map(f => { const p = f.properties; return [{ n: p.nm_area_tombada, e: p.nm_endereco, s: p.cd_setor_fiscal, q: p.cd_quadra_fiscal, l: p.cd_lote, u: p.tx_tipo_uso,
    am: p.an_tombamento_municipio, ae: p.an_tombamento_estado, au: p.an_tombamento_uniao, st: p.tx_situacao_tombamento, z: p.tx_zepec, lk: p.tx_link_resolucao }, simp(f.geometry)]; });
  geo.quadra = (await get(W + 'geoportal:quadra_viaria_editada&bbox=' + B)).features.map(f => [0, simp(f.geometry)]);
  geo.agua = (await get(W + 'geoportal:massa_d_agua&bbox=' + B)).features.map(f => [0, simp(f.geometry)]);
  const gz = await new Response(new Blob([JSON.stringify(geo)]).stream().pipeThrough(new CompressionStream('gzip'))).blob();
  const a = document.createElement('a'); a.href = URL.createObjectURL(gz); a.download = 'sp_geometria.json.gz'; document.body.appendChild(a); a.click();
})();
