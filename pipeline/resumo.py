"""Resumo do relatório de qualidade e linha de base para os controles da Etapa 6.

Uso: python pipeline/resumo.py
Lê saida/relatorio_qualidade.csv e grava saida/resumo_qualidade.md e saida/linha_de_base.json.
"""
import json, sys
from pathlib import Path
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
AQUI = Path(__file__).resolve().parent
SAIDA = AQUI / 'saida'
CENTRO = ['SE', 'REPUBLICA', 'BELA VISTA', 'CONSOLACAO', 'SANTA CECILIA', 'BOM RETIRO', 'BRAS', 'PARI', 'LIBERDADE', 'CAMBUCI']


def fmt(n, casas=0):
    return f'{n:,.{casas}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def main():
    r = pd.read_csv(SAIDA / 'relatorio_qualidade.csv', dtype={'cd_distrito': str})
    man = json.load(open(AQUI / 'cache' / 'fontes.json', encoding='utf-8'))
    pop = pd.read_csv(AQUI / 'fontes' / 'populacao_distritos_censo2022.csv')
    import unicodedata
    chave = lambda s: unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode().upper().strip()
    r['chave'] = r.distrito.map(chave)
    r = r.merge(pop[['distrito_chave', 'populacao_2022']], left_on='chave', right_on='distrito_chave', how='left')

    E = r.edificacoes.sum()
    com_lote = (r.edificacoes * r.pct_com_lote / 100).sum()
    com_ano = (r.edificacoes * r.pct_com_ano / 100).sum()
    lotes = r.lotes.sum()
    lotes_iptu = (r.lotes * r.pct_lotes_com_iptu / 100).sum()
    a69, a70, a71 = r.ano_1969.sum(), r.ano_1970.sum(), r.ano_1971.sum()
    cidade = {
        'distritos': int(len(r)), 'edificacoes': int(E), 'edificacoes_levantamento': int(r.edificacoes_levantamento.sum()),
        'estimadas_pelo_lote': int(r.estimadas_pelo_lote.sum()),
        'pct_com_lote': round(100 * com_lote / E, 1), 'pct_com_ano': round(100 * com_ano / E, 1),
        'lotes': int(lotes), 'pct_lotes_com_iptu': round(100 * lotes_iptu / lotes, 1),
        'ano_1969': int(a69), 'ano_1970': int(a70), 'ano_1971': int(a71),
        'razao_1970_vizinhos': round(a70 / ((a69 + a71) / 2), 1) if a69 + a71 else None,
        'edif_em_favela': int(r.edif_em_favela.sum()), 'edif_em_loteamento': int(r.edif_em_loteamento.sum()),
        'edif_tombadas': int(r.edif_tombadas.sum()),
    }
    c = r[r.chave.isin(CENTRO)]
    centro = {'edificacoes': int(c.edificacoes.sum()), 'pct_com_ano': round((c.edificacoes * c.pct_com_ano).sum() / c.edificacoes.sum(), 1),
              'ano_1970': int(c.ano_1970.sum())} if len(c) == 10 else None

    base = {
        'gerado_em': man.get('ultima_execucao', {}).get('em'),
        'fontes': {'iptu_modificado_no_servidor': man['iptu']['servidor']['modificado_no_servidor'], 'iptu_sha256': man['iptu'].get('sha256')},
        'cidade': cidade,
        'por_distrito': {row.cd_distrito: {'distrito': row.distrito, 'edificacoes': int(row.edificacoes),
                                           'pct_lotes_com_iptu': row.pct_lotes_com_iptu, 'pct_com_ano': row.pct_com_ano}
                         for row in r.itertuples()},
        'controles_etapa_6': {'pct_lotes_com_iptu_minimo': 90, 'variacao_max_edificacoes_pct': 5},
    }
    with open(SAIDA / 'linha_de_base.json', 'w', encoding='utf-8') as f:
        json.dump(base, f, ensure_ascii=False, indent=1)

    abaixo90 = r[r.pct_lotes_com_iptu < 90]
    t = r.sort_values('pct_com_ano')
    L = []
    L.append('# Relatório de qualidade: 96 distritos\n')
    L.append(f"Gerado em {base['gerado_em']} por `pipeline/camadas.py`. Todos os números vêm de `relatorio_qualidade.csv`.\n")
    L.append('## Cidade\n')
    L.append(f"- Edificações: **{fmt(E)}** (levantamento: {fmt(cidade['edificacoes_levantamento'])}; {fmt(cidade['estimadas_pelo_lote'])} com volume estimado pelo lote)")
    L.append(f"- Dentro de um lote fiscal: **{fmt(cidade['pct_com_lote'], 1)}%**")
    L.append(f"- Com ano de construção no IPTU: **{fmt(cidade['pct_com_ano'], 1)}%**")
    L.append(f"- Lotes ligados ao IPTU: **{fmt(cidade['pct_lotes_com_iptu'], 1)}%** de {fmt(lotes)} lotes")
    L.append(f"- Ano 1970: {fmt(a70)} edificações, contra {fmt(a69)} em 1969 e {fmt(a71)} em 1971 ({fmt(cidade['razao_1970_vizinhos'], 1)} vezes a média dos vizinhos)")
    L.append(f"- Em favelas mapeadas: {fmt(cidade['edif_em_favela'])}; em loteamentos irregulares mapeados: {fmt(cidade['edif_em_loteamento'])}")
    if centro:
        L.append(f"- Conferência: os 10 distritos do centro somam {fmt(centro['edificacoes'])} edificações (o `data.json` atual tem 68.684)")
    L.append('\n## Distritos com menor % de edificações com ano\n')
    L.append('| Distrito | Edificações | % com lote | % com ano | Lotes com IPTU |')
    L.append('|---|---:|---:|---:|---:|')
    for row in t.head(10).itertuples():
        L.append(f'| {row.distrito} | {fmt(row.edificacoes)} | {fmt(row.pct_com_lote, 1)}% | {fmt(row.pct_com_ano, 1)}% | {fmt(row.pct_lotes_com_iptu, 1)}% |')
    L.append('\n## Distritos com maior % de edificações com ano\n')
    L.append('| Distrito | Edificações | % com lote | % com ano | Lotes com IPTU |')
    L.append('|---|---:|---:|---:|---:|')
    for row in t.tail(5).iloc[::-1].itertuples():
        L.append(f'| {row.distrito} | {fmt(row.edificacoes)} | {fmt(row.pct_com_lote, 1)}% | {fmt(row.pct_com_ano, 1)}% | {fmt(row.pct_lotes_com_iptu, 1)}% |')
    L.append('\n## Linha de base para a Etapa 6\n')
    L.append(f"- Controle 1 (lotes ligados ao IPTU ≥ 90%): {len(abaixo90)} distrito(s) já estão abaixo hoje" +
             (': ' + ', '.join(f'{x.distrito} ({fmt(x.pct_lotes_com_iptu, 1)}%)' for x in abaixo90.itertuples()) if len(abaixo90) else ''))
    L.append(f"- Controle 2 (total de edificações não varia mais de 5%): base = {fmt(E)}")
    (SAIDA / 'resumo_qualidade.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
