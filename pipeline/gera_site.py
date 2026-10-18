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


if __name__ == '__main__':
    {'distritos': distritos, 'tombados': tombados, 'tiles': tiles}[sys.argv[1]]()
