"""Pipeline do Camadas São Paulo: baixa, cruza e mede as edificações por distrito.

Uso:
    python pipeline/camadas.py --distritos "JARDIM ANGELA" "CIDADE TIRADENTES" PERUS
    python pipeline/camadas.py --todos
    python pipeline/camadas.py --todos --renova iptu edificacao   # baixa de novo só essas fontes

Etapas, todas retomáveis (o que já está no cache é pulado):
  1. fontes     lê a data de atualização de cada fonte (catálogo de metadados do GeoSampa
                e pasta de downloads do IPTU) e grava em cache/fontes.json
  2. iptu       baixa o IPTU da cidade uma única vez e agrega por lote (ou condomínio)
  3. wfs        para cada distrito, baixa edificações, lotes, quadras, bens tombados,
                favelas e loteamentos em quadrículas de 1 km que tocam o distrito;
                as ZEIS-1 vêm de uma vez para a cidade toda (filtro por atributo)
  4. cruzamento IPTU -> lote pelo código fiscal; edificação -> lote pela posição
  5. relatório  métricas de qualidade por distrito em relatorio_qualidade.csv

Método igual ao do pipeline original (pipeline/legado). Diferenças: os dados vêm por
distrito (não por um retângulo fixo do centro), o download roda fora do navegador e,
quando o ponto da edificação cai em mais de um lote, vale o lote que tem ano no IPTU.
"""
import argparse, gzip, hashlib, json, math, os, re, sys, time, unicodedata, zipfile
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import geopandas as gpd
import requests
from shapely.geometry import box, shape

AQUI = Path(__file__).resolve().parent
FONTES = AQUI / 'fontes'
CACHE = AQUI / 'cache'
SAIDA = AQUI / 'saida'
CRS = 'EPSG:31983'

WFS = 'https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wfs'
GEOSAMPA = 'https://novogeosampa.prefeitura.sp.gov.br/'
METADADOS = 'https://metadados.geosampa.prefeitura.sp.gov.br/geonetwork/srv/api/records/{}/formatters/xml'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36'

IPTU_ANO = 2026
IPTU_LAYER = 352
IPTU_BASE = r'\\nas.prodam\du0110_download\GEOPORTAL_DOWNLOAD_SEM_INTERACAO\12_Cadastro\IPTU_INTER'
IPTU_META = 'b971efa1-aad5-42f3-ad28-18f1f4efe270'

# camada WFS -> (campo identificador, metadados no catálogo, campos a guardar, baixar em quadrículas)
CAMADAS = {
    'edificacao': ('cd_identificador', 'bcf69ef1-2f9e-42c2-b7ec-e808f89e8116',
                   ['cd_identificador', 'qt_altura_edificacao', 'dt_atualizacao'], True),
    'lote_cidadao': ('cd_identificador', '62c1113c-36a4-43d1-b763-81ec63b58116',
                     ['cd_identificador', 'cd_setor_fiscal', 'cd_quadra_fiscal', 'cd_lote', 'cd_condominio',
                      'cd_tipo_lote', 'dc_tipo_uso_imovel', 'qt_area_construida', 'tx_situ_lote'], True),
    'quadra_viaria_editada': ('cd_identificador_quadra_viaria_editada_original', 'b3cbe872-f725-4a29-b59d-904af06ee23d',
                              ['cd_identificador_quadra_viaria_editada_original'], True),
    'patrimonio_cultural_bem_tombado': ('cd_identificador', 'f3522ff3-df73-4fc4-bff7-0344945f02f8',
                                        ['cd_identificador', 'nm_area_tombada', 'nm_endereco', 'tx_tipo_uso',
                                         'an_tombamento_municipio', 'an_tombamento_estado', 'an_tombamento_uniao',
                                         'tx_situacao_tombamento', 'tx_link_resolucao', 'dt_carga'], False),
    'habita2geosampa_habi_favela2geosampa': ('gid', 'cc8970eb-fbb2-4671-b9aa-0ea7f0faa1d7',
                                             ['gid', 'nome', 'tot_domicilio', 'areageo_m2', 'anoimplant'], False),
    'habita2geosampa_habi_loteamento2geosampa': ('gid', '3948e9f0-f89e-4219-9032-4d5f49835d32',
                                                 ['gid', 'nome', 'totlotes', 'areageo_m2', 'definicao'], False),
}
# camadas baixadas uma vez para a cidade inteira, filtradas por atributo
# (perímetros de zona da Lei 18.081/2024, o mapa de zoneamento atualizado mais recentemente no GeoSampa)
CAMADAS_CIDADE = {
    'perimetro_zona_lei_18081_24': ('cd_identificador', '9c536c5c-535b-4b8b-b9e0-e1435f470e58',
                                    ['cd_identificador', 'cd_zoneamento_perimetro', 'dt_atualizacao'],
                                    "cd_zoneamento_perimetro='ZEIS-1'"),
}
QUADRICULA = 1000  # metros
PAGINA = 5000
SIMULTANEOS = 4  # pedidos ao WFS em paralelo

