from __future__ import annotations
import json,os
from datetime import UTC,datetime
import requests
URL="https://servicodados.ibge.gov.br/api/v1/localidades/estados/PR/municipios"
r=requests.get(URL,timeout=60,headers={"User-Agent":"SIT-mvp-demo-2026/1.0"})
print(json.dumps({"executado_em":datetime.now(UTC).isoformat(),"metodo":"GET","status":r.status_code,"url_final":r.url,"redirects":[{"status":x.status_code,"url":x.url} for x in r.history],"content_type":r.headers.get("content-type"),"bytes":len(r.content),"proxy_presente":any(os.environ.get(x) for x in ("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY"))},ensure_ascii=False,indent=2))
