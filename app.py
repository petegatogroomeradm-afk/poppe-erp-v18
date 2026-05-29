
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, session, flash
from pathlib import Path
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv
import sqlite3, psycopg2, os, base64, re, urllib.parse, hashlib, secrets, json, zipfile

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

BASE_DIR = Path(__file__).resolve().parent
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_PATH = BASE_DIR / "poppe_orcamentos.db"
for d in ["uploads","pdfs","backups","assinaturas"]:
    (BASE_DIR/d).mkdir(exist_ok=True)

LOGO_FILE = BASE_DIR / 'static' / 'logo_poppe.png'
ASSINATURA_FILE = BASE_DIR / 'static' / 'assinatura_poppe.png'

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "poppe-v19-cloud-pro")

def pg(): return DATABASE_URL.startswith("postgres")
def conn(): return psycopg2.connect(DATABASE_URL) if pg() else sqlite3.connect(DB_PATH)
def q(sql): return sql.replace("?", "%s") if pg() else sql
def ex(cur, sql, params=()): return cur.execute(q(sql), params)
def moeda(v):
    try: v=float(v or 0)
    except: v=0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
def to_float(v):
    try: return float(str(v or "0").replace("R$","").replace(".","").replace(",","."))
    except: return 0.0
def hsenha(s):
    salt=secrets.token_hex(12); h=hashlib.sha256((salt+s).encode()).hexdigest(); return f"{salt}:{h}"
def ok_senha(s, hs):
    if hs == s: return True
    try:
        salt,h=hs.split(":",1); return hashlib.sha256((salt+s).encode()).hexdigest()==h
    except: return False

