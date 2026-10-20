"""Gera os arquivos do site a partir do cache do pipeline.

Uso:
    python pipeline/gera_site.py distritos   -> distritos.json (leve, 96 distritos)
    python pipeline/gera_site.py tombados    -> tombados.json (nome e resolução de cada bem, para o cartão)
    python pipeline/gera_site.py tiles       -> cache/tiles/edificacoes.geojsonl e quadras.geojsonl (entrada do tippecanoe)

Todo número vem de saida/relatorio_qualidade.csv, fontes/populacao_distritos_censo2022.csv
ou do cache processado; nada é digitado à mão.
"""
import json, sys, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd

sys.stdout.reconfigure(encoding='utf-8')
AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
CACHE = AQUI / 'cache'


def chave(s):
    return unicodedata.normalize('NFD', str(s)).encode('ascii', 'ignore').decode().upper().strip()


def nulo(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else v


def historicos():
    """Datas históricas (historical_dates.json) -> {(distrito, linha da edificação): (ano, índice do marco)}.

    Hierarquia das datas: 1º registro histórico documentado, 2º ano do IPTU, 3º sem data.
    Vale para a edificação cujo contorno contém a coordenada do marco.
    """
    H = json.load(open(RAIZ / 'historical_dates.json', encoding='utf-8'))
    M = [(i, m) for i, m in enumerate(H['marcos']) if m.get('aplicar_a_edificacao')]
    pts = gpd.GeoSeries(gpd.points_from_xy([m['coord'][0] for _, m in M], [m['coord'][1] for _, m in M]), crs=4326).to_crs(31983)
    out = {}
    for arq in sorted((CACHE / 'processado').glob('*_edificacoes.parquet')):
        E = gpd.read_parquet(arq, columns=['geometry'])
        x0, y0, x1, y1 = E.total_bounds
        for (i, m), p in zip(M, pts):
            if x0 <= p.x <= x1 and y0 <= p.y <= y1:
                hit = E.index[E.contains(p)]
                if len(hit):
                    out[(arq.name[:2], int(hit[0]))] = (int(m['ano']), i)
    nomes = {i: m['id'] for i, m in M}
    faltam = set(nomes) - {v[1] for v in out.values()}
    if faltam:
        sys.exit(f'marcos sem edificação: {[nomes[i] for i in faltam]}')
    return out


def contagens(arq, hist):
    """Contagens por distrito para as legendas: anos, usos, pavimentos e qualidade da data."""
    cd = arq.name[:2]
    E = pd.read_parquet(arq, columns=['ano_min', 'pav', 'uso', 'est', 'com_lote', 'em_favela', 'em_loteamento', 'em_zeis1', 'tomb'])
    y = E.ano_min.to_numpy().copy()
    for (d, i), (ano, _) in hist.items():
        if d == cd:
            y[i] = ano
    conta = lambda s: {str(k): int(v) for k, v in s.value_counts().sort_index().items()}
    fora = E.em_favela | E.em_loteamento | E.em_zeis1
    return {
        'anos': conta(pd.Series(y[y > 0])),                          # ano exibido (histórico ou IPTU)
        'anos_iptu': conta(E.ano_min[E.ano_min > 0]),               # só IPTU, para a camada de qualidade
        'sem_ano': int((y == 0).sum()),
        'usos': conta(E.uso.fillna('')),
        'pav_20_ou_mais': int((E.pav >= 20).sum()),
        'estimadas_pelo_lote': int(E.est.sum()),
        'sem_lote': int((~E.com_lote.astype(bool)).sum()),
        'sem_lote_em_assentamento': int((~E.com_lote.astype(bool) & fora).sum()),
        'sem_ano_em_assentamento': int(((E.ano_min == 0) & fora).sum()),
        'em_assentamento': int(fora.sum()),
    }


def distritos(destino=RAIZ / 'distritos.json'):
    r = pd.read_csv(AQUI / 'saida' / 'relatorio_qualidade.csv', dtype={'cd_distrito': str})
    pop = pd.read_csv(AQUI / 'fontes' / 'populacao_distritos_censo2022.csv')
    D = gpd.read_file(AQUI / 'fontes' / 'geosampa_distritos_96.geojson')
    D['cd_distrito'] = D.cd_distrito_municipal.astype(str).str.zfill(2)
    D['chave'] = D.nm_distrito_municipal.map(chave)
    D = D.merge(r, on='cd_distrito', how='left').merge(pop[['distrito_chave', 'distrito', 'populacao_2022']],
                                                         left_on='chave', right_on='distrito_chave', how='left', suffixes=('', '_pop'))
    faltam = D[D.populacao_2022.isna() | D.edificacoes.isna()]
    if len(faltam):
        sys.exit(f'distritos sem população ou sem relatório: {list(faltam.nm_distrito_municipal)}')
    # contornos simplificados (15 m) para a vista da cidade inteira
    geo = D.to_crs(31983).geometry.simplify(15).to_crs(4326)
    rotulo = D.to_crs(31983).geometry.representative_point().to_crs(4326)
    man = json.load(open(CACHE / 'fontes.json', encoding='utf-8'))
    hist = historicos()
    arqs = {a.name[:2]: a for a in (CACHE / 'processado').glob('*_edificacoes.parquet')}
    feats = []
    for row, g, pr in zip(D.itertuples(), geo, rotulo):
        p = {
            'cd': row.cd_distrito,
            'nome': row.distrito_pop,                      # com acentos (IBGE)
            'regiao': row.nm_regiao_05,
            'rotulo': [round(pr.x, 5), round(pr.y, 5)],
            'populacao_2022': int(row.populacao_2022),
            'area_km2': row.area_distrito_km2,
            'edificacoes': int(row.edificacoes),
            'ano_medio': nulo(row.ano_medio),
            'ano_mediano': nulo(row.ano_mediano),
            'pct_sem_ano': row.pct_sem_ano,
            'pct_com_lote': row.pct_com_lote,
            'ano_1970': int(row.ano_1970),
            'area_construida_m2': int(row.area_construida_m2),
            # m² construídos (IPTU) por m² de território
            'densidade_construida': round(row.area_construida_m2 / (row.area_distrito_km2 * 1e6), 3),
            'edif_por_mil_hab': round(1000 * row.edificacoes / row.populacao_2022, 1),
            'edif_em_favela': int(row.edif_em_favela),
            'edif_em_loteamento': int(row.edif_em_loteamento),
            'edif_tombadas': int(row.edif_tombadas),
            'edif_em_zeis1': int(row.edif_em_zeis1),
            'pct_lotes_com_iptu': row.pct_lotes_com_iptu,
            **contagens(arqs[row.cd_distrito], hist),
            # o levantamento de edificações não cobre o distrito (menos de 1 edificação para cada 10 lotes)
            'sem_levantamento': bool(row.edificacoes < 0.1 * row.lotes),
        }
        feats.append({'type': 'Feature', 'properties': p, 'geometry': json.loads(gpd.GeoSeries([g]).to_json())['features'][0]['geometry']})
    for f in feats:  # 5 casas decimais (~1 m)
        f['geometry'] = json.loads(json.dumps(f['geometry']), parse_float=lambda x: round(float(x), 5))
    fontes = {
        'iptu': {'arquivo': man['iptu']['servidor']['arquivo'], 'modificado_no_servidor': man['iptu']['servidor']['modificado_no_servidor'][:10],
                 'revisao_metadados': (man['iptu']['metadados'].get('datas', {}).get('revision') or [None])[-1]},
        'camadas': {c: {'titulo': v['metadados'].get('titulo'), 'revisao_metadados': (v['metadados'].get('datas', {}).get('revision') or [None])[-1],
                        'publicacao_metadados': (v['metadados'].get('datas', {}).get('publication') or [None])[-1],
                        'registro_metadados': (v['metadados'].get('data_do_registro') or '')[:10]} for c, v in man['wfs'].items()},
        'populacao': 'IBGE, Censo 2022, tabela 9923',
        'historico': {'arquivo': 'historical_dates.json', 'edificacoes_com_data_historica': len(hist)},
        'processado_em': man.get('ultima_execucao', {}).get('em'),
    }
    base = json.load(open(AQUI / 'saida' / 'linha_de_base.json', encoding='utf-8'))
    out = {'type': 'FeatureCollection', 'fontes': fontes, 'cidade': base['cidade'], 'features': feats}
    s = json.dumps(out, ensure_ascii=False, separators=(',', ':'))
    destino.write_text(s, encoding='utf-8')
    print(f'{destino.name}: {len(feats)} distritos, {len(s.encode()) / 1e6:.2f} MB')


def tombados(destino=RAIZ / 'tombados.json'):
    """Bens tombados citados pelas edificações: id -> [nome, endereço, ano municipal, estadual, federal, link]."""
    out = {}
    for arq in sorted((CACHE / 'processado').glob('*_tombados.parquet')):
        for r in pd.read_parquet(arq).itertuples():
            ano = lambda v: int(v) if v == v and v is not None and str(v).strip() not in ('', '0') else 0
            txt = lambda v: str(v).strip() if v == v and v is not None else ''
            out[str(int(r.cd_identificador))] = [txt(r.nm_area_tombada), txt(r.nm_endereco), ano(r.an_tombamento_municipio),
                                                 ano(r.an_tombamento_estado), ano(r.an_tombamento_uniao), txt(r.tx_link_resolucao)]
    s = json.dumps(out, ensure_ascii=False, separators=(',', ':'))
    destino.write_text(s, encoding='utf-8')
    print(f'{destino.name}: {len(out)} bens, {len(s.encode()) / 1e6:.2f} MB')


def hexagonos(destino=RAIZ / 'hexagonos.json', raio=150):
    """Malha de hexágonos (raio em metros, topo plano, EPSG:31983) para a vista intermediária da cidade.

    Por hexágono: centro, nº de edificações, ano médio (exibido: histórico ou IPTU), sem ano,
    densidade construída (área construída do IPTU / área do hexágono; a área de cada lote é
    dividida igualmente entre as suas edificações), contagem por década para a linha do tempo,
    tombadas, com 20 pavimentos ou mais e contagem por uso (índice na lista 'usos', como no distritos.json).
    """
    hist = historicos()
    DEC = list(range(1900, 2030, 10))           # <1900, 1900s, ..., 2020s
    partes = []
    for arq in sorted((CACHE / 'processado').glob('*_edificacoes.parquet')):
        cd = arq.name[:2]
        E = gpd.read_parquet(arq, columns=['geometry', 'ckey', 'ano_min', 'area', 'tomb', 'pav', 'uso'])
        y = E.ano_min.to_numpy().copy()
        for (d, i), (ano, _) in hist.items():
            if d == cd:
                y[i] = ano
        # área do lote repartida entre as edificações do mesmo lote (sem lote: 0)
        nl = E.groupby('ckey').ckey.transform('size')
        a = (E['area'].fillna(0) / nl).fillna(0).to_numpy()   # E.area seria a área do polígono
        c = E.geometry.centroid
        partes.append(pd.DataFrame({'x': c.x.to_numpy(), 'y': c.y.to_numpy(), 'ano': y, 'a': a,
                                    'tomb': (E.tomb >= 0).to_numpy(), 'p20': (E.pav >= 20).to_numpy(), 'uso': E.uso.fillna('').to_numpy()}))
    P = pd.concat(partes, ignore_index=True)
    USOS = sorted(P.uso.unique())
    P['iu'] = P.uso.map({u: i for i, u in enumerate(USOS)})
    # coordenadas axiais do hexágono de topo plano + arredondamento cúbico
    q = (2 / 3 * P.x) / raio
    r = (-1 / 3 * P.x + np.sqrt(3) / 3 * P.y) / raio
    s = -q - r
    rq, rr, rs = np.round(q), np.round(r), np.round(s)
    dq, dr, ds = (rq - q).abs(), (rr - r).abs(), (rs - s).abs()
    fq = (dq > dr) & (dq > ds)
    fr = ~fq & (dr > ds)
    rq = np.where(fq, -rr - rs, rq)
    rr = np.where(fr, -rq - rs, rr)
    P['q'], P['r'] = rq.astype(int), rr.astype(int)
    P['dec'] = np.where(P.ano > 0, np.searchsorted(DEC, P.ano, side='right'), -1)
    com = P[P.ano > 0]
    g = P.groupby(['q', 'r'])
    H = pd.DataFrame({'n': g.size(), 'a': g.a.sum(), 'sem': g.ano.apply(lambda v: int((v == 0).sum()))})
    H['ano'] = com.groupby(['q', 'r']).ano.mean()
    extra = pd.DataFrame({'tomb': g.tomb.sum(), 'p20': g.p20.sum()})
    usos = P.groupby(['q', 'r', 'iu']).size()
    usos_hex = {k: [] for k in H.index}
    for (q_, r_, iu), n_ in usos.items():
        usos_hex[(q_, r_)].append([int(iu), int(n_)])
    dec = com.groupby(['q', 'r', 'dec']).size().unstack(fill_value=0).reindex(columns=range(len(DEC) + 1), fill_value=0)
    H = H.join(dec).fillna({k: 0 for k in dec.columns}).reset_index()
    area_hex = 3 * np.sqrt(3) / 2 * raio ** 2
    cx = raio * 1.5 * H.q
    cy = raio * np.sqrt(3) * (H.r + H.q / 2)
    ll = gpd.GeoSeries(gpd.points_from_xy(cx, cy), crs=31983).to_crs(4326)
    linhas = []
    for row, p in zip(H.itertuples(index=False), ll):
        hx = (row.q, row.r)
        linhas.append([round(p.x, 5), round(p.y, 5), int(row.n), None if row.ano != row.ano else round(row.ano, 1),
                       int(row.sem), round(row.a / area_hex, 3), [int(row[6 + k]) for k in range(len(DEC) + 1)],
                       int(extra.tomb[hx]), int(extra.p20[hx]), usos_hex[hx]])
    out = {'raio_m': raio, 'decadas': ['<1900'] + [f'{d}s' for d in DEC], 'usos': USOS,
           'campos': ['lon', 'lat', 'edificacoes', 'ano_medio', 'sem_ano', 'densidade_construida', 'por_decada',
                      'tombadas', 'pav_20_ou_mais', 'usos'],
           'hexagonos': linhas}
    s = json.dumps(out, separators=(',', ':'))
    destino.write_text(s, encoding='utf-8')
    print(f'{destino.name}: {len(linhas):,} hexágonos de {raio} m, {int(H.n.sum()):,} edificações, {len(s.encode()) / 1e6:.2f} MB'.replace(',', '.'))


def quadras(destino=CACHE / 'tiles' / 'quadras.geojsonl'):
    """Quadras viárias (chão do mapa ao aproximar), uma vez cada."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    vistos, n = set(), 0
    with open(destino, 'w', encoding='utf-8') as f:
        for arq in sorted((CACHE / 'processado').glob('*_quadras.parquet')):
            Q = gpd.read_parquet(arq)
            Q = Q[~Q.cd_identificador_quadra_viaria_editada_original.isin(vistos)]
            vistos |= set(Q.cd_identificador_quadra_viaria_editada_original)
            Q['geometry'] = Q.geometry.simplify(0.5)
            Q = Q[~Q.geometry.is_empty].to_crs(4326)
            for g in json.loads(Q.geometry.to_json())['features']:
                geom = json.loads(json.dumps(g['geometry']), parse_float=lambda x: round(float(x), 6))
                f.write(json.dumps({'type': 'Feature', 'properties': {}, 'geometry': geom}, separators=(',', ':')) + '\n')
                n += 1
    print(f'{destino.name}: {n:,} quadras'.replace(',', '.'))


def tiles(destino=CACHE / 'tiles' / 'edificacoes.geojsonl'):
    """Uma linha GeoJSON por edificação, com os atributos do data.json antigo e mais:
    zeis (em ZEIS-1), lote (dentro de um lote fiscal), yh/hm (ano e índice do marco histórico)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    arqs = sorted((CACHE / 'processado').glob('*_edificacoes.parquet'))
    hist = historicos()
    n = 0
    with open(destino, 'w', encoding='utf-8') as f:
        for arq in arqs:
            cd = arq.name[:2]
            E = gpd.read_parquet(arq)
            E['yh'], E['hm'] = 0, -1
            for (d, i), (ano, m) in hist.items():
                if d == cd:
                    E.loc[i, ['yh', 'hm']] = ano, m
            E['geometry'] = E.geometry.simplify(0.25)
            E = E[~E.geometry.is_empty].to_crs(4326)
            txt = lambda v: v.strip().replace('  ', ' ') if isinstance(v, str) else ''
            num = lambda v: int(v) if v == v and v is not None else 0
            for r, g in zip(E.itertuples(), json.loads(E.geometry.to_json())['features']):
                p = {'d': cd, 'h': round(float(r.h), 1), 'y0': num(r.ano_min), 'y1': num(r.ano_max), 'pav': num(r.pav),
                     'addr': txt(r.endereco), 'uso': txt(r.uso), 'pad': txt(r.padrao), 'bairro': txt(r.bairro), 'n': num(r.n),
                     'tomb': int(r.tomb), 'est': int(r.est), 'fav': int(bool(r.em_favela)), 'lotirr': int(bool(r.em_loteamento)),
                     'zeis': int(bool(r.em_zeis1)), 'lote': int(bool(r.com_lote)), 'yh': int(r.yh), 'hm': int(r.hm)}
                geom = json.loads(json.dumps(g['geometry']), parse_float=lambda x: round(float(x), 6))
                f.write(json.dumps({'type': 'Feature', 'properties': p, 'geometry': geom}, ensure_ascii=False, separators=(',', ':')) + '\n')
                n += 1
            print(f'  {arq.name}: {len(E)}', flush=True)
    print(f'{destino.name}: {n:,} edificações, {destino.stat().st_size / 1e9:.2f} GB'.replace(',', '.'))
    quadras()


def grupo_uso(u):
    """Mesma regra do useGroup do index.html."""
    import re
    s = (u or '').lower()
    for g, rx in ((4, r'ind[uú]stri|armaz|galp|dep[oó]sito|oficina'), (2, r'misto|loja e resid|resid[eê]ncia e outro'),
                  (3, r'escrit|consult'), (0, r'resid|apartamento|cortiço'), (1, r'loja|comerc|hotel|garagem|posto|servi')):
        if re.search(rx, s):
            return g
    return 5


def qualidade(y0, est, fav, lotirr, zeis):
    """Mesma regra do qualOf do index.html (vetorizada)."""
    q = np.zeros(len(y0), dtype=np.uint8)
    q[(y0 < 1960) & (y0 % 5 == 4) & (y0 > 0)] = 2
    q[y0 == 1970] = 1
    q[(y0 == 0) & ~(fav | lotirr | zeis)] = 3
    q[(y0 == 0) & (fav | lotirr | zeis)] = 5
    q[est] = 4
    return q


def longe(destino=RAIZ / 'quadras_longe.bin', alto=30):
    """Vista de longe: cada quadra viária vira um volume com as edificações que tem dentro;
    as edificações com altura de `alto` metros ou mais (e as poucas fora de qualquer quadra) ficam inteiras.

    Por volume: altura (média das edificações baixas, ponderada pela área do contorno), ano médio,
    anos em que 0, 25, 50, 75 e 100% das edificações datadas já existiam (linha do tempo),
    pavimentos (média ponderada), grupo de uso e qualidade predominantes, se há bem tombado,
    distrito e nº de edificações. Contornos simplificados, só o anel externo.

    Arquivo binário (little-endian): uint32 tamanho do cabeçalho, cabeçalho JSON, e os vetores
    na ordem de cabeçalho['vetores'], cada um começando num múltiplo de 4 bytes.
    """
    from shapely import get_exterior_ring, get_coordinates, get_num_coordinates
    from shapely.geometry.polygon import orient
    hist = historicos()
    Q = []
    for arq in sorted((CACHE / 'processado').glob('*_quadras.parquet')):
        Q.append(gpd.read_parquet(arq))
    Q = pd.concat(Q).drop_duplicates('cd_identificador_quadra_viaria_editada_original').reset_index(drop=True)
    Q = gpd.GeoDataFrame(Q[['geometry']], crs=Q.crs)
    partes = []
    for arq in sorted((CACHE / 'processado').glob('*_edificacoes.parquet')):
        cd = arq.name[:2]
        E = gpd.read_parquet(arq, columns=['geometry', 'h', 'ano_min', 'pav', 'uso', 'tomb', 'est', 'em_favela', 'em_loteamento', 'em_zeis1'])
        y = E.ano_min.fillna(0).astype(int).to_numpy().copy()
        y0 = y.copy()
        for (d, i), (ano, _) in hist.items():
            if d == cd:
                y[i] = ano
        P = gpd.GeoDataFrame({'d': int(cd), 'h': E.h.to_numpy(), 'y': y, 'pav': E.pav.fillna(0).to_numpy(),
                              'g': [grupo_uso(u) for u in E.uso.fillna('')],
                              'q': qualidade(y0, E.est.to_numpy() > 0, E.em_favela.to_numpy(), E.em_loteamento.to_numpy(), E.em_zeis1.to_numpy()),
                              'tomb': (E.tomb >= 0).to_numpy(), 'a': E.area.to_numpy(), 'geometry': E.geometry.to_numpy()}, crs=E.crs)
        j = gpd.sjoin(P.set_geometry(P.representative_point()), Q, how='left', predicate='within')
        P['quadra'] = j[~j.index.duplicated()].index_right.fillna(-1).astype(int)
        partes.append(P)
    P = pd.concat(partes, ignore_index=True)
    soltas = (P.h >= alto) | (P.quadra < 0)
    n = lambda v: f'{int(v):,}'.replace(',', '.')
    print(f'{n(len(P))} edificações: {n(soltas.sum())} inteiras ({n((P.h >= alto).sum())} com {alto} m ou mais), '
          f'as demais em {n(P.quadra[~soltas].nunique())} quadras')

    def resume(G, chaves):
        """Atributos por volume; G tem uma linha por edificação e a coluna 'k' (volume)."""
        G = G.assign(ah=G.a * G.h, ap=G.a * G.pav)
        g = G.groupby('k')
        R = pd.DataFrame(index=chaves)
        R['h'] = g.ah.sum() / g.a.sum()
        R['pav'] = g.ap.sum() / g.a.sum()
        R['n'] = g.size()
        R['tomb'] = g.tomb.any()
        R['d'] = g.d.agg(lambda s: s.mode().iat[0])
        R['g'] = g.g.agg(lambda s: s.mode().iat[0])
        R['q'] = g.q.agg(lambda s: s.mode().iat[0])
        dat = G[G.y > 0]
        R['ym'] = dat.groupby('k').y.mean()
        for c, p in zip(['y0', 'y25', 'y50', 'y75', 'y100'], [0, .25, .5, .75, 1]):
            R[c] = dat.groupby('k').y.quantile(p, interpolation='lower')
        return R.fillna(0)

    # volumes das quadras: só as edificações baixas
    B = P[~soltas].rename(columns={'quadra': 'k'})
    RQ = resume(B, np.sort(B.k.unique()))
    GQ = Q.geometry.iloc[RQ.index].simplify(8)
    # edificações inteiras
    S = P[soltas].reset_index(drop=True)
    RS = resume(S.assign(k=S.index), S.index)
    GS = S.geometry.simplify(2)
    R = pd.concat([RQ.assign(inteira=0), RS.assign(inteira=1)], ignore_index=True)
    G = gpd.GeoSeries(pd.concat([GQ, GS], ignore_index=True).to_numpy(), crs=Q.crs)
    # um anel externo por parte (multipolígonos viram várias partes com os mesmos atributos), anti-horário
    G = G.explode(index_parts=False)
    G = G[~G.is_empty & (G.area > 0)]
    G = gpd.GeoSeries([orient(p, 1.0) for p in G], index=G.index, crs=Q.crs).to_crs(4326)
    R = R.loc[G.index].reset_index(drop=True)
    aneis = get_exterior_ring(G.to_numpy())
    xy = get_coordinates(aneis)
    nv = get_num_coordinates(aneis)
    ini = np.concatenate([[0], np.cumsum(nv)]).astype(np.uint32)
    # coordenadas em uint16 dentro do retângulo da cidade (passo de cerca de 1 m)
    x0, y0 = xy.min(0)
    x1, y1 = xy.max(0)
    qx = np.round((xy[:, 0] - x0) / (x1 - x0) * 65535).astype(np.uint16)
    qy = np.round((xy[:, 1] - y0) / (y1 - y0) * 65535).astype(np.uint16)
    vet = [('inicio', ini), ('xy', np.column_stack([qx, qy]).ravel()),
           ('h_dm', np.round(R.h * 10).clip(0, 65535).astype(np.uint16)),
           ('ano_medio', np.round(R.ym).astype(np.uint16)),
           ('anos_quartis', R[['y0', 'y25', 'y50', 'y75', 'y100']].to_numpy().astype(np.uint16).ravel()),
           ('n', R.n.clip(0, 65535).astype(np.uint16)),
           ('pav', np.round(R.pav).clip(0, 255).astype(np.uint8)), ('uso', R.g.astype(np.uint8)),
           ('qualidade', R.q.astype(np.uint8)), ('tomb', R.tomb.astype(np.uint8)),
           ('distrito', R.d.astype(np.uint8)), ('inteira', R.inteira.astype(np.uint8))]
    cab = {'volumes': len(R), 'vertices': int(len(xy)), 'bbox': [x0, y0, x1, y1], 'alto_m': alto,
           'vetores': [[k, str(v.dtype), int(v.size)] for k, v in vet]}
    c = json.dumps(cab, separators=(',', ':')).encode()
    c += b' ' * (-(4 + len(c)) % 4)
    with open(destino, 'wb') as f:
        f.write(np.uint32(len(c)).tobytes() + c)
        for _, v in vet:
            b = np.ascontiguousarray(v).astype(v.dtype.newbyteorder('<')).tobytes()
            f.write(b + b'\0' * (-len(b) % 4))
    print(f'{destino.name}: {n(len(R))} volumes ({n(len(RQ))} quadras), {n(len(xy))} vértices, '
          f'{destino.stat().st_size / 1e6:.1f} MB')


if __name__ == '__main__':
    {'distritos': distritos, 'tombados': tombados, 'tiles': tiles, 'hexagonos': hexagonos, 'longe': longe}[sys.argv[1]]()
