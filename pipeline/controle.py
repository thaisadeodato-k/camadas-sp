"""Controles de qualidade antes de publicar dados novos no site.

Uso:
    python pipeline/controle.py --anterior linha_de_base_anterior.json

Compara saida/linha_de_base.json (acabada de gerar por resumo.py) com a da última publicação:
  1. lotes ligados ao IPTU: pelo menos 90% em cada distrito e na cidade
  2. total de edificações: não varia mais de 5% em relação à publicação anterior
  3. os 96 distritos estão presentes
Os limites vêm de 'controles_etapa_6' na linha de base. Grava o resultado em saida/controle.md
e termina com erro se algum controle falhar (o workflow então não publica e abre uma issue).
Com --changelog, se tudo passar, registra a atualização no topo do CHANGELOG.md.
"""
import argparse, json, sys
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
SAIDA = Path(__file__).resolve().parent / 'saida'


def fmt(n, casas=0):
    return f'{n:,.{casas}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--anterior', help='linha_de_base.json da última publicação (pode não existir)')
    ap.add_argument('--changelog', help='CHANGELOG.md onde registrar a atualização')
    ap.add_argument('--motivo', default='', help='por que os dados foram gerados de novo')
    a = ap.parse_args()

    atual = json.load(open(SAIDA / 'linha_de_base.json', encoding='utf-8'))
    ant = None
    if a.anterior and Path(a.anterior).exists():
        ant = json.load(open(a.anterior, encoding='utf-8'))
    lim = atual['controles_etapa_6']
    minimo, var_max = lim['pct_lotes_com_iptu_minimo'], lim['variacao_max_edificacoes_pct']
    c = atual['cidade']
    falhas, L = [], []

    abaixo = [d for d in atual['por_distrito'].values() if d['pct_lotes_com_iptu'] < minimo]
    if c['pct_lotes_com_iptu'] < minimo:
        falhas.append(f'Na cidade, só {fmt(c["pct_lotes_com_iptu"], 1)}% dos lotes se ligaram ao IPTU (mínimo {minimo}%).')
    for d in abaixo:
        falhas.append(f'{d["distrito"]}: só {fmt(d["pct_lotes_com_iptu"], 1)}% dos lotes se ligaram ao IPTU (mínimo {minimo}%).')
    L.append(f'- Lotes ligados ao IPTU: {fmt(c["pct_lotes_com_iptu"], 1)}% na cidade; '
             f'{len(abaixo)} distrito(s) abaixo de {minimo}%.')

    if c['distritos'] != 96:
        falhas.append(f'O resultado tem {c["distritos"]} distritos, não 96.')
    L.append(f'- Distritos: {c["distritos"]}.')

    if ant:
        e0, e1 = ant['cidade']['edificacoes'], c['edificacoes']
        var = 100 * (e1 - e0) / e0
        if abs(var) > var_max:
            falhas.append(f'O total de edificações foi de {fmt(e0)} para {fmt(e1)} ({fmt(var, 1)}%; limite ±{var_max}%).')
        L.append(f'- Edificações: {fmt(e0)} → {fmt(e1)} ({"+" if var >= 0 else ""}{fmt(var, 2)}%).')
        L.append(f'- Com ano no IPTU: {fmt(ant["cidade"]["pct_com_ano"], 1)}% → {fmt(c["pct_com_ano"], 1)}%.')
        # maiores variações por distrito, só como informação
        dv = []
        for cd, d in atual['por_distrito'].items():
            d0 = ant['por_distrito'].get(cd)
            if d0 and d0['edificacoes']:
                dv.append((abs(d['edificacoes'] / d0['edificacoes'] - 1), d['distrito'], d0['edificacoes'], d['edificacoes']))
        dv.sort(reverse=True)
        if dv and dv[0][0] > 0:
            L.append('- Distritos que mais mudaram: ' + '; '.join(f'{n} ({fmt(x0)} → {fmt(x1)})' for v, n, x0, x1 in dv[:3] if v > 0) + '.')
    else:
        L.append(f'- Edificações: {fmt(c["edificacoes"])} (sem publicação anterior para comparar).')

    texto = '## Controles de qualidade\n\n'
    texto += ('Todos os controles passaram.\n\n' if not falhas else
              '**Os dados novos não foram publicados**, porque estes controles falharam:\n\n' + '\n'.join(f'- {f}' for f in falhas) + '\n\n')
    texto += '\n'.join(L) + '\n'
    (SAIDA / 'controle.md').write_text(texto, encoding='utf-8')
    print(texto)
    if a.changelog and not falhas:
        registra(Path(a.changelog), a.motivo, L)
    sys.exit(1 if falhas else 0)


def registra(arq, motivo, linhas):
    """Entrada nova logo abaixo do título do CHANGELOG, com o que mudou nas fontes e os números."""
    mud = SAIDA / 'mudancas.md'
    fontes = [l for l in mud.read_text(encoding='utf-8').splitlines() if l.startswith('- ')] if mud.exists() else []
    e = [f'## {date.today().isoformat()}: dados atualizados', '']
    if motivo:
        e += [motivo, '']
    if fontes:
        e += ['Fontes que mudaram:', '', *fontes, '']
    e += ['Resultado:', '', *linhas, '']
    txt = arq.read_text(encoding='utf-8')
    titulo, _, resto = txt.partition('\n\n')
    arq.write_text(titulo + '\n\n' + '\n'.join(e) + '\n' + resto, encoding='utf-8')


if __name__ == '__main__':
    main()