def init_db():
    c=conn(); cur=c.cursor(); idt="SERIAL PRIMARY KEY" if pg() else "INTEGER PRIMARY KEY AUTOINCREMENT"
    tables=[
    f"CREATE TABLE IF NOT EXISTS clientes (id {idt}, nome TEXT NOT NULL, telefone TEXT, endereco TEXT, email TEXT, observacoes TEXT, data_cadastro TEXT)",
    f"CREATE TABLE IF NOT EXISTS orcamentos_mobile (id {idt}, numero TEXT, cliente_id INTEGER, cliente TEXT, telefone TEXT, endereco TEXT, tipo TEXT, descricao TEXT, valor_mao_obra REAL, valor_total REAL, status TEXT, pagamento TEXT, observacoes TEXT, data_criacao TEXT, caminho_pdf TEXT)",
    f"CREATE TABLE IF NOT EXISTS ordens_servico_mobile (id {idt}, numero_os TEXT, orcamento_id INTEGER, cliente TEXT, telefone TEXT, endereco TEXT, descricao TEXT, status TEXT, data_execucao TEXT, valor_total REAL, data_criacao TEXT)",
    f"CREATE TABLE IF NOT EXISTS fotos_mobile (id {idt}, os_id INTEGER, tipo TEXT, caminho TEXT, observacao TEXT, data_cadastro TEXT)",
    f"CREATE TABLE IF NOT EXISTS financeiro_mobile (id {idt}, referencia TEXT, cliente TEXT, valor REAL, status TEXT, vencimento TEXT, data_criacao TEXT)",
    f"CREATE TABLE IF NOT EXISTS usuarios_cloud (id {idt}, usuario TEXT UNIQUE, senha TEXT, nome TEXT, perfil TEXT, ativo INTEGER DEFAULT 1)",
    "CREATE TABLE IF NOT EXISTS configuracoes_cloud (chave TEXT PRIMARY KEY, valor TEXT)",
    f"CREATE TABLE IF NOT EXISTS contratos_cloud (id {idt}, referencia TEXT, cliente TEXT, telefone TEXT, valor REAL, caminho_pdf TEXT, data_criacao TEXT)",
    f"CREATE TABLE IF NOT EXISTS auditoria_cloud (id {idt}, usuario TEXT, acao TEXT, detalhe TEXT, data_hora TEXT)"
    ]
    for t in tables: ex(cur,t)
    ex(cur,"SELECT id FROM usuarios_cloud WHERE usuario=?",("admin",))
    if not cur.fetchone():
        ex(cur,"INSERT INTO usuarios_cloud (usuario, senha, nome, perfil, ativo) VALUES (?, ?, ?, ?, 1)",("admin",hsenha("admin123"),"Administrador","Administrador"))
    defaults={"empresa":"POPPE SERVIÇOS DE ELÉTRICA","responsavel":"Diego Poppe Silva","pix_chave":"31988605372","whatsapp_numero":"31988605372","dominio_sugerido":"erp.poppeservicos.com.br","versao_atual":"19.0.0","url_update":"","whatsapp_api_url":"","whatsapp_api_token":"","mercadopago_token":""}
    for k,v in defaults.items():
        ex(cur,"SELECT chave FROM configuracoes_cloud WHERE chave=?",(k,))
        if not cur.fetchone(): ex(cur,"INSERT INTO configuracoes_cloud (chave, valor) VALUES (?, ?)",(k,v))

    ex(cur, f"CREATE TABLE IF NOT EXISTS servicos_profissionais (id {idt}, codigo TEXT UNIQUE, categoria TEXT, servico TEXT, unidade TEXT, minimo REAL, medio REAL, maximo REAL, tempo TEXT, observacoes TEXT)")
    servicos_padrao = [
        ("0001","Bombeiro hidráulico","Desentupimento simples","serviço",120,200,350,"1h a 2h","Pia/ralo simples."),
        ("0002","Bombeiro hidráulico","Instalação caixa acoplada","un",150,250,400,"1h",""),
        ("0003","Bombeiro hidráulico","Troca sifão / flexível","un",70,100,150,"30min",""),
        ("0004","Bombeiro hidráulico","Troca torneira","un",80,120,180,"1h",""),
        ("0005","CFTV e Segurança","Instalação DVR/NVR básico","serviço",250,450,800,"meio dia",""),
        ("0006","CFTV e Segurança","Instalação câmera IP/Wi-Fi","un",130,180,280,"1h",""),
        ("0007","CFTV e Segurança","Passagem cabo CFTV","metro",8,12,18,"por metro",""),
        ("0008","Cabeamento estruturado","Conectorização RJ45","un",20,30,45,"15min",""),
        ("0009","Cabeamento estruturado","Instalação switch / roteador","un",120,200,350,"1h a 2h",""),
        ("0010","Cabeamento estruturado","Organização rack pequeno","serviço",250,450,700,"meio dia",""),
        ("0011","Cabeamento estruturado","Passagem de cabo de rede","metro",8,12,18,"por metro",""),
        ("0012","Cabeamento estruturado","Ponto de rede CAT5e/CAT6","ponto",120,180,250,"1h a 2h",""),
        ("0013","Criação de sites","Landing page simples","projeto",700,1200,2000,"3 a 7 dias",""),
        ("0014","Criação de sites","Manutenção mensal site","mês",250,500,900,"mensal",""),
        ("0015","Criação de sites","Sistema de agendamento simples","projeto",1800,3000,5000,"10 a 20 dias",""),
        ("0016","Criação de sites","Site institucional até 5 páginas","projeto",1500,2500,4000,"7 a 15 dias",""),
        ("0017","Elétrica","Arandela, pendente ou spot comum","un",55,70,85,"30 a 60min",""),
        ("0018","Elétrica","Atendimento técnico emergencial final de semana","visita",210,240,270,"visita",""),
        ("0019","Elétrica","Atendimento técnico emergencial semana","visita",150,180,210,"visita",""),
        ("0020","Elétrica","Chuveiro elétrico simples","un",80,90,100,"1h",""),
        ("0021","Elétrica","Chuveiro luxo / eletrônico / pressurizado","un",120,135,150,"1h a 2h",""),
        ("0022","Elétrica","DPS","un",95,110,125,"1h",""),
        ("0023","Elétrica","Entrada monofásica QM para QDC","serviço",160,190,220,"até 20m",""),
        ("0024","Elétrica","IDR / DR","un",110,130,150,"1h",""),
        ("0025","Elétrica","Interruptor duplo / bipolar","un",50,60,70,"40 a 60min",""),
        ("0026","Elétrica","Interruptor e tomada juntos","un",50,60,70,"40 a 60min",""),
        ("0027","Elétrica","Interruptor simples ou pulsador","un",40,50,60,"30 a 60min",""),
        ("0028","Elétrica","Instalação sensor de presença","un",80,120,180,"1h a 2h",""),
        ("0029","Elétrica","Lustre grande / luminária","un",100,135,180,"1h a 2h",""),
        ("0030","Elétrica","Lustre simples / luminária","un",70,90,120,"1h",""),
        ("0031","Elétrica","Passagem cabo flexível 1,5mm/2,5mm","metro",3,5,8,"por metro",""),
        ("0032","Elétrica","Tomada 10A ou 20A","un",70,100,130,"30 a 60min",""),
        ("0033","Elétrica","Quadro de distribuição pequeno","serviço",450,700,1200,"meio dia",""),
        ("0034","Montagem de móveis","Montagem móvel pequeno","un",80,120,180,"1h a 2h",""),
        ("0035","Montagem de móveis","Montagem guarda-roupa","un",180,300,500,"3h a 6h",""),
        ("0036","Sistemas Windows","Sistema desktop simples","projeto",1500,2500,4500,"10 a 20 dias",""),
        ("0037","Sistemas Windows","Manutenção sistema existente","hora",80,120,180,"por hora",""),
    ]
    for s in servicos_padrao:
        ex(cur, "SELECT id FROM servicos_profissionais WHERE codigo=?", (s[0],))
        if not cur.fetchone():
            ex(cur, "INSERT INTO servicos_profissionais (codigo,categoria,servico,unidade,minimo,medio,maximo,tempo,observacoes) VALUES (?,?,?,?,?,?,?,?,?)", s)

    c.commit(); c.close()
init_db()


def garantir_tabelas_v20_2():
    """Cria tabelas novas da V20/V20.2 mesmo quando o banco PostgreSQL já existia antes."""
    c = conn()
    cur = c.cursor()
    idt = "SERIAL PRIMARY KEY" if pg() else "INTEGER PRIMARY KEY AUTOINCREMENT"

    ex(cur, f"""
    CREATE TABLE IF NOT EXISTS agenda_mobile (
        id {idt},
        cliente TEXT,
        telefone TEXT,
        endereco TEXT,
        titulo TEXT,
        descricao TEXT,
        data_agenda TEXT,
        hora TEXT,
        tipo TEXT,
        status TEXT,
        valor REAL,
        os_id INTEGER,
        orcamento_id INTEGER,
        data_criacao TEXT
    )
    """)

    ex(cur, f"""
    CREATE TABLE IF NOT EXISTS recebimentos_mobile (
        id {idt},
        referencia TEXT,
        cliente TEXT,
        descricao TEXT,
        valor REAL,
        vencimento TEXT,
        status TEXT,
        data_pagamento TEXT,
        data_criacao TEXT
    )
    """)

    c.commit()
    c.close()


