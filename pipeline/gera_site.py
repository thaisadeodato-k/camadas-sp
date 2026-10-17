"""Gera os arquivos do site a partir do cache do pipeline.

Uso:
    python pipeline/gera_site.py distritos   -> distritos.json (leve, 96 distritos)
    python pipeline/gera_site.py tiles       -> cache/tiles/edificacoes.geojsonl (entrada do tippecanoe)

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
    man = json.load(open(CACHE / 'fontes.json', encoding='utf-8'))
    feats = []
    for row, g in zip(D.itertuples(), geo):
        p = {
            'cd': row.cd_distrito,
            'nome': row.distrito_pop,                      # com acentos (IBGE)
            'regiao': row.nm_regiao_05,
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
                        'registro_metadados': (v['metadados'].get('data_do_registro') or '')[:10]} for c, v in man['wfs'].items()},
        'populacao': 'IBGE, Censo 2022, tabela 9923',
        'processado_em': man.get('ultima_execucao', {}).get('em'),
    }
    out = {'type': 'FeatureCollection', 'fontes': fontes, 'features': feats}
    s = json.dumps(out, ensure_ascii=False, separators=(',', ':'))
    destino.write_text(s, encoding='utf-8')
    print(f'{destino.name}: {len(feats)} distritos, {len(s.encode()) / 1e6:.2f} MB')


def tiles(destino=CACHE / 'tiles' / 'edificacoes.geojsonl'):
    """Uma linha GeoJSON por edificação, com os mesmos atributos do data.json atual."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    arqs = sorted((CACHE / 'processado').glob('*_edificacoes.parquet'))
    n = 0
    with open(destino, 'w', encoding='utf-8') as f:
        for arq in arqs:
            cd = arq.name[:2]
            E = gpd.read_parquet(arq)
            E['geometry'] = E.geometry.simplify(0.25)
            E = E[~E.geometry.is_empty].to_crs(4326)
            txt = lambda v: v.strip().replace('  ', ' ') if isinstance(v, str) else ''
            num = lambda v: int(v) if v == v and v is not None else 0
            for r, g in zip(E.itertuples(), json.loads(E.geometry.to_json())['features']):
                p = {'d': cd, 'h': round(float(r.h), 1), 'y0': num(r.ano_min), 'y1': num(r.ano_max), 'pav': num(r.pav),
                     'addr': txt(r.endereco), 'uso': txt(r.uso), 'pad': txt(r.padrao), 'bairro': txt(r.bairro), 'n': num(r.n),
                     'tomb': int(r.tomb), 'est': int(r.est), 'fav': int(bool(r.em_favela)), 'lotirr': int(bool(r.em_loteamento))}
                geom = json.loads(json.dumps(g['geometry']), parse_float=lambda x: round(float(x), 6))
                f.write(json.dumps({'type': 'Feature', 'properties': p, 'geometry': geom}, ensure_ascii=False, separators=(',', ':')) + '\n')
                n += 1
            print(f'  {arq.name}: {len(E)}', flush=True)
    print(f'{destino.name}: {n:,} edificações, {destino.stat().st_size / 1e9:.2f} GB'.replace(',', '.'))


if __name__ == '__main__':
    {'distritos': distritos, 'tiles': tiles}[sys.argv[1]]()
