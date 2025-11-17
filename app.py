"""
SYGEP - Single-file Streamlit app
Version: 2025-11-17
Author: ISMAILI ALAOUI MOHAMED (adapted)
Notes:
- Single-file refactor that includes:
  - DB pool via psycopg2
  - safe parameterized SQL (no fstrings for SQL)
  - init DB with workflow/notifications/documents tables
  - authentication + persistent sessions in DB
  - notifications center, task/workflow APIs
  - simple PDF generation using fpdf if installed (fallback to txt bytes)
  - careful try/except/finally blocks to avoid SyntaxError
- Configure DB credentials via environment variables or Streamlit secrets
  (SUPABASE_HOST, SUPABASE_DB, SUPABASE_USER, SUPABASE_PASSWORD, SUPABASE_PORT)
"""
import os
import io
import json
import time
import hashlib
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
from PIL import Image

# DB
import psycopg2
from psycopg2 import pool

# Optional: PDF generation
try:
    from fpdf import FPDF
    HAS_FPDF = True
except Exception:
    HAS_FPDF = False

# Load environment (optional .env)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Page config
st.set_page_config(page_title="SYGEP - ERP Pédagogique", layout="wide", page_icon="🎓")

# -----------------------
# DB connection pool
# -----------------------
@st.cache_resource
def init_connection_pool():
    """Create or return a psycopg2 SimpleConnectionPool"""
    # Try environment variables first
    host = os.getenv("SUPABASE_HOST")
    database = os.getenv("SUPABASE_DB", "postgres")
    user = os.getenv("SUPABASE_USER")
    password = os.getenv("SUPABASE_PASSWORD")
    port = os.getenv("SUPABASE_PORT", "5432")
    try:
        if host and user and password:
            poolobj = psycopg2.pool.SimpleConnectionPool(1, 20,
                                                        host=host,
                                                        database=database,
                                                        user=user,
                                                        password=password,
                                                        port=port)
            return poolobj
    except Exception:
        pass
    # Fallback to st.secrets (Streamlit Cloud)
    try:
        sp = st.secrets["supabase"]
        poolobj = psycopg2.pool.SimpleConnectionPool(1, 20,
                                                    host=sp.get("host"),
                                                    database=sp.get("database"),
                                                    user=sp.get("user"),
                                                    password=sp.get("password"),
                                                    port=sp.get("port"))
        return poolobj
    except Exception as e:
        st.error("Erreur: impossible d'initialiser le pool DB. Vérifiez SUPABASE_* dans env or st.secrets.")
        st.stop()

def get_connection():
    poolobj = init_connection_pool()
    return poolobj.getconn()

def release_connection(conn):
    poolobj = init_connection_pool()
    poolobj.putconn(conn)