def cfg(k, default=""):
    c=conn(); cur=c.cursor(); ex(cur,"SELECT valor FROM configuracoes_cloud WHERE chave=?",(k,)); r=cur.fetchone(); c.close(); return r[0] if r else default
def setcfg(k,v):
    c=conn(); cur=c.cursor()
    if pg(): ex(cur,"INSERT INTO configuracoes_cloud (chave,valor) VALUES (?,?) ON CONFLICT (chave) DO UPDATE SET valor=EXCLUDED.valor",(k,v))
    else: ex(cur,"INSERT OR REPLACE INTO configuracoes_cloud (chave,valor) VALUES (?,?)",(k,v))
    c.commit(); c.close()
def audit(a,d=""):
    try:
        c=conn(); cur=c.cursor(); ex(cur,"INSERT INTO auditoria_cloud (usuario,acao,detalhe,data_hora) VALUES (?,?,?,?)",(session.get("usuario","sistema"),a,d,datetime.now().strftime("%d/%m/%Y %H:%M"))); c.commit(); c.close()
    except: pass
def clientes_list():
    c=conn(); cur=c.cursor(); ex(cur,"SELECT id,nome,telefone,endereco,email,observacoes,data_cadastro FROM clientes ORDER BY nome"); r=cur.fetchall(); c.close(); return r
def cliente_get(i):
    if not i: return None
    c=conn(); cur=c.cursor(); ex(cur,"SELECT id,nome,telefone,endereco,email,observacoes,data_cadastro FROM clientes WHERE id=?",(i,)); r=cur.fetchone(); c.close(); return r

PERM={"Administrador":["*"],"Comercial":["dashboard","clientes","orcamentos","contratos","whatsapp","crm","agenda"],"Financeiro":["dashboard","financeiro","admin"],"Técnico":["dashboard","os","fotos","assinatura","agenda"],"Visualização":["dashboard"]}
def allowed(area):
    p=session.get("perfil",""); perms=PERM.get(p,[]); return "*" in perms or area in perms
def login_required(area="dashboard"):
    def dec(fn):
        @wraps(fn)
        def wrap(*a,**kw):
            if "usuario" not in session: return redirect(url_for("login"))
            if not allowed(area): return render_template("erro.html", msg="Sem permissão para esta área.")
            return fn(*a,**kw)
        return wrap
    return dec

@app.before_request
def proteger_login_v19_2():
    endpoint = request.endpoint or ""
    liberadas = {"login", "health", "manifest", "st", "static"}
    if endpoint in liberadas or endpoint.startswith("static"):
        return None
    if "usuario" not in session:
        return redirect(url_for("login"))
    return None

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=request.form.get("usuario","").strip(); s=request.form.get("senha","")
        c=conn(); cur=c.cursor(); ex(cur,"SELECT id,usuario,senha,nome,perfil,ativo FROM usuarios_cloud WHERE usuario=? AND ativo=1",(u,)); r=cur.fetchone(); c.close()
        if r and ok_senha(s,r[2]):
            session.update({"usuario":r[1],"nome":r[3],"perfil":r[4]}); audit("login",u); return redirect(url_for("index"))
        flash("Usuário ou senha inválido.")
    return render_template("login.html")
@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))
@app.route("/health")
def health(): return jsonify(status="ok", database="postgresql" if pg() else "sqlite", version="19.0.0")


@app.route("/")
@login_required("dashboard")
def index():
    c=conn(); cur=c.cursor()
    ex(cur,"SELECT COUNT(*) FROM clientes"); clientes=cur.fetchone()[0]
    ex(cur,"SELECT COUNT(*), COALESCE(SUM(valor_total),0) FROM orcamentos_mobile"); qtd,total=cur.fetchone()
    ex(cur,"SELECT COUNT(*) FROM ordens_servico_mobile"); osq=cur.fetchone()[0]
    ex(cur,"SELECT COALESCE(SUM(valor),0) FROM financeiro_mobile WHERE status='Recebido'"); rec=cur.fetchone()[0]
    ex(cur,"SELECT COALESCE(SUM(valor),0) FROM financeiro_mobile WHERE status!='Recebido'"); pend=cur.fetchone()[0]
    garantir_tabelas_v20_2()
    ex(cur,"SELECT COUNT(*) FROM agenda_mobile WHERE COALESCE(status,'')!='Concluído'")
    agenda_aberta=cur.fetchone()[0]
    ex(cur,"SELECT COALESCE(SUM(valor),0) FROM recebimentos_mobile WHERE COALESCE(status,'')!='Recebido'")
    receber_auto=cur.fetchone()[0]
    c.close()
    return render_template("index.html", clientes=clientes,qtd_orc=qtd,total_orc=total,os_qtd=osq,recebido=rec,pendente=pend,agenda_aberta=agenda_aberta,receber_auto=receber_auto,moeda=moeda)

@app.route("/clientes", methods=["GET","POST"])
@login_required("clientes")
def clientes():
    if request.method=="POST":
        c=conn(); cur=c.cursor(); ex(cur,"INSERT INTO clientes (nome,telefone,endereco,email,observacoes,data_cadastro) VALUES (?,?,?,?,?,?)",(request.form["nome"],request.form.get("telefone",""),request.form.get("endereco",""),request.form.get("email",""),request.form.get("observacoes",""),datetime.now().strftime("%d/%m/%Y %H:%M"))); c.commit(); c.close(); return redirect(url_for("clientes"))
    busca=request.args.get("busca","").strip()
    lista=clientes_list()
    if busca:
        b=busca.lower()
        lista=[c for c in lista if b in (c[1] or "").lower() or b in (c[2] or "").lower() or b in (c[3] or "").lower()]
    return render_template("clientes.html", clientes=lista, busca=busca)


