import pandas as pd, geopandas as gpd, numpy as np, json, re
from shapely.geometry import Polygon, MultiPolygon
L=gpd.read_parquet('L2.parquet'); E=gpd.read_parquet('E2.parquet'); D=gpd.read_parquet('D.parquet')
T=gpd.read_parquet('T.parquet'); Q=gpd.read_parquet('Q.parquet')
U=D.union_all()
# replace outdated footprints on new lots
E['src']='edif'
newl=L[(L.ano_min>=2008)&(L.pav>=4)]
hmax=E.groupby('ckey').h.max()
repl=[]
for _,r in newl.iterrows():
    hm=hmax.get(r.ckey,0)
    if r.pav*3>1.6*max(hm,1):
        repl.append(r)
print('replace lots',len(repl))
rk=set(r.ckey for r in repl)
E=E[~E.ckey.isin(rk)]
add=gpd.GeoDataFrame([dict(h=r.pav*3.0,ckey=r.ckey,ano_min=r.ano_min,ano_max=r.ano_max,pav=r.pav,area=r.area,n=r.n,endereco=r.endereco,uso=r.uso,padrao=r.padrao,bairro=r.bairro,src='lote') for r in repl],geometry=[r.geometry.buffer(-1.5) for r in repl],crs=E.crs)
E=pd.concat([E,add],ignore_index=True)
E=E[~E.geometry.is_empty]
# height fallback
E['h']=E.h.where(E.h>1, E.pav.fillna(1)*3)
E['h']=E.h.clip(2.5,180)
# tombados
Tp=T[T.st.str.upper().str.contains('TOMB',na=False)].copy()
Tp['tid']=range(len(Tp))
pt=gpd.GeoDataFrame({'i':E.index},geometry=E.representative_point(),crs=E.crs)
jt=gpd.sjoin(pt,Tp[['tid','geometry']],how='left',predicate='within').drop_duplicates('i').set_index('i')
E['tomb']=jt.tid.reindex(E.index).fillna(-1).astype(int)
print('tomb buildings',(E.tomb>=0).sum())
# to local meters (true north) around origin
from pyproj import Transformer
tr=Transformer.from_crs('EPSG:31983','EPSG:4326',always_xy=True)
c=U.centroid; lon0,lat0=tr.transform(c.x,c.y)
R=6378137.0; kx=np.cos(np.radians(lat0))*np.pi/180*R; ky=np.pi/180*R
def loc(xs,ys):
    lo,la=tr.transform(xs,ys); return (np.array(lo)-lon0)*kx,(np.array(la)-lat0)*ky
S=5  # units per meter (0.2m)
def enc_poly(g,tol=0.25):
    g=g.simplify(tol)
    polys=[g] if g.geom_type=='Polygon' else list(getattr(g,'geoms',[]))
    out=[]
    for p in polys:
        if p.is_empty or p.area<4: continue
        rings=[p.exterior]+list(p.interiors)[:4]
        rr=[]
        for ring in rings:
            xs,ys=ring.xy; xs=np.array(xs)[:-1]; ys=np.array(ys)[:-1]
            x,y=loc(xs,ys); xi=np.round(x*S).astype(int); yi=np.round(y*S).astype(int)
            f=[]; px=py=0
            for a,b in zip(xi,yi): f+= [int(a-px),int(b-py)]; px,py=a,b
            rr.append(f)
        out.append(rr)
    return out
E=E.reset_index(drop=True)
uso_cats=sorted(E.uso.fillna('—').unique().tolist(), key=lambda s:-(E.uso==s).sum())
pad_cats=sorted(E.padrao.fillna('—').unique().tolist())
tombs=[[str(r.n or ''),str(r.e or ''),int(max(r.am or 0,0)),int(max(r.ae or 0,0)),int(max(r.au or 0,0)),str(r.u or ''),str(r.lk or '')] for r in Tp.itertuples()]
B=[]
for r in E.itertuples():
    pg=enc_poly(r.geometry)
    if not pg: continue
    B.append([pg, round(float(r.h),1), int(r.ano_min) if r.ano_min==r.ano_min else 0, int(r.ano_max) if r.ano_max==r.ano_max else 0,
              int(r.pav) if r.pav==r.pav else 0, (r.endereco if isinstance(r.endereco,str) else '').strip().replace('  ',' '),
              uso_cats.index(r.uso if isinstance(r.uso,str) else '—'), pad_cats.index(r.padrao if isinstance(r.padrao,str) else '—'),
              (r.bairro if isinstance(r.bairro,str) else ''), int(r.n) if r.n==r.n else 0, int(r.tomb), 1 if r.src=='lote' else 0])
Qc=Q[Q.representative_point().within(U.buffer(300))]
quad=[enc_poly(g,0.8) for g in Qc.geometry]; quad=[q for q in quad if q]
dist=[[n, enc_poly(g,2)] for n,g in zip(D.nome,D.geometry)]
dl=[]
for n,g in zip(D.nome,D.geometry):
    p=g.representative_point(); x,y=loc([p.x],[p.y]); dl.append([n,round(float(x[0])),round(float(y[0]))])
data=dict(origin=[lon0,lat0],scale=S,b=B,uso=uso_cats,padrao=pad_cats,tomb=tombs,quad=quad,dist=dist,distLabels=dl)
s=json.dumps(data,separators=(',',':'),ensure_ascii=False)
open('data.json','w').write(s)
print('buildings',len(B),'size MB',len(s)/1e6, 'origin',lon0,lat0)
yrs=pd.Series([b[2] for b in B]); print(yrs[yrs>0].describe())
print(uso_cats[:12])
E.drop(columns='geometry').to_csv('E_attrs.csv',index=False)
