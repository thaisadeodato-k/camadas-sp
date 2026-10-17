import gzip, json, pandas as pd, geopandas as gpd, numpy as np
from shapely.geometry import Polygon, MultiPolygon, shape
from shapely.ops import unary_union
g=json.load(gzip.open('sp_geometria.json.gz'))
def geom(c):
    if not c: return None
    ps=[Polygon(p[0], p[1:]) for p in c if len(p[0])>=4]
    if not ps: return None
    return ps[0] if len(ps)==1 else MultiPolygon(ps)
crs='EPSG:31983'
L=gpd.GeoDataFrame([dict(setor=a[0],quadra=a[1],lote=a[2],cond=a[3],tipo=a[4],uso_l=a[5],area_l=a[6],sit=a[7]) for a,_ in g['lote']], geometry=[geom(c) for _,c in g['lote']], crs=crs)
E=gpd.GeoDataFrame({'h':[a[0] for a,_ in g['edif']]}, geometry=[geom(c) for _,c in g['edif']], crs=crs)
D=gpd.GeoDataFrame({'nome':[a for a,_ in g['dist']]}, geometry=[geom(c) for _,c in g['dist']], crs=crs)
T=gpd.GeoDataFrame(pd.DataFrame([a for a,_ in g['tomb']]), geometry=[geom(c) for _,c in g['tomb']], crs=crs)
Q=gpd.GeoDataFrame(geometry=[geom(c) for _,c in g['quadra']], crs=crs)
A=gpd.GeoDataFrame(geometry=[geom(c) for _,c in g['agua']], crs=crs)
for n,df in [('L',L),('E',E),('D',D),('T',T),('Q',Q),('A',A)]:
    df=df[df.geometry.notna()]; df.to_parquet(f'{n}.parquet')
    print(n,len(df))