@app.route("/clientes/<int:cid>/editar", methods=["GET","POST"])
@login_required("clientes")
def cliente_editar(cid):
    c=conn(); cur=c.cursor()
    if request.method=="POST":
        ex(cur,"UPDATE clientes SET nome=?, telefone=?, endereco=?, email=?, observacoes=? WHERE id=?",
           (request.form.get("nome",""),request.form.get("telefone",""),request.form.get("endereco",""),request.form.get("email",""),request.form.get("observacoes",""),cid))
        c.commit(); c.close(); audit("cliente_editado", str(cid)); return redirect(url_for("clientes"))
    ex(cur,"SELECT id,nome,telefone,endereco,email,observacoes,data_cadastro FROM clientes WHERE id=?",(cid,))
    cliente=cur.fetchone(); c.close()
    return render_template("cliente_editar.html", cliente=cliente)

@app.route("/clientes/<int:cid>/excluir", methods=["POST"])
@login_required("clientes")
def cliente_excluir(cid):
    c=conn(); cur=c.cursor(); ex(cur,"DELETE FROM clientes WHERE id=?",(cid,)); c.commit(); c.close()
    audit("cliente_excluido", str(cid))
    return redirect(url_for("clientes"))

@app.route("/servicos", methods=["GET","POST"])
@login_required("orcamentos")
def servicos():
    if request.method=="POST":
        dados=(request.form.get("codigo","").strip(),request.form.get("categoria","").strip(),request.form.get("servico","").strip(),
               request.form.get("unidade","un").strip(),to_float(request.form.get("minimo")),to_float(request.form.get("medio")),
               to_float(request.form.get("maximo")),request.form.get("tempo","").strip(),request.form.get("observacoes","").strip())
        c=conn(); cur=c.cursor()
        if pg():
            ex(cur,"INSERT INTO servicos_profissionais (codigo,categoria,servico,unidade,minimo,medio,maximo,tempo,observacoes) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT (codigo) DO UPDATE SET categoria=EXCLUDED.categoria, servico=EXCLUDED.servico, unidade=EXCLUDED.unidade, minimo=EXCLUDED.minimo, medio=EXCLUDED.medio, maximo=EXCLUDED.maximo, tempo=EXCLUDED.tempo, observacoes=EXCLUDED.observacoes",dados)
        else:
            ex(cur,"INSERT OR REPLACE INTO servicos_profissionais (codigo,categoria,servico,unidade,minimo,medio,maximo,tempo,observacoes) VALUES (?,?,?,?,?,?,?,?,?)",dados)
        c.commit(); c.close()
        return redirect(url_for("servicos"))
    busca=request.args.get("busca","").strip()
    categoria=request.args.get("categoria","Todas")
    c=conn(); cur=c.cursor()
    ex(cur,"SELECT DISTINCT categoria FROM servicos_profissionais ORDER BY categoria")
    categorias=[r[0] for r in cur.fetchall()]
    sql="SELECT id,codigo,categoria,servico,unidade,minimo,medio,maximo,tempo,observacoes FROM servicos_profissionais"
    params=[]; filtros=[]
    if busca:
        filtros.append("(LOWER(servico) LIKE ? OR LOWER(categoria) LIKE ? OR codigo LIKE ?)")
        params += [f"%{busca.lower()}%", f"%{busca.lower()}%", f"%{busca}%"]
    if categoria and categoria!="Todas":
        filtros.append("categoria=?"); params.append(categoria)
    if filtros: sql += " WHERE " + " AND ".join(filtros)
    sql += " ORDER BY categoria, codigo"
    ex(cur, sql, tuple(params))
    rows=cur.fetchall(); c.close()
    return render_template("servicos.html", servicos=rows, categorias=categorias, busca=busca, categoria=categoria, moeda=moeda)

@app.route("/servicos/<int:sid>/excluir", methods=["POST"])
@login_required("orcamentos")
def servico_excluir(sid):
    c=conn(); cur=c.cursor(); ex(cur,"DELETE FROM servicos_profissionais WHERE id=?",(sid,)); c.commit(); c.close()
    return redirect(url_for("servicos"))