sys.stdout.reconfigure(encoding='utf-8')
http = requests.Session()
http.headers['User-Agent'] = UA


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def agora():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def chave(nome):
    s = unicodedata.normalize('NFD', str(nome)).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', s).strip().upper()


def slug(nome):
    return chave(nome).lower().replace(' ', '-')


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, 'rb') as f:
        for bloco in iter(lambda: f.read(1 << 20), b''):
            h.update(bloco)
    return h.hexdigest()


def grava_json(caminho, obj):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + '.part')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def le_json(caminho, padrao=None):
    try:
        with open(caminho, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return padrao


def pede(metodo, url, tentativas=6, **kw):
    """Requisição com novas tentativas (espera crescente) para quedas do servidor."""
    kw.setdefault('timeout', 180)
    for t in range(tentativas):
        try:
            r = http.request(metodo, url, **kw)
            if r.status_code < 500:
                r.raise_for_status()
                return r
            erro = f'HTTP {r.status_code}'
        except requests.RequestException as e:
            erro = str(e)[:200]
        espera = 5 * 2 ** t
        log(f'  falhou ({erro}); nova tentativa em {espera}s')
        time.sleep(espera)
    raise RuntimeError(f'servidor não respondeu: {url}')


# ---------------------------------------------------------------- 1. fontes

def datas_metadados(uuid):
    """Datas do registro no catálogo do GeoSampa: revisão/publicação/criação do dado e do registro."""
    ns = {'gmd': 'http://www.isotc211.org/2005/gmd', 'gco': 'http://www.isotc211.org/2005/gco'}
    try:
        raiz = ET.fromstring(pede('GET', METADADOS.format(uuid), tentativas=3, timeout=60).content)
    except Exception as e:
        return {'uuid': uuid, 'erro': str(e)[:200]}
    out = {'uuid': uuid, 'url': f'https://metadados.geosampa.prefeitura.sp.gov.br/geonetwork/srv/por/catalog.search#/metadata/{uuid}'}
    ds = raiz.find('gmd:dateStamp/*', ns)
    if ds is not None:
        out['data_do_registro'] = ds.text
    titulo = raiz.find('.//gmd:identificationInfo//gmd:citation/gmd:CI_Citation/gmd:title/gco:CharacterString', ns)
    if titulo is not None:
        out['titulo'] = titulo.text
    for d in raiz.findall('.//gmd:identificationInfo//gmd:citation/gmd:CI_Citation/gmd:date/gmd:CI_Date', ns):
        tipo = d.find('gmd:dateType/gmd:CI_DateTypeCode', ns)
        valor = d.find('gmd:date/*', ns)
        if tipo is not None and valor is not None:
            out.setdefault('datas', {}).setdefault(tipo.get('codeListValue'), []).append(valor.text)
    return out


def iptu_no_servidor():
    r = pede('GET', GEOSAMPA + 'Download/Nas/TreeGeneric', params={'layerId': IPTU_LAYER, 'path': 'XLS_CSV', 'depth': 1, 'includeFiles': 'true'})
    for f in r.json()['node']['children']:
        if f['name'] == f'IPTU_{IPTU_ANO}.zip':
            return {'arquivo': f['name'], 'caminho': f['relativePath'], 'tamanho': f['size'], 'modificado_no_servidor': f['modified']}
    raise RuntimeError(f'IPTU_{IPTU_ANO}.zip não está na pasta de downloads do GeoSampa')


def etapa_fontes():
    log('1. fontes: datas de atualização')
    man = le_json(CACHE / 'fontes.json', {})
    man['verificado_em'] = agora()
    man['iptu'] = {**man.get('iptu', {}), 'servidor': iptu_no_servidor(), 'metadados': datas_metadados(IPTU_META)}
    for camada, (_, uuid, _, _) in CAMADAS.items():
        man.setdefault('wfs', {}).setdefault(camada, {})['metadados'] = datas_metadados(uuid)
    for camada, (_, uuid, _, _) in CAMADAS_CIDADE.items():
        man.setdefault('wfs', {}).setdefault(camada, {})['metadados'] = datas_metadados(uuid)
    for nome in ['geosampa_distritos_96.geojson', 'populacao_distritos_censo2022.csv']:
        man.setdefault('arquivos_locais', {})[nome] = {'sha256': sha256(FONTES / nome)}
    grava_json(CACHE / 'fontes.json', man)
    return man


# ---------------------------------------------------------------- 2. iptu

def etapa_iptu(man):
    pasta = CACHE / 'iptu'
    pasta.mkdir(parents=True, exist_ok=True)
    zipf = pasta / f'IPTU_{IPTU_ANO}.zip'
    srv = man['iptu']['servidor']
    if zipf.exists() and zipf.stat().st_size == srv['tamanho']:
        log(f'2. iptu: {zipf.name} já está no cache')
    else:
        log(f"2. iptu: baixando {zipf.name} ({srv['tamanho'] / 1e6:.0f} MB)")
        pede('GET', GEOSAMPA)
        r = pede('POST', GEOSAMPA + 'Download/DownloadGeneric', stream=True, timeout=600,
                 json={'IdLayer': IPTU_LAYER, 'RelativePathAndFile': srv['caminho'], 'FileName': srv['arquivo'], 'BasePath': IPTU_BASE})
        if 'zip' not in r.headers.get('content-type', ''):
            raise RuntimeError('o GeoSampa não devolveu um arquivo zip: ' + r.text[:300])
        tmp = zipf.with_suffix('.zip.part')
        with open(tmp, 'wb') as f:
            for bloco in r.iter_content(1 << 20):
                f.write(bloco)
        if tmp.stat().st_size != srv['tamanho']:
            raise RuntimeError('download do IPTU incompleto')
        os.replace(tmp, zipf)
    hz = sha256(zipf)
    agg = pasta / f'iptu_{IPTU_ANO}_por_lote.parquet'
    if agg.exists() and man['iptu'].get('sha256') == hz:
        log('   agregação por lote já está no cache')
    else:
        log('   agregando por lote (3,9 milhões de linhas)')
        agrega_iptu(zipf, agg)
    man['iptu'].update({'sha256': hz, 'baixado_em': man['iptu'].get('baixado_em') if man['iptu'].get('sha256') == hz else agora()})
    grava_json(CACHE / 'fontes.json', man)
    return pd.read_parquet(agg)


def agrega_iptu(zipf, destino):
    """Mesma regra do bloco A de pipeline/legado/00_extract_browser.js, depois o groupby de 02_join.py."""
    col = {0: 'sql', 4: 'cond', 6: 'logr', 7: 'num', 9: 'bairro', 15: 'area', 19: 'ano', 20: 'pav', 22: 'uso', 23: 'padrao'}
    partes, linhas = [], 0
    with zipfile.ZipFile(zipf) as z:
        with z.open(z.infolist()[0]) as f:
            for df in pd.read_csv(f, sep=';', encoding='utf-8', dtype=str, usecols=list(col), header=0,
                                  names=None, chunksize=500_000, keep_default_na=False, quoting=3):
                df.columns = [col[i] for i in sorted(col)]
                linhas += len(df)
                setor, quadra, lote = df.sql.str[0:3], df.sql.str[3:6], df.sql.str[6:10]
                cond = df.cond.str.strip()
                eh_cond = (cond != '') & (cond != '00-0')
                df['key'] = np.where(eh_cond, 'C' + setor + quadra + cond, 'L' + setor + quadra + lote)
                df['ano'] = pd.to_numeric(df.ano, errors='coerce').fillna(0).astype(int)
                df['pav'] = pd.to_numeric(df.pav, errors='coerce').fillna(0).astype(int)
                df['area'] = pd.to_numeric(df.area, errors='coerce').fillna(0)
                df['endereco'] = df.logr.str.strip() + ', ' + df.num.str.strip()
                partes.append(df[['key', 'ano', 'pav', 'area', 'endereco', 'uso', 'padrao', 'bairro']])
                log(f'   {linhas:,} linhas lidas'.replace(',', '.'))
    df = pd.concat(partes, ignore_index=True)
    anos = df.ano.where(df.ano > 0)
    g = df.assign(anop=anos).groupby('key', sort=False)
    I = pd.DataFrame({'ano_min': g.anop.min(), 'ano_max': g.ano.max(), 'pav': g.pav.max(), 'area': g.area.sum().round(),
                      'n': g.size(), 'endereco': g.endereco.first(), 'uso': g.uso.first(), 'padrao': g.padrao.first(),
                      'bairro': g.bairro.first()}).reset_index()
    I['ckey'] = np.where(I.key.str[0] == 'C', I.key.str[:7] + I.key.str[7:9], I.key)
    moda = lambda s: s.mode().iat[0] if len(s.mode()) else None
    unicos = I[~I.ckey.duplicated(keep=False)].drop(columns='key')
    multi = I[I.ckey.duplicated(keep=False)]
    gm = multi.groupby('ckey')
    multi = pd.DataFrame({'ano_min': gm.ano_min.min(), 'ano_max': gm.ano_max.max(), 'pav': gm.pav.max(), 'area': gm.area.sum(),
                          'n': gm.n.sum(), 'endereco': gm.endereco.first(), 'uso': gm.uso.agg(moda), 'padrao': gm.padrao.agg(moda),
                          'bairro': gm.bairro.first()}).reset_index()
    out = pd.concat([unicos, multi], ignore_index=True)
    destino.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(destino, index=False)
    log(f'   {linhas:,} linhas -> {len(out):,} lotes/condomínios'.replace(',', '.'))


# ---------------------------------------------------------------- 3. wfs

def baixa_pagina(camada, idc, bbox, inicio):
    r = pede('GET', WFS, params={'service': 'WFS', 'version': '2.0.0', 'request': 'GetFeature', 'typeNames': 'geoportal:' + camada,
                                 'outputFormat': 'application/json', 'srsName': CRS, 'count': PAGINA, 'startIndex': inicio,
                                 'sortBy': idc, 'bbox': ','.join(f'{v:.0f}' for v in bbox) + ',' + CRS})
    try:
        return r.json()['features']
    except Exception:
        raise RuntimeError(f'resposta inválida do WFS para {camada}: {r.text[:300]}')


def quadriculas(poligono, lado):
    x0, y0, x1, y1 = poligono.bounds
    x0, y0 = math.floor(x0 / lado) * lado, math.floor(y0 / lado) * lado
    area = poligono.buffer(50)
    for x in np.arange(x0, x1, lado):
        for y in np.arange(y0, y1, lado):
            c = box(x, y, x + lado, y + lado)
            if c.intersects(area):
                yield f'{int(x)}_{int(y)}', c.bounds


def baixa_camada(pasta, camada, poligono):
    """Baixa uma camada para o distrito. Cada quadrícula fica salva; se cair, recomeça da que faltou."""
    idc, _, campos, em_quadriculas = CAMADAS[camada]
    destino = pasta / f'{camada}.json.gz'
    if destino.exists():
        return destino
    partes = pasta / f'{camada}_partes'
    partes.mkdir(parents=True, exist_ok=True)
    celulas = list(quadriculas(poligono, QUADRICULA)) if em_quadriculas else [('distrito', poligono.buffer(50).bounds)]

    def uma(celula):
        nome, bbox = celula
        arq = partes / f'{nome}.json.gz'
        if arq.exists():
            return
        feats, inicio = [], 0
        while True:
            pag = baixa_pagina(camada, idc, bbox, inicio)
            feats += [{'p': {k: f['properties'].get(k) for k in campos}, 'g': f['geometry']} for f in pag if f.get('geometry')]
            if len(pag) < PAGINA:
                break
            inicio += PAGINA
        with gzip.open(arq.with_suffix('.gz.part'), 'wt', encoding='utf-8') as f:
            json.dump(feats, f, separators=(',', ':'))
        os.replace(arq.with_suffix('.gz.part'), arq)

    # algumas quadrículas ao mesmo tempo: de longe (Actions, nos EUA) cada pedido demora mais
    with ThreadPoolExecutor(SIMULTANEOS) as ex:
        for i, _ in enumerate(ex.map(uma, celulas), 1):
            if i % 10 == 0 or i == len(celulas):
                log(f'     {camada}: {i}/{len(celulas)} quadrículas')
    vistos, todas = set(), []
    for arq in sorted(partes.glob('*.json.gz')):
        with gzip.open(arq, 'rt', encoding='utf-8') as f:
            for ft in json.load(f):
                k = ft['p'][idc]
                if k not in vistos:
                    vistos.add(k)
                    todas.append(ft)
    todas.sort(key=lambda ft: ft['p'][idc])
    with gzip.open(destino.with_suffix('.gz.part'), 'wt', encoding='utf-8') as f:
        json.dump(todas, f, separators=(',', ':'))
    os.replace(destino.with_suffix('.gz.part'), destino)
    for arq in partes.glob('*'):
        arq.unlink()
    partes.rmdir()
    return destino


def baixa_cidade(camada, man):
    """Camada inteira da cidade, só as feições que passam no filtro (ex.: ZEIS-1)."""
    idc, _, campos, filtro = CAMADAS_CIDADE[camada]
    destino = CACHE / 'wfs' / '_cidade' / f'{camada}.json.gz'
    if not destino.exists():
        log(f'3. wfs: {camada} (cidade inteira, {filtro})')
        destino.parent.mkdir(parents=True, exist_ok=True)
        feats, inicio = [], 0
        while True:
            r = pede('GET', WFS, params={'service': 'WFS', 'version': '2.0.0', 'request': 'GetFeature', 'typeNames': 'geoportal:' + camada,
                                         'outputFormat': 'application/json', 'srsName': CRS, 'count': PAGINA, 'startIndex': inicio,
                                         'sortBy': idc, 'cql_filter': filtro})
            pag = r.json()['features']
            feats += [{'p': {k: f['properties'].get(k) for k in campos}, 'g': f['geometry']} for f in pag if f.get('geometry')]
            if len(pag) < PAGINA:
                break
            inicio += PAGINA
        with gzip.open(destino.with_suffix('.gz.part'), 'wt', encoding='utf-8') as f:
            json.dump(feats, f, separators=(',', ':'))
        os.replace(destino.with_suffix('.gz.part'), destino)
    info = man.setdefault('wfs', {}).setdefault(camada, {})
    h = sha256(destino)
    if info.get('cidade', {}).get('sha256') != h:
        info['cidade'] = {'sha256': h, 'baixado_em': agora(), 'filtro': filtro}
    gdf = le_camada(destino)
    if len(gdf):
        info['cidade']['ultima_alteracao_nos_dados'] = str(pd.Series(gdf.dt_atualizacao).dropna().max())
    return gdf


def le_camada(arq):
    with gzip.open(arq, 'rt', encoding='utf-8') as f:
        feats = json.load(f)
    if not feats:
        return gpd.GeoDataFrame(geometry=[], crs=CRS)
    gdf = gpd.GeoDataFrame([ft['p'] for ft in feats], geometry=[shape(ft['g']) for ft in feats], crs=CRS)
    gdf['geometry'] = gdf.geometry.make_valid()
    return gdf[~gdf.geometry.is_empty]


# ---------------------------------------------------------------- 4. cruzamento

def pontos(E):
    """Ponto interno de cada edificação, com 'i' = índice da edificação (posição a posição, sem realinhar)."""
    return gpd.GeoDataFrame({'i': E.index.to_numpy()}, geometry=E.representative_point().to_numpy(), crs=CRS)

def processa_distrito(cd, nome, poligono, I, man, ZEIS):
    s = slug(nome)
    pasta = CACHE / 'wfs' / f'{cd}_{s}'
    pasta.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    log(f'3. wfs: {nome}')
    arqs = {c: baixa_camada(pasta, c, poligono) for c in CAMADAS}
    reg = man.setdefault('wfs', {})
    for c, arq in arqs.items():
        info = reg.setdefault(c, {}).setdefault('por_distrito', {}).get(cd, {})
        h = sha256(arq)
        if info.get('sha256') != h:
            info = {'sha256': h, 'baixado_em': agora()}
        reg[c]['por_distrito'][cd] = info
    t_wfs = time.time() - t0

    log(f'4. cruzamento: {nome}')
    E = le_camada(arqs['edificacao']).rename(columns={'qt_altura_edificacao': 'h'})
    L = le_camada(arqs['lote_cidadao'])
    T = le_camada(arqs['patrimonio_cultural_bem_tombado'])
    FV = le_camada(arqs['habita2geosampa_habi_favela2geosampa'])
    LT = le_camada(arqs['habita2geosampa_habi_loteamento2geosampa'])
    Q = le_camada(arqs['quadra_viaria_editada'])
    for c, df in [('edificacao', E), ('patrimonio_cultural_bem_tombado', T)]:
        col = {'edificacao': 'dt_atualizacao', 'patrimonio_cultural_bem_tombado': 'dt_carga'}[c]
        if len(df) and col in df:
            reg[c]['por_distrito'][cd]['ultima_alteracao_nos_dados'] = str(pd.Series(df[col]).dropna().max())

    dentro = lambda g: g.representative_point().within(poligono)
    E = E[dentro(E.geometry)].copy()
    E['h'] = pd.to_numeric(E.h, errors='coerce')
    n_levantamento = len(E)

    # IPTU -> lote (mesma chave do 02_join.py)
    cond = L.cd_condominio.fillna('00')
    L['ckey'] = np.where(cond != '00', 'C' + L.cd_setor_fiscal + L.cd_quadra_fiscal + cond.str[:2],
                         'L' + L.cd_setor_fiscal + L.cd_quadra_fiscal + L.cd_lote)
    L = L.merge(I, on='ckey', how='left')
    L['no_distrito'] = dentro(L.geometry)
    Ld = L[L.no_distrito]
    situ = Ld.tx_situ_lote.fillna('—').value_counts().to_dict()

    # edificação -> lote: ponto interno da edificação dentro do lote
    pt = pontos(E)
    cols = ['ckey', 'ano_min', 'ano_max', 'pav', 'area', 'n', 'endereco', 'uso', 'padrao', 'bairro', 'tx_situ_lote', 'geometry']
    j = gpd.sjoin(pt, L[cols], how='left', predicate='within')
    n_multi = int(j.i.duplicated().sum())
    j['_tem_ano'] = j.ano_min.notna()
    j['_ativo'] = j.tx_situ_lote.fillna('').str.upper() != 'CANCELADO'
    j = j.sort_values(['i', '_tem_ano', '_ativo'], ascending=[True, False, False]).drop_duplicates('i').set_index('i')
    for c in cols[:-1]:
        E[c] = j[c].reindex(E.index)
    E['com_lote'] = j.index_right.reindex(E.index).notna()
    E['est'] = 0

    # volume estimado pelo lote em prédios novos (03_build.py)
    hmax = E.groupby('ckey').h.max()
    novos = Ld[(Ld.ano_min >= 2008) & (Ld.pav >= 4)]
    novos = novos[[r.pav * 3 > 1.6 * max(hmax.get(r.ckey, 0) or 0, 1) for r in novos.itertuples()]]
    novos = novos.drop_duplicates('ckey')
    if len(novos):
        E = E[~E.ckey.isin(set(novos.ckey))]
        add = novos[cols[:-2] + ['geometry']].copy()
        add['geometry'] = add.geometry.buffer(-1.5)
        add['h'] = add.pav * 3.0
        add['com_lote'] = True
        add['est'] = 1
        E = pd.concat([E, gpd.GeoDataFrame(add, geometry='geometry', crs=CRS)], ignore_index=True)
        E = E[~E.geometry.is_empty]
    E['h'] = E.h.where(E.h > 1, E.pav.fillna(1).clip(lower=1) * 3).clip(2.5, 180)

    # patrimônio tombado
    Tp = T[T.tx_situacao_tombamento.fillna('').str.upper().str.contains('TOMB')] if len(T) else T
    E['tomb'] = -1
    if len(Tp):
        pt = pontos(E)
        jt = gpd.sjoin(pt, Tp[['cd_identificador', 'geometry']], how='left', predicate='within').drop_duplicates('i').set_index('i')
        E['tomb'] = jt.cd_identificador.reindex(E.index).fillna(-1).astype(int)

    # favelas e loteamentos: quantas edificações caem dentro (para a camada de qualidade da Etapa 4)
    def dentro_de(areas):
        if not len(areas):
            return pd.Series(False, index=E.index)
        pt = pontos(E)
        jj = gpd.sjoin(pt, areas[['geometry']], how='inner', predicate='within')
        return pd.Series(E.index.isin(jj.i), index=E.index)
    E['em_favela'] = dentro_de(FV)
    E['em_loteamento'] = dentro_de(LT)
    E['em_zeis1'] = dentro_de(ZEIS.iloc[ZEIS.sindex.query(poligono)])

    E = E.drop(columns=['tx_situ_lote', 'dt_atualizacao'], errors='ignore').reset_index(drop=True)
    E['ano_min'] = E.ano_min.fillna(0).astype(int)
    E['ano_max'] = E.ano_max.fillna(0).astype(int)
    pasta_out = CACHE / 'processado'
    pasta_out.mkdir(parents=True, exist_ok=True)
    E.to_parquet(pasta_out / f'{cd}_{s}_edificacoes.parquet')
    for nome_t, df in [('tombados', Tp), ('quadras', Q), ('favelas', FV), ('loteamentos', LT)]:
        df[dentro(df.geometry)].to_parquet(pasta_out / f'{cd}_{s}_{nome_t}.parquet') if len(df) else None

    com_ano = E.ano_min > 0
    sem_ano = ~com_ano
    pct = lambda a, b: round(100 * a / b, 1) if b else None
    return {
        'cd_distrito': cd, 'distrito': nome,
        'edificacoes': len(E),
        'area_distrito_km2': round(poligono.area / 1e6, 2),
        'ano_medio': round(float(E.ano_min[com_ano].mean()), 1) if com_ano.any() else None,
        'ano_mediano': float(E.ano_min[com_ano].median()) if com_ano.any() else None,
        'pct_sem_ano': pct(sem_ano.sum(), len(E)),
        # área construída declarada no IPTU, uma vez por lote ou condomínio
        'area_construida_m2': int(Ld[Ld.n.notna()].drop_duplicates('ckey')['area'].sum()),
        'area_terrenos_m2': int(Ld.geometry.area.sum()),
        'area_projecao_m2': int(E.geometry.area.sum()),
        'edificacoes_levantamento': n_levantamento,
        'estimadas_pelo_lote': int(E.est.sum()),
        'pct_com_lote': pct(E.com_lote.sum(), len(E)),
        'pct_com_ano': pct(com_ano.sum(), len(E)),
        'ano_1970': int((E.ano_min == 1970).sum()),
        'ano_1969': int((E.ano_min == 1969).sum()),
        'ano_1971': int((E.ano_min == 1971).sum()),
        'lotes': len(Ld),
        'pct_lotes_com_iptu': pct(Ld.n.notna().sum(), len(Ld)),
        'pct_lotes_ativos_com_iptu': pct((Ld.n.notna() & (Ld.tx_situ_lote.fillna('').str.upper() != 'CANCELADO')).sum(),
                                         (Ld.tx_situ_lote.fillna('').str.upper() != 'CANCELADO').sum()),
        'lotes_cancelados': int(situ.get('CANCELADO', 0)),
        'edif_em_mais_de_um_lote': n_multi,
        'favelas': int(dentro(FV.geometry).sum()) if len(FV) else 0,
        'loteamentos_irregulares': int(dentro(LT.geometry).sum()) if len(LT) else 0,
        'edif_em_favela': int(E.em_favela.sum()),
        'pct_sem_ano_em_favela': pct((sem_ano & E.em_favela).sum(), E.em_favela.sum()),
        'edif_em_loteamento': int(E.em_loteamento.sum()),
        'pct_sem_ano_em_loteamento': pct((sem_ano & E.em_loteamento).sum(), E.em_loteamento.sum()),
        'pct_sem_ano_fora_de_ambos': pct((sem_ano & ~E.em_favela & ~E.em_loteamento).sum(), (~E.em_favela & ~E.em_loteamento).sum()),
        'edif_em_zeis1': int(E.em_zeis1.sum()),
        'pct_sem_ano_em_zeis1': pct((sem_ano & E.em_zeis1).sum(), E.em_zeis1.sum()),
        'edif_sem_lote': int((~E.com_lote.astype(bool)).sum()),
        # sem lote fiscal e dentro de favela, loteamento irregular ou ZEIS-1
        'edif_sem_lote_em_favela_lot_zeis1': int((~E.com_lote.astype(bool) & (E.em_favela | E.em_loteamento | E.em_zeis1)).sum()),
        'bens_tombados': int(dentro(Tp.geometry).sum()) if len(Tp) else 0,
        'edif_tombadas': int((E.tomb >= 0).sum()),
        'minutos_download': round(t_wfs / 60, 1),
        'minutos_total': round((time.time() - t0) / 60, 1),
    }


# ---------------------------------------------------------------- principal

def renova(fontes):
    """Tira do cache as fontes que mudaram, para que sejam baixadas de novo."""
    import shutil
    if 'todas' in fontes:
        fontes = ['iptu', *CAMADAS, *CAMADAS_CIDADE]
    desconhecidas = [f for f in fontes if f != 'iptu' and f not in CAMADAS and f not in CAMADAS_CIDADE]
    if desconhecidas:
        sys.exit(f'fonte desconhecida em --renova: {desconhecidas}')
    for f in fontes:
        log(f'0. renova: {f}')
        if f == 'iptu':
            shutil.rmtree(CACHE / 'iptu', ignore_errors=True)
            continue
        for arq in [*(CACHE / 'wfs').glob(f'*/{f}.json.gz'), *(CACHE / 'wfs').glob(f'*/{f}_partes')]:
            shutil.rmtree(arq) if arq.is_dir() else arq.unlink()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--distritos', nargs='+', help='nomes dos distritos (com ou sem acento)')
    g.add_argument('--todos', action='store_true', help='os 96 distritos')
    ap.add_argument('--relatorio', default=str(SAIDA / 'relatorio_qualidade.csv'))
    ap.add_argument('--renova', nargs='*', default=[], metavar='FONTE',
                    help="apaga do cache e baixa de novo: 'iptu', nomes de camadas WFS ou 'todas' (ver verifica_fontes.py)")
    a = ap.parse_args()
    renova(a.renova)

    D = gpd.read_file(FONTES / 'geosampa_distritos_96.geojson').to_crs(CRS)
    D['chave'] = D.nm_distrito_municipal.map(chave)
    if a.todos:
        sel = D
    else:
        pedidos = [chave(n) for n in a.distritos]
        faltam = [n for n in pedidos if n not in set(D.chave)]
        if faltam:
            sys.exit(f'distrito não encontrado: {faltam}')
        sel = D[D.chave.isin(pedidos)].set_index('chave').loc[pedidos].reset_index()

    man = etapa_fontes()
    I = etapa_iptu(man)
    ZEIS = baixa_cidade('perimetro_zona_lei_18081_24', man)
    linhas = []
    for r in sel.itertuples():
        cd = str(r.cd_distrito_municipal).zfill(2)
        linhas.append(processa_distrito(cd, r.nm_distrito_municipal, r.geometry, I, man, ZEIS))
        grava_json(CACHE / 'fontes.json', man)
        l = linhas[-1]
        log(f"   {l['distrito']}: {l['edificacoes']:,} edificações · {l['pct_com_lote']}% com lote · "
            f"{l['pct_com_ano']}% com ano · {l['ano_1970']:,} com ano 1970".replace(',', '.'))

    rel = pd.DataFrame(linhas)
    Path(a.relatorio).parent.mkdir(parents=True, exist_ok=True)
    rel.to_csv(a.relatorio, index=False, encoding='utf-8')
    man['ultima_execucao'] = {'em': agora(), 'distritos': list(rel.distrito)}
    grava_json(CACHE / 'fontes.json', man)
    log(f'5. relatório: {a.relatorio}')


if __name__ == '__main__':
    main()
