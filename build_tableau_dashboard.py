"""Build a local Tableau workbook from the saved native worksheet structure.

Uses Tableau's installed Superstore only as a reference for dashboard zone XML.
No Superstore data or calculations are included. Native rendering is verified separately.
"""
from copy import deepcopy
import json
from pathlib import Path
import uuid
import xml.etree.ElementTree as E
from urllib.parse import quote
import zipfile

BASE=Path(__file__).resolve().parent
OUT=BASE/'tableau'/'cohort'
USER='http://www.tableausoftware.com/xml/user'
E.register_namespace('user',USER)


def node(parent,tag,text=None,**attrs):
    el=E.SubElement(parent,tag,{k.replace('_','-'):str(v) for k,v in attrs.items()})
    el.text=text
    return el


def main():
    manifest=json.loads((OUT/'manifest.json').read_text())
    source=BASE/'tableau'/'Customer Service Requests - Learning Sample.twb'
    root=E.parse(source).getroot()
    for tag in ['worksheets','windows','thumbnails','dashboards','actions']:
        el=root.find(tag)
        if el is not None: root.remove(el)
    ds=root.find('./datasources/datasource')
    dsname=ds.get('name')
    connection=ds.find('connection')
    connection.find('./named-connections/named-connection').set('caption','NYC 311 cohort')
    physical=connection.find('./named-connections/named-connection/connection')
    physical.set('directory',str(OUT));physical.set('filename','requests.csv')
    ds.set('caption','NYC 311 — validated request cohort')
    extract=ds.find('extract')
    if extract is not None: ds.remove(extract)
    for x in ds.findall('./object-graph/objects/object/properties'):
        if x.get('context')=='extract':
            ds.find('./object-graph/objects/object').remove(x)
    fields=[('request_id','string','Request ID'),('category','string','Category'),
      ('agency','string','Agency'),('status','string','Status'),('borough','string','Borough'),
      ('channel','string','Channel'),('opened_at','string','Opened at — source local'),
      ('closed_at','string','Closed at — source local'),('opened_date','string','Opened date'),
      ('hours_to_close','real','Hours to close'),('duration_quality','string','Duration quality'),
      ('not_closed','integer','Not marked Closed'),('open_age_calendar_days','integer','Open age calendar days'),
      ('request_count','integer','Requests'),('open_age_band','string','Open age band')]
    # Keep the object identifier from Tableau's native template, but replace every field definition.
    object_id=ds.find('./object-graph/objects/object').get('id')
    for rel in ds.findall('.//relation'):
        rel.set('name','requests.csv');rel.set('table','[requests#csv]')
        cols=rel.find('columns')
        if cols is not None:
            cols.clear();cols.attrib.update({'character-set':'UTF-8','header':'yes','locale':'en_GB','separator':','})
            for i,(name,typ,_) in enumerate(fields):node(cols,'column',datatype=typ,name=name,ordinal=i)
    md=connection.find('metadata-records')
    md.clear()
    for i,(name,typ,_) in enumerate(fields):
        rec=node(md,'metadata-record',**{'class':'column'})
        for tag,value in [('remote-name',name),('remote-type','129' if typ=='string' else '5' if typ=='real' else '20'),
              ('local-name','['+name+']'),('parent-name','[requests.csv]'),('remote-alias',name),
              ('ordinal',i),('local-type',typ),('aggregation','Count' if typ=='string' else 'Sum'),
              ('contains-null','true'),('object-id','['+object_id+']')]:node(rec,tag,str(value))
    column_position=list(ds).index(ds.find('column'))
    for col in ds.findall('column'):ds.remove(col)
    definitions={}
    for name,typ,caption in fields:
        role='dimension' if typ=='string' else 'measure'
        col=node(ds,'column',name='['+name+']',datatype=typ,caption=caption,role=role,type='nominal' if role=='dimension' else 'quantitative')
        if typ=='real':col.set('default-format','n0.0')
        ds.remove(col)
        ds.insert(column_position,col)
        column_position+=1
        definitions[name]=col
    # Old exports can still be opened, but the final export must include these columns.
    if 'request_count' not in (OUT/'requests.csv').read_text().splitlines()[0].split(','):
        raise ValueError('Re-export request_count/open_age_band before building the dashboard')
    obj=ds.find('./object-graph/objects/object');obj.set('caption','requests.csv')
    sem=ds.find('semantic-values')
    if sem is not None:ds.remove(sem)

    if not (OUT/'requests.hyper').exists():
        raise ValueError('Run build_hyper_extract.py first; Tableau Public requires an extract')
    extract=node(ds,'extract',count='-1',enabled='true',object_id='',units='records',user_specific='false')
    hc=node(extract,'connection',access_mode='readonly',**{'class':'hyper','dbname':str(OUT/'requests.hyper'),'default-settings':'hyper','schema':'Extract','tablename':'Extract','username':'tableau_internal_user','sslmode':''})
    node(hc,'relation',name='Extract',table='[Extract].[Extract]',type='table')
    hm=deepcopy(md)
    for rec in hm:
        rec.find('parent-name').text='[Extract]'
    hc.append(hm)
    ds.remove(extract)
    ds.insert(list(ds).index(ds.find('layout')) if ds.find('layout') is not None else list(ds).index(ds.find('style')),extract)
    node(node(obj,'properties',context='extract'),'relation',name='Extract',table='[Extract].[Extract]',type='table')

    sheets=node(root,'worksheets')
    windows=E.Element('windows',{'source-height':'30'})
    plots=[
      ('Requests by category','category','request_count','Sum',False),
      ('Average hours to close','category','hours_to_close','Avg',False),
      ('Requests opened by day','opened_date','request_count','Sum',True),
      ('Status at extraction','status','request_count','Sum',False),
      ('Requests by agency','agency','request_count','Sum',False),
      ('Not Closed — calendar-day age','open_age_band','not_closed','Sum',False),
    ]
    for name,dim,measure,agg,vertical in plots:
        ws=node(sheets,'worksheet',name=name)
        title=node(node(node(ws,'layout-options'),'title'),'formatted-text')
        node(title,'run',name,fontsize='12',bold='true',fontcolor='#19364a')
        table=node(ws,'table');view=node(table,'view')
        node(node(view,'datasources'),'datasource',name=dsname,caption=ds.get('caption'))
        dep=node(view,'datasource-dependencies',datasource=dsname)
        for col in definitions.values():dep.append(deepcopy(col))
        dimensions=set([dim,'category','agency','opened_date'])
        for d in dimensions:
            node(dep,'column-instance',column='['+d+']',derivation='None',name=f'[none:{d}:nk]',pivot='key',type='nominal')
        meas=f'[{agg.lower()}:{measure}:qk]'
        node(dep,'column-instance',column='['+measure+']',derivation=agg,name=meas,pivot='key',type='quantitative')
        for group,d in enumerate(['category','agency','opened_date'],1):
            f=node(view,'filter',**{'class':'categorical','column':f'[{dsname}].[none:{d}:nk]','filter-group':str(group)})
            gf=node(f,'groupfilter',function='level-members',level=f'[none:{d}:nk]')
            gf.set('{'+USER+'}ui-enumeration','all');gf.set('{'+USER+'}ui-marker','enumerate')
        if dim=='open_age_band':
            f=node(view,'filter',**{'class':'categorical','column':f'[{dsname}].[none:open_age_band:nk]'})
            gf=node(f,'groupfilter',function='except')
            node(gf,'groupfilter',function='level-members',level='[none:open_age_band:nk]')
            node(gf,'groupfilter',function='member',level='[none:open_age_band:nk]',member='"Not applicable"')
        if not vertical and dim!='open_age_band':
            node(node(view,'shelf-sorts'),'shelf-sort-v2',**{'dimension-to-sort':f'[{dsname}].[none:{dim}:nk]',
              'direction':'DESC','is-on-innermost-dimension':'true','measure-to-sort-by':f'[{dsname}].{meas}','shelf':'rows'})
        node(view,'aggregation',value='true');node(table,'style')
        pane=node(node(table,'panes'),'pane',**{'selection-relaxation-option':'selection-relaxation-allow'})
        node(node(pane,'view'),'breakdown',value='auto');node(pane,'mark',**{'class':'Bar'})
        style=node(node(pane,'style'),'style-rule',element='mark')
        node(style,'format',attr='mark-color',value='#287f8e')
        node(style,'format',attr='mark-labels-show',value='true')
        node(table,'rows',f'[{dsname}].{meas}' if vertical else f'[{dsname}].[none:{dim}:nk]')
        node(table,'cols',f'[{dsname}].[none:{dim}:nk]' if vertical else f'[{dsname}].{meas}')
        node(ws,'simple-id',uuid='{'+str(uuid.uuid4()).upper()+'}')
        win=node(windows,'window',**{'class':'worksheet','name':name,'maximized':'true'})
        cards=node(win,'cards');edge=node(cards,'edge',name='top')
        for t in ['columns','rows','title']:node(node(edge,'strip',size='31'),'card',type=t)
        node(node(win,'viewpoint'),'zoom',type='entire-view' if vertical else 'fit-width')
    dashboard=node(node(root,'dashboards'),'dashboard',name='NYC 311 — Service Request Analytics')
    node(dashboard,'style')
    node(dashboard,'size',minwidth='1380',maxwidth='1380',minheight='1040',maxheight='1040')
    zones=node(dashboard,'zones')
    container=node(zones,'zone',id='0',x='0',y='0',w='100000',h='100000',**{'type-v2':'layout-basic'})
    def textzone(zid,text,x,y,w,h,size,color,bold=False):
        z=node(container,'zone',id=zid,x=x,y=y,w=w,h=h,**{'type-v2':'text'})
        run=node(node(z,'formatted-text'),'run',text,fontsize=size,fontcolor=color)
        if bold:run.set('bold','true')
        return z
    summary=manifest['validation']['summary']
    total,valid,mean,median,notclosed,unknown=summary
    snapshot=manifest['finished_at_utc'][:16].replace('T',' ')+' UTC'
    textzone('1','NYC 311 | Service Request Analytics',1000,600,98000,4200,22,'#19364a',True)
    textzone('2',f'Opened 1–7 Sep 2026 • Status as of {snapshot} • Public city-service data',1000,5000,98000,2600,11,'#506374')
    textzone('3',f'{int(total):,} requests     |     {int(notclosed):,} not marked Closed     |     {float(median):.2f}h median closure     |     {int(valid):,} valid closure durations',1000,7900,98000,3800,15,'#19364a',True)
    textzone('4','Filter category, agency and opened date. Scroll category lists to inspect additional rows. Full-cohort totals above remain the baseline.',1000,11900,98000,2400,10,'#506374')
    for i,(d,caption) in enumerate([('category','Category'),('agency','Agency'),('opened_date','Opened date')]):
        z=node(container,'zone',id=str(10+i),x=str(1000+i*32500),y='14800',w='31000',h='5200',name=plots[0][0],mode='checkdropdown',param=f'[{dsname}].[none:{d}:nk]',**{'type-v2':'filter','custom-title':'true'})
        node(node(z,'formatted-text'),'run',caption,fontsize='10')
    for i,(name,*_) in enumerate(plots):
        col=i%2;row=i//2
        z=node(container,'zone',id=str(20+i),name=name,x=str(1000+col*49500),y=str(21100+row*24500),w='48000',h='23400')
        node(z,'layout-cache',**{'type-h':'fixed','type-w':'fixed'})
        zs=node(z,'zone-style')
        for attr,value in [('border-style','solid'),('border-color','#d9e3e7'),('border-width','1'),('margin','4')]:node(zs,'format',attr=attr,value=value)
    textzone('40','Closure means agency-marked Closed, not customer satisfaction. Hours use source wall-clock dates. Age is calendar days, assuming NYC local time. Unknown or invalid durations are excluded.',1000,95100,98000,3800,9,'#506374')
    node(dashboard,'simple-id',uuid='{'+str(uuid.uuid4()).upper()+'}')
    dashwin=node(windows,'window',**{'class':'dashboard','name':dashboard.get('name'),'maximized':'true'})
    views=node(dashwin,'viewpoints')
    for name,*_ in plots:node(node(views,'viewpoint',name=name),'zoom',type='entire-view' if name=='Requests opened by day' else 'fit-width')
    node(dashwin,'active',id='-1')
    windows.remove(dashwin);windows.insert(0,dashwin)
    root.append(windows)
    E.indent(root)
    path=OUT/'NYC 311 Service Request Analytics.twb'
    E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
    # Package a second workbook with a relative CSV path for portable handoff.
    portable=deepcopy(root)
    for c in portable.findall('.//named-connection/connection'):
        c.set('directory','Data')
    portable.find('./datasources/datasource/extract/connection').set('dbname','Data/requests.hyper')
    with zipfile.ZipFile(OUT/'NYC 311 Service Request Analytics.twbx','w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('NYC 311 Service Request Analytics.twb',E.tostring(portable,encoding='utf-8',xml_declaration=True))
        z.write(OUT/'requests.csv','Data/requests.csv')
        z.write(OUT/'requests.hyper','Data/requests.hyper')
    print('Built six worksheets and a dashboard; native open/render verification remains required.')


if __name__=='__main__':main()
