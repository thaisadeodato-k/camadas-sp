"""Tamanho dos blocos de um arquivo PMTiles, por nível de zoom.

Uso:
    python pipeline/mede_blocos.py tiles/edificacoes_longe.pmtiles

Para cada nível: número de blocos, total, mediana, 95% e maior bloco, e o total de uma tela
de computador (15 x 8 blocos, vista de cima) centrada na República e em Pinheiros, que é
quanto o site baixaria ao abrir ali (com a câmera inclinada, um pouco mais).
"""
import math, sys
from collections import defaultdict
from pmtiles.reader import MmapSource, all_tiles

sys.stdout.reconfigure(encoding='utf-8')
LUGARES = {'República': (-46.6430, -23.5440), 'Pinheiros': (-46.6950, -23.5650)}


def bloco(lon, lat, z):
    n = 2 ** z
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return int((lon + 180) / 360 * n), int((1 - y / math.pi) / 2 * n)


def main(arq):
    tam = defaultdict(dict)
    with open(arq, 'rb') as f:
        for (z, x, y), dados in all_tiles(MmapSource(f)):
            tam[z][(x, y)] = len(dados)
    linhas = ['| Zoom | Blocos | Total (MB) | Mediana (KB) | 95% (KB) | Maior (KB) | '
              + ' | '.join(f'Tela em {l} (MB)' for l in LUGARES) + ' |',
              '|' + '---|' * (6 + len(LUGARES))]
    for z in sorted(tam):
        v = sorted(tam[z].values())
        tela = []
        for lon, lat in LUGARES.values():
            cx, cy = bloco(lon, lat, z)
            tela.append(sum(tam[z].get((x, y), 0) for x in range(cx - 7, cx + 8) for y in range(cy - 4, cy + 4)))
        linhas.append(f'| {z} | {len(v):,} | {sum(v) / 1e6:.1f} | {v[len(v) // 2] / 1e3:.0f} | '
                      f'{v[int(len(v) * .95)] / 1e3:.0f} | {v[-1] / 1e3:.0f} | '
                      + ' | '.join(f'{t / 1e6:.1f}' for t in tela) + ' |')
    print('\n'.join(linhas))


if __name__ == '__main__':
    main(sys.argv[1])
