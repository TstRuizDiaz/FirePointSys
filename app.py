from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)
app.secret_key = "chave_super_secreta"

# TOKEN FIXO PARA TODOS OS USUÁRIOS (válido por 6 meses)
TOKEN_SESMT = "f5vx2V2TA32VwC2oeLgwU7bR91f7Fy6eV"
TOKEN_EXPIRACAO = datetime.now() + timedelta(days=180)  # 6 meses de validade

# Configurações de email (ajuste com seus dados)
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'email': 'seu_email@gmail.com',
    'password': 'sua_senha_app'
}

# Configurações de upload
app.config['UPLOAD_FOLDER'] = 'static/uploads/extintores'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Criar pasta de uploads se não existir
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Função para atualizar o schema do banco de dados
def atualizar_schema():
    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()
    
    # Verificar se as colunas novas já existem
    cursor.execute("PRAGMA table_info(usuarios)")
    colunas = [coluna[1] for coluna in cursor.fetchall()]
    
    # Adicionar colunas que faltam
    if 'email' not in colunas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN email TEXT")
    
    if 'token_validado' not in colunas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN token_validado INTEGER DEFAULT 0")
    
    if 'data_validacao_token' not in colunas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN data_validacao_token TEXT")
    
    # Verificar e criar tabela de extintores se não existir
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='extintores'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE extintores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_serie TEXT UNIQUE NOT NULL,
                tipo TEXT NOT NULL,
                capacidade TEXT NOT NULL,
                localizacao TEXT NOT NULL,
                data_instalacao DATE NOT NULL,
                data_ultima_inspecao DATE,
                data_proxima_inspecao DATE NOT NULL,
                status TEXT DEFAULT 'Ativo',
                observacoes TEXT,
                foto_path TEXT,
                usuario_id INTEGER,
                FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
            )
        """)
    
    conn.commit()
    conn.close()
    print("Schema do banco de dados atualizado com sucesso!")

# Criar banco e tabela de usuários, se não existir
def init_db():
    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()
    
    # Verificar se a tabela já existe
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='usuarios'")
    tabela_existe = cursor.fetchone()
    
    if not tabela_existe:
        cursor.execute("""
            CREATE TABLE usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                usuario TEXT NOT NULL UNIQUE,
                senha TEXT NOT NULL,
                email TEXT,
                token_validado INTEGER DEFAULT 0,
                data_validacao_token TEXT
            )
        """)
        
        # Inserir os usuários fornecidos
        usuarios = [
            ("Batista Luan", "031570130", "Lactalis@2028", "luan@empresa.com"),
            ("Rodrigues Flayberthy", "031091556", "3528211407@tSt", "flayberthy@empresa.com"),
            ("Messias Elaine", "031581812", "Lactalis@2026", "elaine@empresa.com")
        ]
        
        cursor.executemany("INSERT INTO usuarios (nome, usuario, senha, email) VALUES (?, ?, ?, ?)", usuarios)
        conn.commit()
        print("Banco de dados criado e usuários inseridos com sucesso!")
    else:
        # Se a tabela já existe, atualizar o schema
        atualizar_schema()
    
    conn.close()

# Função para enviar email de notificação
def enviar_email_notificacao(destinatario, nome_usuario, dias_restantes):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['email']
        msg['To'] = destinatario
        msg['Subject'] = "⚠️ Notificação: Token SESMT perto de expirar"
        
        corpo = f"""
        Olá {nome_usuario},
        
        Seu token de acesso ao sistema SESMT expirará em {dias_restantes} dias.
        
        Data de expiração: {TOKEN_EXPIRACAO.strftime('%d/%m/%Y')}
        
        Entre em contato com o administrador para renovar o token.
        
        Atenciosamente,
        Sistema de Controle de Extintores
        """
        
        msg.attach(MIMEText(corpo, 'plain'))
        
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['email'], EMAIL_CONFIG['password'])
        server.send_message(msg)
        server.quit()
        
        print(f"Email de notificação enviado para {destinatario}")
        return True
    except Exception as e:
        print(f"Erro ao enviar email: {e}")
        return False

# Verificar se precisa enviar notificação de token
def verificar_notificacao_token():
    dias_restantes = (TOKEN_EXPIRACAO - datetime.now()).days
    
    # Enviar notificação se faltar 30, 15, 7 ou 1 dia
    if dias_restantes in [30, 15, 7, 1]:
        conn = sqlite3.connect("banco.db")
        cursor = conn.cursor()
        cursor.execute("SELECT email, nome FROM usuarios WHERE token_validado = 1")
        usuarios = cursor.fetchall()
        conn.close()
        
        for email, nome in usuarios:
            enviar_email_notificacao(email, nome, dias_restantes)

# Rota para verificar usuários (apenas para debug)
@app.route("/debug-usuarios")
def debug_usuarios():
    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios")
    usuarios = cursor.fetchall()
    conn.close()
    
    resultado = "<h1>Usuários no Banco de Dados</h1>"
    for usuario in usuarios:
        resultado += f"<p>ID: {usuario[0]}, Nome: {usuario[1]}, Usuário: {usuario[2]}, Senha: {usuario[3]}, Email: {usuario[4]}, Token Validado: {usuario[5]}</p>"
    
    return resultado

# Página de login (primeiro fator)
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    # Verificar notificações de token
    verificar_notificacao_token()
    
    # Se já estiver autenticado completamente, redireciona para dashboard
    if session.get("token_validado"):
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        usuario = request.form["usuario"].strip()
        senha = request.form["senha"].strip()

        conn = sqlite3.connect("banco.db")
        cursor = conn.cursor()
        
        # Verificar se a coluna token_validado existe
        cursor.execute("PRAGMA table_info(usuarios)")
        colunas = [coluna[1] for coluna in cursor.fetchall()]
        
        if 'token_validado' in colunas:
            cursor.execute("SELECT id, nome, senha, token_validado FROM usuarios WHERE usuario = ?", (usuario,))
        else:
            cursor.execute("SELECT id, nome, senha, 0 as token_validado FROM usuarios WHERE usuario = ?", (usuario,))
            
        resultado = cursor.fetchone()
        conn.close()

        if resultado:
            if 'token_validado' in colunas:
                id_usuario, nome_usuario, senha_db, token_validado = resultado
            else:
                id_usuario, nome_usuario, senha_db, token_validado = resultado
                token_validado = 0  # Para bancos antigos sem a coluna
            
            if senha == senha_db:
                # Salvar dados do usuário na sessão
                session["usuario_id"] = id_usuario
                session["usuario"] = usuario
                session["nome"] = nome_usuario
                session["primeiro_fator"] = True
                
                # Se já validou o token anteriormente, não precisa validar novamente
                if token_validado:
                    session["token_validado"] = True
                    flash("Login realizado com sucesso!")
                    return redirect(url_for('dashboard'))
                else:
                    return redirect(url_for('verificar_token'))
            else:
                flash("Senha incorreta!")
        else:
            flash("Usuário não encontrado!")

        return redirect(url_for("login"))

    return render_template("login.html")

# Página para verificar token SESMT (segundo fator)
@app.route("/verificar-token", methods=["GET", "POST"])
def verificar_token():
    if not session.get("primeiro_fator"):
        return redirect(url_for('login'))
    
    if session.get("token_validado"):
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        token_digitado = request.form["token"].strip()
        
        if token_digitado == TOKEN_SESMT and datetime.now() < TOKEN_EXPIRACAO:
            # Marcar no banco que o usuário já validou o token
            conn = sqlite3.connect("banco.db")
            cursor = conn.cursor()
            
            # Verificar se a coluna existe antes de tentar atualizar
            cursor.execute("PRAGMA table_info(usuarios)")
            colunas = [coluna[1] for coluna in cursor.fetchall()]
            
            if 'token_validado' in colunas and 'data_validacao_token' in colunas:
                cursor.execute("UPDATE usuarios SET token_validado = 1, data_validacao_token = ? WHERE id = ?", 
                              (datetime.now().isoformat(), session["usuario_id"]))
            else:
                # Se as colunas não existem, criar elas primeiro
                atualizar_schema()
                cursor.execute("UPDATE usuarios SET token_validado = 1, data_validacao_token = ? WHERE id = ?", 
                              (datetime.now().isoformat(), session["usuario_id"]))
            
            conn.commit()
            conn.close()
            
            session["token_validado"] = True
            flash("Token validado com sucesso!")
            return redirect(url_for('dashboard'))
        else:
            if datetime.now() > TOKEN_EXPIRACAO:
                flash("Token expirado! Entre em contato com o administrador.")
            else:
                flash("Token incorreto!")
    
    return render_template("verificar_token.html", TOKEN_EXPIRACAO=TOKEN_EXPIRACAO)

# Dashboard (após validação do token)
@app.route("/dashboard")
def dashboard():
    if not session.get("token_validado"):
        flash("Autenticação necessária!")
        return redirect(url_for('login'))
    
    return render_template("dashboard.html", 
                         nome=session["nome"],
                         token_expira=TOKEN_EXPIRACAO.isoformat())

# Cadastrar extintor com foto - CORRIGIDO
@app.route("/extintores/cadastrar", methods=["GET", "POST"])
def cadastrar_extintor():
    if not session.get("token_validado"):
        flash("Acesso não autorizado!")
        return redirect(url_for('login'))
    
    if request.method == "POST":
        # Coletar dados do formulário
        numero_serie = request.form["numero_serie"].strip()
        tipo = request.form["tipo"]
        capacidade = request.form["capacidade"]
        localizacao = request.form["localizacao"]
        data_instalacao = request.form["data_instalacao"]
        data_proxima_inspecao = request.form["data_proxima_inspecao"]
        observacoes = request.form["observacoes"]
        
        # Processar upload da foto
        foto_path = None
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename != '' and allowed_file(file.filename):
                # Gerar nome único para o arquivo
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = secure_filename(f"extintor_{numero_serie}_{timestamp}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # ✅ CORREÇÃO: Salvar apenas o nome do arquivo
                foto_path = filename
                
                print(f"✅ Foto salva em: {filepath}")
                print(f"✅ Nome do arquivo no BD: {foto_path}")

        try:
            conn = sqlite3.connect("banco.db")
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO extintores 
                (numero_serie, tipo, capacidade, localizacao, data_instalacao, 
                 data_proxima_inspecao, observacoes, foto_path, usuario_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (numero_serie, tipo, capacidade, localizacao, data_instalacao,
                  data_proxima_inspecao, observacoes, foto_path, session["usuario_id"]))
            
            conn.commit()
            conn.close()
            flash("Extintor cadastrado com sucesso!")
            return redirect(url_for('listar_extintores'))
            
        except sqlite3.IntegrityError:
            flash("Número de série já existe!")
        except Exception as e:
            flash(f"Erro ao cadastrar: {str(e)}")
    
    return render_template("cadastrar_extintor.html")

# Listar extintores - ATUALIZADA
@app.route("/extintores")
def listar_extintores():
    if not session.get("token_validado"):
        flash("Acesso não autorizado!")
        return redirect(url_for('login'))
    
    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM extintores ORDER BY localizacao, numero_serie")
    extintores = cursor.fetchall()
    conn.close()
    
    # Processar os caminhos das fotos para incluir o caminho completo
    extintores_processados = []
    for extintor in extintores:
        extintor_list = list(extintor)
        if extintor_list[10]:  # Se tem foto_path
            # Adicionar o caminho completo correto
            extintor_list[10] = f"uploads/extintores/{extintor_list[10]}"
        extintores_processados.append(extintor_list)
    
    return render_template("listar_extintores.html", extintores=extintores_processados)

# Rota para corrigir caminhos existentes
@app.route("/corrigir-caminhos")
def corrigir_caminhos():
    conn = sqlite3.connect("banco.db")
    cursor = conn.cursor()
    
    # Listar todos os extintores com foto
    cursor.execute("SELECT id, foto_path FROM extintores WHERE foto_path IS NOT NULL")
    extintores = cursor.fetchall()
    
    for id_ext, foto_path in extintores:
        # Extrair apenas o nome do arquivo do caminho completo
        if foto_path and '/' in foto_path:
            nome_arquivo = foto_path.split('/')[-1]  # Pega apenas o nome do arquivo
            cursor.execute("UPDATE extintores SET foto_path = ? WHERE id = ?", 
                          (nome_arquivo, id_ext))
            print(f"✅ Corrigido: ID {id_ext} - {foto_path} -> {nome_arquivo}")
    
    conn.commit()
    conn.close()
    return "Caminhos corrigidos!"

# Logout
@app.route("/logout")
def logout():
    session.clear()
    flash("Você foi desconectado com sucesso.")
    return redirect(url_for("login"))

if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)