@app.route("/orcamentos", methods=["GET","POST"])
@login_required("orcamentos")
def orcamentos():
    if request.method=="POST":
        cid=request.form.get("cliente_id"); cl=cliente_get(cid) if cid else None
        nome=cl[1] if cl else request.form.get("cliente_manual",""); tel=cl[2] if cl else request.form.get("telefone",""); end=cl[3] if cl else request.form.get("endereco","")
        numero=datetime.now().strftime("ORC-%Y%m%d-%H%M%S"); valor=to_float(request.form.get("valor_total")); venc=request.form.get("vencimento","")
        c=conn(); cur=c.cursor()
        ex(cur,"INSERT INTO orcamentos_mobile (numero,cliente_id,cliente,telefone,endereco,tipo,descricao,valor_mao_obra,valor_total,status,pagamento,observacoes,data_criacao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(numero,cid,nome,tel,end,request.form.get("tipo","Somente mão de obra"),request.form.get("descricao",""),valor,valor,request.form.get("status","Orçamento enviado"),request.form.get("pagamento","50% no início e 50% na entrega"),request.form.get("observacoes",""),datetime.now().strftime("%d/%m/%Y %H:%M")))
        ex(cur,"SELECT id FROM orcamentos_mobile WHERE numero=? ORDER BY id DESC LIMIT 1",(numero,)); oid=cur.fetchone()[0]
        ex(cur,"INSERT INTO financeiro_mobile (referencia,cliente,valor,status,vencimento,data_criacao) VALUES (?,?,?,?,?,?)",(numero,nome,valor,"Pendente",venc,datetime.now().strftime("%d/%m/%Y %H:%M")))
        garantir_tabelas_v20_2()
        entrada = round(valor * 0.5, 2)
        saldo = round(valor - entrada, 2)
        ex(cur,"INSERT INTO recebimentos_mobile (referencia,cliente,descricao,valor,vencimento,status,data_pagamento,data_criacao) VALUES (?,?,?,?,?,?,?,?)",(numero,nome,"Entrada 50%",entrada,"Na aprovação","Pendente","",datetime.now().strftime("%d/%m/%Y %H:%M")))
        ex(cur,"INSERT INTO recebimentos_mobile (referencia,cliente,descricao,valor,vencimento,status,data_pagamento,data_criacao) VALUES (?,?,?,?,?,?,?,?)",(numero,nome,"Saldo 50%",saldo,venc or "Na entrega","Pendente","",datetime.now().strftime("%d/%m/%Y %H:%M")))
        c.commit(); c.close(); return redirect(url_for("orcamento_detalhe",oid=oid))
    c=conn(); cur=c.cursor(); ex(cur,"SELECT id,numero,cliente,tipo,valor_total,status,data_criacao FROM orcamentos_mobile ORDER BY id DESC"); orcs=cur.fetchall(); c.close()
    prefill={"descricao": request.args.get("descricao",""), "valor": request.args.get("valor","")}
    return render_template("orcamentos.html", clientes=clientes_list(), orcamentos=orcs, moeda=moeda, prefill=prefill)

@app.route("/orcamentos/<int:oid>")
@login_required("orcamentos")
def orcamento_detalhe(oid):
    c=conn(); cur=c.cursor(); ex(cur,"SELECT * FROM orcamentos_mobile WHERE id=?",(oid,)); o=cur.fetchone(); c.close(); return render_template("orcamento_detalhe.html",orc=o,moeda=moeda)

def pdf_orc(oid, contrato=False):
    c=conn(); cur=c.cursor(); ex(cur,"SELECT * FROM orcamentos_mobile WHERE id=?",(oid,)); o=cur.fetchone(); c.close()
    if not o: return None
    ref=("CTR" if contrato else o[1]) + "_" + re.sub(r"[^a-zA-Z0-9_-]+","_",o[3] or "cliente") + ".pdf"
    path=BASE_DIR/"pdfs"/ref; styles=getSampleStyleSheet()
    doc=SimpleDocTemplate(str(path), pagesize=A4, rightMargin=15*mm,leftMargin=15*mm,topMargin=12*mm,bottomMargin=12*mm); story=[]
    if LOGO_FILE.exists():
        try:
            story.append(Image(str(LOGO_FILE), width=55*mm, height=28*mm))
            story.append(Spacer(1, 5))
        except Exception:
            pass
    story.append(Paragraph("<b>CONTRATO DE PRESTAÇÃO DE SERVIÇOS</b>" if contrato else "<b>ORÇAMENTO PROFISSIONAL</b>", styles["Title"]))
    story.append(Paragraph(f"<b>{cfg('empresa')}</b><br/>{cfg('responsavel')}", styles["Normal"])); story.append(Spacer(1,8))
    story.append(Paragraph(f"<b>Cliente:</b> {o[3]}<br/><b>Telefone:</b> {o[4]}<br/><b>Endereço:</b> {o[5]}<br/><b>Referência:</b> {o[1]}", styles["Normal"])); story.append(Spacer(1,8))
    story.append(Paragraph("<b>Serviços</b>", styles["Heading2"])); story.append(Paragraph((o[7] or "").replace("\n","<br/>"), styles["Normal"])); story.append(Spacer(1,8))
    story.append(Paragraph(("Este contrato formaliza a execução dos serviços descritos, com garantia de 90 dias sobre mão de obra." if contrato else ("Este orçamento contempla somente mão de obra." if o[6]=="Somente mão de obra" else "Este orçamento contempla mão de obra + materiais por conta da POPPE.")), styles["Normal"]))
    table=Table([["Total",moeda(o[9])],["Pagamento",o[11]],["PIX",cfg("pix_chave")]], colWidths=[45*mm,130*mm])
    table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.25,colors.grey),("BACKGROUND",(0,0),(0,-1),colors.HexColor("#EAF6FF"))])); story.append(Spacer(1,8)); story.append(table)
    if contrato:
        story.append(Spacer(1,35))
        story.append(Paragraph("________________________________________<br/>Cliente", styles["Normal"]))
        story.append(Spacer(1,20))
        if ASSINATURA_FILE.exists():
            try:
                story.append(Image(str(ASSINATURA_FILE), width=55*mm, height=20*mm))
            except Exception:
                pass
        story.append(Paragraph(f"________________________________________<br/>{cfg('empresa')}", styles["Normal"]))
    doc.build(story); return path

@app.route("/orcamentos/<int:oid>/pdf")
@login_required("orcamentos")
def gerar_pdf(oid):
    p=pdf_orc(oid,False); return send_file(p, as_attachment=True) if p else ("Não encontrado",404)
@app.route("/orcamentos/<int:oid>/contrato")
@login_required("contratos")
def contrato(oid):
    p=pdf_orc(oid,True); return send_file(p, as_attachment=True) if p else ("Não encontrado",404)
