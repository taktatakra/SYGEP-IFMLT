import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import hashlib
from PIL import Image
import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration de la page
st.set_page_config(
    page_title="SYGEP v4.0 - Système de Gestion d'Entreprise Pédagogique",
    layout="wide",
    page_icon="🎓",
    initial_sidebar_state="expanded"
)

# ========== GESTION CONNEXION POSTGRESQL (SUPABASE) ==========

@st.cache_resource
def init_connection_pool():
    """Initialise un pool de connexions PostgreSQL"""
    try:
        # Essayer avec les variables d'environnement
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20,
            host=os.getenv('SUPABASE_HOST'),
            database=os.getenv('SUPABASE_DB', 'postgres'),
            user=os.getenv('SUPABASE_USER', 'postgres'),
            password=os.getenv('SUPABASE_PASSWORD'),
            port=os.getenv('SUPABASE_PORT', '5432')
        )
        return connection_pool
    except Exception as e:
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
            st.info("💡 Vérifiez votre fichier .env ou les secrets Streamlit Cloud")
            st.stop()

def get_connection():
    """Obtient une connexion depuis le pool"""
    pool = init_connection_pool()
    return pool.getconn()

def release_connection(conn):
    """Libère une connexion vers le pool"""
    pool = init_connection_pool()
    pool.putconn(conn)

