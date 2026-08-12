from __future__ import annotations
import math, statistics


def ranks(values):
    ordered=sorted(values,key=lambda x:(-x[1],x[0])); return {mid:i+1 for i,(mid,_) in enumerate(ordered)}

def compare_rankings(baseline, alternative):
    common=sorted(set(baseline)&set(alternative)); a=[baseline[x] for x in common]; b=[alternative[x] for x in common]
    if len(common)<2: rho=None
    else:
        ma,mb=statistics.fmean(a),statistics.fmean(b); num=sum((x-ma)*(y-mb) for x,y in zip(a,b)); den=math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b)); rho=num/den if den else None
    changes={x:abs(baseline[x]-alternative[x]) for x in common}
    def changed(n): return sorted(set(x for x in common if baseline[x]<=n)^set(x for x in common if alternative[x]<=n))
    return {"spearman":rho,"mudanca_mediana":statistics.median(changes.values()) if changes else None,
      "maior_mudanca":max(changes.values(),default=None),"alteracoes_top20":changed(20),"alteracoes_top50":changed(50),
      "mais_sensiveis":sorted(changes.items(),key=lambda x:(-x[1],x[0]))[:20]}
