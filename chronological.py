import sys,json,math
from datetime import timedelta
import main,validate
c=json.load(open(sys.argv[1])); items=c['comparables']; results=[]
for item in items:
 try: day=main.timestamp(item['day_start']); bins=main.observations(item['hourly'],day)
 except (KeyError,ValueError):continue
 if main.launch_kind(item)=='exclude' and 'target-history' in (item.get('unlock') or '').lower(): continue
 if 0 not in bins or bins[0]<1 or any(h not in bins for h in range(1,24)):continue
 past=[i for i in items if main.timestamp(i['day_start']) < day]
 test=dict(c,day_start=item['day_start'],game={'name':item['name']},comparables=past,known=[{'viewers':bins[0]}],history_hourly=[{'from':(day+timedelta(hours=h)).isoformat(),'viewers':v} for h,v in bins.items() if h<=0],history=[])
 if len(main.library(test))<8:continue
 pred=main.forecast(test); base=main.forecast(test,mode='persistence'); vals=[]
 for fac in (1,1.15,1.3,1.5):
  p={'hours':[]}
  for row in pred['hours']:
   q=row['q']; med=math.log(q[2]); v=[min(1e9,max(1,math.exp(med+fac*(math.log(x)-med)))) for x in q];p['hours'].append({'hour':row['hour'],'q':v})
  vals.append(validate.score(p,bins))
 results.append((item['name'],main.launch_kind(item),validate.score(base,bins),vals))
for name,kind,base,vals in results:print(name, kind, f'{base[0]:.5f}', *(f'{v[0]:.5f}' for v in vals))
for label,g in [('all',results),('console',[r for r in results if r[1] in ('rolling','console') and 'pc' not in next(i for i in items if i['name']==r[0])['platforms'].lower()])]:
 print(label,len(g),'base',sum(r[2][0] for r in g)/len(g))
 for j in range(4):print('scale', (1,1.15,1.3,1.5)[j], 'loss',sum(r[3][j][0] for r in g)/len(g),'coverage',sum(r[3][j][1] for r in g)/len(g))
