"""Confere, sem baixar os dados, se alguma fonte mudou desde a última atualização do site.

Uso:
    python pipeline/verifica_fontes.py --anterior fontes_verificadas.json --saida pipeline/saida/fontes_verificadas.json

Para cada fonte guarda uma "assinatura" barata de obter:
  - IPTU: nome, tamanho e data do arquivo na pasta de downloads do GeoSampa
  - camadas WFS: datas do registro no catálogo de metadados e número de feições no serviço
Compara com a assinatura anterior (guardada na release "dados") e diz quais fontes mudaram.
Sem mudança, mas com mais de --dias-max dias desde o último download completo, pede tudo de novo
(o catálogo nem sempre registra correções pequenas).

Escreve em $GITHUB_OUTPUT: mudou (true/false), renovar (fontes a baixar de novo) e novo_iptu
(ano de um IPTU mais novo que o usado pelo pipeline, que pede revisão manual), e grava um resumo
em pipeline/saida/mudancas.md.
"""
import argparse, os, re, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from camadas import (CAMADAS, CAMADAS_CIDADE, GEOSAMPA, IPTU_ANO, IPTU_LAYER, SAIDA, WFS,
                     agora, datas_metadados, grava_json, le_json, log, pede)


def iptu_servidor():
    """Arquivos IPTU_AAAA.zip na pasta de downloads: os anos disponíveis e o do ano usado pelo pipeline."""
    r = pede('GET', GEOSAMPA + 'Download/Nas/TreeGeneric', params={'layerId': IPTU_LAYER, 'path': 'XLS_CSV', 'depth': 1, 'includeFiles': 'true'})
    arqs = {}
    for f in r.json()['node']['children']:
        m = re.fullmatch(r'IPTU_(\d{4})\.zip', f['name'])
        if m:
            arqs[int(m.group(1))] = {'arquivo': f['name'], 'tamanho': f['size'], 'modificado_no_servidor': f['modified']}
    return sorted(arqs), arqs.get(IPTU_ANO)


def feicoes(camada, filtro=None):
    """Número de feições da camada no WFS (cidade inteira), sem baixar as feições."""
    p = {'service': 'WFS', 'version': '2.0.0', 'request': 'GetFeature', 'typeNames': 'geoportal:' + camada, 'resultType': 'hits'}
    if filtro:
        p['cql_filter'] = filtro
    try:
        m = re.search(r'numberMatched="(\d+)"', pede('GET', WFS, params=p, tentativas=3, timeout=300).text)
        return int(m.group(1)) if m else None
    except Exception as e:
        log(f'   {camada}: contagem falhou ({str(e)[:150]})')
        return None


def meta(uuid):
    m = datas_metadados(uuid)
    if 'erro' in m:
        log(f'   metadados {uuid}: {m["erro"]}')
        return {}
    d = m.get('datas', {})
    return {'registro': m.get('data_do_registro'), 'revisao': (d.get('revision') or [None])[-1],
            'publicacao': (d.get('publication') or [None])[-1]}


def assinatura():
    log('verificando IPTU')
    anos, iptu = iptu_servidor()
    camadas = {}
    for c, (_, uuid, _, _) in CAMADAS.items():
        log(f'verificando {c}')
        camadas[c] = {**meta(uuid), 'feicoes': feicoes(c)}
    for c, (_, uuid, _, filtro) in CAMADAS_CIDADE.items():
        log(f'verificando {c}')
        camadas[c] = {**meta(uuid), 'feicoes': feicoes(c, filtro)}
    return {'verificado_em': agora(), 'iptu_ano_usado': IPTU_ANO, 'iptu': iptu, 'iptu_ano_mais_recente': max(anos, default=None), 'camadas': camadas}


def compara(ant, nova):
    """Lista de (fonte, motivo). Um valor que não pôde ser lido agora ou antes não conta como mudança."""
    mud = []
    if nova['iptu'] is None:
        raise RuntimeError(f'IPTU_{IPTU_ANO}.zip sumiu da pasta de downloads do GeoSampa')
    a = ant.get('iptu') or {}
    dif = [k for k in ('tamanho', 'modificado_no_servidor') if a.get(k) != nova['iptu'][k]]
    if dif:
        mud.append(('iptu', '; '.join(f'{k}: {a.get(k)} → {nova["iptu"][k]}' for k in dif)))
    for c, v in nova['camadas'].items():
        a = ant.get('camadas', {}).get(c)
        if a is None:
            mud.append((c, 'fonte nova no pipeline'))
            continue
        dif = [k for k in ('registro', 'revisao', 'publicacao', 'feicoes') if v.get(k) is not None and a.get(k) is not None and v[k] != a[k]]
        if dif:
            mud.append((c, '; '.join(f'{k}: {a[k]} → {v[k]}' for k in dif)))
    return mud


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--anterior', help='assinatura da última atualização (pode não existir)')
    ap.add_argument('--saida', default=str(SAIDA / 'fontes_verificadas.json'))
    ap.add_argument('--dias-max', type=int, default=180)
    ap.add_argument('--renovado-em', help='na primeira verificação, data do último download completo (ISO)')
    a = ap.parse_args()

    ant = le_json(Path(a.anterior)) if a.anterior else None
    nova = assinatura()
    if ant is None:
        mud, nota = [], 'Primeira verificação: a assinatura de agora fica como referência para as próximas.'
        nova['ultima_renovacao'] = a.renovado_em or nova['verificado_em']
    else:
        mud, nota = compara(ant, nova), ''
        nova['ultima_renovacao'] = ant.get('ultima_renovacao') or ant['verificado_em']
        dias = (datetime.fromisoformat(nova['verificado_em']) - datetime.fromisoformat(nova['ultima_renovacao'])).days
        if not mud and dias >= a.dias_max:
            mud = [('todas', f'{dias} dias desde o último download completo')]
    # se a atualização der certo, esta assinatura passa a valer com a data de hoje
    if mud:
        nova['ultima_renovacao'] = nova['verificado_em']
    novo_iptu = nova['iptu_ano_mais_recente'] or IPTU_ANO
    novo_iptu = novo_iptu if novo_iptu > IPTU_ANO else ''
    grava_json(Path(a.saida), nova)

    renovar = 'todas' if any(f == 'todas' for f, _ in mud) else ' '.join(f for f, _ in mud)
    L = [f'## Verificação das fontes ({nova["verificado_em"][:10]})', '']
    L += [f'- **{f}**: {m}' for f, m in mud] or ['Nenhuma fonte mudou desde a última atualização.']
    if nota:
        L += ['', nota]
    if novo_iptu:
        L += ['', f'O GeoSampa já publica o IPTU {novo_iptu}; o pipeline usa o {IPTU_ANO}. A troca de ano pede revisão manual.']
    texto = '\n'.join(L) + '\n'
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / 'mudancas.md').write_text(texto, encoding='utf-8')
    print(texto)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as f:
            f.write(f'mudou={"true" if mud else "false"}\nrenovar={renovar}\nnovo_iptu={novo_iptu}\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write(texto)


if __name__ == '__main__':
    main()