# -----------------------
# Database initialization
# -----------------------
def init_database():
    conn = get_connection()
    try:
        c = conn.cursor()
        # Core tables
        c.execute("""
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL,
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS permissions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES utilisateurs(id) ON DELETE CASCADE,
            module VARCHAR(100) NOT NULL,
            acces_lecture BOOLEAN DEFAULT FALSE,
            acces_ecriture BOOLEAN DEFAULT FALSE
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            nom VARCHAR(255) NOT NULL,
            email VARCHAR(255),
            telephone VARCHAR(50),
            date_creation DATE
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS produits (
            id SERIAL PRIMARY KEY,
            nom VARCHAR(255) NOT NULL,
            prix NUMERIC(10,2) NOT NULL,
            stock INTEGER NOT NULL,
            seuil_alerte INTEGER DEFAULT 10
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS fournisseurs (
            id SERIAL PRIMARY KEY,
            nom VARCHAR(255) NOT NULL,
            email VARCHAR(255),
            telephone VARCHAR(50),
            adresse TEXT,
            date_creation DATE
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS commandes (
            id SERIAL PRIMARY KEY,
            client_id INTEGER REFERENCES clients(id),
            produit_id INTEGER REFERENCES produits(id),
            quantite INTEGER,
            date DATE,
            statut VARCHAR(50)
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS achats (
            id SERIAL PRIMARY KEY,
            fournisseur_id INTEGER REFERENCES fournisseurs(id),
            produit_id INTEGER REFERENCES produits(id),
            quantite INTEGER,
            prix_unitaire NUMERIC(10,2),
            date DATE,
            statut VARCHAR(50)
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(255) UNIQUE,
            user_id INTEGER REFERENCES utilisateurs(id),
            username VARCHAR(100),
            role VARCHAR(50),
            last_activity TIMESTAMP
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS logs_acces (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES utilisateurs(id),
            module VARCHAR(100),
            action TEXT,
            date_heure TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        # New tables
        c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES utilisateurs(id),
            target_role VARCHAR(50),
            type VARCHAR(50),
            message TEXT,
            target_module VARCHAR(100),
            related_id INTEGER,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS workflow_tasks (
            id SERIAL PRIMARY KEY,
            task_type VARCHAR(50),
            related_order_id INTEGER,
            assigned_role VARCHAR(50),
            assigned_user_id INTEGER REFERENCES utilisateurs(id),
            status VARCHAR(50) DEFAULT 'pending',
            payload JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            due_at TIMESTAMP
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS workflow_history (
            id SERIAL PRIMARY KEY,
            order_id INTEGER,
            previous_state VARCHAR(50),
            new_state VARCHAR(50),
            by_user_id INTEGER REFERENCES utilisateurs(id),
            note TEXT,
            timestamp TIMESTAMP DEFAULT NOW()
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            doc_type VARCHAR(50),
            related_id INTEGER,
            file_path TEXT,
            metadata JSONB,
            generated_by INTEGER REFERENCES utilisateurs(id),
            created_at TIMESTAMP DEFAULT NOW()
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS emails_log (
            id SERIAL PRIMARY KEY,
            recipient TEXT,
            subject TEXT,
            body TEXT,
            status VARCHAR(20) DEFAULT 'simulated',
            created_at TIMESTAMP DEFAULT NOW()
        )""")
        conn.commit()
        # default admin
        c.execute("SELECT id FROM utilisateurs WHERE username=%s", ("admin",))
        if c.fetchone() is None:
            pwd = hashlib.sha256("admin123".encode()).hexdigest()
            c.execute("INSERT INTO utilisateurs (username, password, role) VALUES (%s, %s, %s) RETURNING id",
                      ("admin", pwd, "admin"))
            uid = c.fetchone()[0]
            modules = ["tableau_bord","clients","produits","fournisseurs","commandes","achats","rapports","utilisateurs","workflow","notifications","documents","formateur"]
            for m in modules:
                c.execute("INSERT INTO permissions (user_id, module, acces_lecture, acces_ecriture) VALUES (%s,%s,%s,%s)",
                          (uid, m, True, True))
            conn.commit()
        # demo data: simple check
        c.execute("SELECT COUNT(*) FROM clients")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO clients (nom,email,telephone,date_creation) VALUES (%s,%s,%s,CURRENT_DATE)",
                      ("Entreprise Alpha","contact@alpha.com","0612345678"))
            c.execute("INSERT INTO produits (nom,prix,stock,seuil_alerte) VALUES (%s,%s,%s,%s)",
                      ("Ordinateur Portable", 899.99, 15, 5))
            conn.commit()
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur init DB: {e}")
    finally:
        release_connection(conn)

# Initialize DB
init_database()

# -----------------------
# Utilities: auth, sessions
# -----------------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_login(username: str, password: str):
    conn = get_connection()
    try:
        c = conn.cursor()
        pwd = hash_password(password)
        c.execute("SELECT id, role FROM utilisateurs WHERE username=%s AND password=%s", (username, pwd))
        r = c.fetchone()
        return r if r else None
    finally:
        release_connection(conn)

def save_session_to_db(user_id: int, username: str, role: str) -> str:
    conn = get_connection()
    try:
        c = conn.cursor()
        session_id = hashlib.sha256(f"{username}_{time.time()}".encode()).hexdigest()
        c.execute("DELETE FROM sessions WHERE last_activity < NOW() - INTERVAL '1 day'")
        c.execute("""INSERT INTO sessions (session_id, user_id, username, role, last_activity)
                     VALUES (%s,%s,%s,%s,NOW())""", (session_id, user_id, username, role))
        conn.commit()
        return session_id
    except Exception:
        conn.rollback()
        raise
    finally:
        release_connection(conn)

