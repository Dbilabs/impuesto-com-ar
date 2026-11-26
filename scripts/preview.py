#!/usr/bin/env python3
"""Arma una vista previa navegable de ./dist con enlaces relativos y APIs simuladas (para mostrar el sitio sin publicarlo).
Uso: python3 scripts/preview.py [carpeta_destino]"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "preview"
SKIP = {"_headers", "_redirects", "robots.txt", "sitemap.xml", "llms.txt", "llms-full.txt", "site.webmanifest"}

MOCK = r"""(function(){
var R=document.documentElement.getAttribute('data-root')||'./';
function rel(u){var m=u.match(/^\/([^?#]*)(\?[^#]*)?(#.*)?$/);if(!m)return u;var p=m[1];if(p===''||p.slice(-1)==='/')p+='index.html';return R+p+(m[2]||'')+(m[3]||'');}
document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a[href^="/"]');if(!a)return;e.preventDefault();location.href=rel(a.getAttribute('href'));},true);
var _set=Object.getOwnPropertyDescriptor(Location.prototype,'href');
window.__go=function(u){location.href=rel(u);};
var of=window.fetch;var periodo=function(){var d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0');};
var res={periodo:periodo(),debito:2310000,credito:1470000,ventas_netas:11000000,compras_netas:7001000,n_emitidos:3,n_recibidos:2,determinado:840000,top_clientes:[],top_proveedores:[{nombre:'Proveedor SRL (ejemplo)',iva:1470000}],calculado:new Date().toISOString()};
window.fetch=function(u,o){u=String(u);if(u.indexOf('/api/')!==0)return of.apply(this,arguments);
var b={};try{b=JSON.parse(o&&o.body||'{}')}catch(e){}
var r={ok:true};
if(u==='/api/iva/conectar'){if(b.clave==='incorrecta')r={ok:false,error:'ARCA rechazó el usuario o la clave fiscal.'};else r={ok:true,token:'demo-token-vista-previa-0000000000000000',consulta:'c1',guardar:!!b.guardar};}
else if(u==='/api/iva/estado'){r={ok:true,cuenta:{cuit:'20123456786',nombre:'Demo',guardar:true},consulta:{id:'c1',periodo:res.periodo,estado:'lista',resultado:res},historial:[res]};}
else if(u==='/api/iva/consultar'||u==='/api/iva/reconectar'){r={ok:true,consulta:'c1'};}
return new Promise(function(ok){setTimeout(function(){ok(new Response(JSON.stringify(r),{status:r.ok?200:400,headers:{'Content-Type':'application/json'}}));},700);});};
var bar=document.createElement('div');bar.textContent='Vista previa de impuestos.com.ar · los formularios y el robot de IVA están simulados (no envían datos)';
bar.style.cssText='position:fixed;bottom:0;left:0;right:0;background:#0F1B2D;color:#fff;font:600 13px system-ui;padding:8px 12px;text-align:center;z-index:99';
document.addEventListener('DOMContentLoaded',function(){document.body.appendChild(bar);document.body.style.paddingBottom='36px';});
})();"""


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(DIST, OUT, ignore=lambda d, names: [n for n in names if n in SKIP or (n.endswith(".txt") and len(n) > 30)])
    (OUT / "assets" / "preview-mock.js").write_text(MOCK, encoding="utf-8")
    for f in OUT.rglob("*.html"):
        depth = len(f.relative_to(OUT).parts) - 1
        root = "../" * depth or "./"

        def fix(m):
            attr, url = m.group(1), m.group(2)
            if url.startswith("//"):
                return m.group(0)
            path, q = re.match(r"([^?#]*)(.*)", url).groups()
            if path in ("", "/"):
                path = "index.html"
            else:
                path = path.lstrip("/")
                if path.endswith("/"):
                    path += "index.html"
            return f'{attr}="{root}{path}{q}"'
        s = f.read_text(encoding="utf-8")
        s = re.sub(r'(href|src)="(/[^"]*)"', fix, s)
        s = s.replace("<html ", f'<html data-root="{root}" ', 1)
        s = s.replace("</head>", f'<script src="{root}assets/preview-mock.js"></script></head>', 1)
        f.write_text(s, encoding="utf-8")
    # redirecciones hechas por JS (location.href = "/...") → relativas
    for js in (OUT / "assets").glob("*.js"):
        t = js.read_text(encoding="utf-8")
        t2 = re.sub(r'location\.href = ("/[^"]*"(?: \+ [^;]+)?);', r"window.__go(\1);", t)
        if t2 != t:
            js.write_text(t2, encoding="utf-8")
    n = sum(1 for _ in OUT.rglob("*") if _.is_file())
    print(f"Vista previa: {OUT} ({n} archivos)")


if __name__ == "__main__":
    main()
