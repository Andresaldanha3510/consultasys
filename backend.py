import sqlite3
import webbrowser
from flask import Flask, jsonify, request, send_from_directory, Response, send_file
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import sys
import json
import csv
import io
import shutil
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

# Configuração de Caminhos
if getattr(sys, 'frozen', False):
    APP_ROOT = os.path.dirname(sys.executable)
else:
    APP_ROOT = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(APP_ROOT, 'uploads')
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'chave-mestra-sistema-clinica-2025'
CORS(app, supports_credentials=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_error'

class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id; self.username = username; self.role = role

class Database:
    def __init__(self, db_name="clinica.db"):
        self.db_path = os.path.join(APP_ROOT, db_name)
        self.init_db()

    def conectar(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self.conectar(); c = conn.cursor()
        
        c.execute("CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, role TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS configuracoes (id INTEGER PRIMARY KEY, nome_clinica TEXT, endereco TEXT, telefone TEXT, cnpj TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS pacientes (id INTEGER PRIMARY KEY, nome TEXT, cpf TEXT, rg TEXT, data_nascimento DATE, sexo TEXT, telefone_principal TEXT, telefone_secundario TEXT, email TEXT, endereco TEXT, convenio_id INTEGER, observacoes_medicas TEXT, medicamentos_em_uso TEXT, responsavel TEXT, foto TEXT, ativo INTEGER DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS profissionais (id INTEGER PRIMARY KEY, nome TEXT, crm TEXT, cpf TEXT, data_nascimento DATE, especialidade_id INTEGER, email TEXT, telefone TEXT, endereco TEXT, dados_bancarios TEXT, cor_agenda TEXT, comissao REAL, bio TEXT, disponibilidade TEXT, ativo INTEGER DEFAULT 1)")
        c.execute("CREATE TABLE IF NOT EXISTS agendamentos (id INTEGER PRIMARY KEY, paciente_id INTEGER, profissional_id INTEGER, data_hora_inicio DATETIME, duracao_minutos INTEGER, data_hora_fim DATETIME, status TEXT, tipo TEXT, motivo_cancelamento TEXT, usuario_cancelou TEXT, observacoes TEXT, sala_id INTEGER, retorno_de_id INTEGER, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS convenios (id INTEGER PRIMARY KEY, nome TEXT, registro_ans TEXT, cnpj TEXT, prazo_pagamento INTEGER, telefone TEXT, email TEXT, site TEXT, tabela_precos TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS prontuarios (id INTEGER PRIMARY KEY, paciente_id INTEGER, profissional_id INTEGER, data_atendimento DATETIME, evolucao_clinica TEXT, diagnostico TEXT, prescricao TEXT, exames_solicitados TEXT, anexos TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS contas_receber (id INTEGER PRIMARY KEY, paciente_id INTEGER, descricao TEXT, valor_total REAL, valor_pago REAL DEFAULT 0, parcelas INTEGER DEFAULT 1, parcela_atual INTEGER DEFAULT 1, status TEXT DEFAULT 'Pendente', data_vencimento DATE, data_pagamento DATE, forma_pagamento TEXT, categoria TEXT, centro_custo TEXT, observacoes TEXT, comprovante TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS contas_pagar (id INTEGER PRIMARY KEY, fornecedor TEXT, descricao TEXT, valor_total REAL, valor_pago REAL DEFAULT 0, parcelas INTEGER DEFAULT 1, parcela_atual INTEGER DEFAULT 1, status TEXT DEFAULT 'Pendente', data_vencimento DATE, data_pagamento DATE, forma_pagamento TEXT, categoria TEXT, centro_custo TEXT, observacoes TEXT, comprovante TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS caixa (id INTEGER PRIMARY KEY, data_hora DATETIME DEFAULT CURRENT_TIMESTAMP, tipo TEXT, valor REAL, descricao TEXT, usuario TEXT, referencia_id INTEGER)")
        for t in ['especialidades', 'salas', 'procedimentos']: 
            c.execute(f"CREATE TABLE IF NOT EXISTS {t} (id INTEGER PRIMARY KEY, nome TEXT)")
        
        admin_pass = generate_password_hash('admin123')
        if not c.execute("SELECT * FROM usuarios WHERE username='admin'").fetchone():
            c.execute("INSERT INTO usuarios (username, password_hash, role) VALUES (?,?,?)", ('admin', admin_pass, 'admin'))
        if not c.execute("SELECT * FROM configuracoes WHERE id=1").fetchone():
            c.execute("INSERT INTO configuracoes (id, nome_clinica, endereco, telefone) VALUES (1, 'Minha Clínica', 'Rua Exemplo, 123', '(11) 9999-9999')")
            
        conn.commit(); conn.close()

db = Database()

@login_manager.user_loader
def load_user(user_id):
    conn = db.conectar(); u = conn.execute("SELECT * FROM usuarios WHERE id=?", (user_id,)).fetchone(); conn.close()
    return User(u['id'], u['username'], u['role']) if u else None

@login_manager.unauthorized_handler
def login_error(): return jsonify({"erro": "Acesso negado"}), 401

@app.route('/')
def index(): return send_from_directory(APP_ROOT, 'sistema.html')

@app.route('/api/login', methods=['POST'])
def login():
    try:
        d = request.json; conn = db.conectar()
        u = conn.execute("SELECT * FROM usuarios WHERE username=?", (d['username'],)).fetchone(); conn.close()
        if u and check_password_hash(u['password_hash'], d['password']):
            login_user(User(u['id'], u['username'], u['role']))
            return jsonify({"msg": "Logado", "user": u['username']})
        return jsonify({"erro": "Dados inválidos"}), 401
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/api/logout', methods=['POST'])
@login_required
def logout(): logout_user(); return jsonify({"msg": "Saiu"})

@app.route('/api/check_auth')
def check_auth():
    if current_user.is_authenticated: return jsonify({"user": current_user.username})
    return jsonify({"erro": "Nao logado"}), 401

# --- CONFIGURAÇÃO DA CLÍNICA ---
@app.route('/api/config', methods=['GET'])
@login_required
def get_config():
    conn = db.conectar(); c = conn.execute("SELECT * FROM configuracoes WHERE id=1").fetchone(); conn.close()
    return jsonify(dict(c) if c else {})

@app.route('/api/config/salvar', methods=['POST'])
@login_required
def save_config():
    d = request.json; conn = db.conectar()
    conn.execute("UPDATE configuracoes SET nome_clinica=?, endereco=?, telefone=? WHERE id=1", (d['nome'], d['end'], d['tel']))
    conn.commit(); conn.close()
    return jsonify({"msg": "Salvo"})

@app.route('/api/mudar_senha', methods=['POST'])
@login_required
def mudar_senha():
    d=request.json; conn=db.conectar()
    u = conn.execute("SELECT password_hash FROM usuarios WHERE id = ?", (current_user.id,)).fetchone()
    if not u or not check_password_hash(u['password_hash'], d['antiga']): conn.close(); return jsonify({"erro": "Senha antiga incorreta"}), 401
    conn.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", (generate_password_hash(d['nova']), current_user.id)); conn.commit(); conn.close()
    return jsonify({"msg": "Sucesso"})

@app.route('/api/backup')
@login_required
def backup():
    bkp = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(db.db_path, os.path.join(APP_ROOT, bkp))
    return send_file(os.path.join(APP_ROOT, bkp), as_attachment=True)

@app.route('/api/dashboard_stats')
@login_required
def dash():
    conn=db.conectar(); c=conn.cursor(); h=datetime.now().strftime("%Y-%m-%d"); m=datetime.now().strftime("%Y-%m")
    s={'hoje':0,'mes':0,'faturamento':0,'pendencias':0,'proximos':[], 'grafico':[]}
    try:
        s['hoje']=c.execute("SELECT COUNT(*) FROM agendamentos WHERE DATE(data_hora_inicio)=? AND status!='Cancelado'",(h,)).fetchone()[0]
        s['mes']=c.execute("SELECT COUNT(*) FROM agendamentos WHERE strftime('%Y-%m',data_hora_inicio)=? AND status!='Cancelado'",(m,)).fetchone()[0]
        s['faturamento']=c.execute("SELECT COALESCE(SUM(valor_pago),0) FROM contas_receber WHERE strftime('%Y-%m',data_pagamento)=?",(m,)).fetchone()[0]
        s['pendencias']=c.execute("SELECT COUNT(*) FROM contas_receber WHERE status='Pendente' AND data_vencimento<?",(h,)).fetchone()[0]
        s['proximos']=[dict(r) for r in c.execute("SELECT a.data_hora_inicio, p.nome as paciente, pr.nome as profissional, s.nome as sala FROM agendamentos a JOIN pacientes p ON a.paciente_id=p.id JOIN profissionais pr ON a.profissional_id=pr.id LEFT JOIN salas s ON a.sala_id=s.id WHERE a.data_hora_inicio >= ? AND a.status NOT IN ('Cancelado','Finalizado') ORDER BY a.data_hora_inicio LIMIT 10", (datetime.now().strftime("%Y-%m-%d 00:00:00"),)).fetchall()]
        s['grafico']=[{'nome': r['nome'] or 'Geral', 'total': r['total']} for r in c.execute("SELECT e.nome, COUNT(a.id) as total FROM agendamentos a JOIN profissionais p ON a.profissional_id = p.id LEFT JOIN especialidades e ON p.especialidade_id = e.id WHERE strftime('%Y-%m', a.data_hora_inicio) = ? AND a.status != 'Cancelado' GROUP BY e.nome ORDER BY total DESC", (m,)).fetchall()]
    except: pass
    conn.close(); return jsonify(s)

@app.route('/api/agenda/calendario', methods=['GET'])
@login_required
def cal_ag():
    conn=db.conectar(); evs=[]; cores={'Agendado':'#F59E0B','Confirmado':'#3B82F6','Realizado':'#10B981','NoShow':'#EF4444','Em Espera':'#8B5CF6','Em Atendimento':'#EC4899'}
    for r in conn.execute("SELECT a.id, a.data_hora_inicio, a.data_hora_fim, a.status, p.nome as paciente FROM agendamentos a JOIN pacientes p ON a.paciente_id=p.id WHERE a.status!='Cancelado'").fetchall():
        evs.append({'id':r['id'],'title':f"{r['paciente']} ({r['status']})",'start':r['data_hora_inicio'],'end':r['data_hora_fim'],'backgroundColor':cores.get(r['status'],'#6B7280'),'borderColor':cores.get(r['status'],'#6B7280')})
    conn.close(); return jsonify(evs)

@app.route('/api/sala_espera')
@login_required
def sala_espera():
    conn=db.conectar()
    hoje = datetime.now().strftime("%Y-%m-%d")
    sql = """
        SELECT a.*, 
               p.nome as paciente_nome, 
               p.telefone_principal as paciente_tel,
               pr.nome as profissional_nome, 
               s.nome as sala_nome 
        FROM agendamentos a 
        JOIN pacientes p ON a.paciente_id=p.id 
        LEFT JOIN profissionais pr ON a.profissional_id=pr.id 
        LEFT JOIN salas s ON a.sala_id=s.id 
        WHERE a.data_hora_inicio BETWEEN ? AND ? 
        ORDER BY a.data_hora_inicio ASC
    """
    r=[dict(x) for x in conn.execute(sql, (f"{hoje} 00:00:00", f"{hoje} 23:59:59")).fetchall()]
    conn.close()
    return jsonify(r)

@app.route('/api/pacientes', methods=['GET'])
@login_required
def list_pac(): f=request.args.get('filtro',''); conn=db.conectar(); r=[dict(x) for x in conn.execute(f"SELECT * FROM pacientes WHERE nome LIKE '%{f}%' OR cpf LIKE '%{f}%' ORDER BY nome").fetchall()]; conn.close(); return jsonify(r)

@app.route('/api/pacientes/salvar', methods=['POST'])
@login_required
def save_pac():
    d=request.json; conn=db.conectar(); end=json.dumps(d.get('endereco',{})); resp=json.dumps(d.get('responsavel',{}))
    v=(d['nome'],d.get('cpf'),d.get('rg'),d.get('nasc'),d.get('sexo'),d.get('tel'),d.get('email'),end,d.get('conv'),d.get('obs'),d.get('meds'),resp)
    if d.get('id'): conn.execute("UPDATE pacientes SET nome=?, cpf=?, rg=?, data_nascimento=?, sexo=?, telefone_principal=?, email=?, endereco=?, convenio_id=?, observacoes_medicas=?, medicamentos_em_uso=?, responsavel=? WHERE id=?", v+(d['id'],))
    else: conn.execute("INSERT INTO pacientes (nome, cpf, rg, data_nascimento, sexo, telefone_principal, email, endereco, convenio_id, observacoes_medicas, medicamentos_em_uso, responsavel) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", v)
    conn.commit(); conn.close(); return jsonify({"msg":"Salvo"})

@app.route('/api/profissionais', methods=['GET'])
@login_required
def list_prof(): conn=db.conectar(); r=[dict(x) for x in conn.execute("SELECT p.*, e.nome as esp_nome FROM profissionais p LEFT JOIN especialidades e ON p.especialidade_id=e.id ORDER BY p.nome").fetchall()]; conn.close(); return jsonify(r)

@app.route('/api/profissionais/salvar', methods=['POST'])
@login_required
def save_prof():
    d=request.json; conn=db.conectar(); disp=json.dumps(d.get('dias',[])); end=json.dumps(d.get('endereco',{})); bank=json.dumps(d.get('banco',{}))
    v=(d['nome'],d.get('crm'),d.get('cpf'),d.get('nasc'),d.get('esp_id'),d.get('email'),d.get('tel'),end,bank,d.get('cor','#10B981'),d.get('comissao',0),d.get('bio'),disp,d.get('ativo',1))
    if d.get('id'): conn.execute("UPDATE profissionais SET nome=?, crm=?, cpf=?, data_nascimento=?, especialidade_id=?, email=?, telefone=?, endereco=?, dados_bancarios=?, cor_agenda=?, comissao=?, bio=?, disponibilidade=?, ativo=? WHERE id=?", v+(d['id'],))
    else: conn.execute("INSERT INTO profissionais (nome, crm, cpf, data_nascimento, especialidade_id, email, telefone, endereco, dados_bancarios, cor_agenda, comissao, bio, disponibilidade, ativo) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", v)
    conn.commit(); conn.close(); return jsonify({"msg":"Salvo"})

@app.route('/api/agenda', methods=['GET'])
@login_required
def list_ag():
    hoje = datetime.now().strftime('%Y-%m-%d')
    dt_ini = request.args.get('inicio', hoje); dt_fim = request.args.get('fim', hoje); prof = request.args.get('prof_id')
    conn = db.conectar()
    q = "SELECT a.*, p.nome as paciente, pr.nome as profissional FROM agendamentos a JOIN pacientes p ON a.paciente_id=p.id JOIN profissionais pr ON a.profissional_id=pr.id WHERE DATE(a.data_hora_inicio) BETWEEN ? AND ?"
    p = [dt_ini, dt_fim]
    if prof: q+=" AND a.profissional_id=?"; p.append(prof)
    r=[dict(x) for x in conn.execute(q+" ORDER BY a.data_hora_inicio", p).fetchall()]; conn.close(); return jsonify(r)

@app.route('/api/agenda/salvar', methods=['POST'])
@login_required
def save_ag():
    d=request.json; conn=db.conectar()
    if not d.get('paciente_id') or not d.get('profissional_id') or not d.get('data') or not d.get('hora'): return jsonify({"erro":"Campos obrigatórios"}), 400
    ini=datetime.strptime(f"{d['data']} {d['hora']}","%Y-%m-%d %H:%M"); fim=ini+timedelta(minutes=int(d.get('duracao',30))); istr,fstr=ini.strftime("%Y-%m-%d %H:%M:%S"),fim.strftime("%Y-%m-%d %H:%M:%S")
    p=[d['profissional_id'],fstr,istr,istr,fstr]; q="SELECT id FROM agendamentos WHERE profissional_id=? AND status!='Cancelado' AND ((data_hora_inicio<? AND data_hora_fim>?) OR (data_hora_inicio>=? AND data_hora_fim<=?))"
    if d.get('id'): q+=" AND id!=?"; p.append(d['id'])
    if conn.execute(q,p).fetchone(): conn.close(); return jsonify({"erro":"Conflito"}),409
    v=(d['paciente_id'],d['profissional_id'],istr,d.get('duracao',30),fstr,d.get('tipo'),d.get('obs'),d.get('sala_id'))
    if d.get('id'): conn.execute("UPDATE agendamentos SET paciente_id=?, profissional_id=?, data_hora_inicio=?, duracao_minutos=?, data_hora_fim=?, tipo=?, observacoes=?, sala_id=? WHERE id=?", v+(d['id'],))
    else: conn.execute("INSERT INTO agendamentos (paciente_id, profissional_id, data_hora_inicio, duracao_minutos, data_hora_fim, tipo, observacoes, sala_id) VALUES (?,?,?,?,?,?,?,?)", v)
    conn.commit(); conn.close(); return jsonify({"msg":"Ok"})

@app.route('/api/agenda/deletar/<int:id>', methods=['DELETE'])
@login_required
def del_ag(id):
    conn=db.conectar(); conn.execute("DELETE FROM agendamentos WHERE id=?",(id,)); conn.commit(); conn.close(); return jsonify({"msg":"Deletado"})

@app.route('/api/agenda/status', methods=['POST'])
@login_required
def st_ag(): conn=db.conectar(); conn.execute("UPDATE agendamentos SET status=? WHERE id=?",(request.json['status'],request.json['id'])); conn.commit(); conn.close(); return jsonify({"msg":"Ok"})

@app.route('/api/agenda/iniciar_atendimento_paciente', methods=['POST'])
@login_required
def ini_atend_pac():
    d=request.json; h=datetime.now().strftime("%Y-%m-%d"); conn=db.conectar()
    ag = conn.execute("SELECT id FROM agendamentos WHERE paciente_id=? AND data_hora_inicio BETWEEN ? AND ? AND status NOT IN ('Cancelado','Finalizado')", (d['id'], f"{h} 00:00:00", f"{h} 23:59:59")).fetchone()
    if ag:
        conn.execute("UPDATE agendamentos SET status='Em Atendimento' WHERE id=?", (ag['id'],))
    else:
        prof_id = d.get('prof_id')
        if not prof_id: 
            p = conn.execute("SELECT id FROM profissionais WHERE ativo=1 LIMIT 1").fetchone()
            prof_id = p['id'] if p else 1 
        now = datetime.now(); ini_str = now.strftime("%Y-%m-%d %H:%M:%S"); fim_str = (now + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO agendamentos (paciente_id, profissional_id, data_hora_inicio, duracao_minutos, data_hora_fim, status, tipo, observacoes) VALUES (?,?,?,?,?,?,?,?)", (d['id'], prof_id, ini_str, 30, fim_str, 'Em Atendimento', 'Encaixe', 'Criado via Atendimento'))
    conn.commit(); conn.close(); return jsonify({"msg": "Atualizado"})

@app.route('/api/agendamento/transferir', methods=['POST'])
@login_required
def tr_ag():
    d=request.json; conn=db.conectar(); ini=datetime.strptime(f"{d['data']} {d['hora']}","%Y-%m-%d %H:%M"); fim=ini+timedelta(minutes=30); istr,fstr=ini.strftime("%Y-%m-%d %H:%M:%S"),fim.strftime("%Y-%m-%d %H:%M:%S")
    if conn.execute("SELECT id FROM agendamentos WHERE profissional_id=? AND status!='Cancelado' AND id!=? AND ((data_hora_inicio<? AND data_hora_fim>?) OR (data_hora_inicio>=? AND data_hora_fim<=?))", (d['profissional_id'],d['id'],fstr,istr,istr,fstr)).fetchone(): conn.close(); return jsonify({"erro":"Indisponível"}),409
    conn.execute("UPDATE agendamentos SET profissional_id=?, data_hora_inicio=?, data_hora_fim=?, status='Agendado' WHERE id=?",(d['profissional_id'],istr,fstr,d['id'])); conn.commit(); conn.close(); return jsonify({"msg":"Ok"})

@app.route('/api/financeiro/<t>', methods=['GET'])
@login_required
def list_fin(t):
    conn=db.conectar()
    if t=='caixa': r=conn.execute("SELECT * FROM caixa ORDER BY data_hora DESC LIMIT 100").fetchall()
    elif t=='receber': r=conn.execute("SELECT c.*, p.nome as pessoa FROM contas_receber c LEFT JOIN pacientes p ON c.paciente_id=p.id ORDER BY c.data_vencimento").fetchall()
    else: r=conn.execute("SELECT c.*, c.fornecedor as pessoa FROM contas_pagar c ORDER BY c.data_vencimento").fetchall()
    conn.close(); return jsonify([dict(x) for x in r])

@app.route('/api/financeiro/salvar', methods=['POST'])
@login_required
def save_fin():
    d=request.json; conn=db.conectar(); 
    if not d.get('valor') or not d.get('venc'): return jsonify({"erro": "Valor/Vencimento obrigatórios"}), 400
    t=d['tipo']; parc=int(d.get('parc',1)); val=float(d['valor'])/parc; dt=datetime.strptime(d['venc'],"%Y-%m-%d")
    for i in range(parc):
        venc=(dt+timedelta(days=30*i)).strftime("%Y-%m-%d"); desc=f"{d['desc']} ({i+1}/{parc})" if parc>1 else d['desc']
        if t=='receber': conn.execute("INSERT INTO contas_receber (paciente_id, descricao, valor_total, data_vencimento, categoria, centro_custo, forma_pagamento, parcelas, parcela_atual) VALUES (?,?,?,?,?,?,?,?,?)",(d.get('paciente_id'),desc,val,venc,d['cat'],d.get('cc'),d['forma'],parc,i+1))
        else: conn.execute("INSERT INTO contas_pagar (fornecedor, descricao, valor_total, data_vencimento, categoria, centro_custo, forma_pagamento, parcelas, parcela_atual) VALUES (?,?,?,?,?,?,?,?,?)",(d.get('fornecedor'),desc,val,venc,d['cat'],d.get('cc'),d['forma'],parc,i+1))
    conn.commit(); conn.close(); return jsonify({"msg":"Ok"})

@app.route('/api/financeiro/baixar', methods=['POST'])
@login_required
def baixa_fin():
    d=request.json; conn=db.conectar(); tab=f"contas_{d['tipo']}"; c=conn.execute(f"SELECT * FROM {tab} WHERE id=?",(d['id'],)).fetchone()
    np=float(c['valor_pago'])+float(d['valor_pago']); st='Pago' if np>=float(c['valor_total'])-0.1 else 'Parcial'
    conn.execute(f"UPDATE {tab} SET status=?, valor_pago=?, data_pagamento=? WHERE id=?",(st,np,datetime.now().strftime("%Y-%m-%d"),d['id']))
    conn.execute("INSERT INTO caixa (tipo, valor, descricao, usuario, referencia_id) VALUES (?,?,?,?,?)",('Entrada' if d['tipo']=='receber' else 'Saída', d['valor_pago'], f"Baixa: {c['descricao']}", current_user.username, d['id']))
    conn.commit(); conn.close(); return jsonify({"msg":"Ok"})

@app.route('/api/auxiliares/<t>', methods=['GET'])
@login_required
def list_ax(t): 
    if t not in ['especialidades','salas','procedimentos','convenios']: return jsonify([])
    conn=db.conectar(); r=[dict(x) for x in conn.execute(f"SELECT * FROM {t} ORDER BY nome").fetchall()]; conn.close(); return jsonify(r)
@app.route('/api/auxiliares/<t>/salvar', methods=['POST'])
@login_required
def save_ax(t): conn=db.conectar(); conn.execute(f"INSERT INTO {t} (nome) VALUES (?)",(request.json['nome'],)); conn.commit(); conn.close(); return jsonify({"msg":"Ok"})
@app.route('/api/auxiliares/<t>/deletar/<int:id>', methods=['DELETE'])
@login_required
def del_ax(t, id): conn=db.conectar(); conn.execute(f"DELETE FROM {t} WHERE id=?",(id,)); conn.commit(); conn.close(); return jsonify({"msg":"Ok"})

@app.route('/api/convenios', methods=['GET'])
@login_required
def list_conv(): conn=db.conectar(); r=[dict(x) for x in conn.execute("SELECT * FROM convenios ORDER BY nome").fetchall()]; conn.close(); return jsonify(r)
@app.route('/api/convenios/salvar', methods=['POST'])
@login_required
def save_conv():
    d=request.json; conn=db.conectar(); v=(d['nome'],d.get('ans'),d.get('cnpj'),d.get('prazo',30),d.get('tel'),d.get('email'),d.get('site'))
    if d.get('id'): conn.execute("UPDATE convenios SET nome=?, registro_ans=?, cnpj=?, prazo_pagamento=?, telefone=?, email=?, site=? WHERE id=?", v+(d['id'],))
    else: conn.execute("INSERT INTO convenios (nome, registro_ans, cnpj, prazo_pagamento, telefone, email, site) VALUES (?,?,?,?,?,?,?)", v)
    conn.commit(); conn.close(); return jsonify({"msg":"Ok"})
@app.route('/api/auxiliares/convenios/deletar/<int:id>', methods=['DELETE'])
@login_required
def del_conv(id): conn=db.conectar(); conn.execute("DELETE FROM convenios WHERE id=?",(id,)); conn.commit(); conn.close(); return jsonify({"msg":"Ok"})

@app.route('/api/prontuario/<int:id>', methods=['GET'])
@login_required
def list_pr(id): conn=db.conectar(); r=[dict(x) for x in conn.execute("SELECT p.*, prof.nome as profissional FROM prontuarios p JOIN profissionais prof ON p.profissional_id=prof.id WHERE p.paciente_id=? ORDER BY p.data_atendimento DESC",(id,)).fetchall()]; conn.close(); return jsonify(r)
@app.route('/api/prontuario/salvar', methods=['POST'])
@login_required
def save_pr(): d=request.json; conn=db.conectar(); conn.execute("INSERT INTO prontuarios (paciente_id, profissional_id, data_atendimento, evolucao_clinica, diagnostico, prescricao, exames_solicitados) VALUES (?,?,?,?,?,?,?)",(d['paciente_id'],d['profissional_id'],datetime.now().strftime("%Y-%m-%d %H:%M"),d['evolucao'],d.get('diagnostico'),d.get('prescricao'),d.get('exames'))); conn.commit(); conn.close(); return jsonify({"msg":"Ok"})

# --- RELATÓRIOS ROBUSTOS E NOVOS ---
@app.route('/api/relatorios/gerar', methods=['POST'])
@login_required
def rel():
    d = request.json; conn = db.conectar(); res = []
    ini, fim = d['inicio'], d['fim']

    if d['tipo'] == 'agendamentos':
        q = """SELECT a.data_hora_inicio, p.nome as paciente, pr.nome as profissional, a.status 
               FROM agendamentos a 
               JOIN pacientes p ON a.paciente_id=p.id 
               JOIN profissionais pr ON a.profissional_id=pr.id 
               WHERE DATE(a.data_hora_inicio) BETWEEN ? AND ? ORDER BY a.data_hora_inicio"""
        res = [dict(r) for r in conn.execute(q, (ini, fim)).fetchall()]
    
    elif d['tipo'] == 'financeiro':
        # Entradas
        r_in = conn.execute("SELECT data_vencimento as data, descricao, categoria, 'Receita' as tipo, valor_total as valor FROM contas_receber WHERE data_vencimento BETWEEN ? AND ?", (ini, fim)).fetchall()
        # Saídas
        r_out = conn.execute("SELECT data_vencimento as data, descricao, categoria, 'Despesa' as tipo, valor_total as valor FROM contas_pagar WHERE data_vencimento BETWEEN ? AND ?", (ini, fim)).fetchall()
        
        for x in r_in: res.append(dict(x))
        for x in r_out: res.append(dict(x))
        res.sort(key=lambda x: x['data'])

    elif d['tipo'] == 'profissionais':
        q = """SELECT pr.nome as profissional, COUNT(a.id) as atendimentos, 
               SUM(CASE WHEN a.status='Finalizado' THEN 1 ELSE 0 END) as finalizados
               FROM agendamentos a
               JOIN profissionais pr ON a.profissional_id=pr.id
               WHERE DATE(a.data_hora_inicio) BETWEEN ? AND ?
               GROUP BY pr.nome"""
        res = [dict(r) for r in conn.execute(q, (ini, fim)).fetchall()]

    elif d['tipo'] == 'pacientes':
        res = [dict(r) for r in conn.execute("SELECT nome, cpf, telefone_principal, email, created_at as cadastro FROM pacientes ORDER BY nome").fetchall()]
        
    elif d['tipo'] == 'convenios':
        q = """SELECT c.nome as convenio, COUNT(a.id) as atendimentos
               FROM agendamentos a
               JOIN pacientes p ON a.paciente_id=p.id
               JOIN convenios c ON p.convenio_id=c.id
               WHERE DATE(a.data_hora_inicio) BETWEEN ? AND ?
               GROUP BY c.nome ORDER BY atendimentos DESC"""
        res = [dict(r) for r in conn.execute(q, (ini, fim)).fetchall()]

    elif d['tipo'] == 'aniversariantes':
        # Pega o mês da data de inicio
        mes = datetime.strptime(ini, "%Y-%m-%d").strftime("%m")
        q = """SELECT nome, strftime('%d/%m', data_nascimento) as dia, telefone_principal 
               FROM pacientes 
               WHERE strftime('%m', data_nascimento) = ? ORDER BY strftime('%d', data_nascimento)"""
        res = [dict(r) for r in conn.execute(q, (mes,)).fetchall()]

    conn.close(); return jsonify(res)

@app.route('/api/exportar/<tipo>')
@login_required
def exportar(tipo):
    conn=db.conectar(); output=io.StringIO(); writer=csv.writer(output)
    if tipo=='financeiro': 
        cursor=conn.execute("SELECT data_hora, tipo, descricao, valor FROM caixa")
        writer.writerow(['Data','Tipo','Descricao','Valor'])
    if tipo=='pacientes':
        cursor=conn.execute("SELECT nome, cpf, telefone_principal, email FROM pacientes")
        writer.writerow(['Nome','CPF','Tel','Email'])
    writer.writerows(cursor.fetchall()); conn.close()
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": f"attachment; filename={tipo}.csv"})

if __name__ == '__main__':
    import socket
    
    # Função para descobrir o IP do computador na rede Wi-Fi/Cabo
    def obter_ip_rede():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Não conecta realmente, apenas para ver qual IP o roteador atribuiu
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    ip_local = obter_ip_rede()
    porta = 5000
    
    print("="*50)
    print(f"🚀 SISTEMA ONLINE!")
    print(f"🔹 No Computador Principal, acesse: http://localhost:{porta}")
    print(f"🔸 NOS OUTROS COMPUTADORES, digite: http://{ip_local}:{porta}")
    print("="*50)
    print("⚠️  IMPORTANTE: Se aparecer um aviso do Firewall do Windows,")
    print("    clique em 'PERMITIR ACESSO' para que os outros consigam entrar.")
    print("="*50)

    # Abre o navegador no servidor automaticamente
    webbrowser.open_new(f'http://127.0.0.1:{porta}')
    
    # host='0.0.0.0' é o segredo que libera o acesso para a rede
    app.run(host='0.0.0.0', port=porta, debug=True)