def load_session_from_db(session_id: str):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""SELECT user_id, username, role FROM sessions
                     WHERE session_id=%s AND last_activity > NOW() - INTERVAL '1 day'""", (session_id,))
        res = c.fetchone()
        if res:
            c.execute("UPDATE sessions SET last_activity=NOW() WHERE session_id=%s", (session_id,))
            conn.commit()
        return res
    finally:
        release_connection(conn)

def delete_session_from_db(session_id: str):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM sessions WHERE session_id=%s", (session_id,))
        conn.commit()
    finally:
        release_connection(conn)

def get_user_permissions(user_id: int):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT module, acces_lecture, acces_ecriture FROM permissions WHERE user_id=%s", (user_id,))
        rows = c.fetchall()
        perms = {}
        for m, lec, ecr in rows:
            perms[m] = {'lecture': bool(lec), 'ecriture': bool(ecr)}
        return perms
    finally:
        release_connection(conn)

def log_access(user_id: int, module: str, action: str):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO logs_acces (user_id, module, action) VALUES (%s,%s,%s)", (user_id, module, action))
        conn.commit()
    finally:
        release_connection(conn)

# -----------------------
# Data getters (parameterized!)
# -----------------------
def get_clients():
    conn = get_connection()
    try:
        return pd.read_sql_query("SELECT * FROM clients ORDER BY id", conn)
    finally:
        release_connection(conn)

def get_produits():
    conn = get_connection()
    try:
        return pd.read_sql_query("SELECT * FROM produits ORDER BY id", conn)
    finally:
        release_connection(conn)

def get_fournisseurs():
    conn = get_connection()
    try:
        return pd.read_sql_query("SELECT * FROM fournisseurs ORDER BY id", conn)
    finally:
        release_connection(conn)

def get_commandes():
    conn = get_connection()
    try:
        q = """
        SELECT c.id, cl.nom AS client, p.nom AS produit, c.quantite,
               (c.quantite * p.prix) AS montant, c.date, c.statut
        FROM commandes c
        JOIN clients cl ON c.client_id = cl.id
        JOIN produits p ON c.produit_id = p.id
        ORDER BY c.date DESC NULLS LAST
        """
        return pd.read_sql_query(q, conn)
    finally:
        release_connection(conn)

def get_achats():
    conn = get_connection()
    try:
        q = """
        SELECT a.id, f.nom AS fournisseur, p.nom AS produit, a.quantite,
               a.prix_unitaire, (a.quantite * a.prix_unitaire) AS montant_total, a.date, a.statut
        FROM achats a
        JOIN fournisseurs f ON a.fournisseur_id = f.id
        JOIN produits p ON a.produit_id = p.id
        ORDER BY a.date DESC NULLS LAST
        """
        return pd.read_sql_query(q, conn)
    finally:
        release_connection(conn)

def get_produits_stock_faible():
    conn = get_connection()
    try:
        return pd.read_sql_query("SELECT * FROM produits WHERE stock <= seuil_alerte ORDER BY id", conn)
    finally:
        release_connection(conn)

# -----------------------
# Notifications API
# -----------------------
def create_notification(user_id=None, target_role=None, ntype="info", message="", target_module=None, related_id=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""INSERT INTO notifications (user_id, target_role, type, message, target_module, related_id)
                     VALUES (%s,%s,%s,%s,%s,%s)""", (user_id, target_role, ntype, message, target_module, related_id))
        conn.commit()
    finally:
        release_connection(conn)

def list_notifications_for_user(user_id=None, role=None, only_unread=False, limit=50):
    conn = get_connection()
    try:
        c = conn.cursor()
        if user_id:
            if only_unread:
                c.execute("""SELECT id, user_id, target_role, type, message, target_module, related_id, is_read, created_at
                             FROM notifications
                             WHERE (user_id = %s OR target_role = %s) AND is_read = FALSE
                             ORDER BY created_at DESC LIMIT %s""", (user_id, role, limit))
            else:
                c.execute("""SELECT id, user_id, target_role, type, message, target_module, related_id, is_read, created_at
                             FROM notifications
                             WHERE (user_id = %s OR target_role = %s)
                             ORDER BY created_at DESC LIMIT %s""", (user_id, role, limit))
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

def mark_notification_read(notification_id: int):
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

