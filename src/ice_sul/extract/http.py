"""Download HTTP auditável com retries apenas para falhas transitórias."""
from __future__ import annotations
import hashlib,json,time
from datetime import UTC,datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,build_opener,HTTPRedirectHandler
TRANSIENT={429,502,503,504};UA="SIT-mvp-demo-2026/1.0 (+dados-publicos)"
class TracingRedirect(HTTPRedirectHandler):
    def __init__(self):self.history=[]
    def redirect_request(self,req,fp,code,msg,headers,newurl):self.history.append({"status":code,"url":newurl});return super().redirect_request(req,fp,code,msg,headers,newurl)
def download(url:str,destination:Path,*,source:str,indicators:list[str],period:str="",timeout=60,max_attempts=4):
    redirect=TracingRedirect();opener=build_opener(redirect);attempt=0
    while True:
      attempt+=1
      try:
       with opener.open(Request(url,headers={"User-Agent":UA}),timeout=timeout) as response:body=response.read();status=response.status;final=response.url;headers=dict(response.headers)
       break
      except HTTPError as exc:
       if exc.code not in TRANSIENT or attempt>=max_attempts:raise
       retry=exc.headers.get("Retry-After");delay=float(retry) if retry and retry.isdigit() else 2**(attempt-1);time.sleep(min(delay,30))
    if not body:raise ValueError("resposta vazia")
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():raise FileExistsError(f"raw imutável já existe: {destination}")
    destination.write_bytes(body)
    return {"fonte":source,"indicadores":indicators,"url":url,"metodo":"GET","parametros":{},"periodo":period,"data_hora_utc":datetime.now(UTC).isoformat(),"status_http":status,"url_final":final,"redirects":redirect.history,"content_type":headers.get("Content-Type"),"tamanho":len(body),"sha256":hashlib.sha256(body).hexdigest(),"arquivo":str(destination),"validacao":"recebido_nao_vazio"}
