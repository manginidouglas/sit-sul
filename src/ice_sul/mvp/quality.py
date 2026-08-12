from __future__ import annotations
import statistics
from collections import Counter, defaultdict
from .scoring import percentile


def indicator_quality(indicator, ids, raw, treated, flags, metadata, municipalities):
    valid = [x for x in raw if x is not None]
    flag_counts = Counter(metadata.get((mid, indicator), {}).get("flag_qualidade", "ausente") for mid in ids)
    def dist(field):
        out = defaultdict(lambda: {"total": 0, "validos": 0})
        for mid, value in zip(ids, raw):
            group = str(municipalities[mid].get(field, "nao_informado"))
            out[group]["total"] += 1; out[group]["validos"] += value is not None
        return dict(out)
    quantiles = {f"p{int(p*100)}": percentile(valid, p) if valid else None for p in (.01,.05,.25,.5,.75,.95,.99)}
    indexed = [(mid, x) for mid, x in zip(ids, raw) if x is not None]
    return {"indicador_id": indicator, "status": "indisponivel" if not valid else "disponivel",
      "cobertura": len(valid)/len(ids), "zeros": sum(x == 0 for x in valid), "ausentes": len(ids)-len(valid),
      "nao_aplicaveis": flag_counts["nao_aplicavel"], "media": statistics.fmean(valid) if valid else None,
      "mediana": statistics.median(valid) if valid else None, "desvio_padrao": statistics.pstdev(valid) if valid else None,
      **quantiles, "min_bruto": min(valid) if valid else None, "max_bruto": max(valid) if valid else None,
      "min_tratado": min((x for x in treated if x is not None), default=None), "max_tratado": max((x for x in treated if x is not None), default=None),
      "winsorizados": sum(flags), "distribuicao_uf": dist("uf_sigla"), "distribuicao_porte": dist("grupo_porte"),
      "top": sorted(indexed,key=lambda x:(-x[1],x[0]))[:10], "bottom": sorted(indexed,key=lambda x:(x[1],x[0]))[:10],
      "flags": dict(flag_counts)}
