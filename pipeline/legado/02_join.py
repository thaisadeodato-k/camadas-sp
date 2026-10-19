import pandas as pd, geopandas as gpd, numpy as np
L=gpd.read_parquet('L.parquet'); E=gpd.read_parquet('E.parquet'); D=gpd.read_parquet('D.parquet')
I=pd.read_csv('sp_iptu_centro.csv.gz',sep=';',dtype=str)
for c in ['ano_min','ano_max','pav','area','n']: I[c]=pd.to_numeric(I[c],errors='coerce')
I['ckey']=np.where(I.key.str[0]=='C', I.key.str[:7]+I.key.str[7:9], I.key)
Ig=I.groupby('ckey').agg(ano_min=('ano_min',lambda s: s[s>0].min() if (s>0).any() else np.nan),ano_max=('ano_max','max'),pav=('pav','max'),area=('area','sum'),n=('n','sum'),endereco=('endereco','first'),uso=('uso',lambda s:s.mode().iat[0]),padrao=('padrao',lambda s:s.mode().iat[0]),bairro=('bairro','first')).reset_index()
L['ckey']=np.where(L.cond!='00','C'+L.setor+L.quadra+L.cond.str[:2],'L'+L.setor+L.quadra+L.lote)
L=L.merge(Ig,on='ckey',how='left')
print('lots',len(L),'matched',L.ano_min.notna().sum(), 'by type', L.groupby(L.cond!='00').ano_min.apply(lambda s:s.notna().mean()).to_dict())
print('unmatched setores', L[L.ano_min.isna()].setor.value_counts().head(10).to_dict())
U=D.union_all() if hasattr(D,'union_all') else D.unary_union
L=L[L.representative_point().within(U)]
print('lots in districts',len(L),'matched',L.ano_min.notna().mean())
E['pt']=E.representative_point()
Ep=gpd.GeoDataFrame(E.drop(columns='geometry'),geometry='pt',crs=E.crs)
Ep=Ep[Ep.within(U)]
j=gpd.sjoin(Ep,L[['ckey','ano_min','ano_max','pav','area','n','endereco','uso','padrao','bairro','tipo','geometry']],how='left',predicate='within')
j=j[~j.index.duplicated()]
print('buildings in districts',len(j),'with year',j.ano_min.notna().mean())
print(pd.cut(j.ano_min,[0,1900,1930,1945,1964,1985,2000,2014,2030]).value_counts().sort_index())
E2=E.loc[j.index].copy(); 
for c in ['ckey','ano_min','ano_max','pav','area','n','endereco','uso','padrao','bairro']: E2[c]=j[c]
E2=E2.drop(columns='pt'); E2.to_parquet('E2.parquet'); L.to_parquet('L2.parquet')
# new lots post-2008 check
new=L[L.ano_min>=2008]
print('lots >=2008', len(new))