# ========== INITIALISATION BASE DE DONNÉES ==========
def init_database():
    """Initialise les tables PostgreSQL avec workflow"""
    conn = get_connection()
    try:
        c = conn.cursor()
        
        # Table Utilisateurs
        c.execute('''CREATE TABLE IF NOT EXISTS utilisateurs
                     (id SERIAL PRIMARY KEY,
                      username VARCHAR(100) UNIQUE NOT NULL,
                      password VARCHAR(255) NOT NULL,
                      role VARCHAR(50) NOT NULL,
                      nom_complet VARCHAR(255),
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Table Permissions
        c.execute('''CREATE TABLE IF NOT EXISTS permissions
                     (id SERIAL PRIMARY KEY,
                      user_id INTEGER REFERENCES utilisateurs(id) ON DELETE CASCADE,
                      module VARCHAR(100) NOT NULL,
                      acces_lecture BOOLEAN DEFAULT FALSE,
                      acces_ecriture BOOLEAN DEFAULT FALSE)''')
        
        # Table Clients
        c.execute('''CREATE TABLE IF NOT EXISTS clients
                     (id SERIAL PRIMARY KEY,
                      nom VARCHAR(255) NOT NULL,
                      email VARCHAR(255),
                      telephone VARCHAR(50),
                      adresse TEXT,
                      date_creation DATE)''')
        
        # Table Produits
        c.execute('''CREATE TABLE IF NOT EXISTS produits
                     (id SERIAL PRIMARY KEY,
                      nom VARCHAR(255) NOT NULL,
                      reference VARCHAR(100),
                      prix DECIMAL(10,2) NOT NULL,
                      stock INTEGER NOT NULL,
                      seuil_alerte INTEGER DEFAULT 10)''')
        
        # Table Fournisseurs
        c.execute('''CREATE TABLE IF NOT EXISTS fournisseurs
                     (id SERIAL PRIMARY KEY,
                      nom VARCHAR(255) NOT NULL,
                      email VARCHAR(255),
                      telephone VARCHAR(50),
                      adresse TEXT,
                      date_creation DATE)''')
        
        # Table Commandes Workflow
        c.execute('''CREATE TABLE IF NOT EXISTS commandes_workflow
                     (id SERIAL PRIMARY KEY,
                      numero VARCHAR(50) UNIQUE,
                      client_id INTEGER REFERENCES clients(id),
                      commercial_id INTEGER REFERENCES utilisateurs(id),
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      statut VARCHAR(50) DEFAULT 'nouveau',
                      montant_total DECIMAL(10,2) DEFAULT 0,
                      notes TEXT)''')
        
        # Table Lignes de Commandes
        c.execute('''CREATE TABLE IF NOT EXISTS commandes_lignes
                     (id SERIAL PRIMARY KEY,
                      commande_id INTEGER REFERENCES commandes_workflow(id) ON DELETE CASCADE,
                      produit_id INTEGER REFERENCES produits(id),
                      quantite INTEGER,
                      prix_unitaire DECIMAL(10,2),
                      sous_total DECIMAL(10,2))''')
        
        # Table Achats Workflow
        c.execute('''CREATE TABLE IF NOT EXISTS achats_workflow
                     (id SERIAL PRIMARY KEY,
                      numero VARCHAR(50) UNIQUE,
                      fournisseur_id INTEGER REFERENCES fournisseurs(id),
                      approvisionneur_id INTEGER REFERENCES utilisateurs(id),
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      statut VARCHAR(50) DEFAULT 'demande',
                      montant_total DECIMAL(10,2) DEFAULT 0,
                      notes TEXT)''')
        
        # Table Lignes d'Achats
        c.execute('''CREATE TABLE IF NOT EXISTS achats_lignes
                     (id SERIAL PRIMARY KEY,
                      achat_id INTEGER REFERENCES achats_workflow(id) ON DELETE CASCADE,
                      produit_id INTEGER REFERENCES produits(id),
                      quantite INTEGER,
                      prix_unitaire DECIMAL(10,2),
                      sous_total DECIMAL(10,2))''')
        
        # Table Notifications
        c.execute('''CREATE TABLE IF NOT EXISTS notifications
                     (id SERIAL PRIMARY KEY,
                      user_id INTEGER REFERENCES utilisateurs(id),
                      type VARCHAR(100),
                      message TEXT,
                      reference_id INTEGER,
                      reference_type VARCHAR(50),
                      lu BOOLEAN DEFAULT FALSE,
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Table Historique Workflow
        c.execute('''CREATE TABLE IF NOT EXISTS workflow_historique
                     (id SERIAL PRIMARY KEY,
                      type VARCHAR(50),
                      reference_id INTEGER,
                      etape VARCHAR(100),
                      user_id INTEGER REFERENCES utilisateurs(id),
                      action TEXT,
                      date_action TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Table Sessions
        c.execute('''CREATE TABLE IF NOT EXISTS sessions
                     (id SERIAL PRIMARY KEY,
                      session_id VARCHAR(255) UNIQUE,
                      user_id INTEGER REFERENCES utilisateurs(id),
                      username VARCHAR(100),
                      role VARCHAR(50),
                      last_activity TIMESTAMP)''')
        
        # Table Logs
        c.execute('''CREATE TABLE IF NOT EXISTS logs_acces
                     (id SERIAL PRIMARY KEY,
                      user_id INTEGER REFERENCES utilisateurs(id),
                      module VARCHAR(100),
                      action TEXT,
                      date_heure TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        conn.commit()
        
        # Créer utilisateur admin par défaut
        c.execute("SELECT COUNT(*) FROM utilisateurs WHERE username = %s", ('admin',))
        if c.fetchone()[0] == 0:
            password_hash = hashlib.sha256("admin123".encode()).hexdigest()
            c.execute("INSERT INTO utilisateurs (username, password, role, nom_complet) VALUES (%s, %s, %s, %s) RETURNING id",
                      ('admin', password_hash, 'admin', 'Administrateur'))
            user_id = c.fetchone()[0]
            
            modules = ["tableau_bord", "workflow", "clients", "produits", "fournisseurs", 
                      "commandes", "achats", "rapports", "utilisateurs", "notifications"]
            for module in modules:
                c.execute("INSERT INTO permissions (user_id, module, acces_lecture, acces_ecriture) VALUES (%s, %s, %s, %s)",
                          (user_id, module, True, True))
            
            conn.commit()
        
        # Données de démonstration
        c.execute("SELECT COUNT(*) FROM clients")
        if c.fetchone()[0] == 0:
            c.execute("""INSERT INTO clients (nom, email, telephone, adresse, date_creation) VALUES 
                        ('Entreprise ABC SARL', 'contact@abc.ma', '0612345678', '15 Rue Hassan II, Casablanca', CURRENT_DATE),
                        ('Société XYZ', 'info@xyz.ma', '0698765432', '25 Avenue Mohammed V, Rabat', CURRENT_DATE)""")
            
            c.execute("""INSERT INTO produits (nom, reference, prix, stock, seuil_alerte) VALUES 
                        ('Ordinateur Portable HP', 'PC-HP-001', 8990.00, 15, 5),
                        ('Souris Sans Fil Logitech', 'SOU-LOG-001', 299.00, 50, 20),
                        ('Clavier Mécanique', 'CLAV-MEC-001', 799.00, 30, 10),
                        ('Écran 24 pouces Dell', 'ECR-DELL-24', 1999.00, 12, 5),
                        ('Imprimante HP LaserJet', 'IMP-HP-LJ', 3500.00, 8, 3)""")
            
            c.execute("""INSERT INTO fournisseurs (nom, email, telephone, adresse, date_creation) VALUES 
                        ('TechSupply Morocco', 'ventes@techsupply.ma', '0522334455', '50 Bd Zerktouni, Casablanca', CURRENT_DATE),
                        ('GlobalParts SARL', 'commercial@globalparts.ma', '0537556677', '12 Rue Patrice Lumumba, Rabat', CURRENT_DATE)""")
            
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
        c.execute("SELECT id, role, nom_complet FROM utilisateurs WHERE username=%s AND password=%s", 
                  (username, password_hash))
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
            permissions[row[0]] = {'lecture': bool(row[1]), 'ecriture': bool(row[2])}
        return permissions
    finally:
        release_connection(conn)

def has_access(module, access_type='lecture'):
    if st.session_state.role == "admin":
        return True
    permissions = st.session_state.get('permissions', {})
    module_perms = permissions.get(module, {'lecture': False, 'ecriture': False})
    return module_perms.get(access_type, False)

def log_access(user_id, module, action):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO logs_acces (user_id, module, action) VALUES (%s, %s, %s)",
                  (user_id, module, action))
        conn.commit()
    finally:
        release_connection(conn)

# Fonctions Notifications
def creer_notification(user_id, type_notif, message, reference_id=None, reference_type=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""INSERT INTO notifications (user_id, type, message, reference_id, reference_type)
                     VALUES (%s, %s, %s, %s, %s)""",
                  (user_id, type_notif, message, reference_id, reference_type))
        conn.commit()
    finally:
        release_connection(conn)

def get_notifications_non_lues(user_id):
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM notifications WHERE user_id=%s AND lu=FALSE ORDER BY date_creation DESC", 
                               conn, params=(user_id,))
        return df
    finally:
        release_connection(conn)

def marquer_notification_lue(notif_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE notifications SET lu=TRUE WHERE id=%s", (notif_id,))
        conn.commit()
    finally:
        release_connection(conn)

def get_count_notifications_non_lues(user_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM notifications WHERE user_id=%s AND lu=FALSE", (user_id,))
        count = c.fetchone()[0]
        return count
    finally:
        release_connection(conn)

# Fonctions Workflow
def generer_numero_commande():
    date_str = datetime.now().strftime("%Y%m%d")
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM commandes_workflow WHERE numero LIKE %s", (f"BC-{date_str}-%",))
        count = c.fetchone()[0] + 1
        return f"BC-{date_str}-{count:03d}"
    finally:
        release_connection(conn)

def generer_numero_achat():
    date_str = datetime.now().strftime("%Y%m%d")
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM achats_workflow WHERE numero LIKE %s", (f"BF-{date_str}-%",))
        count = c.fetchone()[0] + 1
        return f"BF-{date_str}-{count:03d}"
    finally:
        release_connection(conn)

def ajouter_historique_workflow(type_wf, reference_id, etape, user_id, action):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""INSERT INTO workflow_historique (type, reference_id, etape, user_id, action)
                     VALUES (%s, %s, %s, %s, %s)""",
                  (type_wf, reference_id, etape, user_id, action))
        conn.commit()
    finally:
        release_connection(conn)

# Fonctions de base
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

def get_produits_stock_faible():
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM produits WHERE stock <= seuil_alerte ORDER BY stock", conn)
        return df
    finally:
        release_connection(conn)

def save_session_to_db(user_id, username, role):
    conn = get_connection()
    try:
        c = conn.cursor()
        import time
        session_id = hashlib.sha256(f"{username}_{time.time()}".encode()).hexdigest()
        c.execute("DELETE FROM sessions WHERE last_activity < NOW() - INTERVAL '1 day'")
        c.execute("""INSERT INTO sessions (session_id, user_id, username, role, last_activity) 
                     VALUES (%s, %s, %s, %s, NOW())
                     ON CONFLICT (session_id) DO UPDATE SET last_activity = NOW()""",
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

# ========== INITIALISATION ==========
init_database()

# Gestion session
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_id = None
    st.session_state.role = None
    st.session_state.nom_complet = None
    st.session_state.permissions = {}
    st.session_state.session_id = None

# Restaurer session
if not st.session_state.logged_in:
    query_params = st.query_params
    if 'session_id' in query_params:
        session_id = query_params['session_id']
        session_data = load_session_from_db(session_id)
        if session_data:
            user_id, username, role = session_data
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.user_id = user_id
            st.session_state.role = role
            st.session_state.permissions = get_user_permissions(user_id)
            st.session_state.session_id = session_id

# ========== PAGE DE CONNEXION ==========
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col1:
        try:
            if os.path.exists("Logo_ofppt.png"):
                logo = Image.open("Logo_ofppt.png")
                st.image(logo, width=150)
        except:
            st.write("🎓")
    
    with col2:
        st.markdown("""
        <div style="text-align: center;">
            <h1 style="color: #1e3a8a;">🎓 SYGEP v4.0</h1>
            <h3 style="color: #3b82f6;">Système de Gestion d'Entreprise Pédagogique</h3>
            <p style="color: #e11d48; font-size: 16px; font-weight: bold;">
                🆕 WORKFLOW COMPLET - SIMULATION RÉALISTE
            </p>
            <p style="color: #64748b; font-size: 14px;">
                <strong>Développé par :</strong> ISMAILI ALAOUI MOHAMED<br>
                IFMLT ZENATA - OFPPT
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div style="text-align: center; padding: 10px; background-color: #f1f5f9; border-radius: 10px;">
            <p style="margin: 0; font-size: 13px;"><strong>📅 Date</strong></p>
            <p style="color: #1e40af; font-size: 16px; font-weight: bold;">
                {datetime.now().strftime('%d/%m/%Y')}
            </p>
            <p style="font-size: 12px;">{datetime.now().strftime('%H:%M:%S')}</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.title("🔐 Authentification Utilisateur")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.form("login_form"):
            username = st.text_input("Nom d'utilisateur")
            password = st.text_input("Mot de passe", type="password")
            submit = st.form_submit_button("Se connecter", use_container_width=True)
            
            if submit:
                result = verify_login(username, password)
                if result:
                    user_id, role, nom_complet = result
                    session_id = save_session_to_db(user_id, username, role)
                    
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.user_id = user_id
                    st.session_state.role = role
                    st.session_state.nom_complet = nom_complet or username
                    st.session_state.permissions = get_user_permissions(user_id)
                    st.session_state.session_id = session_id
                    
                    log_access(user_id, "connexion", "Connexion réussie")
                    st.query_params['session_id'] = session_id
                    
                    st.success("✅ Connexion réussie !")
                    st.rerun()
                else:
                    st.error("❌ Identifiants incorrects")
        
        st.info("💡 **Compte par défaut**\nUsername: admin\nPassword: admin123")
        st.success("🎓 **Version Workflow Professionnel** - Simulateur d'Entreprise Complet !")
    
    st.stop()

# ========== INTERFACE PRINCIPALE ==========
col_logo, col_titre, col_date = st.columns([1, 4, 1])

with col_logo:
    try:
        if os.path.exists("Logo_ofppt.png"):
            logo = Image.open("Logo_ofppt.png")
            st.image(logo, width=100)
    except:
        st.write("🎓")

with col_titre:
    st.markdown("""
    <div style="text-align: center;">
        <h1 style="color: #1e3a8a;">🎓 SYGEP v4.0 - Workflow Professionnel</h1>
        <p style="color: #64748b; font-size: 14px;">
            Développé par <strong>ISMAILI ALAOUI MOHAMED</strong> - IFMLT ZENATA
        </p>
    </div>
    """, unsafe_allow_html=True)

with col_date:
    date_actuelle = datetime.now()
    jour_semaine = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'][date_actuelle.weekday()]
    
    st.markdown(f"""
    <div style="text-align: center; padding: 10px; background-color: #f1f5f9; border-radius: 10px;">
        <p style="margin: 0; font-size: 12px;"><strong>📅 {jour_semaine}</strong></p>
        <p style="color: #1e40af; font-size: 18px; font-weight: bold;">
            {date_actuelle.strftime('%d/%m/%Y')}
        </p>
        <p style="font-size: 13px;">🕐 {date_actuelle.strftime('%H:%M:%S')}</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# Badge notifications
count_notifs = get_count_notifications_non_lues(st.session_state.user_id)
badge_notif = f" 🔔 ({count_notifs})" if count_notifs > 0 else ""

st.markdown(f"""
<div style="background: linear-gradient(90deg, #3b82f6 0%, #1e40af 100%); 
            padding: 15px; border-radius: 10px;">
    <h2 style="color: white; margin: 0; text-align: center;">
        👤 {st.session_state.nom_complet} ({st.session_state.role.upper()}){badge_notif}
    </h2>
</div>
""", unsafe_allow_html=True)

# Bouton déconnexion
if st.sidebar.button("🚪 Se déconnecter", use_container_width=True):
    log_access(st.session_state.user_id, "deconnexion", "Déconnexion")
    if st.session_state.session_id:
        delete_session_from_db(st.session_state.session_id)
    st.query_params.clear()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

st.sidebar.divider()

# Menu navigation
menu_items = []
if has_access("tableau_bord"):
    menu_items.append("🏠 Tableau de Bord")
if has_access("notifications"):
    notif_badge = f" ({count_notifs})" if count_notifs > 0 else ""
    menu_items.append(f"🔔 Notifications{notif_badge}")
if has_access("workflow"):
    menu_items.append("🔄 Workflow Commandes")
if has_access("clients"):
    menu_items.append("👥 Gestion Clients")
if has_access("produits"):
    menu_items.append("📦 Gestion Produits")
if has_access("fournisseurs"):
    menu_items.append("🏭 Gestion Fournisseurs")
if has_access("rapports"):
    menu_items.append("📊 Rapports")
if has_access("utilisateurs"):
    menu_items.append("👤 Utilisateurs")

menu_items.append("ℹ️ À Propos")

menu = st.sidebar.selectbox("🧭 Navigation", menu_items)

# ========== TABLEAU DE BORD ==========
if menu == "🏠 Tableau de Bord":
    if not has_access("tableau_bord"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "tableau_bord", "Consultation")
    st.header("📈 Tableau de Bord")
    
    # Alertes stock
    produits_alerte = get_produits_stock_faible()
    if not produits_alerte.empty:
        st.warning(f"⚠️ **{len(produits_alerte)} produit(s) en stock faible !**")
        with st.expander("Voir les produits"):
            st.dataframe(produits_alerte[['nom', 'reference', 'stock', 'seuil_alerte']], hide_index=True)
    
    # Métriques principales
    col1, col2, col3, col4 = st.columns(4)
    
    clients = get_clients()
    produits = get_produits()
    
    conn = get_connection()
    try:
        commandes = pd.read_sql_query("SELECT * FROM commandes_workflow", conn)
        achats = pd.read_sql_query("SELECT * FROM achats_workflow", conn)
    finally:
        release_connection(conn)
    
    with col1:
        st.metric("👥 Clients", len(clients))
    with col2:
        st.metric("📦 Produits", len(produits))
    with col3:
        st.metric("📋 Commandes", len(commandes))
    with col4:
        st.metric("🏭 Achats", len(achats))
    
    st.divider()
    
    # Notifications récentes
    st.subheader("🔔 Dernières Notifications")
    notifs = get_notifications_non_lues(st.session_state.user_id)
    if not notifs.empty:
        for _, notif in notifs.head(5).iterrows():
            with st.container():
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.info(f"**{notif['type']}** : {notif['message']}")
                with col2:
                    if st.button("✅ Lu", key=f"notif_{notif['id']}"):
                        marquer_notification_lue(notif['id'])
                        st.rerun()
    else:
        st.success("✅ Aucune notification en attente")
    
    # Graphiques
    st.divider()
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📦 Niveaux de Stock")
        if not produits.empty:
            st.bar_chart(produits.set_index('nom')['stock'])
    
    with col2:
        st.subheader("📊 Statuts Commandes")
        if not commandes.empty:
            st.bar_chart(commandes['statut'].value_counts())

# ========== CENTRE DE NOTIFICATIONS ==========
elif menu.startswith("🔔 Notifications"):
    if not has_access("notifications"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "notifications", "Consultation")
    st.header("🔔 Centre de Notifications")
    
    tab1, tab2 = st.tabs(["📬 Non Lues", "📫 Historique"])
    
    with tab1:
        notifs_non_lues = get_notifications_non_lues(st.session_state.user_id)
        
        if not notifs_non_lues.empty:
            st.info(f"Vous avez **{len(notifs_non_lues)}** notification(s) en attente")
            
            for _, notif in notifs_non_lues.iterrows():
                with st.expander(f"📩 {notif['type']} - {notif['date_creation']}", expanded=True):
                    st.write(f"**Message :** {notif['message']}")
                    
                    if notif['reference_id'] and notif['reference_type']:
                        st.write(f"**Référence :** {notif['reference_type']} #{notif['reference_id']}")
                    
                    col1, col2 = st.columns([3, 1])
                    with col2:
                        if st.button("✅ Marquer comme lu", key=f"mark_{notif['id']}"):
                            marquer_notification_lue(notif['id'])
                            st.success("✅ Notification marquée comme lue")
                            st.rerun()
        else:
            st.success("✅ Aucune notification en attente")
            st.balloons()
    
    with tab2:
        conn = get_connection()
        try:
            toutes_notifs = pd.read_sql_query("""SELECT * FROM notifications 
                                                 WHERE user_id=%s 
                                                 ORDER BY date_creation DESC 
                                                 LIMIT 50""", 
                                              conn, params=(st.session_state.user_id,))
        finally:
            release_connection(conn)
        
        if not toutes_notifs.empty:
            st.dataframe(toutes_notifs[['type', 'message', 'date_creation', 'lu']], 
                        use_container_width=True, hide_index=True)
        else:
            st.info("Aucune notification dans l'historique")

# ========== WORKFLOW COMMANDES ==========
elif menu == "🔄 Workflow Commandes":
    if not has_access("workflow"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "workflow", "Consultation")
    st.header("🔄 Workflow de la Chaîne Logistique")
    
    st.info("""
    ### 📋 Étapes du Workflow
    1. **Commercial** : Crée la commande client
    2. **Gestionnaire Stock** : Valide la disponibilité
    3. **Approvisionneur** : Commande fournisseur si besoin
    4. **Réceptionnaire** : Réceptionne marchandise
    5. **Expéditeur** : Prépare et expédie
    6. **Comptable** : Facture client
    """)
    
    # Affichage selon le rôle
    role = st.session_state.role
    
    # CRÉATION DE COMMANDE (tous les rôles peuvent créer)
    with st.expander("📝 Créer une Nouvelle Commande", expanded=True):
        clients_df = get_clients()
        produits_df = get_produits()
        
        if clients_df.empty or produits_df.empty:
            st.error("⚠️ Veuillez d'abord ajouter des clients et produits")
        else:
            with st.form("form_nouvelle_commande"):
                st.write("### 👤 Informations Client")
                
                col1, col2 = st.columns(2)
                with col1:
                    client_id = st.selectbox(
                        "Client *",
                        clients_df['id'].tolist(),
                        format_func=lambda x: clients_df[clients_df['id']==x]['nom'].iloc[0]
                    )
                
                with col2:
                    numero_commande = generer_numero_commande()
                    st.text_input("Numéro de commande", value=numero_commande, disabled=True)
                
                st.divider()
                st.write("### 📦 Produits")
                
                produit_id = st.selectbox(
                    "Produit *",
                    produits_df['id'].tolist(),
                    format_func=lambda x: f"{produits_df[produits_df['id']==x]['nom'].iloc[0]} - {produits_df[produits_df['id']==x]['prix'].iloc[0]:.2f} DH"
                )
                
                quantite = st.number_input("Quantité *", min_value=1, value=1, step=1)
                
                prix_unit = produits_df[produits_df['id']==produit_id]['prix'].iloc[0]
                sous_total = prix_unit * quantite
                
                st.metric("Sous-total", f"{sous_total:.2f} DH")
                
                st.divider()
                st.write("### 💰 Récapitulatif")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Montant HT", f"{sous_total:.2f} DH")
                with col2:
                    tva = sous_total * 0.20
                    st.metric("TVA (20%)", f"{tva:.2f} DH")
                with col3:
                    montant_ttc = sous_total + tva
                    st.metric("Montant TTC", f"{montant_ttc:.2f} DH")
                
                notes = st.text_area("Notes / Observations")
                
                submitted = st.form_submit_button("✅ Créer la Commande", type="primary", use_container_width=True)
                
                if submitted:
                    try:
                        conn = get_connection()
                        c = conn.cursor()
                        
                        # Créer la commande
                        c.execute("""INSERT INTO commandes_workflow 
                                    (numero, client_id, commercial_id, statut, montant_total, notes)
                                    VALUES (%s, %s, %s, 'nouveau', %s, %s) RETURNING id""",
                                 (numero_commande, client_id, st.session_state.user_id, montant_ttc, notes))
                        
                        commande_id = c.fetchone()[0]
                        
                        # Ajouter la ligne
                        c.execute("""INSERT INTO commandes_lignes 
                                    (commande_id, produit_id, quantite, prix_unitaire, sous_total)
                                    VALUES (%s, %s, %s, %s, %s)""",
                                 (commande_id, produit_id, quantite, prix_unit, sous_total))
                        
                        # Historique
                        ajouter_historique_workflow('commande', commande_id, 'creation', 
                                                   st.session_state.user_id, 
                                                   f"Commande {numero_commande} créée")
                        
                        # Notifier gestionnaire de stock (pour démo, on notifie l'admin)
                        c.execute("SELECT id FROM utilisateurs WHERE role = 'admin' LIMIT 1")
                        result = c.fetchone()
                        if result:
                            creer_notification(result[0], "Nouvelle Commande", 
                                             f"Commande {numero_commande} créée. Validation requise.",
                                             commande_id, "commande")
                        
                        conn.commit()
                        release_connection(conn)
                        
                        st.success(f"✅ Commande {numero_commande} créée avec succès !")
                        st.balloons()
                        
                        st.info(f"""
                        📋 **Récapitulatif de la commande**
                        - Numéro : {numero_commande}
                        - Client : {clients_df[clients_df['id']==client_id]['nom'].iloc[0]}
                        - Montant TTC : {montant_ttc:.2f} DH
                        - Statut : En attente de validation
                        
                        ➡️ La commande a été transmise pour validation.
                        """)
                        
                    except Exception as e:
                        st.error(f"❌ Erreur : {e}")
    
    st.divider()
    
    # LISTE DES COMMANDES
    st.subheader("📊 Toutes les Commandes")
    
    conn = get_connection()
    try:
        toutes_commandes = pd.read_sql_query("""
            SELECT cw.id, cw.numero, c.nom as client, cw.montant_total, 
                   cw.date_creation, cw.statut
            FROM commandes_workflow cw
            JOIN clients c ON cw.client_id = c.id
            ORDER BY cw.date_creation DESC
        """, conn)
    finally:
        release_connection(conn)
    
    if not toutes_commandes.empty:
        st.dataframe(toutes_commandes, use_container_width=True, hide_index=True)
        
        # Statistiques
        st.divider()
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Commandes", len(toutes_commandes))
        with col2:
            ca_total = toutes_commandes['montant_total'].sum()
            st.metric("CA Total", f"{ca_total:.2f} DH")
        with col3:
            panier_moyen = toutes_commandes['montant_total'].mean()
            st.metric("Panier Moyen", f"{panier_moyen:.2f} DH")
        with col4:
            nb_nouveau = len(toutes_commandes[toutes_commandes['statut']=='nouveau'])
            st.metric("En attente", nb_nouveau)
    else:
        st.info("Aucune commande enregistrée")

# ========== GESTION CLIENTS ==========
elif menu == "👥 Gestion Clients":
    if not has_access("clients"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "clients", "Consultation")
    st.header("👥 Gestion des Clients")
    
    tab1, tab2 = st.tabs(["📋 Liste", "➕ Ajouter"])
    
    with tab1:
        clients = get_clients()
        if not clients.empty:
            st.dataframe(clients, use_container_width=True, hide_index=True)
            
            if has_access("clients", "ecriture"):
                st.divider()
                col1, col2 = st.columns([3, 1])
                with col1:
                    client_id = st.selectbox("Supprimer", clients['id'].tolist(),
                                            format_func=lambda x: clients[clients['id']==x]['nom'].iloc[0])
                with col2:
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
                email = st.text_input("Email *")
                telephone = st.text_input("Téléphone")
                adresse = st.text_area("Adresse")
                
                if st.form_submit_button("Enregistrer"):
                    if nom and email:
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("""INSERT INTO clients (nom, email, telephone, adresse, date_creation) 
                                        VALUES (%s, %s, %s, %s, CURRENT_DATE)""",
                                     (nom, email, telephone, adresse))
                            conn.commit()
                            log_access(st.session_state.user_id, "clients", f"Ajout: {nom}")
                            st.success(f"✅ Client '{nom}' ajouté !")
                            st.rerun()
                        finally:
                            release_connection(conn)
                    else:
                        st.error("Nom et email requis")

# ========== GESTION PRODUITS ==========
elif menu == "📦 Gestion Produits":
    if not has_access("produits"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "produits", "Consultation")
    st.header("📦 Gestion des Produits")
    
    tab1, tab2 = st.tabs(["📋 Liste", "➕ Ajouter"])
    
    with tab1:
        produits = get_produits()
        if not produits.empty:
            produits['statut'] = produits.apply(
                lambda r: '🔴' if r['stock'] <= r['seuil_alerte'] else '🟢', axis=1)
            st.dataframe(produits, use_container_width=True, hide_index=True)
            
            if has_access("produits", "ecriture"):
                st.divider()
                st.subheader("📝 Ajuster Stock")
                col1, col2, col3 = st.columns(3)
                with col1:
                    prod_id = st.selectbox("Produit", produits['id'].tolist(),
                                          format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0])
                with col2:
                    ajust = st.number_input("Ajustement", value=0, step=1)
                with col3:
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
                reference = st.text_input("Référence *")
                prix = st.number_input("Prix (DH) *", min_value=0.0, step=0.01)
                stock = st.number_input("Stock initial", min_value=0, step=1)
                seuil = st.number_input("Seuil d'alerte", min_value=0, step=1, value=10)
                
                if st.form_submit_button("Enregistrer"):
                    if nom and reference and prix > 0:
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("""INSERT INTO produits (nom, reference, prix, stock, seuil_alerte) 
                                        VALUES (%s, %s, %s, %s, %s)""",
                                     (nom, reference, prix, stock, seuil))
                            conn.commit()
                            log_access(st.session_state.user_id, "produits", f"Ajout: {nom}")
                            st.success(f"✅ Produit '{nom}' ajouté !")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur : {e}")
                        finally:
                            release_connection(conn)
                    else:
                        st.error("Tous les champs requis")

# ========== GESTION FOURNISSEURS ==========
elif menu == "🏭 Gestion Fournisseurs":
    if not has_access("fournisseurs"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "fournisseurs", "Consultation")
    st.header("🏭 Gestion des Fournisseurs")
    
    tab1, tab2 = st.tabs(["📋 Liste", "➕ Ajouter"])
    
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
                            c.execute("""INSERT INTO fournisseurs (nom, email, telephone, adresse, date_creation) 
                                        VALUES (%s, %s, %s, %s, CURRENT_DATE)""",
                                     (nom, email, telephone, adresse))
                            conn.commit()
                            log_access(st.session_state.user_id, "fournisseurs", f"Ajout: {nom}")
                            st.success(f"✅ Fournisseur '{nom}' ajouté !")
                            st.rerun()
                        finally:
                            release_connection(conn)
                    else:
                        st.error("Nom requis")

# ========== RAPPORTS ==========
elif menu == "📊 Rapports":
    if not has_access("rapports"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "rapports", "Consultation")
    st.header("📊 Rapports & Analytics")
    
    tab1, tab2 = st.tabs(["📈 KPIs", "📜 Logs"])
    
    with tab1:
        st.subheader("📈 Indicateurs Clés")
        
        conn = get_connection()
        try:
            commandes = pd.read_sql_query("SELECT * FROM commandes_workflow", conn)
            achats = pd.read_sql_query("SELECT * FROM achats_workflow", conn)
        finally:
            release_connection(conn)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            nb_cmd_mois = len(commandes[commandes['date_creation'] >= (datetime.now() - timedelta(days=30)).isoformat()])
            st.metric("Commandes (30j)", nb_cmd_mois)
        
        with col2:
            ca_mois = commandes[commandes['date_creation'] >= (datetime.now() - timedelta(days=30)).isoformat()]['montant_total'].sum()
            st.metric("CA (30j)", f"{ca_mois:.2f} DH")
        
        with col3:
            if not commandes.empty:
                panier_moyen = commandes['montant_total'].mean()
                st.metric("Panier Moyen", f"{panier_moyen:.2f} DH")
        
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Évolution Commandes")
            if not commandes.empty:
                commandes['date'] = pd.to_datetime(commandes['date_creation'])
                evolution = commandes.groupby(commandes['date'].dt.date).size()
                st.line_chart(evolution)
        
        with col2:
            st.subheader("💰 CA par Statut")
            if not commandes.empty:
                ca_statut = commandes.groupby('statut')['montant_total'].sum()
                st.bar_chart(ca_statut)
    
    with tab2:
        st.subheader("📜 Logs d'Accès")
        
        conn = get_connection()
        try:
            logs = pd.read_sql_query("""
                SELECT l.date_heure, u.username, l.module, l.action
                FROM logs_acces l
                JOIN utilisateurs u ON l.user_id = u.id
                ORDER BY l.date_heure DESC
                LIMIT 100
            """, conn)
        finally:
            release_connection(conn)
        
        if not logs.empty:
            st.dataframe(logs, use_container_width=True, hide_index=True)
        else:
            st.info("Aucun log")

# ========== GESTION UTILISATEURS ==========
elif menu == "👤 Utilisateurs":
    if not has_access("utilisateurs"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "utilisateurs", "Consultation")
    st.header("👤 Gestion des Utilisateurs")
    
    st.subheader("📋 Liste des Utilisateurs")
    conn = get_connection()
    try:
        users = pd.read_sql_query("SELECT id, username, role, nom_complet, date_creation FROM utilisateurs ORDER BY id", conn)
        st.dataframe(users, use_container_width=True, hide_index=True)
    finally:
        release_connection(conn)

# ========== À PROPOS ==========
elif menu == "ℹ️ À Propos":
    st.header("ℹ️ À Propos de SYGEP v4.0")
    
    st.success("""
    ### 🌐 Mode Workflow Professionnel Activé !
    
    ✅ **Base de données partagée PostgreSQL (Supabase)**
    - Tous les étudiants travaillent sur les mêmes données
    - Synchronisation en temps réel
    - Aucune perte de données
    
    ✅ **Workflow complet**
    - Chaîne logistique complète
    - Notifications entre services
    - Traçabilité totale des actions
    """)
    
    st.markdown("""
    ### 🎓 Objectifs Pédagogiques
    
    - Comprendre le fonctionnement d'un ERP réel
    - Travailler en mode collaboratif
    - Gérer des rôles et permissions
    - Suivre les flux logistiques complets
    
    ### 📚 Modules Implémentés
    
    - **Tableau de Bord** : Vue synthétique KPIs
    - **Workflow** : Chaîne logistique complète
    - **CRM** : Gestion clients
    - **Inventaire** : Stocks et produits
    - **Fournisseurs** : Partenaires
    - **Rapports** : BI et analytics
    - **Administration** : Utilisateurs et sécurité
    
    ### 🔧 Technologies
    
    - **Frontend** : Streamlit (Python)
    - **Backend** : PostgreSQL via Supabase
    - **Hébergement** : Streamlit Cloud
    - **Sécurité** : SHA-256, Permissions granulaires
    
    ### 👨‍🏫 Développeur
    
    **ISMAILI ALAOUI MOHAMED**  
    Formateur en Logistique et Transport  
    IFMLT ZENATA - OFPPT
    
    ---
    
    Version 4.0 - Workflow Professionnel
    """)

# Footer sidebar
st.sidebar.markdown("---")
date_footer = datetime.now().strftime('%d/%m/%Y')
st.sidebar.markdown(f"""
<div style="background-color: #f8fafc; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0;">
    <p style="margin: 0; font-size: 11px; color: #64748b; text-align: center;">
        <strong style="color: #1e40af;">SYGEP v4.0</strong><br>
        🔄 Workflow Professionnel
    </p>
    <hr style="margin: 10px 0; border: 0; border-top: 1px solid #cbd5e1;">
    <p style="margin: 0; font-size: 10px; color: #64748b; text-align: center;">
        Développé par<br>
        <strong style="color: #1e3a8a;">ISMAILI ALAOUI MOHAMED</strong><br>
        Formateur en Logistique et Transport<br>
        <strong>IFMLT ZENATA - OFPPT</strong>
    </p>
    <hr style="margin: 10px 0; border: 0; border-top: 1px solid #cbd5e1;">
    <p style="margin: 0; font-size: 10px; color: #64748b; text-align: center;">
        📅 {date_footer}<br>
        Session: <strong>{st.session_state.username}</strong>
    </p>
</div>
""", unsafe_allow_html=True)
