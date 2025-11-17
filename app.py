# SYGEP - Système de Gestion d'Entreprise Pédagogique
# Version enrichie : notifications, workflow tâches, génération de documents (PDF si fpdf installé)
# Remarques : configurez vos variables SUPABASE_* dans .env ou st.secrets sur Streamlit Cloud

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json
import hashlib
from PIL import Image
import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv
import io
import time

# PDF optional
try:
    from fpdf import FPDF
    HAS_FPDF = True
except Exception:
    HAS_FPDF = False

# Charger les variables d'environnement
load_dotenv()

# Configuration de la page
st.set_page_config(
    page_title="SYGEP - Système de Gestion d'Entreprise Pédagogique",
    layout="wide",
    page_icon="🎓",
    initial_sidebar_state="expanded"
)

# ========== GESTION CONNEXION POSTGRESQL (SUPABASE) ==========

@st.cache_resource
def init_connection_pool():
    """Initialise un pool de connexions PostgreSQL"""
    try:
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20,  # min et max connexions
            host=os.getenv('SUPABASE_HOST'),
            database=os.getenv('SUPABASE_DB', 'postgres'),
            user=os.getenv('SUPABASE_USER', 'postgres'),
            password=os.getenv('SUPABASE_PASSWORD'),
            port=os.getenv('SUPABASE_PORT', '5432')
        )
        return connection_pool
    except Exception as e:
        # Fallback vers secrets.toml pour Streamlit Cloud
        try:
            connection_pool = psycopg2.pool.SimpleConnectionPool(
                1, 20,
                host=st.secrets["supabase"]["host"],
                database=st.secrets["supabase"]["database"],
                user=st.secrets["supabase"]["user"],
                password=st.secrets["supabase"]["password"],
                port=st.secrets["supabase"]["port"]
            )
            return connection_pool
        except Exception as e2:
            st.error(f"❌ Erreur de connexion à la base de données: {e2}")
            st.stop()

def get_connection():
    """Obtient une connexion depuis le pool"""
    pool_ = init_connection_pool()
    return pool_.getconn()

def release_connection(conn):
    """Libère une connexion vers le pool"""
    pool_ = init_connection_pool()
    pool_.putconn(conn)

