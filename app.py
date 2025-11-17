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
        
        # Table Commandes Clients (WORKFLOW COMPLET)
        c.execute('''CREATE TABLE IF NOT EXISTS commandes_clients
                     (id SERIAL PRIMARY KEY,
                      numero VARCHAR(50) UNIQUE,
                      client_id INTEGER REFERENCES clients(id),
                      produit_id INTEGER REFERENCES produits(id),
                      quantite INTEGER,
                      prix_unitaire DECIMAL(10,2),
                      montant_total DECIMAL(10,2),
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      statut VARCHAR(50) DEFAULT 'Nouveau',
                      commercial_id INTEGER REFERENCES utilisateurs(id),
                      gestionnaire_id INTEGER,
                      expediteur_id INTEGER,
                      comptable_id INTEGER,
                      date_validation_stock TIMESTAMP,
                      date_expedition TIMESTAMP,
                      date_facturation TIMESTAMP,
                      notes TEXT)''')
        
        # Table Commandes Fournisseurs (WORKFLOW APPRO)
        c.execute('''CREATE TABLE IF NOT EXISTS commandes_fournisseurs
                     (id SERIAL PRIMARY KEY,
                      numero VARCHAR(50) UNIQUE,
                      fournisseur_id INTEGER REFERENCES fournisseurs(id),
                      produit_id INTEGER REFERENCES produits(id),
                      quantite INTEGER,
                      prix_unitaire DECIMAL(10,2),
                      montant_total DECIMAL(10,2),
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      statut VARCHAR(50) DEFAULT 'En attente',
                      approvisionneur_id INTEGER REFERENCES utilisateurs(id),
                      receptionnaire_id INTEGER,
                      date_reception TIMESTAMP,
                      quantite_recue INTEGER,
                      notes TEXT)''')
        
        # Table Notifications
        c.execute('''CREATE TABLE IF NOT EXISTS notifications
                     (id SERIAL PRIMARY KEY,
                      user_id INTEGER REFERENCES utilisateurs(id),
                      titre VARCHAR(255),
                      message TEXT,
                      type VARCHAR(50),
                      commande_id INTEGER,
                      lue BOOLEAN DEFAULT FALSE,
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Table Documents (Bons, Factures)
        c.execute('''CREATE TABLE IF NOT EXISTS documents
                     (id SERIAL PRIMARY KEY,
                      type_doc VARCHAR(50),
                      numero VARCHAR(50),
                      commande_id INTEGER,
                      contenu TEXT,
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      cree_par INTEGER REFERENCES utilisateurs(id))''')
        
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
                      ('admin', password_hash, 'admin', 'Administrateur Système'))
            user_id = c.fetchone()[0]
            
            modules = ["tableau_bord", "clients", "produits", "fournisseurs", "commandes", "achats", 
                       "rapports", "utilisateurs", "workflow", "notifications", "formateur"]
            for module in modules:
                c.execute("INSERT INTO permissions (user_id, module, acces_lecture, acces_ecriture) VALUES (%s, %s, %s, %s)",
                          (user_id, module, True, True))
            
            conn.commit()
        
        # Données de démonstration (laisser pour l'initialisation)
        c.execute("SELECT COUNT(*) FROM clients")
        if c.fetchone()[0] == 0:
            # Clients
            c.execute("""INSERT INTO clients (nom, email, telephone, adresse, date_creation) VALUES 
                        ('Entreprise ABC SARL', 'contact@abc-sarl.ma', '0522334455', '123 Bd Hassan II, Casablanca', CURRENT_DATE),
                        ('Société XYZ Trading', 'info@xyz-trading.ma', '0612345678', '456 Av Mohammed V, Rabat', CURRENT_DATE),
                        ('LOGIMAR Logistics', 'achats@logimar.ma', '0698765432', '789 Zone Industrielle, Tanger', CURRENT_DATE)""")
            
            # Produits
            c.execute("""INSERT INTO produits (nom, reference, prix, stock, seuil_alerte) VALUES 
                        ('Ordinateur Portable HP ProBook', 'HP-PB-450', 899.99, 15, 5),
                        ('Imprimante Laser Canon', 'CAN-LBP-6030', 249.99, 8, 3),
                        ('Souris Sans Fil Logitech', 'LOG-M185', 29.99, 50, 20),
                        ('Clavier Mécanique Corsair', 'COR-K70', 129.99, 12, 5),
                        ('Écran Dell 24 pouces', 'DELL-P2422H', 199.99, 6, 3)""")
            
            # Fournisseurs
            c.execute("""INSERT INTO fournisseurs (nom, email, telephone, adresse, date_creation) VALUES 
                        ('TechSupply Maroc', 'ventes@techsupply.ma', '0522111222', 'Casablanca Technopark', CURRENT_DATE),
                        ('GlobalParts SARL', 'contact@globalparts.ma', '0537334455', 'Rabat Technopolis', CURRENT_DATE),
                        ('Digital Distributors', 'info@digitaldist.ma', '0539887766', 'Tanger Free Zone', CURRENT_DATE)""")
            
            conn.commit()
            
    except Exception as e:
        st.error(f"Erreur initialisation BDD: {e}")
        conn.rollback()
    finally:
        release_connection(conn)

# ========== FONCTIONS WORKFLOW ET UTILITAIRES ==========

def get_user_ids_by_role(role_list):
    """Récupère les IDs des utilisateurs ayant un des rôles spécifiés"""
    conn = get_connection()
    try:
        # Convertir une chaîne simple en liste pour la requête SQL si nécessaire
        if isinstance(role_list, str):
            role_list = [role_list]
            
        # Utiliser UNNEST pour décomposer le tableau de rôles dans la clause IN
        query = "SELECT id FROM utilisateurs WHERE role = ANY(%s)"
        df = pd.read_sql_query(query, conn, params=(role_list,))
        return df['id'].tolist()
    finally:
        release_connection(conn)

def creer_notification(user_id, titre, message, type_notif, commande_id=None):
    """Crée une notification pour un utilisateur"""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""INSERT INTO notifications (user_id, titre, message, type, commande_id) 
                    VALUES (%s, %s, %s, %s, %s)""",
                  (user_id, titre, message, type_notif, commande_id))
        conn.commit()
    finally:
        release_connection(conn)

def get_notifications_non_lues(user_id):
    """Récupère les notifications non lues d'un utilisateur"""
    conn = get_connection()
    try:
        query = """SELECT id, titre, message, type, commande_id, date_creation 
                   FROM notifications 
                   WHERE user_id = %s AND lue = FALSE 
                   ORDER BY date_creation DESC"""
        df = pd.read_sql_query(query, conn, params=(user_id,))
        return df
    finally:
        release_connection(conn)

def marquer_notification_lue(notif_id):
    """Marque une notification comme lue"""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE notifications SET lue = TRUE WHERE id = %s", (notif_id,))
        conn.commit()
    finally:
        release_connection(conn)

def generer_numero_commande(type_doc='BC'):
    """Génère un numéro de commande unique (BC-CLI-AAAA/MM/HHMMSS ou BC-FOUR-AAAA/MM/HHMMSS)"""
    now = datetime.now()
    # Ajout d'une partie de l'heure pour garantir l'unicité
    return f"{type_doc.upper()}-{now.year}{now.month:02d}-{now.strftime('%H%M%S')}"

def generer_document_client(cmd_id, type_doc):
    """Génère le contenu HTML/Markdown pour la simulation de document client (BC, BL, Facture)"""
    conn = get_connection()
    try:
        query = """
        SELECT cc.numero, c.nom as client_nom, c.adresse as client_adresse,
               p.nom as produit_nom, cc.quantite, cc.prix_unitaire, cc.montant_total,
               u.nom_complet as createur_nom, cc.date_creation
        FROM commandes_clients cc
        JOIN clients c ON cc.client_id = c.id
        JOIN produits p ON cc.produit_id = p.id
        JOIN utilisateurs u ON cc.commercial_id = u.id
        WHERE cc.id = %s
        """
        df = pd.read_sql_query(query, conn, params=(cmd_id,))
        if df.empty:
            return "Document non trouvé."

        data = df.iloc[0]
        
        # HTML Content Simulation
        html_content = f"""
        <div style="border: 2px solid #3b82f6; padding: 20px; border-radius: 10px; font-family: sans-serif;">
            <h2 style="color: #1e3a8a; text-align: center;">{type_doc.upper()} - N° {data['numero']}</h2>
            <p><strong>Entreprise :</strong> SYGEP Logistics</p>
            <p><strong>Date :</strong> {datetime.now().strftime('%d/%m/%Y')}</p>
            <hr>
            <h3>Informations Client</h3>
            <p><strong>Client :</strong> {data['client_nom']}</p>
            <p><strong>Adresse :</strong> {data['client_adresse']}</p>
            <hr>
            <h3>Détails</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background-color: #f1f5f9;">
                        <th style="border: 1px solid #e2e8f0; padding: 8px;">Produit</th>
                        <th style="border: 1px solid #e2e8f0; padding: 8px;">Qté</th>
                        <th style="border: 1px solid #e2e8f0; padding: 8px;">Prix Unitaire</th>
                        <th style="border: 1px solid #e2e8f0; padding: 8px;">Total</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td style="border: 1px solid #e2e8f0; padding: 8px;">{data['produit_nom']}</td>
                        <td style="border: 1px solid #e2e8f0; padding: 8px; text-align: center;">{data['quantite']}</td>
                        <td style="border: 1px solid #e2e8f0; padding: 8px; text-align: right;">{data['prix_unitaire']:.2f} €</td>
                        <td style="border: 1px solid #e2e8f0; padding: 8px; text-align: right;">{data['montant_total']:.2f} €</td>
                    </tr>
                </tbody>
            </table>
            <h3 style="text-align: right; color: #d97706;">TOTAL : {data['montant_total']:.2f} €</h3>
            <hr>
            <p style="font-size: 12px; text-align: center;">Document généré par {data['createur_nom']} le {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}.</p>
        </div>
        """
        return html_content
    finally:
        release_connection(conn)

def creer_document(cmd_id, type_doc, contenu, createur_id, numero_doc=None):
    """Enregistre le document (simulation de PDF) dans la BDD"""
    conn = get_connection()
    try:
        c = conn.cursor()
        if not numero_doc:
             numero_doc = generer_numero_commande(type_doc.replace(" ", "-").upper())
        c.execute("""INSERT INTO documents (type_doc, numero, commande_id, contenu, cree_par) 
                    VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                  (type_doc, numero_doc, cmd_id, contenu, createur_id))
        conn.commit()
        return numero_doc
    finally:
        release_connection(conn)

# Fonctions CRUD génériques (simplifiées)
@st.cache_data(ttl=5) # Cache court pour le temps réel
def fetch_data(table, columns='*', where_clause='', params=()):
    conn = get_connection()
    try:
        query = f"SELECT {columns} FROM {table} {where_clause}"
        df = pd.read_sql_query(query, conn, params=params)
        return df
    finally:
        release_connection(conn)

def get_commandes_en_attente_validation():
    """Récupère les commandes en attente de validation stock"""
    return fetch_data("""commandes_clients cc JOIN clients c ON cc.client_id = c.id JOIN produits p ON cc.produit_id = p.id""", 
                      columns="cc.id, cc.numero, c.nom as client, p.nom as produit, cc.quantite, cc.montant_total, cc.date_creation, cc.statut, cc.produit_id",
                      where_clause="WHERE cc.statut IN ('Nouveau', 'En attente validation') ORDER BY cc.date_creation DESC")

def get_commandes_a_preparer():
    """Récupère les commandes validées à préparer (Expéditeur)"""
    return fetch_data("""commandes_clients cc JOIN clients c ON cc.client_id = c.id JOIN produits p ON cc.produit_id = p.id""", 
                      columns="cc.id, cc.numero, c.nom as client, p.nom as produit, cc.quantite, cc.montant_total, cc.statut",
                      where_clause="WHERE cc.statut = 'Validée - Stock OK' ORDER BY cc.date_creation DESC")

def get_commandes_a_expedier():
    """Récupère les commandes à expédier (Expéditeur)"""
    return fetch_data("""commandes_clients cc JOIN clients c ON cc.client_id = c.id JOIN produits p ON cc.produit_id = p.id""", 
                      columns="cc.id, cc.numero, c.nom as client, p.nom as produit, cc.quantite, cc.montant_total, cc.statut",
                      where_clause="WHERE cc.statut = 'Préparée' ORDER BY cc.date_creation DESC")

def get_commandes_a_facturer():
    """Récupère les commandes à facturer (Comptable)"""
    return fetch_data("""commandes_clients cc JOIN clients c ON cc.client_id = c.id JOIN produits p ON cc.produit_id = p.id""", 
                      columns="cc.id, cc.numero, c.nom as client, p.nom as produit, cc.quantite, cc.montant_total, cc.statut, cc.date_expedition",
                      where_clause="WHERE cc.statut = 'Expédiée' ORDER BY cc.date_expedition DESC")

def get_alertes_stock():
    """Récupère les produits en stock faible"""
    return fetch_data("produits", columns="id, nom, stock, seuil_alerte", where_clause="WHERE stock <= seuil_alerte ORDER BY stock ASC")

# ========== FONCTIONS UTILITAIRES DE CONNEXION ET PERMISSIONS (existantes) ==========
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
            permissions[row[0]] = {
                'lecture': bool(row[1]),
                'ecriture': bool(row[2])
            }
        return permissions
    finally:
        release_connection(conn)

def has_access(module, access_type='lecture'):
    if st.session_state.role == "admin" or st.session_state.role == "formateur":
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

# Gestion de l'authentification avec persistance
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_id = None
    st.session_state.role = None
    st.session_state.nom_complet = None
    st.session_state.permissions = {}
    st.session_state.session_id = None

# Restaurer session si existe
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

# ========== PAGE DE CONNEXION (EXISTANTE) ==========
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
                <strong>Formateur en Logistique et Transport</strong><br>
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
                    st.session_state.nom_complet = nom_complet
                    st.session_state.permissions = get_user_permissions(user_id)
                    st.session_state.session_id = session_id
                    
                    log_access(user_id, "connexion", "Connexion réussie")
                    st.query_params['session_id'] = session_id
                    
                    st.success("✅ Connexion réussie !")
                    st.rerun()
                else:
                    st.error("❌ Identifiants incorrects")
        
        st.info("💡 **Compte administrateur**\nUsername: admin\nPassword: admin123")
        st.success("""
        🌟 **NOUVEAUTÉS v4.0**
        - 🔄 Workflow complet de la chaîne logistique
        - 🔔 Notifications en temps réel
        - 📄 Génération automatique de documents
        - 👥 Rôles métiers réalistes
        - 🎓 Mode TP guidé pour formateurs
        """)
    
    st.stop()

# ========== INTERFACE PRINCIPALE (EXISTANTE) ==========
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
        <h1 style="color: #1e3a8a;">🎓 SYGEP v4.0 - Workflow Pédagogique</h1>
        <p style="color: #64748b; font-size: 14px;">
            Développé par <strong>ISMAILI ALAOUI MOHAMED</strong> - IFMLT ZENATA - OFPPT
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

# Afficher notifications (EXISTANTE)
notifs = get_notifications_non_lues(st.session_state.user_id)
if not notifs.empty:
    with st.expander(f"🔔 {len(notifs)} Notification(s) Non Lue(s)", expanded=True):
        for idx, notif in notifs.iterrows():
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{notif['titre']}**")
                st.caption(notif['message'])
                st.caption(f"📅 {notif['date_creation']}")
            with col2:
                if st.button("✓ Lue", key=f"notif_{notif['id']}"):
                    marquer_notification_lue(notif['id'])
                    st.rerun()

st.markdown(f"""
<div style="background: linear-gradient(90deg, #3b82f6 0%, #1e40af 100%); 
            padding: 15px; border-radius: 10px;">
    <h2 style="color: white; margin: 0; text-align: center;">
        👤 Connecté : {st.session_state.nom_complet or st.session_state.username} ({st.session_state.role.upper()})
    </h2>
</div>
""", unsafe_allow_html=True)

# Bouton déconnexion (EXISTANTE)
if st.sidebar.button("🚪 Se Déconnecter", use_container_width=True):
    log_access(st.session_state.user_id, "deconnexion", "Déconnexion")
    if st.session_state.session_id:
        delete_session_from_db(st.session_state.session_id)
    st.query_params.clear()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

st.sidebar.divider()

# Menu navigation adapté au rôle (MIS A JOUR)
menu_items = []
if has_access("tableau_bord"): menu_items.append("📊 Tableau de Bord")
if has_access("workflow"): menu_items.append("🔄 Workflow Commandes")
if has_access("achats"): menu_items.append("🏭 Workflow Approvisionnement")
if has_access("clients"): menu_items.append("👥 Gestion Clients")
if has_access("produits"): menu_items.append("📦 Gestion Produits")
if has_access("fournisseurs"): menu_items.append("📦 Gestion Fournisseurs")
if has_access("rapports"): menu_items.append("💰 Rapports & Facturation")
if has_access("formateur") or st.session_state.role == "admin": menu_items.append("🎓 Mode Formateur/Admin")
if has_access("utilisateurs"): menu_items.append("👤 Gestion Utilisateurs")
menu_items.append("ℹ️ À Propos")

menu = st.sidebar.selectbox("🧭 Navigation", menu_items)

# =========================================================================
# ======================== MODULES WORKFLOW V4.0 ==========================
# =========================================================================

# ========== MODULE WORKFLOW COMMANDES (Ventes & Logistique) ==========
if menu == "🔄 Workflow Commandes":
    st.header("🔄 Workflow de la Chaîne Logistique (Ventes -> Expédition)")
    role = st.session_state.role
    
    # ----------------------------------------------------
    # 1. Commercial - Création de la commande
    # ----------------------------------------------------
    if role in ['commercial', 'admin']:
        st.subheader("👔 Étape 1 : Création de Commande Client")
        
        with st.form("form_commande_client"):
            conn = get_connection()
            try:
                clients = pd.read_sql_query("SELECT id, nom FROM clients ORDER BY nom", conn)
                produits = pd.read_sql_query("SELECT id, nom, reference, prix, stock FROM produits ORDER BY nom", conn)
                
                client_id = st.selectbox("Client *", clients['id'].tolist(),
                                         format_func=lambda x: clients[clients['id']==x]['nom'].iloc[0], key="client_id_select")
                
                # Permettre de sélectionner un produit et afficher son prix/stock
                produit_select_options = [f"{row['nom']} ({row['reference']}) - {row['prix']:.2f} € / Stock: {row['stock']}" 
                                          for index, row in produits.iterrows()]
                produit_selection = st.selectbox("Produit *", produit_select_options, key="produit_select")
                
                # Extraire l'ID du produit sélectionné
                produit_name = produit_selection.split(' (')[0]
                produit_id = produits[produits['nom'] == produit_name].iloc[0]['id']
                produit_stock = produits[produits['id'] == produit_id].iloc[0]['stock']

                quantite = st.number_input("Quantité *", min_value=1, step=1, value=1, key="quantite_input")
                notes = st.text_area("Notes / Demande client")
                
                if st.form_submit_button("📝 Créer Commande Client", type="primary"):
                    produit = produits[produits['id'] == produit_id].iloc[0]
                    prix_unitaire = produit['prix']
                    montant_total = prix_unitaire * quantite
                    numero = generer_numero_commande('BC-CLI')
                    
                    c = conn.cursor()
                    c.execute("""INSERT INTO commandes_clients 
                                 (numero, client_id, produit_id, quantite, prix_unitaire, montant_total, 
                                  statut, commercial_id, notes)
                                 VALUES (%s, %s, %s, %s, %s, %s, 'Nouveau', %s, %s) RETURNING id""",
                              (numero, client_id, produit_id, quantite, prix_unitaire, montant_total,
                               st.session_state.user_id, notes))
                    cmd_id = c.fetchone()[0]
                    conn.commit()
                    
                    # Génération du Bon de Commande (Document)
                    contenu_bc = generer_document_client(cmd_id, "Bon de Commande Client")
                    creer_document(cmd_id, "Bon de Commande Client", contenu_bc, st.session_state.user_id, numero)
                    
                    # Notifier gestionnaire stock
                    gestionnaire_ids = get_user_ids_by_role(['stock', 'gestionnaire', 'admin'])
                    for gid in gestionnaire_ids:
                        creer_notification(gid, 
                                           f"🆕 Nouvelle Commande {numero}",
                                           f"Commande client à valider : {quantite} × {produit['nom']}",
                                           "commande_nouvelle", cmd_id)
                    
                    log_access(st.session_state.user_id, "workflow", f"Création commande {numero}")
                    st.success(f"✅ Commande {numero} créée ! Montant : {montant_total:.2f} €")
                    st.rerun()
            finally:
                release_connection(conn)
        
        st.divider()
        st.subheader("📋 Mes Commandes Créées")
        mes_commandes = fetch_data("""commandes_clients cc JOIN clients c ON cc.client_id = c.id JOIN produits p ON cc.produit_id = p.id""", 
                                    columns="cc.numero, c.nom as client, p.nom as produit, cc.quantite, cc.montant_total, cc.statut, cc.date_creation",
                                    where_clause=f"WHERE cc.commercial_id = {st.session_state.user_id} ORDER BY cc.date_creation DESC LIMIT 20")
        if not mes_commandes.empty:
            st.dataframe(mes_commandes, use_container_width=True, hide_index=True)
        else:
            st.info("Aucune commande créée")

    # ----------------------------------------------------
    # 2. Gestionnaire Stock - Validation & Préparation
    # ----------------------------------------------------
    if role in ['stock', 'gestionnaire', 'expediteur', 'admin']:
        st.subheader("📦 Étape 2 : Gestion Stock & Préparation Commande")
        
        # --- A. Validation Stock (Stock/Gestionnaire)
        if role in ['stock', 'gestionnaire', 'admin']:
            st.markdown("##### 2.1 Validation Stock")
            cmd_attente = get_commandes_en_attente_validation()
            
            if not cmd_attente.empty:
                st.warning(f"⚠️ {len(cmd_attente)} commande(s) en attente de validation stock")
                
                for idx, cmd in cmd_attente.iterrows():
                    with st.expander(f"🔍 Commande {cmd['numero']} - {cmd['client']}", expanded=True):
                        col1, col2, col3 = st.columns(3)
                        with col1: st.metric("Produit", cmd['produit']); st.metric("Quantité demandée", cmd['quantite'])
                        with col2: st.metric("Montant", f"{cmd['montant_total']:.2f} €"); st.metric("Statut", cmd['statut'])
                        
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("SELECT stock, seuil_alerte FROM produits WHERE id = %s", (cmd['produit_id'],))
                            stock_data = c.fetchone()
                            stock_dispo = stock_data[0]
                            seuil_alerte = stock_data[1]
                            
                            with col3:
                                st.metric("Stock disponible", stock_dispo)
                                
                                if stock_dispo >= cmd['quantite']:
                                    st.success("✅ Stock suffisant")
                                    if st.button(f"✅ Valider Stock", key=f"val_{cmd['id']}"):
                                        c.execute("""UPDATE commandes_clients 
                                                     SET statut = 'Validée - Stock OK', 
                                                         gestionnaire_id = %s,
                                                         date_validation_stock = NOW()
                                                     WHERE id = %s""",
                                                    (st.session_state.user_id, cmd['id']))
                                        conn.commit()
                                        
                                        # Notifier l'Expéditeur
                                        expediteur_ids = get_user_ids_by_role(['expediteur', 'admin'])
                                        for eid in expediteur_ids:
                                            creer_notification(eid, 
                                                               f"📦 Commande à Préparer {cmd['numero']}",
                                                               f"La commande pour {cmd['client']} est validée et prête à être préparée.",
                                                               "commande_prete", cmd['id'])
                                        
                                        log_access(st.session_state.user_id, "workflow", f"Validation stock OK pour {cmd['numero']}")
                                        st.success(f"Stock validé pour {cmd['numero']}. Notification envoyée à l'Expéditeur.")
                                        st.rerun()
                                else:
                                    st.error("❌ Stock insuffisant")
                                    manquant = cmd['quantite'] - stock_dispo
                                    st.caption(f"Il manque **{manquant}** unités.")
                                    
                                    if st.button(f"🚨 Alerter Approvisionneur", key=f"alert_{cmd['id']}"):
                                        c.execute("""UPDATE commandes_clients 
                                                     SET statut = 'En attente appro', 
                                                         gestionnaire_id = %s,
                                                         date_validation_stock = NOW()
                                                     WHERE id = %s""",
                                                    (st.session_state.user_id, cmd['id']))
                                        conn.commit()
                                        
                                        # Notifier l'Approvisionneur
                                        appro_ids = get_user_ids_by_role(['approvisionneur', 'admin'])
                                        for aid in appro_ids:
                                            creer_notification(aid, 
                                                               f"🔥 ALERTE Approvisionnement Urgent",
                                                               f"Rupture de stock pour le produit {cmd['produit']} (manque {manquant}). Commande Client {cmd['numero']} bloquée.",
                                                               "alerte_stock", cmd['produit_id'])

                                        log_access(st.session_state.user_id, "workflow", f"Alerte approvisionnement pour {cmd['numero']}")
                                        st.error(f"Statut mis à jour en 'En attente appro'. Approvisionneur notifié.")
                                        st.rerun()
                        finally:
                            release_connection(conn)
            else:
                st.info("Aucune commande en attente de validation stock.")
            
            st.divider()

        # --- B. Préparation Commande (Expéditeur/Stock)
        if role in ['expediteur', 'stock', 'admin']:
            st.markdown("##### 2.2 Préparation des Commandes")
            cmd_a_preparer = get_commandes_a_preparer()
            
            if not cmd_a_preparer.empty:
                st.info(f"📦 {len(cmd_a_preparer)} commande(s) prête(s) à être préparée(s)")
                
                for idx, cmd in cmd_a_preparer.iterrows():
                    with st.expander(f"📋 Préparer Commande {cmd['numero']} - {cmd['client']}", expanded=True):
                        st.write(f"**Produit :** {cmd['produit']} | **Quantité :** {cmd['quantite']}")
                        
                        if st.button(f"📑 Générer Bon de Préparation et Préparer", key=f"prep_{cmd['id']}"):
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                
                                # Création du Bon de Préparation (Document)
                                contenu_bp = generer_document_client(cmd['id'], "Bon de Préparation")
                                creer_document(cmd['id'], "Bon de Préparation", contenu_bp, st.session_state.user_id)
                                
                                # Changement de statut
                                c.execute("""UPDATE commandes_clients 
                                             SET statut = 'Préparée', 
                                                 expediteur_id = %s
                                             WHERE id = %s""",
                                            (st.session_state.user_id, cmd['id']))
                                conn.commit()

                                log_access(st.session_state.user_id, "workflow", f"Préparation commande {cmd['numero']}")
                                st.success(f"Commande {cmd['numero']} est maintenant 'Préparée' et prête à être expédiée.")
                                st.rerun()
                            finally:
                                release_connection(conn)
            else:
                st.caption("Aucune commande en attente de préparation.")
            
            st.divider()

        # --- C. Expédition Commande (Expéditeur)
        if role in ['expediteur', 'admin']:
            st.markdown("##### 2.3 Expédition et Livraison")
            cmd_a_expedier = get_commandes_a_expedier()
            
            if not cmd_a_expedier.empty:
                st.success(f"🚚 {len(cmd_a_expedier)} commande(s) prête(s) à l'expédition")
                
                for idx, cmd in cmd_a_expedier.iterrows():
                    with st.expander(f"🚚 Expédier Commande {cmd['numero']} - {cmd['client']}", expanded=True):
                        st.write(f"**Produit :** {cmd['produit']} | **Quantité :** {cmd['quantite']}")
                        
                        if st.button(f"✔️ Valider Expédition et Générer BL", key=f"exp_{cmd['id']}"):
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                
                                # 1. Déduction du stock
                                c.execute("UPDATE produits SET stock = stock - %s WHERE id IN (SELECT produit_id FROM commandes_clients WHERE id = %s) RETURNING id",
                                            (cmd['quantite'], cmd['id']))
                                produit_id = c.fetchone()[0]

                                # 2. Création du Bon de Livraison (Document)
                                numero_bl = generer_numero_commande('BL')
                                contenu_bl = generer_document_client(cmd['id'], "Bon de Livraison")
                                creer_document(cmd['id'], "Bon de Livraison", contenu_bl, st.session_state.user_id, numero_bl)
                                
                                # 3. Changement de statut commande client
                                c.execute("""UPDATE commandes_clients 
                                             SET statut = 'Expédiée', 
                                                 expediteur_id = %s,
                                                 date_expedition = NOW()
                                             WHERE id = %s""",
                                            (st.session_state.user_id, cmd['id']))
                                conn.commit()

                                # 4. Notifier le Comptable
                                comptable_ids = get_user_ids_by_role(['comptable', 'admin'])
                                for cid in comptable_ids:
                                    creer_notification(cid, 
                                                       f"💰 Commande à Facturer {cmd['numero']}",
                                                       f"La commande {cmd['numero']} a été expédiée. Facture Client à générer.",
                                                       "facturation_requise", cmd['id'])
                                
                                # 5. Notifier le Commercial (pour suivi client)
                                c.execute("SELECT commercial_id FROM commandes_clients WHERE id = %s", (cmd['id'],))
                                commercial_id = c.fetchone()[0]
                                creer_notification(commercial_id, 
                                                   f"🚚 Commande Expédiée {cmd['numero']}",
                                                   f"Votre commande {cmd['numero']} a été livrée (BL N° {numero_bl}).",
                                                   "commande_expediee", cmd['id'])

                                log_access(st.session_state.user_id, "workflow", f"Expédition et déstockage pour {cmd['numero']}")
                                st.success(f"Expédition validée. Stock mis à jour. Facturation requise.")
                                st.rerun()
                            finally:
                                release_connection(conn)
            else:
                st.caption("Aucune commande en attente d'expédition.")

# ========== MODULE WORKFLOW APPROVISIONNEMENT (Achats & Réception) ==========
if menu == "🏭 Workflow Approvisionnement":
    st.header("🏭 Workflow Approvisionnement (Fournisseurs -> Réception)")
    role = st.session_state.role

    # ----------------------------------------------------
    # 1. Approvisionneur - Création de Commande Fournisseur
    # ----------------------------------------------------
    if role in ['approvisionneur', 'stock', 'admin']:
        st.subheader("🏭 Étape 1 : Achats & Commandes Fournisseurs")
        
        # Afficher les alertes stock
        alertes = get_alertes_stock()
        if not alertes.empty:
            st.error(f"🚨 **{len(alertes)} Produits en ALERTE Stock !**")
            
            # Joindre les commandes clients bloquées à l'alerte
            commandes_bloquees = fetch_data("commandes_clients cc JOIN produits p ON cc.produit_id = p.id",
                                            columns="cc.id, cc.numero, p.nom, cc.quantite, p.stock",
                                            where_clause="WHERE cc.statut = 'En attente appro'")
            if not commandes_bloquees.empty:
                st.warning("Commandes clients bloquées:")
                st.dataframe(commandes_bloquees[['numero', 'nom', 'quantite', 'stock']], hide_index=True)
            
            st.markdown("---")
            
        with st.form("form_commande_fournisseur"):
            conn = get_connection()
            try:
                fournisseurs = fetch_data("fournisseurs", columns="id, nom")
                produits_achats = fetch_data("produits", columns="id, nom, reference, stock")
                
                four_id = st.selectbox("Fournisseur *", fournisseurs['id'].tolist(),
                                       format_func=lambda x: fournisseurs[fournisseurs['id']==x]['nom'].iloc[0], key="four_id_select")
                produit_id_achat = st.selectbox("Produit à commander *", produits_achats['id'].tolist(),
                                                format_func=lambda x: f"{produits_achats[produits_achats['id']==x]['nom'].iloc[0]} (Stock: {produits_achats[produits_achats['id']==x]['stock'].iloc[0]})", 
                                                key="produit_achat_select")
                
                quantite_achat = st.number_input("Quantité à commander *", min_value=1, step=1, value=15, key="quantite_achat_input")
                prix_achat = st.number_input("Prix d'Achat Unitaire *", min_value=0.01, step=0.01, value=750.00, key="prix_achat_input")
                notes_achat = st.text_area("Notes d'achat / Délai de livraison")
                
                if st.form_submit_button("📝 Créer Commande Fournisseur", type="primary"):
                    montant_total_achat = prix_achat * quantite_achat
                    numero_cf = generer_numero_commande('BC-FOUR')
                    
                    c = conn.cursor()
                    c.execute("""INSERT INTO commandes_fournisseurs 
                                 (numero, fournisseur_id, produit_id, quantite, prix_unitaire, montant_total, 
                                  statut, approvisionneur_id, notes)
                                 VALUES (%s, %s, %s, %s, %s, %s, 'Commandée', %s, %s) RETURNING id""",
                              (numero_cf, four_id, produit_id_achat, quantite_achat, prix_achat, montant_total_achat,
                               st.session_state.user_id, notes_achat))
                    cf_id = c.fetchone()[0]
                    conn.commit()

                    # Notification pour le Réceptionnaire
                    receptionnaire_ids = get_user_ids_by_role(['receptionnaire', 'admin'])
                    for rid in receptionnaire_ids:
                        creer_notification(rid, 
                                           f"🚚 Livraison Attendue {numero_cf}",
                                           f"Commande Fournisseur passée : {quantite_achat} × {produits_achats[produits_achats['id']==produit_id_achat].iloc[0]['nom']} à réceptionner.",
                                           "livraison_attendue", cf_id)

                    log_access(st.session_state.user_id, "achats", f"Création commande fournisseur {numero_cf}")
                    st.success(f"✅ Commande Fournisseur {numero_cf} créée et notifiée pour réception.")
                    st.rerun()
            finally:
                release_connection(conn)
        
    # ----------------------------------------------------
    # 2. Réceptionnaire - Réception de Marchandise
    # ----------------------------------------------------
    if role in ['receptionnaire', 'admin']:
        st.subheader("📥 Étape 2 : Réception de Marchandise")
        
        cf_a_recevoir = fetch_data("""commandes_fournisseurs cf JOIN fournisseurs f ON cf.fournisseur_id = f.id JOIN produits p ON cf.produit_id = p.id""", 
                                    columns="cf.id, cf.numero, f.nom as fournisseur, p.nom as produit, cf.quantite, cf.prix_unitaire, p.stock",
                                    where_clause="WHERE cf.statut = 'Commandée' ORDER BY cf.date_creation DESC")
        
        if not cf_a_recevoir.empty:
            st.success(f"📦 **{len(cf_a_recevoir)} Livraison(s) Attendue(s) / Arrivée(s)**")
            
            for idx, cf in cf_a_recevoir.iterrows():
                with st.expander(f"📦 Réception Commande Fournisseur {cf['numero']} - {cf['fournisseur']}", expanded=True):
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Produit", cf['produit'])
                        st.metric("Quantité Commandée", cf['quantite'])
                    with col2:
                        st.metric("Prix Unitaire Achat", f"{cf['prix_unitaire']:.2f} €")
                        st.metric("Stock Actuel", cf['stock'])

                    with st.form(f"form_reception_{cf['id']}"):
                        qte_recue = st.number_input("Quantité réellement reçue *", min_value=1, step=1, value=cf['quantite'], key=f"qte_recue_{cf['id']}")
                        
                        if st.form_submit_button(f"✔️ Valider Réception et Mettre à jour Stock", type="primary"):
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                
                                # 1. Mise à jour du stock
                                c.execute("UPDATE produits SET stock = stock + %s WHERE id IN (SELECT produit_id FROM commandes_fournisseurs WHERE id = %s)",
                                            (qte_recue, cf['id']))
                                
                                # 2. Création du Bon de Réception (Document)
                                numero_br = generer_numero_commande('BR')
                                # Le contenu du BR est simple ici, basé sur la CF
                                contenu_br = f"Réception de {qte_recue} unités pour la CF {cf['numero']} du fournisseur {cf['fournisseur']}."
                                creer_document(cf['id'], "Bon de Réception", contenu_br, st.session_state.user_id, numero_br)
                                
                                # 3. Changement de statut commande fournisseur
                                statut_final = 'Partiellement Reçue' if qte_recue < cf['quantite'] else 'Reçue'
                                c.execute("""UPDATE commandes_fournisseurs 
                                             SET statut = %s, 
                                                 receptionnaire_id = %s,
                                                 date_reception = NOW(),
                                                 quantite_recue = %s
                                             WHERE id = %s""",
                                            (statut_final, st.session_state.user_id, qte_recue, cf['id']))
                                conn.commit()

                                # 4. Notifier le Comptable (pour paiement Fournisseur)
                                comptable_ids = get_user_ids_by_role(['comptable', 'admin'])
                                for cid in comptable_ids:
                                    creer_notification(cid, 
                                                       f"💰 Facture Fournisseur à Payer (BR N°{numero_br})",
                                                       f"La marchandise pour la Commande Fournisseur {cf['numero']} a été reçue (Qté: {qte_recue}). Procéder au paiement.",
                                                       "paiement_requise", cf['id'])
                                
                                # 5. Notifier l'Approvisionneur
                                c.execute("SELECT approvisionneur_id FROM commandes_fournisseurs WHERE id = %s", (cf['id'],))
                                appro_id = c.fetchone()[0]
                                creer_notification(appro_id, 
                                                   f"✅ Réception Terminée {cf['numero']}",
                                                   f"La commande fournisseur {cf['numero']} a été réceptionnée. Statut: {statut_final}.",
                                                   "reception_ok", cf['id'])
                                
                                log_access(st.session_state.user_id, "achats", f"Réception {statut_final} de {cf['numero']}")
                                st.success(f"Réception validée. Stock mis à jour de +{qte_recue} unités. Paiement Fournisseur requis.")
                                st.rerun()
                            finally:
                                release_connection(conn)
        else:
            st.info("Aucune commande fournisseur en attente de réception.")


# ========== MODULE RAPPORTS & FACTURATION (Comptable) ==========
if menu == "💰 Rapports & Facturation":
    st.header("💰 Rapports & Facturation")
    role = st.session_state.role

    if role in ['comptable', 'admin']:
        st.subheader("📝 Étape 3 : Facturation Client")
        cmd_a_facturer = get_commandes_a_facturer()

        if not cmd_a_facturer.empty:
            st.warning(f"⚠️ {len(cmd_a_facturer)} Commande(s) Client(s) Expédiée(s) à Facturer")

            for idx, cmd in cmd_a_facturer.iterrows():
                with st.expander(f"🧾 Facturer Commande {cmd['numero']} - {cmd['client']}", expanded=True):
                    st.write(f"**Montant Total :** {cmd['montant_total']:.2f} € | **Expédiée le :** {cmd['date_expedition'].strftime('%d/%m/%Y')}")

                    if st.button(f"✔️ Émettre Facture Client", key=f"fact_cli_{cmd['id']}"):
                        conn = get_connection()
                        try:
                            c = conn.cursor()

                            # 1. Création de la Facture Client (Document)
                            numero_fac_cli = generer_numero_commande('FAC-CLI')
                            contenu_fac_cli = generer_document_client(cmd['id'], "Facture Client")
                            creer_document(cmd['id'], "Facture Client", contenu_fac_cli, st.session_state.user_id, numero_fac_cli)
                            
                            # 2. Changement de statut commande client
                            c.execute("""UPDATE commandes_clients 
                                         SET statut = 'Facturée', 
                                             comptable_id = %s,
                                             date_facturation = NOW()
                                         WHERE id = %s""",
                                        (st.session_state.user_id, cmd['id']))
                            conn.commit()

                            log_access(st.session_state.user_id, "facturation", f"Facturation client {cmd['numero']} (N° {numero_fac_cli})")
                            st.success(f"Facture Client N°{numero_fac_cli} émise pour {cmd['client']}.")
                            st.rerun()
                        finally:
                            release_connection(conn)
        else:
            st.info("Aucune commande client en attente de facturation.")

        st.divider()
        
        st.subheader("💸 Paiement Fournisseur")
        # Ici on affiche les Commandes Fournisseurs reçues mais non payées
        cf_a_payer = fetch_data("""commandes_fournisseurs cf JOIN fournisseurs f ON cf.fournisseur_id = f.id JOIN produits p ON cf.produit_id = p.id""", 
                                columns="cf.id, cf.numero, f.nom as fournisseur, p.nom as produit, cf.montant_total, cf.statut, cf.date_reception, cf.quantite_recue",
                                where_clause="WHERE cf.statut IN ('Reçue', 'Partiellement Reçue') ORDER BY cf.date_reception DESC")
        
        if not cf_a_payer.empty:
            st.warning(f"💸 **{len(cf_a_payer)} Facture(s) Fournisseur(s) à Payer**")

            for idx, cf in cf_a_payer.iterrows():
                with st.expander(f"Payez Fournisseur {cf['fournisseur']} - CF N°{cf['numero']}", expanded=True):
                    st.write(f"**Montant Total :** {cf['montant_total']:.2f} € | **Produit :** {cf['produit']} | **Qté Reçue :** {cf['quantite_recue']}")

                    if st.button(f"✔️ Valider Paiement Fournisseur", key=f"pay_four_{cf['id']}"):
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("UPDATE commandes_fournisseurs SET statut = 'Payée' WHERE id = %s", (cf['id'],))
                            conn.commit()

                            log_access(st.session_state.user_id, "paiement", f"Paiement fournisseur {cf['numero']} effectué.")
                            st.success(f"Paiement pour la CF {cf['numero']} validé. Statut : Payée.")
                            st.rerun()
                        finally:
                            release_connection(conn)
        else:
            st.info("Aucun paiement fournisseur en attente.")

    # ----------------------------------------------------
    # Rapports Généraux (Lecture Seule - pour Directeur et Comptable)
    # ----------------------------------------------------
    if role in ['comptable', 'directeur', 'admin']:
        st.divider()
        st.subheader("📈 Rapports d'Activité")
        
        col1, col2, col3 = st.columns(3)
        
        # Calcul CA
        ca = fetch_data("commandes_clients", columns="SUM(montant_total) as total", where_clause="WHERE statut = 'Facturée'")
        total_ca = ca.iloc[0]['total'] if not ca.empty and ca.iloc[0]['total'] is not None else 0
        col1.metric("Chiffre d'Affaires Facturé", f"{total_ca:.2f} €")
        
        # Calcul Coûts d'Achat
        achats = fetch_data("commandes_fournisseurs", columns="SUM(montant_total) as total", where_clause="WHERE statut = 'Payée'")
        total_achats = achats.iloc[0]['total'] if not achats.empty and achats.iloc[0]['total'] is not None else 0
        col2.metric("Coûts d'Achat Payés", f"{total_achats:.2f} €")

        # Calcul Marge Brute
        marge = total_ca - total_achats
        col3.metric("Marge Brute (Simplifiée)", f"{marge:.2f} €")

        # Visualisation du Stock Actuel
        st.markdown("##### État des Stocks")
        stocks_df = fetch_data("produits", columns="nom, stock, seuil_alerte")
        if not stocks_df.empty:
            st.dataframe(stocks_df, use_container_width=True, hide_index=True)


# ========== MODULE TABLEAU DE BORD (Directeur) ==========
if menu == "📊 Tableau de Bord":
    st.header("📊 Tableau de Bord (Lecture Seule)")
    
    if st.session_state.role in ['directeur', 'admin']:
        # Réutiliser la logique de Rapports pour le KPI
        
        st.info("Cette section est réservée à la direction pour une vue d'ensemble et des indicateurs clés.")
        
        col1, col2, col3 = st.columns(3)
        
        # Calcul CA (Facturé)
        ca = fetch_data("commandes_clients", columns="SUM(montant_total) as total", where_clause="WHERE statut = 'Facturée'")
        total_ca = ca.iloc[0]['total'] if not ca.empty and ca.iloc[0]['total'] is not None else 0
        col1.metric("Chiffre d'Affaires Facturé", f"{total_ca:.2f} €")
        
        # Nombre de commandes en cours
        cmd_en_cours = fetch_data("commandes_clients", columns="COUNT(id) as total", where_clause="WHERE statut NOT IN ('Facturée', 'Annulée')")
        total_en_cours = cmd_en_cours.iloc[0]['total'] if not cmd_en_cours.empty and cmd_en_cours.iloc[0]['total'] is not None else 0
        col2.metric("Commandes Clients en Cours", total_en_cours)
        
        # Alertes Stock
        alertes = get_alertes_stock()
        col3.metric("Alertes Stock", f"{len(alertes)} 🚨")

        st.divider()
        st.subheader("Flux des Commandes Clients")
        toutes_commandes = fetch_data("""commandes_clients cc JOIN clients c ON cc.client_id = c.id JOIN produits p ON cc.produit_id = p.id""", 
                                     columns="cc.numero, c.nom as client, p.nom as produit, cc.quantite, cc.montant_total, cc.statut, cc.date_creation",
                                     where_clause="ORDER BY cc.date_creation DESC LIMIT 30")
        st.dataframe(toutes_commandes, use_container_width=True, hide_index=True)
    else:
        st.warning("Accès restreint au rôle Directeur/Admin.")

# ========== MODULE GESTION CLIENTS (Placeholder) ==========
if menu == "👥 Gestion Clients":
    st.header("👥 Gestion Clients")
    if has_access('clients', 'lecture'):
        st.info("Ceci est le module de gestion des fiches clients. Seul le commercial a les droits d'écriture (création/modification).")
        # Implémentation simplifiée
        clients_df = fetch_data("clients")
        if has_access('clients', 'ecriture'):
             st.subheader("Ajouter un Client")
             # Formulaire d'ajout rapide (omitted for brevity, assume CRUD form is here)
        st.subheader("Liste des Clients")
        st.dataframe(clients_df, use_container_width=True, hide_index=True)
    else:
        st.error("Accès refusé.")

# ========== MODULE GESTION PRODUITS (Placeholder) ==========
if menu == "📦 Gestion Produits":
    st.header("📦 Gestion Produits et Stocks")
    if has_access('produits', 'lecture'):
        st.info("Ceci est le catalogue produits. Seul le rôle admin/gestionnaire peut mettre à jour les fiches (prix/stock).")
        # Implémentation simplifiée
        produits_df = fetch_data("produits")
        st.subheader("Liste des Produits")
        st.dataframe(produits_df, use_container_width=True, hide_index=True)
    else:
        st.error("Accès refusé.")

# ========== MODULE GESTION FOURNISSEURS (Placeholder) ==========
if menu == "📦 Gestion Fournisseurs":
    st.header("🏭 Gestion Fournisseurs")
    if has_access('fournisseurs', 'lecture'):
        st.info("Ceci est le répertoire des fournisseurs.")
        # Implémentation simplifiée
        fournisseurs_df = fetch_data("fournisseurs")
        st.subheader("Liste des Fournisseurs")
        st.dataframe(fournisseurs_df, use_container_width=True, hide_index=True)
    else:
        st.error("Accès refusé.")

# ========== MODULE GESTION UTILISATEURS (Placeholder) ==========
if menu == "👤 Gestion Utilisateurs":
    st.header("👤 Gestion Utilisateurs et Permissions")
    if has_access('utilisateurs', 'ecriture'):
        st.info("Réservé à l'administrateur. Permet la création/modification des comptes et des rôles.")
        # Implémentation simplifiée
        users_df = fetch_data("utilisateurs", columns="id, username, role, nom_complet, date_creation")
        st.subheader("Liste des Utilisateurs")
        st.dataframe(users_df, use_container_width=True, hide_index=True)
    else:
        st.error("Accès refusé.")

# ========== MODULE FORMATEUR/ADMIN ==========
if menu == "🎓 Mode Formateur/Admin":
    st.header("🎓 Outils Formateur / Administration")
    if has_access('formateur', 'ecriture') or st.session_state.role == "admin":
        st.success("Bienvenue dans le tableau de bord de supervision.")
        
        st.subheader("🌐 Sessions Actives")
        sessions_df = fetch_data("sessions", columns="username, role, last_activity")
        st.dataframe(sessions_df, use_container_width=True, hide_index=True)

        st.subheader("📜 Logs d'Activité Récentes")
        logs_df = fetch_data("logs_acces", columns="id, action, module, date_heure, user_id", 
                             where_clause="ORDER BY date_heure DESC LIMIT 20")
        st.dataframe(logs_df, use_container_width=True, hide_index=True)
        
        st.subheader("📄 Documents Générés (Simulation)")
        docs_df = fetch_data("documents", columns="numero, type_doc, date_creation")
        st.dataframe(docs_df, use_container_width=True, hide_index=True)
        
        # Simulation d'événement (ex: Réinitialisation)
        st.subheader("⚠️ Outils de Maintenance")
        if st.button("🔴 Réinitialiser les Commandes/Documents (TP Suivant)", type="secondary"):
            conn = get_connection()
            try:
                c = conn.cursor()
                # Réinitialiser les tables de transaction
                c.execute("DELETE FROM commandes_clients")
                c.execute("DELETE FROM commandes_fournisseurs")
                c.execute("DELETE FROM documents")
                c.execute("DELETE FROM notifications")
                
                # Remettre le stock initial pour les produits de démo
                c.execute("UPDATE produits SET stock = 15 WHERE reference = 'HP-PB-450'")
                c.execute("UPDATE produits SET stock = 8 WHERE reference = 'CAN-LBP-6030'")
                c.execute("UPDATE produits SET stock = 50 WHERE reference = 'LOG-M185'")
                c.execute("UPDATE produits SET stock = 12 WHERE reference = 'COR-K70'")
                c.execute("UPDATE produits SET stock = 6 WHERE reference = 'DELL-P2422H'")
                
                conn.commit()
                st.success("Système réinitialisé pour le prochain TP. Les données de transaction (Commandes, Docs, Notifications) ont été effacées.")
                st.rerun()
            finally:
                release_connection(conn)
    else:
        st.error("Accès refusé.")


# ========== MODULE À PROPOS (EXISTANTE) ==========
if menu == "ℹ️ À Propos":
    st.header("ℹ️ À Propos - SYGEP v4.0")
    st.info("""
    **SYGEP v4.0 : Système de Gestion d'Entreprise Pédagogique**

    Cette version intègre un **Workflow Complet** simulant la chaîne logistique :
    - **Vente** (Commercial)
    - **Validation Stock** (Gestionnaire Stock)
    - **Approvisionnement** (Approvisionneur)
    - **Réception** (Réceptionnaire)
    - **Expédition** (Expéditeur)
    - **Facturation** (Comptable)

    L'application utilise une base de données **PostgreSQL (via Supabase)** et le framework **Streamlit** pour une expérience en **temps réel** permettant la simulation d'un travail collaboratif entre étudiants.
    
    **Développé par :** ISMAILI ALAOUI MOHAMED - Formateur en Logistique et Transport - IFMLT ZENATA - OFPPT
    """)