@app.route("/orcamentos/<int:oid>/whatsapp")
@login_required("whatsapp")
def zap(oid):
    c=conn(); cur=c.cursor(); ex(cur,"SELECT * FROM orcamentos_mobile WHERE id=?",(oid,)); o=cur.fetchone(); c.close()
    tel=re.sub(r"\D+","",o[4] or ""); msg=f"Olá, {o[3]}! Segue orçamento {o[1]}. Valor: {moeda(o[9])}. PIX: {cfg('pix_chave')}. Serviços: {o[7]}"
    return redirect(f"https://wa.me/55{tel}?text={urllib.parse.quote(msg)}")
@app.route("/pix/<int:oid>")
@login_required("orcamentos")
def pix(oid):
    c=conn(); cur=c.cursor(); ex(cur,"SELECT numero,cliente,valor_total FROM orcamentos_mobile WHERE id=?",(oid,)); o=cur.fetchone(); c.close()
    payload=f"PIX: {cfg('pix_chave')} | Cliente: {o[1]} | Valor: {moeda(o[2])} | Ref: {o[0]}"
    return render_template("pix.html", payload=payload, pix=cfg("pix_chave"), valor=moeda(o[2]))

@app.route("/orcamentos/servico/<int:sid>")
@login_required("orcamentos")
def orcamento_com_servico(sid):
    c=conn(); cur=c.cursor()
    ex(cur,"SELECT codigo,categoria,servico,unidade,minimo,medio,maximo,tempo,observacoes FROM servicos_profissionais WHERE id=?",(sid,))
    s=cur.fetchone(); c.close()
    if not s:
        return redirect(url_for("servicos"))
    descricao = f"{s[2]}\nCategoria: {s[1]}\nUnidade: {s[3]}\nTempo estimado: {s[7]}"
    valor = s[5] or 0
    return redirect(url_for("orcamentos", descricao=descricao, valor=valor))

@app.route("/os", methods=["GET","POST"])
@login_required("os")
def os_view():
    if request.method=="POST":
        n=datetime.now().strftime("OS-%Y%m%d-%H%M%S"); c=conn(); cur=c.cursor()
        ex(cur,"INSERT INTO ordens_servico_mobile (numero_os,orcamento_id,cliente,telefone,endereco,descricao,status,data_execucao,valor_total,data_criacao) VALUES (?,?,?,?,?,?,?,?,?,?)",(n,None,request.form.get("cliente",""),request.form.get("telefone",""),request.form.get("endereco",""),request.form.get("descricao",""),request.form.get("status","Aberta"),request.form.get("data_execucao",""),to_float(request.form.get("valor_total")),datetime.now().strftime("%d/%m/%Y %H:%M"))); c.commit(); c.close(); return redirect(url_for("os_view"))
    c=conn(); cur=c.cursor(); ex(cur,"SELECT id,numero_os,cliente,status,data_execucao,valor_total,data_criacao FROM ordens_servico_mobile ORDER BY id DESC"); rows=cur.fetchall(); c.close()
    return render_template("os.html", ordens=rows, moeda=moeda)


@app.route("/orcamentos/<int:oid>/gerar-os")
@login_required("os")
def gerar_os_orcamento(oid):
    c=conn(); cur=c.cursor()
    ex(cur,"SELECT id,numero,cliente,telefone,endereco,descricao,status,valor_total FROM orcamentos_mobile WHERE id=?",(oid,))
    o=cur.fetchone()
    if not o:
        c.close(); return redirect(url_for("orcamentos"))
    numero_os=datetime.now().strftime("OS-%Y%m%d-%H%M%S")
    ex(cur,"INSERT INTO ordens_servico_mobile (numero_os,orcamento_id,cliente,telefone,endereco,descricao,status,data_execucao,valor_total,data_criacao) VALUES (?,?,?,?,?,?,?,?,?,?)",(numero_os,oid,o[2],o[3],o[4],o[5],"Aberta","",o[7],datetime.now().strftime("%d/%m/%Y %H:%M")))
    ex(cur,"UPDATE orcamentos_mobile SET status=? WHERE id=?",("Aprovado",oid))
    c.commit(); c.close()
    return redirect(url_for("os_view"))