# ========== INITIALISATION BASE DE DONNÉES (avec nouvelles tables) ==========
def init_database():
    """Initialise les tables PostgreSQL"""
    conn = get_connection()
    try:
        c = conn.cursor()
        # Tables existantes
        c.execute('''CREATE TABLE IF NOT EXISTS utilisateurs
                     (id SERIAL PRIMARY KEY,
                      username VARCHAR(100) UNIQUE NOT NULL,
                      password VARCHAR(255) NOT NULL,
                      role VARCHAR(50) NOT NULL,
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS permissions
                     (id SERIAL PRIMARY KEY,
                      user_id INTEGER REFERENCES utilisateurs(id) ON DELETE CASCADE,
                      module VARCHAR(100) NOT NULL,
                      acces_lecture BOOLEAN DEFAULT FALSE,
                      acces_ecriture BOOLEAN DEFAULT FALSE)''')

        c.execute('''CREATE TABLE IF NOT EXISTS clients
                     (id SERIAL PRIMARY KEY,
                      nom VARCHAR(255) NOT NULL,
                      email VARCHAR(255),
                      telephone VARCHAR(50),
                      date_creation DATE)''')

        c.execute('''CREATE TABLE IF NOT EXISTS produits
                     (id SERIAL PRIMARY KEY,
                      nom VARCHAR(255) NOT NULL,
                      prix DECIMAL(10,2) NOT NULL,
                      stock INTEGER NOT NULL,
                      seuil_alerte INTEGER DEFAULT 10)''')

        c.execute('''CREATE TABLE IF NOT EXISTS fournisseurs
                     (id SERIAL PRIMARY KEY,
                      nom VARCHAR(255) NOT NULL,
                      email VARCHAR(255),
                      telephone VARCHAR(50),
                      adresse TEXT,
                      date_creation DATE)''')

        c.execute('''CREATE TABLE IF NOT EXISTS commandes
                     (id SERIAL PRIMARY KEY,
                      client_id INTEGER REFERENCES clients(id),
                      produit_id INTEGER REFERENCES produits(id),
                      quantite INTEGER,
                      date DATE,
                      statut VARCHAR(50))''')

        c.execute('''CREATE TABLE IF NOT EXISTS achats
                     (id SERIAL PRIMARY KEY,
                      fournisseur_id INTEGER REFERENCES fournisseurs(id),
                      produit_id INTEGER REFERENCES produits(id),
                      quantite INTEGER,
                      prix_unitaire DECIMAL(10,2),
                      date DATE,
                      statut VARCHAR(50))''')

        c.execute('''CREATE TABLE IF NOT EXISTS sessions
                     (id SERIAL PRIMARY KEY,
                      session_id VARCHAR(255) UNIQUE,
                      user_id INTEGER REFERENCES utilisateurs(id),
                      username VARCHAR(100),
                      role VARCHAR(50),
                      last_activity TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS logs_acces
                     (id SERIAL PRIMARY KEY,
                      user_id INTEGER REFERENCES utilisateurs(id),
                      module VARCHAR(100),
                      action TEXT,
                      date_heure TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        # Nouveaux: notifications, tasks, history, documents, emails_log
        c.execute('''CREATE TABLE IF NOT EXISTS notifications
                     (id SERIAL PRIMARY KEY,
                      user_id INTEGER REFERENCES utilisateurs(id),
                      target_role VARCHAR(50),
                      type VARCHAR(50),
                      message TEXT,
                      target_module VARCHAR(100),
                      related_id INTEGER,
                      is_read BOOLEAN DEFAULT FALSE,
                      created_at TIMESTAMP DEFAULT NOW())''')

        c.execute('''CREATE TABLE IF NOT EXISTS workflow_tasks
                     (id SERIAL PRIMARY KEY,
                      task_type VARCHAR(50),
                      related_order_id INTEGER,
                      assigned_role VARCHAR(50),
                      assigned_user_id INTEGER REFERENCES utilisateurs(id),
                      status VARCHAR(50) DEFAULT 'pending',
                      payload JSONB,
                      created_at TIMESTAMP DEFAULT NOW(),
                      due_at TIMESTAMP)''')

        c.execute('''CREATE TABLE IF NOT EXISTS workflow_history
                     (id SERIAL PRIMARY KEY,
                      order_id INTEGER,
                      previous_state VARCHAR(50),
                      new_state VARCHAR(50),
                      by_user_id INTEGER REFERENCES utilisateurs(id),
                      note TEXT,
                      timestamp TIMESTAMP DEFAULT NOW())''')

        c.execute('''CREATE TABLE IF NOT EXISTS documents
                     (id SERIAL PRIMARY KEY,
                      doc_type VARCHAR(50),
                      related_id INTEGER,
                      file_path TEXT,
                      metadata JSONB,
                      generated_by INTEGER REFERENCES utilisateurs(id),
                      created_at TIMESTAMP DEFAULT NOW())''')

        c.execute('''CREATE TABLE IF NOT EXISTS emails_log
                     (id SERIAL PRIMARY KEY,
                      recipient TEXT,
                      subject TEXT,
                      body TEXT,
                      status VARCHAR(20) DEFAULT 'simulated',
                      created_at TIMESTAMP DEFAULT NOW())''')

        conn.commit()

        # Créer utilisateur admin par défaut si n'existe pas
        c.execute("SELECT COUNT(*) FROM utilisateurs WHERE username = %s", ('admin',))
        if c.fetchone()[0] == 0:
            password_hash = hashlib.sha256("admin123".encode()).hexdigest()
            c.execute("INSERT INTO utilisateurs (username, password, role) VALUES (%s, %s, %s) RETURNING id",
                      ('admin', password_hash, 'admin'))
            user_id = c.fetchone()[0]

            modules = ["tableau_bord", "clients", "produits", "fournisseurs", "commandes", "achats", "rapports", "utilisateurs", "workflow", "notifications", "documents", "formateur"]
            for module in modules:
                c.execute("INSERT INTO permissions (user_id, module, acces_lecture, acces_ecriture) VALUES (%s, %s, %s, %s)",
                          (user_id, module, True, True))
            conn.commit()

        # Ajouter données de démonstration si tables vides
        c.execute("SELECT COUNT(*) FROM clients")
        if c.fetchone()[0] == 0:
            c.execute("""INSERT INTO clients (nom, email, telephone, date_creation) VALUES 
                        ('Entreprise Alpha', 'contact@alpha.com', '0612345678', CURRENT_DATE),
                        ('Société Beta', 'info@beta.com', '0698765432', CURRENT_DATE)""")
            c.execute("""INSERT INTO produits (nom, prix, stock, seuil_alerte) VALUES 
                        ('Ordinateur Portable', 899.99, 15, 5),
                        ('Souris Sans Fil', 29.99, 50, 20),
                        ('Clavier Mécanique', 79.99, 30, 10)""")
            c.execute("""INSERT INTO fournisseurs (nom, email, telephone, adresse, date_creation) VALUES 
                        ('TechSupply Co', 'contact@techsupply.com', '0511223344', '12 Rue de la Tech, Paris', CURRENT_DATE),
                        ('GlobalParts', 'info@globalparts.com', '0522334455', '45 Avenue du Commerce, Lyon', CURRENT_DATE)""")
            c.execute("""INSERT INTO commandes (client_id, produit_id, quantite, date, statut) VALUES 
                        (1, 1, 2, CURRENT_DATE - INTERVAL '5 days', 'Livrée'),
                        (2, 2, 5, CURRENT_DATE - INTERVAL '2 days', 'En cours')""")
            conn.commit()

    except Exception as e:
        st.error(f"Erreur initialisation BDD: {e}")
        conn.rollback()
    finally:
        release_connection(conn)

# ========== FONCTIONS UTILITAIRES ==========
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_login(username, password):
    conn = get_connection()
    try:
        c = conn.cursor()
        password_hash = hash_password(password)
        c.execute("SELECT id, role FROM utilisateurs WHERE username=%s AND password=%s", (username, password_hash))
        result = c.fetchone()
        return result if result else None
    finally:
        release_connection(conn)

def get_user_permissions(user_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT module, acces_lecture, acces_ecriture FROM permissions WHERE user_id=%s", (user_id,))
        permissions = {}
        for row in c.fetchall():
            permissions[row[0]] = {
                'lecture': bool(row[1]),
                'ecriture': bool(row[2])
            }
        return permissions
    finally:
        release_connection(conn)

def has_access(module, access_type='lecture'):
    if st.session_state.get('role') == "admin":
        return True
    permissions = st.session_state.get('permissions', {})
    module_perms = permissions.get(module, {'lecture': False, 'ecriture': False})
    return module_perms.get(access_type, False)

def log_access(user_id, module, action):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO logs_acces (user_id, module, action) VALUES (%s, %s, %s)", (user_id, module, action))
        conn.commit()
    finally:
        release_connection(conn)

def get_clients():
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM clients ORDER BY id", conn)
        return df
    finally:
        release_connection(conn)

def get_produits():
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM produits ORDER BY id", conn)
        return df
    finally:
        release_connection(conn)

def get_fournisseurs():
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM fournisseurs ORDER BY id", conn)
        return df
    finally:
        release_connection(conn)

def get_commandes():
    conn = get_connection()
    try:
        query = """
        SELECT c.id, cl.nom as client, p.nom as produit, c.quantite, 
               (c.quantite * p.prix) as montant, c.date, c.statut
        FROM commandes c
        JOIN clients cl ON c.client_id = cl.id
        JOIN produits p ON c.produit_id = p.id
        ORDER BY c.date DESC
        """
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        release_connection(conn)

def get_achats():
    conn = get_connection()
    try:
        query = """
        SELECT a.id, f.nom as fournisseur, p.nom as produit, a.quantite, 
               a.prix_unitaire, (a.quantite * a.prix_unitaire) as montant_total, a.date, a.statut
        FROM achats a
        JOIN fournisseurs f ON a.fournisseur_id = f.id
        JOIN produits p ON a.produit_id = p.id
        ORDER BY a.date DESC
        """
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        release_connection(conn)

# ========== SESSIONS (persistantes) ==========
def save_session_to_db(user_id, username, role):
    conn = get_connection()
    try:
        c = conn.cursor()
        session_id = hashlib.sha256(f"{username}_{time.time()}".encode()).hexdigest()
        c.execute("DELETE FROM sessions WHERE last_activity < NOW() - INTERVAL '1 day'")
        c.execute("""INSERT INTO sessions (session_id, user_id, username, role, last_activity) 
                     VALUES (%s, %s, %s, %s, NOW())""",
                  (session_id, user_id, username, role))
        conn.commit()
        return session_id
    finally:
        release_connection(conn)

def load_session_from_db(session_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""SELECT user_id, username, role FROM sessions 
                     WHERE session_id=%s AND last_activity > NOW() - INTERVAL '1 day'""",
                  (session_id,))
        result = c.fetchone()
        if result:
            c.execute("UPDATE sessions SET last_activity=NOW() WHERE session_id=%s", (session_id,))
            conn.commit()
        return result
    finally:
        release_connection(conn)

def delete_session_from_db(session_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM sessions WHERE session_id=%s", (session_id,))
        conn.commit()
    finally:
        release_connection(conn)

# ========== NOTIFICATIONS ==========
def create_notification(user_id=None, target_role=None, ntype="info", message="", target_module=None, related_id=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""INSERT INTO notifications (user_id, target_role, type, message, target_module, related_id)
                     VALUES (%s, %s, %s, %s, %s, %s)""",
                  (user_id, target_role, ntype, message, target_module, related_id))
        conn.commit()
    finally:
        release_connection(conn)

def list_notifications_for_user(user_id=None, role=None, only_unread=False, limit=100):
    conn = get_connection()
    try:
        c = conn.cursor()
        if user_id:
            if only_unread:
                c.execute("""SELECT id, user_id, target_role, type, message, target_module, related_id, is_read, created_at
                             FROM notifications
                             WHERE (user_id = %s OR target_role = %s) AND is_read = FALSE
                             ORDER BY created_at DESC
                             LIMIT %s""", (user_id, role, limit))
            else:
                c.execute("""SELECT id, user_id, target_role, type, message, target_module, related_id, is_read, created_at
                             FROM notifications
                             WHERE (user_id = %s OR target_role = %s)
                             ORDER BY created_at DESC
                             LIMIT %s""", (user_id, role, limit))
        else:
            if only_unread:
                c.execute("SELECT id, user_id, target_role, type, message, target_module, related_id, is_read, created_at FROM notifications WHERE is_read = FALSE ORDER BY created_at DESC LIMIT %s", (limit,))
            else:
                c.execute("SELECT id, user_id, target_role, type, message, target_module, related_id, is_read, created_at FROM notifications ORDER BY created_at DESC LIMIT %s", (limit,))
        rows = c.fetchall()
        cols = ['id','user_id','target_role','type','message','target_module','related_id','is_read','created_at']
        df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
        return df
    finally:
        release_connection(conn)

def mark_notification_read(notification_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s", (notification_id,))
        conn.commit()
    finally:
        release_connection(conn)

def count_unread_notifications(user_id=None, role=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        if user_id:
            c.execute("SELECT COUNT(*) FROM notifications WHERE (user_id=%s OR target_role=%s) AND is_read=FALSE", (user_id, role))
        else:
            c.execute("SELECT COUNT(*) FROM notifications WHERE is_read=FALSE")
        res = c.fetchone()
        return int(res[0]) if res and res[0] is not None else 0
    finally:
        release_connection(conn)

# ========== WORKFLOW TASKS ==========
def create_workflow_task(task_type, related_order_id=None, assigned_role=None, assigned_user_id=None, payload=None, due_at=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        payload_json = json.dumps(payload) if payload else None
        c.execute("""INSERT INTO workflow_tasks (task_type, related_order_id, assigned_role, assigned_user_id, status, payload, due_at)
                     VALUES (%s, %s, %s, %s, 'pending', %s, %s) RETURNING id""",
                  (task_type, related_order_id, assigned_role, assigned_user_id, payload_json, due_at))
        task_id = c.fetchone()[0]
        conn.commit()
        # notifications
        if assigned_user_id:
            create_notification(user_id=assigned_user_id, ntype="task", message=f"Tâche assignée: {task_type}", target_module="workflow", related_id=task_id)
        elif assigned_role:
            create_notification(target_role=assigned_role, ntype="task", message=f"Nouvelle tâche pour rôle {assigned_role}: {task_type}", target_module="workflow", related_id=task_id)
        return task_id
    finally:
        release_connection(conn)

def get_tasks_for_user(user_id, role):
    conn = get_connection()
    try:
        query = """SELECT id, task_type, related_order_id, assigned_role, assigned_user_id, status, payload, created_at, due_at
                   FROM workflow_tasks WHERE (assigned_user_id = %s OR assigned_role = %s)
                   ORDER BY created_at DESC"""
        df = pd.read_sql_query(query, conn, params=(user_id, role))
        return df
    finally:
        release_connection(conn)

def update_task_status(task_id, new_status, by_user_id=None, note=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT status, related_order_id FROM workflow_tasks WHERE id = %s", (task_id,))
        r = c.fetchone()
        if not r:
            return False
        previous = r[0]
        related_order = r[1]
        c.execute("UPDATE workflow_tasks SET status = %s WHERE id = %s", (new_status, task_id))
        c.execute("INSERT INTO workflow_history (order_id, previous_state, new_state, by_user_id, note) VALUES (%s, %s, %s, %s, %s)",
                  (related_order, previous, new_status, by_user_id, note))
        conn.commit()
        create_notification(target_role='directeur', ntype='info', message=f"Tâche {task_id} passée à {new_status}", target_module='workflow', related_id=task_id)
        return True
    finally:
        release_connection(conn)

# ========== DOCUMENTS (PDF generation) ==========
def generate_order_pdf(order_id, doc_type="bon_de_commande", generated_by=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT c.id, cl.nom as client, p.nom as produit, c.quantite, p.prix, (c.quantite * p.prix) as montant, c.date, c.statut
            FROM commandes c
            JOIN clients cl ON c.client_id = cl.id
            JOIN produits p ON c.produit_id = p.id
            WHERE c.id = %s
        """, (order_id,))
        r = c.fetchone()
        if not r:
            return None
        id_, client, produit, quantite, prix, montant, date_, statut = r
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{doc_type}_{order_id}_{timestamp}.pdf"

        if HAS_FPDF:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(0, 10, txt=f"{doc_type.replace('_',' ').upper()} - Commande #{order_id}", ln=1, align='C')
            pdf.ln(5)
            pdf.cell(0, 8, txt=f"Client: {client}", ln=1)
            pdf.cell(0, 8, txt=f"Produit: {produit}", ln=1)
            pdf.cell(0, 8, txt=f"Quantité: {quantite}", ln=1)
            pdf.cell(0, 8, txt=f"Prix unitaire: {float(prix):.2f} €", ln=1)
            pdf.cell(0, 8, txt=f"Montant: {float(montant):.2f} €", ln=1)
            pdf.cell(0, 8, txt=f"Date: {date_} - Statut: {statut}", ln=1)
            buf = io.BytesIO()
            pdf.output(buf)
            buf.seek(0)
            c.execute("INSERT INTO documents (doc_type, related_id, file_path, metadata, generated_by) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                      (doc_type, order_id, filename, json.dumps({'generated_at': timestamp}), generated_by))
            doc_id = c.fetchone()[0]
            conn.commit()
            return {'doc_id': doc_id, 'filename': filename, 'bytes': buf.read()}
        else:
            # fallback simple text file
            content = f"{doc_type.upper()} - Commande #{order_id}\nClient: {client}\nProduit: {produit}\nQuantité: {quantite}\nPrix unitaire: {float(prix):.2f} €\nMontant: {float(montant):.2f} €\nDate: {date_}\nStatut: {statut}\n"
            buf = io.BytesIO(content.encode('utf-8'))
            c.execute("INSERT INTO documents (doc_type, related_id, file_path, metadata, generated_by) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                      (doc_type, order_id, filename, json.dumps({'generated_at': timestamp, 'fallback': True}), generated_by))
            doc_id = c.fetchone()[0]
            conn.commit()
            return {'doc_id': doc_id, 'filename': filename, 'bytes': buf.read()}
    finally:
        release_connection(conn)

# ========== INITIALISATION ==========
init_database()

# Gestion de l'authentification avec persistance
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_id = None
    st.session_state.role = None
    st.session_state.permissions = {}
    st.session_state.session_id = None
    st.session_state.auto_refresh = True

# Restaurer session si existe
if not st.session_state.logged_in:
    query_params = st.experimental_get_query_params()
    if 'session_id' in query_params:
        session_id = query_params.get('session_id')[0]
        session_data = load_session_from_db(session_id)
        if session_data:
            user_id, username, role = session_data
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.user_id = user_id
            st.session_state.role = role
            st.session_state.permissions = get_user_permissions(user_id)
            st.session_state.session_id = session_id
            log_access(user_id, "connexion", "Reconnexion via session persistante")
            st.experimental_rerun()

# ========== PAGE DE CONNEXION ==========
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        try:
            if os.path.exists("Logo_ofppt.png"):
                logo = Image.open("Logo_ofppt.png")
                st.image(logo, width=150)
        except Exception:
            st.write("🎓")
    with col2:
        st.markdown("""
        <div style="text-align: center;">
            <h1 style="color: #1e3a8a;">🎓 SYGEP</h1>
            <h3 style="color: #3b82f6;">Système de Gestion d'Entreprise Pédagogique</h3>
            <p style="color: #64748b; font-size: 14px;">
                <strong>Développé par :</strong> ISMAILI ALAOUI MOHAMED<br>
                IFMLT ZENATA - OFPPT
            </p>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div style="text-align: center; padding: 10px; background-color: #f1f5f9; border-radius: 10px;">
            <p style="margin: 0; font-size: 13px;">📅 {datetime.now().strftime('%d/%m/%Y')}</p>
            <p style="font-size: 13px;">🕐 {datetime.now().strftime('%H:%M:%S')}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.title("🔐 Authentification Utilisateur")
    with st.form("login_form"):
        username = st.text_input("Nom d'utilisateur")
        password = st.text_input("Mot de passe", type="password")
        remember = st.checkbox("Se souvenir de moi")
        submit = st.form_submit_button("Se connecter", use_container_width=True)
        if submit:
            result = verify_login(username, password)
            if result:
                user_id, role = result
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.user_id = user_id
                st.session_state.role = role
                st.session_state.permissions = get_user_permissions(user_id)
                if remember:
                    session_id = save_session_to_db(user_id, username, role)
                    st.session_state.session_id = session_id
                    st.experimental_set_query_params(session_id=session_id)
                log_access(user_id, "connexion", "Connexion réussie")
                st.success("✅ Connexion réussie !")
                st.experimental_rerun()
            else:
                st.error("❌ Identifiants incorrects")

    st.info("Compte par défaut: admin / admin123")
    st.stop()

# ========== INTERFACE PRINCIPALE ==========
col_logo, col_titre, col_date = st.columns([1, 4, 1])
with col_logo:
    try:
        if os.path.exists("Logo_ofppt.png"):
            logo = Image.open("Logo_ofppt.png")
            st.image(logo, width=100)
    except Exception:
        st.write("🎓")
with col_titre:
    st.markdown(f"""
    <div style="text-align: center;">
        <h1 style="color: #1e3a8a;">🎓 SYGEP - Système de Gestion d'Entreprise Pédagogique</h1>
        <p style="color: #64748b; font-size: 14px;">
            Connecté : <strong>{st.session_state.username}</strong> ({st.session_state.role})
        </p>
    </div>
    """, unsafe_allow_html=True)
with col_date:
    date_actuelle = datetime.now()
    st.markdown(f"<div style='text-align:center'>{date_actuelle.strftime('%d/%m/%Y %H:%M:%S')}</div>", unsafe_allow_html=True)

st.markdown("---")

# Sidebar: logout + notifications badge + navigation
if st.sidebar.button("🚪 Se déconnecter", use_container_width=True):
    log_access(st.session_state.user_id, "deconnexion", "Déconnexion")
    if st.session_state.session_id:
        delete_session_from_db(st.session_state.session_id)
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.experimental_rerun()

st.sidebar.divider()
st.session_state.auto_refresh = st.sidebar.checkbox("Auto-refresh (6s)", value=st.session_state.auto_refresh)
if st.session_state.auto_refresh:
    st.markdown('<meta http-equiv="refresh" content="6">', unsafe_allow_html=True)

unread = count_unread_notifications(st.session_state.user_id, st.session_state.role)
st.sidebar.markdown(f"### 🔔 Notifications ({unread})")
with st.sidebar.expander("Aperçu notifications"):
    ndf = list_notifications_for_user(st.session_state.user_id, st.session_state.role, only_unread=False, limit=10)
    if not ndf.empty:
        for _, r in ndf.iterrows():
            status = "🔵" if not r['is_read'] else "⚪"
            st.write(f"{status} [{r['type']}] {r['message']}")
            if not r['is_read']:
                if st.button(f"Marquer lu #{r['id']}", key=f"mr_{r['id']}"):
                    mark_notification_read(r['id'])
                    st.experimental_rerun()
    else:
        st.write("Aucune notification")

st.sidebar.divider()

# Build menu
menu_items = []
if has_access("tableau_bord"): menu_items.append("Tableau de Bord")
if has_access("clients"): menu_items.append("Gestion Clients")
if has_access("produits"): menu_items.append("Gestion Produits")
if has_access("fournisseurs"): menu_items.append("Gestion Fournisseurs")
if has_access("commandes"): menu_items.append("Gestion Commandes")
if has_access("achats"): menu_items.append("Gestion Achats")
if has_access("rapports"): menu_items.append("Rapports & Exports")
if has_access("utilisateurs"): menu_items.append("Gestion Utilisateurs")
menu_items.append("Workflow & Tâches")
menu_items.append("Centre Notifications")
if st.session_state.role == "admin" or has_access("formateur"):
    menu_items.append("Mode Formateur")
menu_items.append("À Propos")

menu = st.sidebar.selectbox("Navigation", menu_items)

# ========== PAGES ==========
if menu == "Tableau de Bord":
    if not has_access("tableau_bord"):
        st.error("❌ Accès refusé")
        st.stop()
    log_access(st.session_state.user_id, "tableau_bord", "Consultation")
    st.header("📈 Tableau de Bord")
    produits_alerte = get_produits()
    if not produits_alerte.empty:
        produits_alerte = produits_alerte[produits_alerte['stock'] <= produits_alerte['seuil_alerte']]
        if not produits_alerte.empty:
            st.warning(f"⚠️ {len(produits_alerte)} produit(s) en stock faible !")
    col1, col2, col3, col4 = st.columns(4)
    clients = get_clients()
    produits = get_produits()
    commandes = get_commandes()
    with col1:
        st.metric("👥 Clients", len(clients))
    with col2:
        st.metric("📦 Produits", len(produits))
    with col3:
        st.metric("🛒 Commandes", len(commandes))
    with col4:
        ca_total = commandes['montant'].sum() if not commandes.empty else 0
        st.metric("💰 CA Total", f"{ca_total:.2f} €")
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📦 Niveau de Stock")
        if not produits.empty:
            st.bar_chart(produits.set_index('nom')['stock'])
    with col2:
        st.subheader("📊 Statut des Commandes")
        if not commandes.empty:
            st.bar_chart(commandes['statut'].value_counts())

elif menu == "Gestion Clients":
    if not has_access("clients"):
        st.error("❌ Accès refusé")
        st.stop()
    log_access(st.session_state.user_id, "clients", "Consultation")
    st.header("👥 Gestion des Clients")
    tab1, tab2 = st.tabs(["Liste", "Ajouter"])
    with tab1:
        clients = get_clients()
        if not clients.empty:
            st.dataframe(clients, use_container_width=True, hide_index=True)
            if has_access("clients", "ecriture"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    client_id = st.selectbox("Supprimer", clients['id'].tolist(), format_func=lambda x: clients[clients['id']==x]['nom'].iloc[0])
                with col2:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Supprimer"):
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("DELETE FROM clients WHERE id=%s", (client_id,))
                            conn.commit()
                            log_access(st.session_state.user_id, "clients", f"Suppression ID:{client_id}")
                            st.success("✅ Client supprimé")
                            st.rerun()
                        finally:
                            release_connection(conn)
        else:
            st.info("Aucun client")
    with tab2:
        if not has_access("clients", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            with st.form("form_client"):
                nom = st.text_input("Nom *")
                email = st.text_input("Email")
                telephone = st.text_input("Téléphone")
                if st.form_submit_button("Enregistrer"):
                    if nom and email:
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("INSERT INTO clients (nom, email, telephone, date_creation) VALUES (%s, %s, %s, CURRENT_DATE)", (nom, email, telephone))
                            conn.commit()
                            log_access(st.session_state.user_id, "clients", f"Ajout: {nom}")
                            st.success(f"✅ Client '{nom}' ajouté !")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erreur: {e}")
                        finally:
                            release_connection(conn)
                    else:
                        st.error("Nom et email requis")

elif menu == "Gestion Produits":
    if not has_access("produits"):
        st.error("❌ Accès refusé")
        st.stop()
    log_access(st.session_state.user_id, "produits", "Consultation")
    st.header("📦 Gestion des Produits")
    tab1, tab2 = st.tabs(["Liste", "Ajouter"])
    with tab1:
        produits = get_produits()
        if not produits.empty:
            produits['statut'] = produits.apply(lambda r: '🔴' if r['stock'] <= r['seuil_alerte'] else '🟢', axis=1)
            st.dataframe(produits, use_container_width=True, hide_index=True)
            if has_access("produits", "ecriture"):
                st.divider()
                st.subheader("📝 Ajuster Stock")
                col1, col2, col3 = st.columns(3)
                with col1:
                    prod_id = st.selectbox("Produit", produits['id'].tolist(), format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0])
                with col2:
                    ajust = st.number_input("Ajustement", value=0, step=1)
                with col3:
                    st.write("")
                    st.write("")
                    if st.button("✅ Appliquer"):
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s", (ajust, prod_id))
                            conn.commit()
                            log_access(st.session_state.user_id, "produits", f"Ajustement stock ID:{prod_id}")
                            st.success("✅ Stock mis à jour")
                            st.rerun()
                        finally:
                            release_connection(conn)
        else:
            st.info("Aucun produit")
    with tab2:
        if not has_access("produits", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            with st.form("form_produit"):
                nom = st.text_input("Nom *")
                prix = st.number_input("Prix (€) *", min_value=0.0, step=0.01)
                stock = st.number_input("Stock initial", min_value=0, step=1)
                seuil = st.number_input("Seuil d'alerte", min_value=0, step=1, value=10)
                if st.form_submit_button("Enregistrer"):
                    if nom and prix > 0:
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("INSERT INTO produits (nom, prix, stock, seuil_alerte) VALUES (%s, %s, %s, %s)", (nom, prix, stock, seuil))
                            conn.commit()
                            log_access(st.session_state.user_id, "produits", f"Ajout: {nom}")
                            st.success(f"✅ Produit '{nom}' ajouté !")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erreur: {e}")
                        finally:
                            release_connection(conn)
                    else:
                        st.error("Nom et prix > 0 requis")

elif menu == "Gestion Fournisseurs":
    if not has_access("fournisseurs"):
        st.error("❌ Accès refusé")
        st.stop()
    log_access(st.session_state.user_id, "fournisseurs", "Consultation")
    st.header("🏭 Gestion des Fournisseurs")
    tab1, tab2 = st.tabs(["Liste", "Ajouter"])
    with tab1:
        fournisseurs = get_fournisseurs()
        if not fournisseurs.empty:
            st.dataframe(fournisseurs, use_container_width=True, hide_index=True)
        else:
            st.info("Aucun fournisseur")
    with tab2:
        if not has_access("fournisseurs", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            with st.form("form_fournisseur"):
                nom = st.text_input("Nom *")
                email = st.text_input("Email")
                telephone = st.text_input("Téléphone")
                adresse = st.text_area("Adresse")
                if st.form_submit_button("Enregistrer"):
                    if nom:
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("INSERT INTO fournisseurs (nom, email, telephone, adresse, date_creation) VALUES (%s, %s, %s, %s, CURRENT_DATE)", (nom, email, telephone, adresse))
                            conn.commit()
                            log_access(st.session_state.user_id, "fournisseurs", f"Ajout: {nom}")
                            st.success(f"✅ Fournisseur '{nom}' ajouté !")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erreur: {e}")
                        finally:
                            release_connection(conn)
                    else:
                        st.error("Nom requis")

elif menu == "Gestion Commandes":
    if not has_access("commandes"):
        st.error("❌ Accès refusé")
        st.stop()
    log_access(st.session_state.user_id, "commandes", "Consultation")
    st.header("🛒 Gestion des Commandes")
    tab1, tab2 = st.tabs(["Liste", "Créer"])
    with tab1:
        commandes = get_commandes()
        if not commandes.empty:
            st.dataframe(commandes, use_container_width=True, hide_index=True)
            if has_access("commandes", "ecriture"):
                st.divider()
                st.subheader("📝 Changer Statut / Générer Document")
                col1, col2 = st.columns(2)
                with col1:
                    cmd_id = st.selectbox("Commande N°", commandes['id'].tolist())
                    statut = st.selectbox("Statut", ["En attente", "En cours", "Livrée", "Annulée"])
                    if st.button("✅ Mettre à jour"):
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("UPDATE commandes SET statut = %s WHERE id = %s", (statut, cmd_id))
                            conn.commit()
                            log_access(st.session_state.user_id, "commandes", f"MAJ statut ID:{cmd_id} -> {statut}")
                            create_notification(target_role='directeur', ntype='info', message=f"Commande #{cmd_id} -> {statut}", target_module='commandes', related_id=cmd_id)
                            st.success("Statut mis à jour")
                            st.rerun()
                        finally:
                            release_connection(conn)
                with col2:
                    if st.button("📄 Générer PDF commande sélectionnée"):
                        sel = st.session_state.get('last_selected_cmd', None)
                        # try to use cmd_id variable if exists
                        order_to_gen = cmd_id if 'cmd_id' in locals() else None
                        if order_to_gen:
                            pdf = generate_order_pdf(order_to_gen, doc_type="bon_de_commande", generated_by=st.session_state.user_id)
                            if pdf:
                                st.download_button("Télécharger PDF", data=pdf['bytes'], file_name=pdf['filename'])
                                st.success("Document généré et enregistré en base")
                            else:
                                st.error("Impossible de générer le document")
        else:
            st.info("Aucune commande")
    with tab2:
        if not has_access("commandes", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            clients = get_clients()
            produits = get_produits()
            if clients.empty or produits.empty:
                st.warning("⚠️ Il faut au moins 1 client et 1 produit")
            else:
                with st.form("form_commande"):
                    client_id = st.selectbox("Client *", clients['id'].tolist(), format_func=lambda x: clients[clients['id']==x]['nom'].iloc[0])
                    produit_id = st.selectbox("Produit *", produits['id'].tolist(), format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0])
                    quantite = st.number_input("Quantité *", min_value=1, step=1, value=1)
                    if st.form_submit_button("Créer"):
                        produit = produits[produits['id'] == produit_id].iloc[0]
                        if produit['stock'] >= quantite:
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("""INSERT INTO commandes (client_id, produit_id, quantite, date, statut) 
                                            VALUES (%s, %s, %s, CURRENT_DATE, 'En attente') RETURNING id""",
                                          (client_id, produit_id, quantite))
                                cmd_id = c.fetchone()[0]
                                c.execute("UPDATE produits SET stock = stock - %s WHERE id = %s", (quantite, produit_id))
                                conn.commit()
                                log_access(st.session_state.user_id, "commandes", f"Création: {cmd_id}")
                                # créer tâche préparation
                                create_workflow_task("preparation_commande", related_order_id=cmd_id, assigned_role="stock", payload={'quantite': quantite, 'produit_id': produit_id})
                                st.success(f"✅ Commande créée ! N°{cmd_id}")
                                st.rerun()
                            finally:
                                release_connection(conn)
                        else:
                            # créer tâche approvisionnement
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("""INSERT INTO commandes (client_id, produit_id, quantite, date, statut) 
                                            VALUES (%s, %s, %s, CURRENT_DATE, 'En attente appro') RETURNING id""",
                                          (client_id, produit_id, quantite))
                                cmd_id = c.fetchone()[0]
                                conn.commit()
                                create_workflow_task("approvisionnement", related_order_id=cmd_id, assigned_role="approvisionneur", payload={'quantite': quantite, 'produit_id': produit_id})
                                create_notification(target_role="approvisionneur", ntype="alert", message=f"Commande #{cmd_id} nécessite approvisionnement", target_module="achats", related_id=cmd_id)
                                st.warning(f"❌ Stock insuffisant ! Tâche d'approvisionnement créée (Commande #{cmd_id})")
                            finally:
                                release_connection(conn)

elif menu == "Gestion Achats":
    if not has_access("achats"):
        st.error("❌ Accès refusé")
        st.stop()
    log_access(st.session_state.user_id, "achats", "Consultation")
    st.header("📈 Gestion des Achats")
    tab1, tab2 = st.tabs(["Liste", "Créer"])
    with tab1:
        achats = get_achats()
        if not achats.empty:
            st.dataframe(achats, use_container_width=True, hide_index=True)
        else:
            st.info("Aucun achat")
    with tab2:
        if not has_access("achats", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            fournisseurs = get_fournisseurs()
            produits = get_produits()
            if fournisseurs.empty or produits.empty:
                st.error("❌ Veuillez d'abord ajouter des fournisseurs et des produits.")
            else:
                with st.form("form_achat"):
                    fournisseur_id = st.selectbox("Fournisseur *", fournisseurs['id'].tolist(), format_func=lambda x: fournisseurs[fournisseurs['id']==x]['nom'].iloc[0])
                    produit_id = st.selectbox("Produit *", produits['id'].tolist(), format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0])
                    quantite = st.number_input("Quantité *", min_value=1, step=1)
                    prix_unitaire = st.number_input("Prix Unitaire (DH) *", min_value=0.01, step=0.01)
                    if st.form_submit_button("Enregistrer l'Achat"):
                        if quantite > 0 and prix_unitaire > 0:
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("INSERT INTO achats (fournisseur_id, produit_id, quantite, prix_unitaire, date, statut) VALUES (%s, %s, %s, %s, CURRENT_DATE, %s)",
                                          (fournisseur_id, produit_id, quantite, prix_unitaire, "En attente"))
                                conn.commit()
                                log_access(st.session_state.user_id, "achats", f"Création Achat pour fournisseur:{fournisseur_id}")
                                st.success("✅ Achat enregistré !")
                                st.rerun()
                            finally:
                                release_connection(conn)
                        else:
                            st.error("Quantité et prix unitaire doivent être supérieurs à zéro")

elif menu == "Rapports & Exports":
    if not has_access("rapports"):
        st.error("❌ Accès refusé")
        st.stop()
    log_access(st.session_state.user_id, "rapports", "Consultation")
    st.header("📊 Rapports & Exports")
    tab1, tab2 = st.tabs(["KPIs", "Logs"])
    with tab1:
        commandes = get_commandes()
        achats = get_achats()
        st.subheader("KPIs")
        col1, col2 = st.columns(2)
        with col1:
            nb_livrees = len(commandes[commandes['statut'] == 'Livrée']) if not commandes.empty else 0
            st.metric("Commandes Livrées", nb_livrees)
        with col2:
            valeur_achats = (achats['montant_total'].sum()) if not achats.empty and 'montant_total' in achats.columns else 0
            st.metric("Valeur Achats", f"{valeur_achats:.2f} DH")
    with tab2:
        st.subheader("Logs d'accès")
        conn = get_connection()
        try:
            logs = pd.read_sql_query("""
                SELECT l.date_heure, u.username, l.module, l.action
                FROM logs_acces l
                JOIN utilisateurs u ON l.user_id = u.id
                ORDER BY l.date_heure DESC
                LIMIT 200
            """, conn)
            if not logs.empty:
                st.dataframe(logs, use_container_width=True)
            else:
                st.info("Aucun log")
        finally:
            release_connection(conn)

elif menu == "Gestion Utilisateurs":
    if not has_access("utilisateurs"):
        st.error("❌ Accès refusé")
        st.stop()
    log_access(st.session_state.user_id, "utilisateurs", "Consultation")
    st.header("👤 Gestion des Utilisateurs")
    tab1, tab2, tab3 = st.tabs(["Utilisateurs", "Permissions", "Logs"])
    with tab1:
        conn = get_connection()
        try:
            users = pd.read_sql_query("SELECT id, username, role, date_creation FROM utilisateurs ORDER BY id", conn)
            if not users.empty:
                st.dataframe(users, use_container_width=True, hide_index=True)
                st.divider()
                col1, col2 = st.columns([3,1])
                with col1:
                    selectable = users[users['role'] != 'admin']['id'].tolist()
                    if selectable:
                        user_id = st.selectbox("Supprimer", selectable, format_func=lambda x: users[users['id']==x]['username'].iloc[0])
                    else:
                        user_id = None
                with col2:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Supprimer"):
                        if user_id:
                            try:
                                c = conn.cursor()
                                c.execute("DELETE FROM utilisateurs WHERE id=%s", (user_id,))
                                conn.commit()
                                log_access(st.session_state.user_id, "utilisateurs", f"Suppression ID:{user_id}")
                                st.success("✅ Utilisateur supprimé")
                                st.rerun()
                            finally:
                                release_connection(conn)
                        else:
                            st.error("Aucun utilisateur sélectionnable")
            else:
                st.info("Aucun utilisateur")
        finally:
            try:
                release_connection(conn)
            except Exception:
                pass
    with tab2:
        st.subheader("🔑 Permissions (lecture)")
        conn = get_connection()
        try:
            users = pd.read_sql_query("SELECT id, username, role FROM utilisateurs", conn)
            if not users.empty:
                user_sel = st.selectbox("Utilisateur", users['id'].tolist(), format_func=lambda x: f"{users[users['id']==x]['username'].iloc[0]} ({users[users['id']==x]['role'].iloc[0]})")
                perms = get_user_permissions(user_sel)
                if perms:
                    perms_df = pd.DataFrame([{'Module': k, 'Lecture': v['lecture'], 'Écriture': v['ecriture']} for k,v in perms.items()])
                    st.dataframe(perms_df, use_container_width=True, hide_index=True)
                else:
                    st.info("Aucune permission configurée pour cet utilisateur")
            else:
                st.info("Aucun utilisateur")
        finally:
            release_connection(conn)
    with tab3:
        st.subheader("📊 Logs d'accès (recent)")
        conn = get_connection()
        try:
            logs = pd.read_sql_query("SELECT l.date_heure, u.username, l.module, l.action FROM logs_acces l JOIN utilisateurs u ON l.user_id = u.id ORDER BY l.date_heure DESC LIMIT 200", conn)
            if not logs.empty:
                st.dataframe(logs, use_container_width=True)
            else:
                st.info("Aucun log")
        finally:
            release_connection(conn)

elif menu == "Workflow & Tâches":
    st.header("🔁 Workflow & Tâches")
    tasks = get_tasks_for_user(st.session_state.user_id, st.session_state.role)
    st.subheader("Mes tâches")
    if not tasks.empty:
        st.dataframe(tasks[['id','task_type','related_order_id','assigned_role','assigned_user_id','status','created_at']], use_container_width=True)
        st.divider()
        st.subheader("Mettre à jour une tâche")
        t_id = st.number_input("ID tâche", min_value=1, step=1)
        new_status = st.selectbox("Nouveau statut", ["pending", "in_progress", "done", "cancelled"])
        note = st.text_input("Note (optionnel)")
        if st.button("Mettre à jour la tâche"):
            ok = update_task_status(int(t_id), new_status, by_user_id=st.session_state.user_id, note=note)
            if ok:
                st.success("✅ Tâche mise à jour")
                st.rerun()
            else:
                st.error("❌ Tâche introuvable")
    else:
        st.info("Aucune tâche assignée")

    st.markdown("---")
    st.subheader("Créer une tâche (tests/formateur)")
    with st.form("create_task_form"):
        ttype = st.text_input("Type tâche", value="test_task")
        rel_order = st.number_input("Order lié (optionnel)", min_value=0, step=1, value=0)
        arole = st.text_input("Rôle assigné (ex: stock, approvisionneur)")
        auser = st.number_input("User ID assigné (optionnel)", min_value=0, step=1, value=0)
        payload_txt = st.text_area("Payload JSON", value='{}')
        if st.form_submit_button("Créer tâche"):
            try:
                payload = json.loads(payload_txt)
            except Exception:
                payload = {}
            assigned_user = auser if auser > 0 else None
            assigned_role = arole.strip() if arole.strip() else None
            tid = create_workflow_task(ttype, related_order_id=(rel_order if rel_order>0 else None), assigned_role=assigned_role, assigned_user_id=(assigned_user if assigned_user else None), payload=payload)
            st.success(f"Tâche créée #{tid}")

elif menu == "Centre Notifications":
    st.header("🔔 Centre Notifications")
    notifs = list_notifications_for_user(st.session_state.user_id, st.session_state.role, only_unread=False, limit=200)
    if not notifs.empty:
        for _, row in notifs.iterrows():
            status = "🔵 NON LU" if not row['is_read'] else "⚪ LU"
            st.write(f"{status} — [{row['type']}] {row['message']} — {row['created_at']}")
            if not row['is_read']:
                if st.button(f"Marquer lu #{row['id']}", key=f"m_{row['id']}"):
                    mark_notification_read(row['id'])
                    st.experimental_rerun()
    else:
        st.info("Aucune notification")

elif menu == "Mode Formateur":
    if st.session_state.role != "admin" and not has_access("formateur"):
        st.error("Accès refusé")
        st.stop()
    st.header("🎓 Mode Formateur")
    st.markdown("Simulateur d'événements: livraison fournisseur / paiement client / injection d'événements.")
    produits = get_produits()
    fournisseurs = get_fournisseurs()
    with st.form("sim_delivery"):
        produit_id = st.selectbox("Produit", produits['id'].tolist(), format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0])
        qty = st.number_input("Quantité livrée", min_value=1, step=1, value=5)
        if st.form_submit_button("Simuler livraison"):
            conn = get_connection()
            try:
                c = conn.cursor()
                c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s", (qty, produit_id))
                conn.commit()
                create_notification(target_role='stock', ntype='info', message=f"Livraison simulée: +{qty} unités sur produit {produit_id}", target_module='produits', related_id=produit_id)
                log_access(st.session_state.user_id, "formateur", f"Simulated delivery product {produit_id} qty {qty}")
                st.success("✅ Livraison simulée et notification envoyée")
            finally:
                release_connection(conn)
    with st.form("sim_payment"):
        order_id = st.number_input("Commande ID", min_value=0, step=1)
        montant = st.number_input("Montant", min_value=0.0, step=0.01)
        if st.form_submit_button("Simuler paiement"):
            conn = get_connection()
            try:
                c = conn.cursor()
                c.execute("INSERT INTO emails_log (recipient, subject, body, status) VALUES (%s,%s,%s,%s)", (st.session_state.username, f"Paiement simulé commande #{order_id}", f"Montant: {montant}", "simulated"))
                conn.commit()
                create_notification(target_role='comptable', ntype='info', message=f"Paiement simulé pour commande #{order_id} montant {montant:.2f}€", target_module='comptabilite', related_id=order_id)
                st.success("✅ Paiement simulé et notifié")
            finally:
                release_connection(conn)

elif menu == "À Propos":
    st.header("ℹ️ À Propos de SYGEP")
    st.markdown("""
    SYGEP - Système pédagogique ERP.
    - Mode Multi-Utilisateurs (Postgres / Supabase)
    - Notifications en base
    - Workflow & tâches assignables par rôle
    - Génération de documents (PDF si fpdf installé)
    """)

# Footer sidebar
st.sidebar.markdown("---")
date_footer = datetime.now().strftime('%d/%m/%Y')
st.sidebar.markdown(f"""
<div style="background-color: #f8fafc; padding: 12px; border-radius: 8px; text-align:center;">
    <strong>SYGEP v3.1</strong><br>
    Session: {st.session_state.username}<br>
    {date_footer}
</div>
""", unsafe_allow_html=True)