# -----------------------
# Workflow tasks API
# -----------------------
def create_workflow_task(task_type, related_order_id=None, assigned_role=None, assigned_user_id=None, payload=None, due_at=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        payload_json = json.dumps(payload) if payload else None
        c.execute("""INSERT INTO workflow_tasks (task_type, related_order_id, assigned_role, assigned_user_id, status, payload, due_at)
                     VALUES (%s,%s,%s,%s,'pending',%s,%s) RETURNING id""", (task_type, related_order_id, assigned_role, assigned_user_id, payload_json, due_at))
        task_id = c.fetchone()[0]
        conn.commit()
        # create notification
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
        q = """SELECT id, task_type, related_order_id, assigned_role, assigned_user_id, status, payload, created_at, due_at
               FROM workflow_tasks WHERE (assigned_user_id = %s OR assigned_role = %s) ORDER BY created_at DESC"""
        return pd.read_sql_query(q, conn, params=(user_id, role))
    finally:
        release_connection(conn)

def update_task_status(task_id, new_status, by_user_id=None, note=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT status, related_order_id FROM workflow_tasks WHERE id=%s", (task_id,))
        r = c.fetchone()
        if not r:
            return False
        previous = r[0]
        related_order = r[1]
        c.execute("UPDATE workflow_tasks SET status=%s WHERE id=%s", (new_status, task_id))
        c.execute("INSERT INTO workflow_history (order_id, previous_state, new_state, by_user_id, note) VALUES (%s,%s,%s,%s,%s)", (related_order, previous, new_status, by_user_id, note))
        conn.commit()
        create_notification(target_role='directeur', ntype='info', message=f"Tâche {task_id} -> {new_status}", target_module='workflow', related_id=task_id)
        return True
    finally:
        release_connection(conn)

# -----------------------
# Documents: generate PDF (fpdf) or fallback bytes
# -----------------------
def generate_order_pdf(order_id, doc_type="bon_commande", generated_by=None):
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
            pdf.cell(200, 10, txt=f"{doc_type.replace('_',' ').upper()} - Commande #{order_id}", ln=1, align='C')
            pdf.ln(5)
            pdf.cell(100, 8, txt=f"Client: {client}", ln=1)
            pdf.cell(100, 8, txt=f"Produit: {produit}", ln=1)
            pdf.cell(100, 8, txt=f"Quantité: {quantite}", ln=1)
            pdf.cell(100, 8, txt=f"Prix Unitaire: {float(prix):.2f} €", ln=1)
            pdf.cell(100, 8, txt=f"Montant: {float(montant):.2f} €", ln=1)
            pdf.cell(100, 8, txt=f"Statut: {statut}", ln=1)
            buf = io.BytesIO()
            pdf.output(buf)
            buf.seek(0)
            c.execute("INSERT INTO documents (doc_type, related_id, file_path, metadata, generated_by) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                      (doc_type, order_id, filename, json.dumps({"generated_at": timestamp}), generated_by))
            doc_id = c.fetchone()[0]
            conn.commit()
            return {'doc_id': doc_id, 'filename': filename, 'bytes': buf.read()}
        else:
            content = f"{doc_type.upper()} - Commande #{order_id}\nClient: {client}\nProduit: {produit}\nQuantité: {quantite}\nPrix Unitaire: {float(prix):.2f} €\nMontant: {float(montant):.2f} €\nStatut: {statut}\n"
            buf = io.BytesIO(content.encode("utf-8"))
            c.execute("INSERT INTO documents (doc_type, related_id, file_path, metadata, generated_by) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                      (doc_type, order_id, filename, json.dumps({"generated_at": timestamp, "fallback": True}), generated_by))
            doc_id = c.fetchone()[0]
            conn.commit()
            return {'doc_id': doc_id, 'filename': filename, 'bytes': buf.read()}
    finally:
        release_connection(conn)

# -----------------------
# Streamlit UI: session state defaults
# -----------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_id = None
    st.session_state.role = None
    st.session_state.permissions = {}
    st.session_state.session_id = None
    st.session_state.auto_refresh = True

# Restore session via query param
if not st.session_state.logged_in:
    q = st.experimental_get_query_params()
    if "session_id" in q:
        sid = q["session_id"][0]
        sdata = load_session_from_db(sid)
        if sdata:
            uid, uname, role = sdata
            st.session_state.logged_in = True
            st.session_state.user_id = uid
            st.session_state.username = uname
            st.session_state.role = role
            st.session_state.permissions = get_user_permissions(uid)
            st.session_state.session_id = sid

# -----------------------
# Login page
# -----------------------
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 3, 1])
    with col1:
        try:
            if os.path.exists("Logo_ofppt.png"):
                logo = Image.open("Logo_ofppt.png")
                st.image(logo, width=140)
        except Exception:
            pass
    with col2:
        st.markdown("<h1 style='text-align:center;color:#1e3a8a;'>🎓 SYGEP</h1>", unsafe_allow_html=True)
        with st.form("login"):
            username = st.text_input("Nom d'utilisateur")
            password = st.text_input("Mot de passe", type="password")
            submitted = st.form_submit_button("Se connecter")
            if submitted:
                user = verify_login(username, password)
                if user:
                    uid, role = user
                    sid = save_session_to_db(uid, username, role)
                    st.session_state.logged_in = True
                    st.session_state.user_id = uid
                    st.session_state.username = username
                    st.session_state.role = role
                    st.session_state.permissions = get_user_permissions(uid)
                    st.session_state.session_id = sid
                    log_access(uid, "connexion", "Connexion réussie")
                    # set query param for persistence
                    st.experimental_set_query_params(session_id=sid)
                    st.success("Connexion réussie")
                    st.experimental_rerun()
                else:
                    st.error("Identifiants incorrects")
        st.info("Compte par défaut: admin / admin123")
    with col3:
        st.markdown(f"<div style='text-align:center;padding:8px;background:#f1f5f9;border-radius:8px;'><strong>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</strong></div>", unsafe_allow_html=True)
    st.stop()

# -----------------------
# Main UI
# -----------------------
# Header
col_logo, col_title, col_clock = st.columns([1, 6, 1])
with col_logo:
    try:
        if os.path.exists("Logo_ofppt.png"):
            st.image(Image.open("Logo_ofppt.png"), width=90)
    except Exception:
        pass
with col_title:
    st.markdown(f"<h2 style='text-align:center;color:#1e3a8a;'>🎓 SYGEP - Connecté : {st.session_state.username} ({st.session_state.role})</h2>", unsafe_allow_html=True)
with col_clock:
    st.markdown(f"<div style='text-align:center'>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</div>", unsafe_allow_html=True)

st.markdown("---")

# Sidebar controls
if st.sidebar.button("Se déconnecter"):
    log_access(st.session_state.user_id, "deconnexion", "Déconnexion")
    if st.session_state.session_id:
        delete_session_from_db(st.session_state.session_id)
    # clear session state
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.experimental_rerun()

st.sidebar.markdown("### Options")
st.session_state.auto_refresh = st.sidebar.checkbox("Auto-refresh 6s", value=st.session_state.auto_refresh)
if st.session_state.auto_refresh:
    st.markdown('<meta http-equiv="refresh" content="6">', unsafe_allow_html=True)

# Show permission summary
if st.session_state.role != "admin":
    with st.sidebar.expander("Mes Permissions"):
        for m, p in st.session_state.permissions.items():
            lec = "📖" if p.get("lecture") else ""
            ecr = "✏️" if p.get("ecriture") else ""
            st.write(f"- {m}: {lec} {ecr}")

# Notification badge
unread_count = count_unread_notifications(st.session_state.user_id, st.session_state.role)
st.sidebar.markdown(f"### 🔔 Notifications ({unread_count})")

# Build menu
menu = []
if st.session_state.role == "admin" or st.session_state.permissions.get("tableau_bord", {}).get("lecture"):
    menu.append("Tableau de Bord")
if st.session_state.role == "admin" or st.session_state.permissions.get("clients", {}).get("lecture"):
    menu.append("Clients")
if st.session_state.role == "admin" or st.session_state.permissions.get("produits", {}).get("lecture"):
    menu.append("Produits")
if st.session_state.role == "admin" or st.session_state.permissions.get("commandes", {}).get("lecture"):
    menu.append("Commandes")
menu.append("Workflow & Tâches")
menu.append("Notifications")
if st.session_state.role == "admin" or st.session_state.permissions.get("formateur", {}).get("lecture"):
    menu.append("Mode Formateur")
menu.append("À propos")

choice = st.sidebar.selectbox("Navigation", menu)

# ---------------
# Pages
# ---------------
if choice == "Tableau de Bord":
    log_access(st.session_state.user_id, "tableau_bord", "Consultation")
    st.header("Tableau de Bord")
    produits = get_produits()
    clients = get_clients()
    commandes = get_commandes()
    col1, col2, col3 = st.columns(3)
    col1.metric("Clients", len(clients))
    col2.metric("Produits", len(produits))
    ca = commandes['montant'].sum() if not commandes.empty else 0.0
    col3.metric("CA", f"{ca:.2f} €")
    st.subheader("Niveau de stock")
    if not produits.empty:
        st.bar_chart(produits.set_index("nom")["stock"])
    low = get_produits_stock_faible()
    if not low.empty:
        st.warning(f"{len(low)} produit(s) en stock faible")

elif choice == "Clients":
    st.header("Gestion Clients")
    if not (st.session_state.role == "admin" or st.session_state.permissions.get("clients", {}).get("lecture")):
        st.error("Accès refusé")
        st.stop()
    tabs = st.tabs(["Liste", "Ajouter"])
    with tabs[0]:
        df = get_clients()
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            if st.session_state.role == "admin" or st.session_state.permissions.get("clients", {}).get("ecriture"):
                st.markdown("---")
                to_del = st.selectbox("Supprimer client", df["id"].tolist(), format_func=lambda x: df[df["id"]==x]["nom"].iloc[0])
                if st.button("Supprimer"):
                    conn = get_connection()
                    try:
                        c = conn.cursor()
                        c.execute("DELETE FROM clients WHERE id=%s", (to_del,))
                        conn.commit()
                        log_access(st.session_state.user_id, "clients", f"Suppression {to_del}")
                        st.success("Client supprimé")
                        st.experimental_rerun()
                    finally:
                        release_connection(conn)
        else:
            st.info("Aucun client")
    with tabs[1]:
        if not (st.session_state.role == "admin" or st.session_state.permissions.get("clients", {}).get("ecriture")):
            st.warning("Pas de droits d'écriture")
        else:
            with st.form("add_client"):
                nom = st.text_input("Nom")
                email = st.text_input("Email")
                tel = st.text_input("Téléphone")
                if st.form_submit_button("Ajouter"):
                    if not nom or not email:
                        st.error("Nom et email requis")
                    else:
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("INSERT INTO clients (nom,email,telephone,date_creation) VALUES (%s,%s,%s,CURRENT_DATE)", (nom,email,tel))
                            conn.commit()
                            log_access(st.session_state.user_id, "clients", f"Ajout {nom}")
                            st.success("Client ajouté")
                            st.experimental_rerun()
                        finally:
                            release_connection(conn)

elif choice == "Produits":
    st.header("Gestion Produits")
    if not (st.session_state.role == "admin" or st.session_state.permissions.get("produits", {}).get("lecture")):
        st.error("Accès refusé")
        st.stop()
    tabs = st.tabs(["Liste", "Ajouter"])
    with tabs[0]:
        df = get_produits()
        if not df.empty:
            df["statut"] = df.apply(lambda r: "🔴" if r["stock"] <= r["seuil_alerte"] else "🟢", axis=1)
            st.dataframe(df, use_container_width=True)
            if st.session_state.role == "admin" or st.session_state.permissions.get("produits", {}).get("ecriture"):
                st.markdown("---")
                prod = st.selectbox("Produit", df["id"].tolist(), format_func=lambda x: df[df["id"]==x]["nom"].iloc[0])
                ajust = st.number_input("Ajustement stock (+/-)", value=0, step=1)
                if st.button("Appliquer ajustement"):
                    conn = get_connection()
                    try:
                        c = conn.cursor()
                        c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s", (ajust, prod))
                        conn.commit()
                        log_access(st.session_state.user_id, "produits", f"Ajustement {prod} {ajust}")
                        st.success("Stock mis à jour")
                        st.experimental_rerun()
                    finally:
                        release_connection(conn)
        else:
            st.info("Aucun produit")
    with tabs[1]:
        if not (st.session_state.role == "admin" or st.session_state.permissions.get("produits", {}).get("ecriture")):
            st.warning("Pas de droits d'écriture")
        else:
            with st.form("add_prod"):
                nom = st.text_input("Nom")
                prix = st.number_input("Prix (€)", min_value=0.0, step=0.01)
                stock = st.number_input("Stock initial", min_value=0, step=1)
                seuil = st.number_input("Seuil d'alerte", min_value=0, step=1, value=10)
                if st.form_submit_button("Ajouter"):
                    if not nom or prix <= 0:
                        st.error("Nom et prix > 0 requis")
                    else:
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("INSERT INTO produits (nom,prix,stock,seuil_alerte) VALUES (%s,%s,%s,%s)", (nom, prix, stock, seuil))
                            conn.commit()
                            log_access(st.session_state.user_id, "produits", f"Ajout {nom}")
                            st.success("Produit ajouté")
                            st.experimental_rerun()
                        finally:
                            release_connection(conn)

elif choice == "Commandes":
    st.header("Gestion Commandes")
    if not (st.session_state.role == "admin" or st.session_state.permissions.get("commandes", {}).get("lecture")):
        st.error("Accès refusé")
        st.stop()
    tabs = st.tabs(["Liste", "Créer"])
    with tabs[0]:
        df = get_commandes()
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            if st.session_state.role == "admin" or st.session_state.permissions.get("commandes", {}).get("ecriture"):
                st.markdown("---")
                cmd = st.selectbox("Commande", df["id"].tolist())
                statut = st.selectbox("Statut", ["En attente","Validée","En préparation","Expédiée","Livrée","Annulée","En attente appro"])
                if st.button("Mettre à jour statut"):
                    conn = get_connection()
                    try:
                        c = conn.cursor()
                        c.execute("UPDATE commandes SET statut=%s WHERE id=%s", (statut, cmd))
                        conn.commit()
                        log_access(st.session_state.user_id, "commandes", f"MAJ statut {cmd} -> {statut}")
                        create_notification(target_role='directeur', ntype='info', message=f"Commande #{cmd} -> {statut}", target_module='commandes', related_id=cmd)
                        st.success("Statut mis à jour")
                        st.experimental_rerun()
                    finally:
                        release_connection(conn)
        else:
            st.info("Aucune commande")
    with tabs[1]:
        if not (st.session_state.role == "admin" or st.session_state.permissions.get("commandes", {}).get("ecriture")):
            st.warning("Pas de droits d'écriture")
        else:
            clients = get_clients()
            produits = get_produits()
            if clients.empty or produits.empty:
                st.warning("Besoin d'au moins 1 client et 1 produit")
            else:
                with st.form("create_cmd"):
                    client_id = st.selectbox("Client", clients["id"].tolist(), format_func=lambda x: clients[clients["id"]==x]["nom"].iloc[0])
                    produit_id = st.selectbox("Produit", produits["id"].tolist(), format_func=lambda x: f"{produits[produits['id']==x]['nom'].iloc[0]} - {produits[produits['id']==x]['prix'].iloc[0]:.2f} €")
                    quantite = st.number_input("Quantité", min_value=1, step=1, value=1)
                    if st.form_submit_button("Créer commande"):
                        prod_row = produits[produits["id"] == produit_id].iloc[0]
                        if prod_row["stock"] >= quantite:
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("INSERT INTO commandes (client_id, produit_id, quantite, date, statut) VALUES (%s,%s,%s,CURRENT_DATE,%s) RETURNING id", (client_id, produit_id, quantite, "En attente"))
                                new_id = c.fetchone()[0]
                                c.execute("UPDATE produits SET stock = stock - %s WHERE id = %s", (quantite, produit_id))
                                conn.commit()
                                create_workflow_task("preparation_commande", related_order_id=new_id, assigned_role="stock", payload={"quantite": quantite, "produit_id": produit_id})
                                log_access(st.session_state.user_id, "commandes", f"Création commande {new_id}")
                                st.success(f"Commande créée #{new_id}")
                                st.experimental_rerun()
                            finally:
                                release_connection(conn)
                        else:
                            # create approvisionnement task
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("INSERT INTO commandes (client_id, produit_id, quantite, date, statut) VALUES (%s,%s,%s,CURRENT_DATE,%s) RETURNING id", (client_id, produit_id, quantite, "En attente appro"))
                                new_id = c.fetchone()[0]
                                conn.commit()
                                create_workflow_task("approvisionnement", related_order_id=new_id, assigned_role="approvisionneur", payload={"quantite": quantite, "produit_id": produit_id})
                                create_notification(target_role="approvisionneur", ntype="alert", message=f"Commande #{new_id} demande approvisionnement", target_module="achats", related_id=new_id)
                                st.warning(f"Stock insuffisant. Approvisionnement demandé (commande #{new_id})")
                            finally:
                                release_connection(conn)

elif choice == "Workflow & Tâches":
    st.header("Workflow & Tâches")
    tasks = get_tasks_for_user(st.session_state.user_id, st.session_state.role)
    st.subheader("Mes tâches")
    if not tasks.empty:
        st.dataframe(tasks[["id","task_type","related_order_id","assigned_role","assigned_user_id","status","created_at"]], use_container_width=True)
        st.markdown("---")
        tid = st.number_input("ID tâche", min_value=1, step=1)
        new_status = st.selectbox("Nouveau statut", ["pending","in_progress","done","cancelled"])
        note = st.text_input("Note")
        if st.button("Mettre à jour tâche"):
            ok = update_task_status(int(tid), new_status, by_user_id=st.session_state.user_id, note=note)
            if ok:
                st.success("Tâche mise à jour")
                st.experimental_rerun()
            else:
                st.error("Tâche introuvable")
    else:
        st.info("Aucune tâche assignée")
    st.markdown("---")
    st.subheader("Créer une tâche manuelle")
    with st.form("create_task"):
        ttype = st.text_input("Type", value="test_task")
        rel_order = st.number_input("Order lié (0 = none)", min_value=0, step=1, value=0)
        arole = st.text_input("Rôle assigné")
        auser = st.number_input("User ID assigné (0 = none)", min_value=0, step=1, value=0)
        payload_txt = st.text_area("Payload JSON", value="{}")
        if st.form_submit_button("Créer tâche"):
            try:
                payload = json.loads(payload_txt)
            except Exception:
                payload = {}
            assigned_user = auser if auser > 0 else None
            assigned_role = arole.strip() if arole.strip() else None
            tid = create_workflow_task(ttype, related_order_id=(rel_order if rel_order>0 else None), assigned_role=assigned_role, assigned_user_id=(assigned_user if assigned_user else None), payload=payload)
            st.success(f"Tâche créée #{tid}")

elif choice == "Notifications":
    st.header("Centre Notifications")
    df = list_notifications_for_user(st.session_state.user_id, st.session_state.role, only_unread=False, limit=200)
    if not df.empty:
        for _, row in df.iterrows():
            status = "NON LU" if not row["is_read"] else "LU"
            st.write(f"[{status}] {row['type']} - {row['message']} ({row['created_at']})")
            if not row["is_read"]:
                if st.button(f"Marquer lu #{row['id']}", key=f"mr{row['id']}"):
                    mark_notification_read(row["id"])
                    st.experimental_rerun()
    else:
        st.info("Aucune notification")

elif choice == "Mode Formateur":
    st.header("Mode Formateur (Simulateur)")
    if not (st.session_state.role == "admin" or st.session_state.permissions.get("formateur", {}).get("lecture")):
        st.error("Accès refusé")
        st.stop()
    fournisseurs = get_fournisseurs()
    produits = get_produits()
    with st.form("simulate_delivery"):
        prod = st.selectbox("Produit", produits["id"].tolist(), format_func=lambda x: produits[produits["id"]==x]["nom"].iloc[0])
        qty = st.number_input("Quantité livrée", min_value=1, step=1, value=5)
        if st.form_submit_button("Simuler livraison"):
            conn = get_connection()
            try:
                c = conn.cursor()
                c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s", (qty, prod))
                conn.commit()
                create_notification(target_role="stock", ntype="info", message=f"Livraison simulée: +{qty} unités produit {prod}", target_module="produits", related_id=prod)
                log_access(st.session_state.user_id, "formateur", f"Simulated delivery prod {prod} qty {qty}")
                st.success("Livraison simulée et notification envoyée")
            finally:
                release_connection(conn)
    with st.form("simulate_payment"):
        order = st.number_input("Commande ID", min_value=0, step=1)
        amount = st.number_input("Montant", min_value=0.0, step=0.01)
        if st.form_submit_button("Simuler paiement"):
            conn = get_connection()
            try:
                c = conn.cursor()
                c.execute("INSERT INTO emails_log (recipient, subject, body, status) VALUES (%s,%s,%s,%s)", (st.session_state.username, f"Payment simulated order {order}", f"Payment {amount}", "simulated"))
                conn.commit()
                create_notification(target_role="comptable", ntype="info", message=f"Paiement simulé commande #{order} {amount:.2f}€", target_module="comptabilite", related_id=order)
                st.success("Paiement simulé")
            finally:
                release_connection(conn)

elif choice == "À propos":
    st.header("À propos")
    st.markdown("""
    SYGEP - Version single-file refactor
    - Mode multi-utilisateurs (base partagée Supabase/Postgres)
    - Workflow, notifications, documents (PDF)
    - Mode Formateur pour simuler événements
    """)

# Footer summary
st.sidebar.markdown("---")
st.sidebar.write(f"User: {st.session_state.username}")
st.sidebar.write(f"Role: {st.session_state.role}")
st.sidebar.write(f"Session: {st.session_state.session_id[:8]+'...' if st.session_state.session_id else '—'}")