@app.route("/agenda", methods=["GET","POST"])
@login_required("agenda")
def agenda():
    garantir_tabelas_v20_2()
    if request.method=="POST":
        c=conn(); cur=c.cursor()
        ex(cur,"INSERT INTO agenda_mobile (cliente,telefone,endereco,titulo,descricao,data_agenda,hora,tipo,status,valor,os_id,orcamento_id,data_criacao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (request.form.get("cliente",""),request.form.get("telefone",""),request.form.get("endereco",""),request.form.get("titulo","Visita técnica"),request.form.get("descricao",""),request.form.get("data_agenda",""),request.form.get("hora",""),request.form.get("tipo","Visita técnica"),request.form.get("status","Agendado"),to_float(request.form.get("valor")),None,None,datetime.now().strftime("%d/%m/%Y %H:%M")))
        c.commit(); c.close(); return redirect(url_for("agenda"))
    busca=request.args.get("busca","")
    c=conn(); cur=c.cursor()
    sql="SELECT id,cliente,telefone,endereco,titulo,descricao,data_agenda,hora,tipo,status,valor,data_criacao FROM agenda_mobile"
    params=[]
    if busca:
        sql += " WHERE LOWER(cliente) LIKE ? OR LOWER(titulo) LIKE ? OR data_agenda LIKE ?"
        params=[f"%{busca.lower()}%",f"%{busca.lower()}%",f"%{busca}%"]
    sql += " ORDER BY data_agenda, hora"
    ex(cur,sql,tuple(params)); rows=cur.fetchall(); c.close()
    return render_template("agenda.html", agenda=rows, busca=busca, moeda=moeda)

@app.route("/financeiro/receber/<int:rid>", methods=["POST"])
@login_required("financeiro")
def marcar_recebido(rid):
    c=conn(); cur=c.cursor()
    ex(cur,"UPDATE recebimentos_mobile SET status='Recebido', data_pagamento=? WHERE id=?",(datetime.now().strftime("%d/%m/%Y %H:%M"),rid))
    c.commit(); c.close()
    return redirect(url_for("financeiro"))

@app.route("/financeiro/excluir/<int:rid>", methods=["POST"])
@login_required("financeiro")
def excluir_recebimento(rid):
    c=conn(); cur=c.cursor(); ex(cur,"DELETE FROM recebimentos_mobile WHERE id=?",(rid,)); c.commit(); c.close()
    return redirect(url_for("financeiro"))


@app.route("/fotos", methods=["GET","POST"])
@login_required("fotos")
def fotos():
    if request.method=="POST":
        arq=request.files.get("foto"); caminho=""
        if arq:
            caminho=BASE_DIR/"uploads"/(datetime.now().strftime("%Y%m%d_%H%M%S_")+arq.filename); arq.save(caminho)
        c=conn(); cur=c.cursor(); ex(cur,"INSERT INTO fotos_mobile (os_id,tipo,caminho,observacao,data_cadastro) VALUES (?,?,?,?,?)",(request.form.get("os_id") or None,request.form.get("tipo","Antes"),str(caminho),request.form.get("observacao",""),datetime.now().strftime("%d/%m/%Y %H:%M"))); c.commit(); c.close(); return redirect(url_for("fotos"))
    c=conn(); cur=c.cursor(); ex(cur,"SELECT id,os_id,tipo,caminho,observacao,data_cadastro FROM fotos_mobile ORDER BY id DESC"); fs=cur.fetchall(); ex(cur,"SELECT id,numero_os,cliente FROM ordens_servico_mobile ORDER BY id DESC"); oss=cur.fetchall(); c.close()
    return render_template("fotos.html", fotos=fs, ordens=oss)

@app.route("/assinatura")
@login_required("assinatura")
def assinatura(): return render_template("assinatura.html")
@app.route("/assinatura/salvar", methods=["POST"])
@login_required("assinatura")
def salvar_ass():
    data=request.json.get("imagem",""); nome=request.json.get("nome","assinatura")
    if "," in data: data=data.split(",",1)[1]
    p=BASE_DIR/"assinaturas"/(re.sub(r"[^a-zA-Z0-9_-]+","_",nome)+"_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".png"); p.write_bytes(base64.b64decode(data)); return jsonify(ok=True,arquivo=str(p))


@app.route("/financeiro")
@login_required("financeiro")
def financeiro():
    garantir_tabelas_v20_2()
    c=conn(); cur=c.cursor()
    ex(cur,"SELECT id,referencia,cliente,valor,status,vencimento,data_criacao FROM financeiro_mobile ORDER BY id DESC")
    itens=cur.fetchall()
    try:
        ex(cur,"SELECT id,referencia,cliente,descricao,valor,vencimento,status,data_pagamento,data_criacao FROM recebimentos_mobile ORDER BY id DESC")
        recebimentos=cur.fetchall()
    except Exception:
        recebimentos=[]
    ex(cur,"SELECT COALESCE(SUM(valor),0) FROM financeiro_mobile WHERE status='Recebido'")
    rec=cur.fetchone()[0]
    ex(cur,"SELECT COALESCE(SUM(valor),0) FROM financeiro_mobile WHERE status!='Recebido'")
    pend=cur.fetchone()[0]
    try:
        ex(cur,"SELECT COALESCE(SUM(valor),0) FROM recebimentos_mobile WHERE status='Recebido'")
        rec_auto=cur.fetchone()[0]
        ex(cur,"SELECT COALESCE(SUM(valor),0) FROM recebimentos_mobile WHERE status!='Recebido'")
        pend_auto=cur.fetchone()[0]
    except Exception:
        rec_auto=0; pend_auto=0
    c.close()
    return render_template("financeiro.html", itens=itens, recebimentos=recebimentos, recebido=rec, pendente=pend, rec_auto=rec_auto, pend_auto=pend_auto, moeda=moeda)

@app.route("/crm")
@login_required("crm")
def crm():
    c=conn(); cur=c.cursor(); ex(cur,"SELECT id,numero,cliente,valor_total,status,data_criacao FROM orcamentos_mobile ORDER BY id DESC"); rows=cur.fetchall(); c.close()
    etapas=["Orçamento enviado","Aguardando aprovação","Aprovado","Em execução","Finalizado","Recusado"]; dados={e:[] for e in etapas}
    for r in rows: dados[r[4] if r[4] in dados else etapas[0]].append(r)
    return render_template("crm.html", etapas=etapas, dados=dados, moeda=moeda)

@app.route("/admin", methods=["GET","POST"])
@login_required("admin")
def admin():
    if request.method=="POST":
        if request.form.get("acao")=="usuario":
            u=request.form.get("usuario",""); s=request.form.get("senha",""); n=request.form.get("nome",""); p=request.form.get("perfil","Visualização")
            if u and s:
                c=conn(); cur=c.cursor()
                if pg(): ex(cur,"INSERT INTO usuarios_cloud (usuario,senha,nome,perfil,ativo) VALUES (?,?,?,?,1) ON CONFLICT (usuario) DO UPDATE SET senha=EXCLUDED.senha,nome=EXCLUDED.nome,perfil=EXCLUDED.perfil,ativo=1",(u,hsenha(s),n,p))
                else: ex(cur,"INSERT OR REPLACE INTO usuarios_cloud (usuario,senha,nome,perfil,ativo) VALUES (?,?,?,?,1)",(u,hsenha(s),n,p))
                c.commit(); c.close()
        else:
            for k in ["empresa","responsavel","pix_chave","whatsapp_numero","dominio_sugerido","url_update","whatsapp_api_url","whatsapp_api_token","mercadopago_token"]: setcfg(k,request.form.get(k,""))
        return redirect(url_for("admin"))
    c=conn(); cur=c.cursor(); ex(cur,"SELECT id,usuario,nome,perfil,ativo FROM usuarios_cloud ORDER BY id"); users=cur.fetchall(); ex(cur,"SELECT id,usuario,acao,detalhe,data_hora FROM auditoria_cloud ORDER BY id DESC LIMIT 80"); aud=cur.fetchall(); c.close()
    keys=["empresa","responsavel","pix_chave","whatsapp_numero","dominio_sugerido","url_update","whatsapp_api_url","whatsapp_api_token","mercadopago_token"]
    return render_template("admin.html", usuarios=users, auditoria=aud, cfg={k:cfg(k) for k in keys})

@app.route("/admin/upload-identidade", methods=["POST"])
@login_required("admin")
def upload_identidade():
    logo = request.files.get("logo")
    assinatura = request.files.get("assinatura")
    if logo and logo.filename:
        logo.save(LOGO_FILE)
    if assinatura and assinatura.filename:
        assinatura.save(ASSINATURA_FILE)
    return redirect(url_for("admin"))


@app.route("/admin/usuarios/<int:uid>/editar", methods=["GET","POST"])
@login_required("admin")
def usuario_editar(uid):
    c=conn(); cur=c.cursor()
    if request.method=="POST":
        usuario=request.form.get("usuario","").strip()
        nome=request.form.get("nome","").strip()
        perfil=request.form.get("perfil","Visualização")
        ativo=1 if request.form.get("ativo")=="1" else 0
        nova_senha=request.form.get("senha","").strip()
        if nova_senha:
            ex(cur,"UPDATE usuarios_cloud SET usuario=?, nome=?, perfil=?, ativo=?, senha=? WHERE id=?",
               (usuario,nome,perfil,ativo,hsenha(nova_senha),uid))
        else:
            ex(cur,"UPDATE usuarios_cloud SET usuario=?, nome=?, perfil=?, ativo=? WHERE id=?",
               (usuario,nome,perfil,ativo,uid))
        c.commit(); c.close()
        audit("usuario_editado", usuario)
        return redirect(url_for("admin"))
    ex(cur,"SELECT id,usuario,nome,perfil,ativo FROM usuarios_cloud WHERE id=?",(uid,))
    usuario=cur.fetchone(); c.close()
    return render_template("usuario_editar.html", usuario=usuario)

@app.route("/admin/usuarios/<int:uid>/excluir", methods=["POST"])
@login_required("admin")
def usuario_excluir(uid):
    c=conn(); cur=c.cursor()
    ex(cur,"SELECT usuario FROM usuarios_cloud WHERE id=?",(uid,))
    row=cur.fetchone()
    if row and row[0] != "admin":
        ex(cur,"DELETE FROM usuarios_cloud WHERE id=?",(uid,))
        audit("usuario_excluido", row[0])
    c.commit(); c.close()
    return redirect(url_for("admin"))

@app.route("/admin/usuarios/<int:uid>/status", methods=["POST"])
@login_required("admin")
def usuario_status(uid):
    c=conn(); cur=c.cursor()
    ex(cur,"SELECT usuario, ativo FROM usuarios_cloud WHERE id=?",(uid,))
    row=cur.fetchone()
    if row and row[0] != "admin":
        novo=0 if row[1] else 1
        ex(cur,"UPDATE usuarios_cloud SET ativo=? WHERE id=?",(novo,uid))
        audit("usuario_status", f"{row[0]}={novo}")
    c.commit(); c.close()
    return redirect(url_for("admin"))



@app.route("/admin/corrigir-banco")
@login_required("admin")
def corrigir_banco():
    garantir_tabelas_v20_2()
    return render_template("erro.html", msg="Banco corrigido com sucesso. Tabelas agenda_mobile e recebimentos_mobile verificadas/criadas.")


@app.route("/backup")
@login_required("admin")
def backup():
    p=BASE_DIR/"backups"/("backup_poppe_v19_"+datetime.now().strftime("%Y%m%d_%H%M%S")+".zip")
    with zipfile.ZipFile(p,"w",zipfile.ZIP_DEFLATED) as z:
        if DB_PATH.exists(): z.write(DB_PATH,"poppe_orcamentos.db")
        for folder in ["uploads","pdfs","assinaturas"]:
            d=BASE_DIR/folder
            for f in d.rglob("*"):
                if f.is_file(): z.write(f, f"{folder}/{f.relative_to(d)}")
        z.writestr("backup_info.json", json.dumps({"versao":"19.0.0","data":datetime.now().isoformat()},ensure_ascii=False))
    return send_file(p, as_attachment=True)
@app.route("/cloud")
@login_required("admin")
def cloud(): return render_template("cloud.html", database="PostgreSQL/Supabase" if pg() else "SQLite local", dominio=cfg("dominio_sugerido"))
@app.route("/update")
@login_required("admin")
def update(): return render_template("update.html", versao=cfg("versao_atual"), url_update=cfg("url_update"))
@app.route("/manifest.json")
def manifest(): return send_file(BASE_DIR/"static"/"manifest.json")
@app.route("/static/<path:path>")
def st(path): return send_file(BASE_DIR/"static"/path)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","8080")), debug=True)
