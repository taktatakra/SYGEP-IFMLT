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

# Charger les variables d'environnement
load_dotenv()

# Configuration de la page
st.set_page_config(
    page_title="SYGEP ERP - Système de Gestion Intégré",
    layout="wide",
    page_icon="🏢",
    initial_sidebar_state="expanded"
)

# ========== GESTION CONNEXION POSTGRESQL (SUPABASE) ==========

@st.cache_resource
def init_connection_pool():
    """Initialise un pool de connexions PostgreSQL"""
    try:
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
    pool = init_connection_pool()
    return pool.getconn()

def release_connection(conn):
    pool = init_connection_pool()
    pool.putconn(conn)

# ========== INITIALISATION BASE DE DONNÉES ==========
def init_database():
    """Initialise les tables PostgreSQL avec relations améliorées"""
    conn = get_connection()
    try:
        c = conn.cursor()
        
        # Table Utilisateurs avec plus de champs
        c.execute('''CREATE TABLE IF NOT EXISTS utilisateurs
                     (id SERIAL PRIMARY KEY,
                      username VARCHAR(100) UNIQUE NOT NULL,
                      password VARCHAR(255) NOT NULL,
                      email VARCHAR(255),
                      role VARCHAR(50) NOT NULL,
                      actif BOOLEAN DEFAULT TRUE,
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      date_modification TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Table Permissions
        c.execute('''CREATE TABLE IF NOT EXISTS permissions
                     (id SERIAL PRIMARY KEY,
                      user_id INTEGER REFERENCES utilisateurs(id) ON DELETE CASCADE,
                      module VARCHAR(100) NOT NULL,
                      acces_lecture BOOLEAN DEFAULT FALSE,
                      acces_ecriture BOOLEAN DEFAULT FALSE,
                      acces_suppression BOOLEAN DEFAULT FALSE)''')
        
        # Table Clients améliorée
        c.execute('''CREATE TABLE IF NOT EXISTS clients
                     (id SERIAL PRIMARY KEY,
                      nom VARCHAR(255) NOT NULL,
                      email VARCHAR(255),
                      telephone VARCHAR(50),
                      adresse TEXT,
                      ville VARCHAR(100),
                      code_postal VARCHAR(20),
                      pays VARCHAR(100) DEFAULT 'Maroc',
                      type_client VARCHAR(50),
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      date_modification TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Table Catégories Produits
        c.execute('''CREATE TABLE IF NOT EXISTS categories
                     (id SERIAL PRIMARY KEY,
                      nom VARCHAR(255) NOT NULL UNIQUE,
                      description TEXT,
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Table Produits améliorée
        c.execute('''CREATE TABLE IF NOT EXISTS produits
                     (id SERIAL PRIMARY KEY,
                      nom VARCHAR(255) NOT NULL,
                      description TEXT,
                      prix DECIMAL(15,2) NOT NULL,
                      cout DECIMAL(15,2),
                      stock INTEGER NOT NULL DEFAULT 0,
                      stock_min INTEGER DEFAULT 10,
                      categorie_id INTEGER REFERENCES categories(id),
                      code_barre VARCHAR(100),
                      actif BOOLEAN DEFAULT TRUE,
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      date_modification TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Table Fournisseurs améliorée
        c.execute('''CREATE TABLE IF NOT EXISTS fournisseurs
                     (id SERIAL PRIMARY KEY,
                      nom VARCHAR(255) NOT NULL,
                      email VARCHAR(255),
                      telephone VARCHAR(50),
                      adresse TEXT,
                      ville VARCHAR(100),
                      code_postal VARCHAR(20),
                      pays VARCHAR(100) DEFAULT 'Maroc',
                      contact_nom VARCHAR(255),
                      contact_telephone VARCHAR(50),
                      actif BOOLEAN DEFAULT TRUE,
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      date_modification TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Table Commandes améliorée
        c.execute('''CREATE TABLE IF NOT EXISTS commandes
                     (id SERIAL PRIMARY KEY,
                      numero_commande VARCHAR(100) UNIQUE,
                      client_id INTEGER REFERENCES clients(id),
                      date_commande DATE NOT NULL,
                      date_livraison_prevue DATE,
                      statut VARCHAR(50) DEFAULT 'En attente',
                      montant_total DECIMAL(15,2) DEFAULT 0,
                      notes TEXT,
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      date_modification TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Table Lignes Commandes
        c.execute('''CREATE TABLE IF NOT EXISTS lignes_commandes
                     (id SERIAL PRIMARY KEY,
                      commande_id INTEGER REFERENCES commandes(id) ON DELETE CASCADE,
                      produit_id INTEGER REFERENCES produits(id),
                      quantite INTEGER NOT NULL,
                      prix_unitaire DECIMAL(15,2) NOT NULL,
                      montant_ligne DECIMAL(15,2) GENERATED ALWAYS AS (quantite * prix_unitaire) STORED)''')
        
        # Table Achats améliorée
        c.execute('''CREATE TABLE IF NOT EXISTS achats
                     (id SERIAL PRIMARY KEY,
                      numero_achat VARCHAR(100) UNIQUE,
                      fournisseur_id INTEGER REFERENCES fournisseurs(id),
                      date_achat DATE NOT NULL,
                      date_reception_prevue DATE,
                      statut VARCHAR(50) DEFAULT 'En attente',
                      montant_total DECIMAL(15,2) DEFAULT 0,
                      notes TEXT,
                      date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      date_modification TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Table Lignes Achats
        c.execute('''CREATE TABLE IF NOT EXISTS lignes_achats
                     (id SERIAL PRIMARY KEY,
                      achat_id INTEGER REFERENCES achats(id) ON DELETE CASCADE,
                      produit_id INTEGER REFERENCES produits(id),
                      quantite INTEGER NOT NULL,
                      prix_unitaire DECIMAL(15,2) NOT NULL,
                      montant_ligne DECIMAL(15,2) GENERATED ALWAYS AS (quantite * prix_unitaire) STORED)''')
        
        # Table Sessions
        c.execute('''CREATE TABLE IF NOT EXISTS sessions
                     (id SERIAL PRIMARY KEY,
                      session_id VARCHAR(255) UNIQUE,
                      user_id INTEGER REFERENCES utilisateurs(id),
                      username VARCHAR(100),
                      role VARCHAR(50),
                      last_activity TIMESTAMP)''')
        
        # Table Logs améliorée
        c.execute('''CREATE TABLE IF NOT EXISTS logs_acces
                     (id SERIAL PRIMARY KEY,
                      user_id INTEGER REFERENCES utilisateurs(id),
                      module VARCHAR(100),
                      action TEXT,
                      details JSONB,
                      date_heure TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        conn.commit()
        
        # Créer utilisateur admin par défaut si n'existe pas
        c.execute("SELECT COUNT(*) FROM utilisateurs WHERE username = %s", ('admin',))
        if c.fetchone()[0] == 0:
            password_hash = hashlib.sha256("admin123".encode()).hexdigest()
            c.execute("""INSERT INTO utilisateurs (username, password, email, role) 
                         VALUES (%s, %s, %s, %s) RETURNING id""",
                      ('admin', password_hash, 'admin@sygep.ma', 'admin'))
            user_id = c.fetchone()[0]
            
            # Donner tous les droits à l'admin
            modules = ["tableau_bord", "clients", "produits", "categories", "fournisseurs", 
                      "commandes", "achats", "rapports", "utilisateurs"]
            for module in modules:
                c.execute("""INSERT INTO permissions (user_id, module, acces_lecture, acces_ecriture, acces_suppression) 
                             VALUES (%s, %s, %s, %s, %s)""",
                          (user_id, module, True, True, True))
            
            conn.commit()
        
        # Ajouter données de démonstration si tables vides
        c.execute("SELECT COUNT(*) FROM clients")
        if c.fetchone()[0] == 0:
            # Catégories
            c.execute("""INSERT INTO categories (nom, description) VALUES 
                        ('Informatique', 'Produits informatiques et accessoires'),
                        ('Bureautique', 'Fournitures de bureau'),
                        ('Électronique', 'Appareils électroniques')""")
            
            # Clients
            c.execute("""INSERT INTO clients (nom, email, telephone, adresse, ville, type_client) VALUES 
                        ('Entreprise Alpha SARL', 'contact@alpha.com', '0612345678', '123 Avenue Hassan II', 'Casablanca', 'Entreprise'),
                        ('Société Beta SA', 'info@beta.com', '0698765432', '45 Rue Mohammed V', 'Rabat', 'Entreprise'),
                        ('Mr. Ahmed Khan', 'ahmed.khan@email.com', '0622334455', '78 Boulevard Anfa', 'Casablanca', 'Particulier')""")
            
            # Fournisseurs
            c.execute("""INSERT INTO fournisseurs (nom, email, telephone, adresse, ville, contact_nom) VALUES 
                        ('TechSupply Maroc', 'contact@techsupply.ma', '0511223344', '12 Rue de la Tech, Casablanca', 'Casablanca', 'Mr. Hassan'),
                        ('GlobalParts Morocco', 'info@globalparts.ma', '0522334455', '45 Avenue du Commerce, Rabat', 'Rabat', 'Mme. Fatima')""")
            
            # Produits
            c.execute("""INSERT INTO produits (nom, description, prix, cout, stock, stock_min, categorie_id) VALUES 
                        ('Ordinateur Portable Dell', 'Core i7, 16GB RAM, 512GB SSD', 8999.99, 6500.00, 15, 3, 1),
                        ('Souris Sans Fil Logitech', 'Souris ergonomique sans fil', 299.99, 150.00, 50, 10, 1),
                        ('Clavier Mécanique RGB', 'Clavier gaming mécanique RGB', 799.99, 450.00, 30, 5, 1),
                        ('Imprimante Laser HP', 'Imprimante laser monochrome', 1899.99, 1200.00, 8, 2, 2)""")
            
            conn.commit()
            
    except Exception as e:
        st.error(f"Erreur initialisation BDD: {e}")
        conn.rollback()
    finally:
        release_connection(conn)

# ========== FONCTIONS UTILITAIRES AMÉLIORÉES ==========
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_login(username, password):
    conn = get_connection()
    try:
        c = conn.cursor()
        password_hash = hash_password(password)
        c.execute("SELECT id, role FROM utilisateurs WHERE username=%s AND password=%s AND actif=true", 
                 (username, password_hash))
        result = c.fetchone()
        return result if result else None
    finally:
        release_connection(conn)

def get_user_permissions(user_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT module, acces_lecture, acces_ecriture, acces_suppression FROM permissions WHERE user_id=%s", (user_id,))
        permissions = {}
        for row in c.fetchall():
            permissions[row[0]] = {
                'lecture': bool(row[1]),
                'ecriture': bool(row[2]),
                'suppression': bool(row[3])
            }
        return permissions
    finally:
        release_connection(conn)

def has_access(module, access_type='lecture'):
    if st.session_state.role == "admin":
        return True
    permissions = st.session_state.get('permissions', {})
    module_perms = permissions.get(module, {'lecture': False, 'ecriture': False, 'suppression': False})
    return module_perms.get(access_type, False)

def log_access(user_id, module, action, details=None):
    conn = get_connection()
    try:
        c = conn.cursor()
        details_json = json.dumps(details) if details else None
        c.execute("INSERT INTO logs_acces (user_id, module, action, details) VALUES (%s, %s, %s, %s)",
                  (user_id, module, action, details_json))
        conn.commit()
    finally:
        release_connection(conn)

# ========== FONCTIONS CRUD GÉNÉRIQUES ==========
def create_record(table, data, user_id, module):
    """Fonction générique pour créer un enregistrement"""
    conn = get_connection()
    try:
        c = conn.cursor()
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        values = tuple(data.values())
        
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING id"
        c.execute(query, values)
        record_id = c.fetchone()[0]
        conn.commit()
        
        log_access(user_id, module, f"Création {table}", {"id": record_id, "data": data})
        return record_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        release_connection(conn)

def update_record(table, record_id, data, user_id, module):
    """Fonction générique pour mettre à jour un enregistrement"""
    conn = get_connection()
    try:
        c = conn.cursor()
        set_clause = ', '.join([f"{key} = %s" for key in data.keys()])
        values = tuple(data.values()) + (record_id,)
        
        query = f"UPDATE {table} SET {set_clause}, date_modification = CURRENT_TIMESTAMP WHERE id = %s"
        c.execute(query, values)
        conn.commit()
        
        log_access(user_id, module, f"Modification {table}", {"id": record_id, "data": data})
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        release_connection(conn)

def delete_record(table, record_id, user_id, module):
    """Fonction générique pour supprimer un enregistrement"""
    conn = get_connection()
    try:
        c = conn.cursor()
        query = f"DELETE FROM {table} WHERE id = %s"
        c.execute(query, (record_id,))
        conn.commit()
        
        log_access(user_id, module, f"Suppression {table}", {"id": record_id})
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        release_connection(conn)

def get_record(table, record_id):
    """Fonction générique pour récupérer un enregistrement"""
    conn = get_connection()
    try:
        query = f"SELECT * FROM {table} WHERE id = %s"
        df = pd.read_sql_query(query, conn, params=(record_id,))
        return df.iloc[0] if not df.empty else None
    finally:
        release_connection(conn)

def get_all_records(table, where_clause="", order_by="id"):
    """Fonction générique pour récupérer tous les enregistrements"""
    conn = get_connection()
    try:
        query = f"SELECT * FROM {table}"
        if where_clause:
            query += f" WHERE {where_clause}"
        if order_by:
            query += f" ORDER BY {order_by}"
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        release_connection(conn)

# ========== FONCTIONS SPÉCIFIQUES AUX MODULES ==========
def get_clients():
    return get_all_records("clients", "actif=true", "nom")

def get_produits():
    conn = get_connection()
    try:
        query = """
        SELECT p.*, c.nom as categorie_nom 
        FROM produits p 
        LEFT JOIN categories c ON p.categorie_id = c.id 
        WHERE p.actif = true
        ORDER BY p.nom
        """
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        release_connection(conn)

def get_categories():
    return get_all_records("categories", "", "nom")

def get_fournisseurs():
    return get_all_records("fournisseurs", "actif=true", "nom")

def get_commandes():
    conn = get_connection()
    try:
        query = """
        SELECT c.*, cl.nom as client_nom,
               (SELECT SUM(montant_ligne) FROM lignes_commandes WHERE commande_id = c.id) as montant_total
        FROM commandes c
        JOIN clients cl ON c.client_id = cl.id
        ORDER BY c.date_creation DESC
        """
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        release_connection(conn)

def get_achats():
    conn = get_connection()
    try:
        query = """
        SELECT a.*, f.nom as fournisseur_nom,
               (SELECT SUM(montant_ligne) FROM lignes_achats WHERE achat_id = a.id) as montant_total
        FROM achats a
        JOIN fournisseurs f ON a.fournisseur_id = f.id
        ORDER BY a.date_creation DESC
        """
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        release_connection(conn)

def get_produits_stock_faible():
    conn = get_connection()
    try:
        query = "SELECT * FROM produits WHERE stock <= stock_min AND actif = true"
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        release_connection(conn)

def generate_numero_commande():
    """Génère un numéro de commande unique"""
    prefix = "CMD"
    date_str = datetime.now().strftime("%Y%m%d")
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM commandes WHERE date_creation::date = CURRENT_DATE")
        count = c.fetchone()[0] + 1
        return f"{prefix}{date_str}{count:04d}"
    finally:
        release_connection(conn)

def generate_numero_achat():
    """Génère un numéro d'achat unique"""
    prefix = "ACH"
    date_str = datetime.now().strftime("%Y%m%d")
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM achats WHERE date_creation::date = CURRENT_DATE")
        count = c.fetchone()[0] + 1
        return f"{prefix}{date_str}{count:04d}"
    finally:
        release_connection(conn)

# ========== GESTION DES SESSIONS ==========
def save_session_to_db(user_id, username, role):
    conn = get_connection()
    try:
        c = conn.cursor()
        import time
        session_id = hashlib.sha256(f"{username}_{time.time()}".encode()).hexdigest()
        
        # Nettoyer anciennes sessions
        c.execute("DELETE FROM sessions WHERE last_activity < NOW() - INTERVAL '1 day'")
        
        # Sauvegarder nouvelle session
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

# ========== PAGE DE CONNEXION ==========
if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col1:
        try:
            if os.path.exists("Logo_ofppt.png"):
                logo = Image.open("Logo_ofppt.png")
                st.image(logo, width=150)
        except:
            st.write("🏢")
    
    with col2:
        st.markdown("""
        <div style="text-align: center;">
            <h1 style="color: #1e3a8a;">🏢 SYGEP ERP</h1>
            <h3 style="color: #3b82f6;">Système de Gestion d'Entreprise Professionnel</h3>
            <p style="color: #64748b; font-size: 14px;">
                <strong>Développé par :</strong> ISMAILI ALAOUI MOHAMED<br>
                <strong>ERP Complet - Gestion Intégrée</strong>
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
                    user_id, role = result
                    session_id = save_session_to_db(user_id, username, role)
                    
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.user_id = user_id
                    st.session_state.role = role
                    st.session_state.permissions = get_user_permissions(user_id)
                    st.session_state.session_id = session_id
                    
                    log_access(user_id, "connexion", "Connexion réussie")
                    st.query_params['session_id'] = session_id
                    
                    st.success("✅ Connexion réussie !")
                    st.rerun()
                else:
                    st.error("❌ Identifiants incorrects ou compte inactif")
        
        st.info("💡 **Compte par défaut**\nUsername: admin\nPassword: admin123")
    
    st.stop()

# ========== INTERFACE PRINCIPALE ==========
col_logo, col_titre, col_date = st.columns([1, 4, 1])

with col_logo:
    try:
        if os.path.exists("Logo_ofppt.png"):
            logo = Image.open("Logo_ofppt.png")
            st.image(logo, width=100)
    except:
        st.write("🏢")

with col_titre:
    st.markdown("""
    <div style="text-align: center;">
        <h1 style="color: #1e3a8a;">🏢 SYGEP - Système de Gestion d'Entreprise Professionnel</h1>
        <p style="color: #64748b; font-size: 14px;">
            ERP Complet avec Gestion des Stocks, Ventes, Achats et Clients
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

st.markdown(f"""
<div style="background: linear-gradient(90deg, #3b82f6 0%, #1e40af 100%); 
            padding: 15px; border-radius: 10px;">
    <h2 style="color: white; margin: 0; text-align: center;">
        👤 Connecté : {st.session_state.username} ({st.session_state.role.upper()}) | 🌐 Mode Professionnel
    </h2>
</div>
""", unsafe_allow_html=True)

# Afficher permissions
if st.session_state.role != "admin":
    with st.sidebar.expander("🔑 Mes Permissions"):
        for module, perms in st.session_state.permissions.items():
            icon = "✅" if perms['lecture'] or perms['ecriture'] or perms['suppression'] else "❌"
            lecture = "📖" if perms['lecture'] else ""
            ecriture = "✏️" if perms['ecriture'] else ""
            suppression = "🗑️" if perms['suppression'] else ""
            st.write(f"{icon} **{module.replace('_', ' ').title()}** {lecture} {ecriture} {suppression}")

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
if has_access("tableau_bord"): menu_items.append("📊 Tableau de Bord")
if has_access("clients"): menu_items.append("👥 Gestion des Clients")
if has_access("categories"): menu_items.append("📁 Catégories Produits")
if has_access("produits"): menu_items.append("📦 Gestion des Produits")
if has_access("fournisseurs"): menu_items.append("🚚 Gestion des Fournisseurs")
if has_access("commandes"): menu_items.append("🛒 Gestion des Commandes")
if has_access("achats"): menu_items.append("📋 Gestion des Achats")
if has_access("rapports"): menu_items.append("📈 Rapports & Analytics")
if has_access("utilisateurs"): menu_items.append("👤 Administration")
menu_items.append("ℹ️ À Propos")

menu = st.sidebar.selectbox("🧭 Navigation", menu_items)

# ========== TABLEAU DE BORD ==========
if menu == "📊 Tableau de Bord":
    if not has_access("tableau_bord"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "tableau_bord", "Consultation")
    st.header("📈 Tableau de Bord SYGEP")
    
    # Alertes
    produits_alerte = get_produits_stock_faible()
    if not produits_alerte.empty:
        st.warning(f"⚠️ **{len(produits_alerte)} produit(s) en stock faible !**")
        with st.expander("Voir les produits en alerte"):
            st.dataframe(produits_alerte[['nom', 'stock', 'stock_min']], use_container_width=True)
    
    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    clients = get_clients()
    produits = get_produits()
    commandes = get_commandes()
    achats = get_achats()
    
    with col1:
        st.metric("👥 Clients Actifs", len(clients))
    with col2:
        st.metric("📦 Produits en Stock", len(produits))
    with col3:
        st.metric("🛒 Commandes", len(commandes))
    with col4:
        ca_total = commandes['montant_total'].sum() if not commandes.empty and 'montant_total' in commandes.columns else 0
        st.metric("💰 CA Total", f"{ca_total:,.2f} €")
    
    st.divider()
    
    # Graphiques
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📦 Niveau de Stock")
        if not produits.empty:
            # Top 10 produits par stock
            top_produits = produits.nlargest(10, 'stock')[['nom', 'stock']]
            st.bar_chart(top_produits.set_index('nom'))
    
    with col2:
        st.subheader("📊 Statut des Commandes")
        if not commandes.empty:
            status_counts = commandes['statut'].value_counts()
            st.bar_chart(status_counts)

    # Dernières activités
    st.subheader("📋 Dernières Commandes")
    if not commandes.empty:
        dernières_commandes = commandes.head(5)[['numero_commande', 'client_nom', 'date_commande', 'statut', 'montant_total']]
        st.dataframe(dernières_commandes, use_container_width=True)

# ========== GESTION DES CLIENTS ==========
elif menu == "👥 Gestion des Clients":
    if not has_access("clients"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "clients", "Consultation")
    st.header("👥 Gestion des Clients")
    
    tab1, tab2, tab3 = st.tabs(["📋 Liste des Clients", "➕ Ajouter Client", "✏️ Modifier Client"])
    
    with tab1:
        clients = get_clients()
        if not clients.empty:
            # Afficher avec des colonnes sélectionnées
            cols_to_show = ['id', 'nom', 'email', 'telephone', 'ville', 'type_client', 'date_creation']
            display_cols = [col for col in cols_to_show if col in clients.columns]
            
            st.dataframe(clients[display_cols], use_container_width=True, hide_index=True)
            
            # Section suppression
            if has_access("clients", "suppression"):
                st.subheader("🗑️ Supprimer un Client")
                col1, col2 = st.columns([3, 1])
                with col1:
                    client_id = st.selectbox("Sélectionner le client à supprimer", 
                                           clients['id'].tolist(),
                                           format_func=lambda x: f"{clients[clients['id']==x]['nom'].iloc[0]} (ID: {x})",
                                           key="delete_client")
                with col2:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Supprimer", key="btn_delete_client"):
                        try:
                            # Vérifier si le client a des commandes
                            conn = get_connection()
                            c = conn.cursor()
                            c.execute("SELECT COUNT(*) FROM commandes WHERE client_id = %s", (int(client_id),))
                            commandes_count = c.fetchone()[0]
                            
                            if commandes_count > 0:
                                st.error("❌ Impossible de supprimer : ce client a des commandes associées")
                            else:
                                delete_record("clients", int(client_id), st.session_state.user_id, "clients")
                                st.success("✅ Client supprimé avec succès")
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de la suppression : {e}")
        else:
            st.info("Aucun client enregistré")
    
    with tab2:
        if not has_access("clients", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            with st.form("form_nouveau_client"):
                col1, col2 = st.columns(2)
                
                with col1:
                    nom = st.text_input("Nom *", placeholder="Raison sociale ou nom complet")
                    email = st.text_input("Email *", placeholder="email@entreprise.com")
                    telephone = st.text_input("Téléphone", placeholder="+212 6XX-XXXXXX")
                    type_client = st.selectbox("Type de client", ["Entreprise", "Particulier", "Administration"])
                
                with col2:
                    adresse = st.text_area("Adresse")
                    ville = st.text_input("Ville", value="Casablanca")
                    code_postal = st.text_input("Code Postal")
                    pays = st.text_input("Pays", value="Maroc")
                
                if st.form_submit_button("💾 Enregistrer le Client"):
                    if nom and email:
                        try:
                            data = {
                                'nom': nom,
                                'email': email,
                                'telephone': telephone,
                                'adresse': adresse,
                                'ville': ville,
                                'code_postal': code_postal,
                                'pays': pays,
                                'type_client': type_client
                            }
                            client_id = create_record("clients", data, st.session_state.user_id, "clients")
                            st.success(f"✅ Client '{nom}' ajouté avec succès (ID: {client_id})")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de l'ajout : {e}")
                    else:
                        st.error("❌ Les champs Nom et Email sont obligatoires")
    
    with tab3:
        if not has_access("clients", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            clients = get_clients()
            if not clients.empty:
                client_id = st.selectbox("Sélectionner le client à modifier", 
                                       clients['id'].tolist(),
                                       format_func=lambda x: f"{clients[clients['id']==x]['nom'].iloc[0]} (ID: {x})",
                                       key="edit_client")
                
                if client_id:
                    client_data = get_record("clients", client_id)
                    if client_data is not None:
                        with st.form("form_modifier_client"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                nom = st.text_input("Nom *", value=client_data['nom'])
                                email = st.text_input("Email *", value=client_data['email'])
                                telephone = st.text_input("Téléphone", value=client_data['telephone'] or "")
                                type_client = st.selectbox("Type de client", 
                                                         ["Entreprise", "Particulier", "Administration"],
                                                         index=["Entreprise", "Particulier", "Administration"].index(client_data['type_client']) if client_data['type_client'] in ["Entreprise", "Particulier", "Administration"] else 0)
                            
                            with col2:
                                adresse = st.text_area("Adresse", value=client_data['adresse'] or "")
                                ville = st.text_input("Ville", value=client_data['ville'] or "Casablanca")
                                code_postal = st.text_input("Code Postal", value=client_data['code_postal'] or "")
                                pays = st.text_input("Pays", value=client_data['pays'] or "Maroc")
                            
                            if st.form_submit_button("💾 Mettre à jour le Client"):
                                if nom and email:
                                    try:
                                        data = {
                                            'nom': nom,
                                            'email': email,
                                            'telephone': telephone,
                                            'adresse': adresse,
                                            'ville': ville,
                                            'code_postal': code_postal,
                                            'pays': pays,
                                            'type_client': type_client
                                        }
                                        update_record("clients", client_id, data, st.session_state.user_id, "clients")
                                        st.success(f"✅ Client '{nom}' modifié avec succès")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Erreur lors de la modification : {e}")
                                else:
                                    st.error("❌ Les champs Nom et Email sont obligatoires")
            else:
                st.info("Aucun client à modifier")

# ========== GESTION DES CATÉGORIES ==========
elif menu == "📁 Catégories Produits":
    if not has_access("categories"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "categories", "Consultation")
    st.header("📁 Gestion des Catégories Produits")
    
    tab1, tab2, tab3 = st.tabs(["📋 Liste", "➕ Ajouter", "✏️ Modifier"])
    
    with tab1:
        categories = get_categories()
        if not categories.empty:
            st.dataframe(categories, use_container_width=True, hide_index=True)
            
            if has_access("categories", "suppression"):
                st.subheader("🗑️ Supprimer une Catégorie")
                col1, col2 = st.columns([3, 1])
                with col1:
                    categorie_id = st.selectbox("Sélectionner la catégorie à supprimer", 
                                              categories['id'].tolist(),
                                              format_func=lambda x: categories[categories['id']==x]['nom'].iloc[0],
                                              key="delete_cat")
                with col2:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Supprimer", key="btn_delete_cat"):
                        try:
                            # Vérifier si la catégorie a des produits
                            conn = get_connection()
                            c = conn.cursor()
                            c.execute("SELECT COUNT(*) FROM produits WHERE categorie_id = %s", (int(categorie_id),))
                            produits_count = c.fetchone()[0]
                            
                            if produits_count > 0:
                                st.error("❌ Impossible de supprimer : des produits sont associés à cette catégorie")
                            else:
                                delete_record("categories", int(categorie_id), st.session_state.user_id, "categories")
                                st.success("✅ Catégorie supprimée avec succès")
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de la suppression : {e}")
        else:
            st.info("Aucune catégorie")
    
    with tab2:
        if not has_access("categories", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            with st.form("form_nouvelle_categorie"):
                nom = st.text_input("Nom de la catégorie *")
                description = st.text_area("Description")
                
                if st.form_submit_button("💾 Créer la Catégorie"):
                    if nom:
                        try:
                            data = {
                                'nom': nom,
                                'description': description
                            }
                            categorie_id = create_record("categories", data, st.session_state.user_id, "categories")
                            st.success(f"✅ Catégorie '{nom}' créée avec succès")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de la création : {e}")
                    else:
                        st.error("❌ Le nom est obligatoire")
    
    with tab3:
        if not has_access("categories", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            categories = get_categories()
            if not categories.empty:
                categorie_id = st.selectbox("Sélectionner la catégorie à modifier", 
                                          categories['id'].tolist(),
                                          format_func=lambda x: categories[categories['id']==x]['nom'].iloc[0],
                                          key="edit_cat")
                
                if categorie_id:
                    categorie_data = get_record("categories", categorie_id)
                    if categorie_data is not None:
                        with st.form("form_modifier_categorie"):
                            nom = st.text_input("Nom *", value=categorie_data['nom'])
                            description = st.text_area("Description", value=categorie_data['description'] or "")
                            
                            if st.form_submit_button("💾 Mettre à jour la Catégorie"):
                                if nom:
                                    try:
                                        data = {
                                            'nom': nom,
                                            'description': description
                                        }
                                        update_record("categories", categorie_id, data, st.session_state.user_id, "categories")
                                        st.success(f"✅ Catégorie '{nom}' modifiée avec succès")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Erreur lors de la modification : {e}")
                                else:
                                    st.error("❌ Le nom est obligatoire")
            else:
                st.info("Aucune catégorie à modifier")

# ========== GESTION DES PRODUITS ==========
elif menu == "📦 Gestion des Produits":
    if not has_access("produits"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "produits", "Consultation")
    st.header("📦 Gestion des Produits")
    
    tab1, tab2, tab3 = st.tabs(["📋 Liste des Produits", "➕ Ajouter Produit", "✏️ Modifier Produit"])
    
    with tab1:
        produits = get_produits()
        if not produits.empty:
            # Colonnes à afficher
            display_cols = ['id', 'nom', 'prix', 'stock', 'stock_min', 'categorie_nom']
            if 'categorie_nom' not in produits.columns:
                display_cols = ['id', 'nom', 'prix', 'stock', 'stock_min']
            
            st.dataframe(produits[display_cols], use_container_width=True, hide_index=True)
            
            # Section ajustement stock
            if has_access("produits", "ecriture"):
                st.subheader("📊 Ajustement de Stock")
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                with col1:
                    prod_id = st.selectbox("Produit", produits['id'].tolist(),
                                          format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0],
                                          key="adjust_stock")
                with col2:
                    ajust_type = st.selectbox("Type", ["Ajouter", "Retirer"], key="adjust_type")
                with col3:
                    quantite = st.number_input("Quantité", min_value=1, value=1, key="adjust_qty")
                with col4:
                    st.write("")
                    st.write("")
                    if st.button("✅ Appliquer", key="btn_adjust"):
                        try:
                            conn = get_connection()
                            c = conn.cursor()
                            current_stock = produits[produits['id'] == prod_id]['stock'].iloc[0]
                            
                            if ajust_type == "Retirer" and current_stock < quantite:
                                st.error("❌ Stock insuffisant")
                            else:
                                adjustment = quantite if ajust_type == "Ajouter" else -quantite
                                c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s", 
                                         (adjustment, int(prod_id)))
                                conn.commit()
                                log_access(st.session_state.user_id, "produits", 
                                         f"Ajustement stock: {adjustment} pour produit {prod_id}")
                                st.success("✅ Stock mis à jour")
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de l'ajustement : {e}")
            
            # Section suppression
            if has_access("produits", "suppression"):
                st.subheader("🗑️ Supprimer un Produit")
                col1, col2 = st.columns([3, 1])
                with col1:
                    prod_id_del = st.selectbox("Sélectionner le produit à supprimer", 
                                             produits['id'].tolist(),
                                             format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0],
                                             key="delete_prod")
                with col2:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Supprimer", key="btn_delete_prod"):
                        try:
                            # Vérifier si le produit a des commandes ou achats
                            conn = get_connection()
                            c = conn.cursor()
                            c.execute("SELECT COUNT(*) FROM lignes_commandes WHERE produit_id = %s", (int(prod_id_del),))
                            commandes_count = c.fetchone()[0]
                            c.execute("SELECT COUNT(*) FROM lignes_achats WHERE produit_id = %s", (int(prod_id_del),))
                            achats_count = c.fetchone()[0]
                            
                            if commandes_count > 0 or achats_count > 0:
                                st.error("❌ Impossible de supprimer : ce produit est utilisé dans des commandes ou achats")
                            else:
                                delete_record("produits", int(prod_id_del), st.session_state.user_id, "produits")
                                st.success("✅ Produit supprimé avec succès")
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de la suppression : {e}")
        else:
            st.info("Aucun produit")
    
    with tab2:
        if not has_access("produits", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            categories = get_categories()
            with st.form("form_nouveau_produit"):
                col1, col2 = st.columns(2)
                
                with col1:
                    nom = st.text_input("Nom du produit *")
                    description = st.text_area("Description")
                    if not categories.empty:
                        categorie_id = st.selectbox("Catégorie", 
                                                  categories['id'].tolist(),
                                                  format_func=lambda x: categories[categories['id']==x]['nom'].iloc[0])
                    else:
                        st.warning("Aucune catégorie disponible. Créez d'abord une catégorie.")
                        categorie_id = None
                    code_barre = st.text_input("Code barre (optionnel)")
                
                with col2:
                    prix = st.number_input("Prix de vente (€) *", min_value=0.0, step=0.01, format="%.2f")
                    cout = st.number_input("Coût (€)", min_value=0.0, step=0.01, format="%.2f")
                    stock = st.number_input("Stock initial", min_value=0, value=0)
                    stock_min = st.number_input("Stock minimum d'alerte", min_value=0, value=10)
                
                if st.form_submit_button("💾 Créer le Produit"):
                    if nom and prix > 0:
                        try:
                            data = {
                                'nom': nom,
                                'description': description,
                                'prix': prix,
                                'cout': cout if cout > 0 else None,
                                'stock': stock,
                                'stock_min': stock_min,
                                'categorie_id': categorie_id if categorie_id else None,
                                'code_barre': code_barre or None
                            }
                            produit_id = create_record("produits", data, st.session_state.user_id, "produits")
                            st.success(f"✅ Produit '{nom}' créé avec succès (ID: {produit_id})")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de la création : {e}")
                    else:
                        st.error("❌ Le nom et le prix sont obligatoires (prix > 0)")
    
    with tab3:
        if not has_access("produits", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            produits = get_produits()
            categories = get_categories()
            
            if not produits.empty:
                produit_id = st.selectbox("Sélectionner le produit à modifier", 
                                        produits['id'].tolist(),
                                        format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0],
                                        key="edit_prod")
                
                if produit_id:
                    produit_data = get_record("produits", produit_id)
                    if produit_data is not None:
                        with st.form("form_modifier_produit"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                nom = st.text_input("Nom du produit *", value=produit_data['nom'])
                                description = st.text_area("Description", value=produit_data['description'] or "")
                                if not categories.empty:
                                    current_cat = produit_data['categorie_id'] if produit_data['categorie_id'] else categories['id'].iloc[0]
                                    categorie_id = st.selectbox("Catégorie", 
                                                              categories['id'].tolist(),
                                                              index=categories['id'].tolist().index(current_cat) if current_cat in categories['id'].tolist() else 0,
                                                              format_func=lambda x: categories[categories['id']==x]['nom'].iloc[0])
                                else:
                                    categorie_id = None
                                code_barre = st.text_input("Code barre", value=produit_data['code_barre'] or "")
                            
                            with col2:
                                prix = st.number_input("Prix de vente (€) *", min_value=0.0, step=0.01, 
                                                     value=float(produit_data['prix']), format="%.2f")
                                cout = st.number_input("Coût (€)", min_value=0.0, step=0.01, 
                                                     value=float(produit_data['cout']) if produit_data['cout'] else 0.0, format="%.2f")
                                stock_min = st.number_input("Stock minimum d'alerte", min_value=0, 
                                                          value=int(produit_data['stock_min']))
                                actif = st.checkbox("Produit actif", value=bool(produit_data['actif']))
                            
                            if st.form_submit_button("💾 Mettre à jour le Produit"):
                                if nom and prix > 0:
                                    try:
                                        data = {
                                            'nom': nom,
                                            'description': description,
                                            'prix': prix,
                                            'cout': cout if cout > 0 else None,
                                            'stock_min': stock_min,
                                            'categorie_id': categorie_id if categorie_id else None,
                                            'code_barre': code_barre or None,
                                            'actif': actif
                                        }
                                        update_record("produits", produit_id, data, st.session_state.user_id, "produits")
                                        st.success(f"✅ Produit '{nom}' modifié avec succès")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Erreur lors de la modification : {e}")
                                else:
                                    st.error("❌ Le nom et le prix sont obligatoires (prix > 0)")
            else:
                st.info("Aucun produit à modifier")

# ========== GESTION DES FOURNISSEURS ==========
elif menu == "🚚 Gestion des Fournisseurs":
    if not has_access("fournisseurs"):
        st.error("❌ Accès refusé")
        st.stop()

    log_access(st.session_state.user_id, "fournisseurs", "Consultation")
    st.header("🚚 Gestion des Fournisseurs")

    tab1, tab2, tab3 = st.tabs(["📋 Liste", "➕ Ajouter", "✏️ Modifier"])

    with tab1:
        fournisseurs = get_fournisseurs()
        if not fournisseurs.empty:
            display_cols = ['id', 'nom', 'email', 'telephone', 'ville', 'contact_nom', 'date_creation']
            st.dataframe(fournisseurs[display_cols], use_container_width=True, hide_index=True)

            if has_access("fournisseurs", "suppression"):
                st.subheader("🗑️ Supprimer un Fournisseur")
                col1, col2 = st.columns([3, 1])
                with col1:
                    fournisseur_id = st.selectbox("Sélectionner le fournisseur à supprimer", 
                                                fournisseurs['id'].tolist(),
                                                format_func=lambda x: fournisseurs[fournisseurs['id']==x]['nom'].iloc[0],
                                                key="delete_fourn")
                with col2:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Supprimer", key="btn_delete_fourn"):
                        try:
                            # Vérifier si le fournisseur a des achats
                            conn = get_connection()
                            c = conn.cursor()
                            c.execute("SELECT COUNT(*) FROM achats WHERE fournisseur_id = %s", (int(fournisseur_id),))
                            achats_count = c.fetchone()[0]
                            
                            if achats_count > 0:
                                st.error("❌ Impossible de supprimer : des achats sont associés à ce fournisseur")
                            else:
                                delete_record("fournisseurs", int(fournisseur_id), st.session_state.user_id, "fournisseurs")
                                st.success("✅ Fournisseur supprimé avec succès")
                                st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de la suppression : {e}")
        else:
            st.info("Aucun fournisseur")

    with tab2:
        if not has_access("fournisseurs", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            with st.form("form_nouveau_fournisseur"):
                col1, col2 = st.columns(2)
                
                with col1:
                    nom = st.text_input("Nom du fournisseur *")
                    email = st.text_input("Email")
                    telephone = st.text_input("Téléphone")
                    contact_nom = st.text_input("Nom du contact")
                
                with col2:
                    adresse = st.text_area("Adresse")
                    ville = st.text_input("Ville", value="Casablanca")
                    code_postal = st.text_input("Code Postal")
                    pays = st.text_input("Pays", value="Maroc")

                if st.form_submit_button("💾 Créer le Fournisseur"):
                    if nom:
                        try:
                            data = {
                                'nom': nom,
                                'email': email,
                                'telephone': telephone,
                                'adresse': adresse,
                                'ville': ville,
                                'code_postal': code_postal,
                                'pays': pays,
                                'contact_nom': contact_nom
                            }
                            fournisseur_id = create_record("fournisseurs", data, st.session_state.user_id, "fournisseurs")
                            st.success(f"✅ Fournisseur '{nom}' créé avec succès (ID: {fournisseur_id})")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de la création : {e}")
                    else:
                        st.error("❌ Le nom est obligatoire")

    with tab3:
        if not has_access("fournisseurs", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            fournisseurs = get_fournisseurs()
            if not fournisseurs.empty:
                fournisseur_id = st.selectbox("Sélectionner le fournisseur à modifier", 
                                            fournisseurs['id'].tolist(),
                                            format_func=lambda x: fournisseurs[fournisseurs['id']==x]['nom'].iloc[0],
                                            key="edit_fourn")
                
                if fournisseur_id:
                    fournisseur_data = get_record("fournisseurs", fournisseur_id)
                    if fournisseur_data is not None:
                        with st.form("form_modifier_fournisseur"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                nom = st.text_input("Nom du fournisseur *", value=fournisseur_data['nom'])
                                email = st.text_input("Email", value=fournisseur_data['email'] or "")
                                telephone = st.text_input("Téléphone", value=fournisseur_data['telephone'] or "")
                                contact_nom = st.text_input("Nom du contact", value=fournisseur_data['contact_nom'] or "")
                            
                            with col2:
                                adresse = st.text_area("Adresse", value=fournisseur_data['adresse'] or "")
                                ville = st.text_input("Ville", value=fournisseur_data['ville'] or "Casablanca")
                                code_postal = st.text_input("Code Postal", value=fournisseur_data['code_postal'] or "")
                                pays = st.text_input("Pays", value=fournisseur_data['pays'] or "Maroc")
                                actif = st.checkbox("Fournisseur actif", value=bool(fournisseur_data['actif']))

                            if st.form_submit_button("💾 Mettre à jour le Fournisseur"):
                                if nom:
                                    try:
                                        data = {
                                            'nom': nom,
                                            'email': email,
                                            'telephone': telephone,
                                            'adresse': adresse,
                                            'ville': ville,
                                            'code_postal': code_postal,
                                            'pays': pays,
                                            'contact_nom': contact_nom,
                                            'actif': actif
                                        }
                                        update_record("fournisseurs", fournisseur_id, data, st.session_state.user_id, "fournisseurs")
                                        st.success(f"✅ Fournisseur '{nom}' modifié avec succès")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"❌ Erreur lors de la modification : {e}")
                                else:
                                    st.error("❌ Le nom est obligatoire")
            else:
                st.info("Aucun fournisseur à modifier")

# ========== GESTION DES COMMANDES ==========
elif menu == "🛒 Gestion des Commandes":
    if not has_access("commandes"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "commandes", "Consultation")
    st.header("🛒 Gestion des Commandes")
    
    tab1, tab2, tab3 = st.tabs(["📋 Liste des Commandes", "➕ Nouvelle Commande", "📝 Gestion Commandes"])
    
    with tab1:
        commandes = get_commandes()
        if not commandes.empty:
            display_cols = ['id', 'numero_commande', 'client_nom', 'date_commande', 'statut', 'montant_total']
            st.dataframe(commandes[display_cols], use_container_width=True, hide_index=True)
        else:
            st.info("Aucune commande")
    
    with tab2:
        if not has_access("commandes", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            clients = get_clients()
            produits = get_produits()
            
            if clients.empty or produits.empty:
                st.warning("⚠️ Il faut au moins 1 client et 1 produit pour créer une commande")
            else:
                with st.form("form_nouvelle_commande"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        client_id = st.selectbox("Client *", clients['id'].tolist(),
                                                format_func=lambda x: clients[clients['id']==x]['nom'].iloc[0])
                        date_commande = st.date_input("Date de commande *", value=datetime.now())
                        date_livraison = st.date_input("Date livraison prévue")
                    
                    with col2:
                        notes = st.text_area("Notes")
                    
                    st.subheader("📦 Produits de la commande")
                    
                    # Interface pour ajouter plusieurs produits
                    if 'lignes_commande' not in st.session_state:
                        st.session_state.lignes_commande = []
                    
                    col_prod, col_qty, col_prix, col_action = st.columns([3, 1, 1, 1])
                    with col_prod:
                        produit_selected = st.selectbox("Produit", produits['id'].tolist(),
                                                      format_func=lambda x: f"{produits[produits['id']==x]['nom'].iloc[0]} - Stock: {produits[produits['id']==x]['stock'].iloc[0]}")
                    with col_qty:
                        quantite = st.number_input("Quantité", min_value=1, value=1)
                    with col_prix:
                        produit_prix = produits[produits['id'] == produit_selected]['prix'].iloc[0]
                        st.info(f"Prix: {produit_prix:.2f} €")
                    with col_action:
                        st.write("")
                        if st.button("➕ Ajouter"):
                            produit_nom = produits[produits['id'] == produit_selected]['nom'].iloc[0]
                            st.session_state.lignes_commande.append({
                                'produit_id': produit_selected,
                                'produit_nom': produit_nom,
                                'quantite': quantite,
                                'prix_unitaire': produit_prix,
                                'montant': quantite * produit_prix
                            })
                            st.rerun()
                    
                    # Afficher les lignes ajoutées
                    if st.session_state.lignes_commande:
                        st.write("**Produits commandés :**")
                        total_commande = 0
                        for i, ligne in enumerate(st.session_state.lignes_commande):
                            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                            with col1:
                                st.write(f"{ligne['produit_nom']}")
                            with col2:
                                st.write(f"Qty: {ligne['quantite']}")
                            with col3:
                                st.write(f"{ligne['prix_unitaire']:.2f} €")
                            with col4:
                                if st.button("🗑️", key=f"del_{i}"):
                                    st.session_state.lignes_commande.pop(i)
                                    st.rerun()
                            total_commande += ligne['montant']
                        
                        st.success(f"**Total commande : {total_commande:.2f} €**")
                    
                    if st.form_submit_button("💾 Créer la Commande"):
                        if st.session_state.lignes_commande:
                            try:
                                conn = get_connection()
                                c = conn.cursor()
                                
                                # Créer la commande
                                numero_commande = generate_numero_commande()
                                c.execute("""INSERT INTO commandes (numero_commande, client_id, date_commande, 
                                            date_livraison_prevue, statut, notes) 
                                            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                                         (numero_commande, int(client_id), date_commande, 
                                          date_livraison, 'En attente', notes))
                                commande_id = c.fetchone()[0]
                                
                                # Ajouter les lignes de commande
                                for ligne in st.session_state.lignes_commande:
                                    c.execute("""INSERT INTO lignes_commandes (commande_id, produit_id, quantite, prix_unitaire)
                                                VALUES (%s, %s, %s, %s)""",
                                             (commande_id, int(ligne['produit_id']), int(ligne['quantite']), float(ligne['prix_unitaire'])))
                                
                                conn.commit()
                                log_access(st.session_state.user_id, "commandes", f"Création commande {numero_commande}")
                                st.session_state.lignes_commande = []
                                st.success(f"✅ Commande {numero_commande} créée avec succès !")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Erreur lors de la création : {e}")
                        else:
                            st.error("❌ Ajoutez au moins un produit à la commande")
    
    with tab3:
        if not has_access("commandes", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            commandes = get_commandes()
            if not commandes.empty:
                st.subheader("📝 Gestion des Commandes")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    commande_id = st.selectbox("Sélectionner la commande", 
                                             commandes['id'].tolist(),
                                             format_func=lambda x: f"{commandes[commandes['id']==x]['numero_commande'].iloc[0]} - {commandes[commandes['id']==x]['client_nom'].iloc[0]}")
                with col2:
                    nouveau_statut = st.selectbox("Nouveau statut", 
                                                ["En attente", "Confirmée", "En préparation", "Expédiée", "Livrée", "Annulée"])
                with col3:
                    st.write("")
                    st.write("")
                    if st.button("✅ Mettre à jour le statut"):
                        try:
                            update_record("commandes", int(commande_id), 
                                        {'statut': nouveau_statut}, 
                                        st.session_state.user_id, "commandes")
                            st.success("✅ Statut de la commande mis à jour")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de la mise à jour : {e}")
                
                # Suppression de commande
                if has_access("commandes", "suppression"):
                    st.subheader("🗑️ Supprimer une Commande")
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        commande_id_del = st.selectbox("Sélectionner la commande à supprimer", 
                                                     commandes['id'].tolist(),
                                                     format_func=lambda x: f"{commandes[commandes['id']==x]['numero_commande'].iloc[0]} - {commandes[commandes['id']==x]['client_nom'].iloc[0]}",
                                                     key="delete_cmd")
                    with col2:
                        st.write("")
                        st.write("")
                        if st.button("🗑️ Supprimer", key="btn_delete_cmd"):
                            try:
                                delete_record("commandes", int(commande_id_del), st.session_state.user_id, "commandes")
                                st.success("✅ Commande supprimée avec succès")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Erreur lors de la suppression : {e}")

# ========== GESTION DES ACHATS ==========
elif menu == "📋 Gestion des Achats":
    if not has_access("achats"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "achats", "Consultation")
    st.header("📋 Gestion des Achats")
    
    tab1, tab2, tab3 = st.tabs(["📋 Liste des Achats", "➕ Nouvel Achat", "📝 Gestion Achats"])
    
    with tab1:
        achats = get_achats()
        if not achats.empty:
            display_cols = ['id', 'numero_achat', 'fournisseur_nom', 'date_achat', 'statut', 'montant_total']
            st.dataframe(achats[display_cols], use_container_width=True, hide_index=True)
        else:
            st.info("Aucun achat")
    
    with tab2:
        if not has_access("achats", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            fournisseurs = get_fournisseurs()
            produits = get_produits()
            
            if fournisseurs.empty or produits.empty:
                st.warning("⚠️ Il faut au moins 1 fournisseur et 1 produit pour créer un achat")
            else:
                with st.form("form_nouvel_achat"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        fournisseur_id = st.selectbox("Fournisseur *", fournisseurs['id'].tolist(),
                                                     format_func=lambda x: fournisseurs[fournisseurs['id']==x]['nom'].iloc[0])
                        date_achat = st.date_input("Date d'achat *", value=datetime.now())
                        date_reception = st.date_input("Date réception prévue")
                    
                    with col2:
                        notes = st.text_area("Notes")
                    
                    st.subheader("📦 Produits à acheter")
                    
                    # Interface pour ajouter plusieurs produits
                    if 'lignes_achat' not in st.session_state:
                        st.session_state.lignes_achat = []
                    
                    col_prod, col_qty, col_prix, col_action = st.columns([3, 1, 1, 1])
                    with col_prod:
                        produit_selected = st.selectbox("Produit", produits['id'].tolist(),
                                                      format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0],
                                                      key="achat_prod")
                    with col_qty:
                        quantite = st.number_input("Quantité", min_value=1, value=1, key="achat_qty")
                    with col_prix:
                        prix_unitaire = st.number_input("Prix unitaire (€)", min_value=0.01, value=0.01, step=0.01, format="%.2f")
                    with col_action:
                        st.write("")
                        if st.button("➕ Ajouter", key="add_achat"):
                            produit_nom = produits[produits['id'] == produit_selected]['nom'].iloc[0]
                            st.session_state.lignes_achat.append({
                                'produit_id': produit_selected,
                                'produit_nom': produit_nom,
                                'quantite': quantite,
                                'prix_unitaire': prix_unitaire,
                                'montant': quantite * prix_unitaire
                            })
                            st.rerun()
                    
                    # Afficher les lignes ajoutées
                    if st.session_state.lignes_achat:
                        st.write("**Produits à acheter :**")
                        total_achat = 0
                        for i, ligne in enumerate(st.session_state.lignes_achat):
                            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                            with col1:
                                st.write(f"{ligne['produit_nom']}")
                            with col2:
                                st.write(f"Qty: {ligne['quantite']}")
                            with col3:
                                st.write(f"{ligne['prix_unitaire']:.2f} €")
                            with col4:
                                if st.button("🗑️", key=f"del_achat_{i}"):
                                    st.session_state.lignes_achat.pop(i)
                                    st.rerun()
                            total_achat += ligne['montant']
                        
                        st.success(f"**Total achat : {total_achat:.2f} €**")
                    
                    if st.form_submit_button("💾 Créer l'Achat"):
                        if st.session_state.lignes_achat:
                            try:
                                conn = get_connection()
                                c = conn.cursor()
                                
                                # Créer l'achat
                                numero_achat = generate_numero_achat()
                                c.execute("""INSERT INTO achats (numero_achat, fournisseur_id, date_achat, 
                                            date_reception_prevue, statut, notes) 
                                            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                                         (numero_achat, int(fournisseur_id), date_achat, 
                                          date_reception, 'En attente', notes))
                                achat_id = c.fetchone()[0]
                                
                                # Ajouter les lignes d'achat
                                for ligne in st.session_state.lignes_achat:
                                    c.execute("""INSERT INTO lignes_achats (achat_id, produit_id, quantite, prix_unitaire)
                                                VALUES (%s, %s, %s, %s)""",
                                             (achat_id, int(ligne['produit_id']), int(ligne['quantite']), float(ligne['prix_unitaire'])))
                                
                                conn.commit()
                                log_access(st.session_state.user_id, "achats", f"Création achat {numero_achat}")
                                st.session_state.lignes_achat = []
                                st.success(f"✅ Achat {numero_achat} créé avec succès !")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Erreur lors de la création : {e}")
                        else:
                            st.error("❌ Ajoutez au moins un produit à l'achat")
    
    with tab3:
        if not has_access("achats", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            achats = get_achats()
            if not achats.empty:
                st.subheader("📝 Gestion des Achats")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    achat_id = st.selectbox("Sélectionner l'achat", 
                                          achats['id'].tolist(),
                                          format_func=lambda x: f"{achats[achats['id']==x]['numero_achat'].iloc[0]} - {achats[achats['id']==x]['fournisseur_nom'].iloc[0]}")
                with col2:
                    nouveau_statut = st.selectbox("Nouveau statut", 
                                                ["En attente", "Confirmé", "En cours", "Reçu", "Annulé"],
                                                key="statut_achat")
                with col3:
                    st.write("")
                    st.write("")
                    if st.button("✅ Mettre à jour le statut"):
                        try:
                            update_record("achats", int(achat_id), 
                                        {'statut': nouveau_statut}, 
                                        st.session_state.user_id, "achats")
                            
                            # Si le statut est "Reçu", mettre à jour les stocks
                            if nouveau_statut == "Reçu":
                                conn = get_connection()
                                c = conn.cursor()
                                # Récupérer les lignes de l'achat
                                c.execute("SELECT produit_id, quantite FROM lignes_achats WHERE achat_id = %s", (int(achat_id),))
                                lignes = c.fetchall()
                                
                                for produit_id, quantite in lignes:
                                    c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s", 
                                             (int(quantite), int(produit_id)))
                                
                                conn.commit()
                                st.info("✅ Stocks mis à jour automatiquement")
                            
                            st.success("✅ Statut de l'achat mis à jour")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de la mise à jour : {e}")
                
                # Suppression d'achat
                if has_access("achats", "suppression"):
                    st.subheader("🗑️ Supprimer un Achat")
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        achat_id_del = st.selectbox("Sélectionner l'achat à supprimer", 
                                                  achats['id'].tolist(),
                                                  format_func=lambda x: f"{achats[achats['id']==x]['numero_achat'].iloc[0]} - {achats[achats['id']==x]['fournisseur_nom'].iloc[0]}",
                                                  key="delete_achat")
                    with col2:
                        st.write("")
                        st.write("")
                        if st.button("🗑️ Supprimer", key="btn_delete_achat"):
                            try:
                                delete_record("achats", int(achat_id_del), st.session_state.user_id, "achats")
                                st.success("✅ Achat supprimé avec succès")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Erreur lors de la suppression : {e}")

# ========== RAPPORTS & ANALYTICS ==========
elif menu == "📈 Rapports & Analytics":
    if not has_access("rapports"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "rapports", "Consultation")
    st.header("📈 Rapports & Analytics")
    
    tab1, tab2, tab3 = st.tabs(["📊 Tableaux de Bord", "📋 Rapports Détaillés", "📤 Exports"])
    
    with tab1:
        st.subheader("Indicateurs Clés de Performance")
        
        # Récupérer les données
        clients = get_clients()
        produits = get_produits()
        commandes = get_commandes()
        achats = get_achats()
        
        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("👥 Clients Actifs", len(clients))
        with col2:
            st.metric("📦 Produits en Stock", len(produits))
        with col3:
            commandes_actives = len(commandes[commandes['statut'].isin(['En attente', 'Confirmée', 'En préparation'])])
            st.metric("🛒 Commandes Actives", commandes_actives)
        with col4:
            ca_total = commandes['montant_total'].sum() if not commandes.empty and 'montant_total' in commandes.columns else 0
            st.metric("💰 Chiffre d'Affaires", f"{ca_total:,.2f} €")
        
        # Graphiques
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📦 Top Produits par Stock")
            if not produits.empty:
                top_produits = produits.nlargest(10, 'stock')[['nom', 'stock']]
                st.bar_chart(top_produits.set_index('nom'))
        
        with col2:
            st.subheader("📊 Répartition des Commandes par Statut")
            if not commandes.empty:
                status_counts = commandes['statut'].value_counts()
                st.bar_chart(status_counts)
    
    with tab2:
        st.subheader("Rapports Détaillés")
        
        rapport_type = st.selectbox("Type de rapport", 
                                  ["Commandes par Client", "Produits les plus Vendus", "Achats par Fournisseur"])
        
        if rapport_type == "Commandes par Client":
            commandes = get_commandes()
            if not commandes.empty:
                commandes_par_client = commandes.groupby('client_nom')['montant_total'].sum().sort_values(ascending=False)
                st.dataframe(commandes_par_client, use_container_width=True)
        
        elif rapport_type == "Produits les plus Vendus":
            # Ce rapport nécessiterait une vue spécifique dans la base de données
            st.info("Fonctionnalité en cours de développement")
        
        elif rapport_type == "Achats par Fournisseur":
            achats = get_achats()
            if not achats.empty:
                achats_par_fournisseur = achats.groupby('fournisseur_nom')['montant_total'].sum().sort_values(ascending=False)
                st.dataframe(achats_par_fournisseur, use_container_width=True)
    
    with tab3:
        st.subheader("Exports de Données")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📥 Exporter Clients"):
                clients = get_clients()
                csv = clients.to_csv(index=False)
                st.download_button(
                    label="💾 Télécharger CSV",
                    data=csv,
                    file_name=f"clients_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            if st.button("📥 Exporter Produits"):
                produits = get_produits()
                csv = produits.to_csv(index=False)
                st.download_button(
                    label="💾 Télécharger CSV",
                    data=csv,
                    file_name=f"produits_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
        
        with col3:
            if st.button("📥 Exporter Commandes"):
                commandes = get_commandes()
                csv = commandes.to_csv(index=False)
                st.download_button(
                    label="💾 Télécharger CSV",
                    data=csv,
                    file_name=f"commandes_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

# ========== ADMINISTRATION ==========
elif menu == "👤 Administration":
    if not has_access("utilisateurs"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "utilisateurs", "Consultation")
    st.header("👤 Administration du Système")
    
    tab1, tab2, tab3, tab4 = st.tabs(["👥 Utilisateurs", "🔑 Permissions", "📊 Logs", "➕ Nouvel Utilisateur"])
    
    with tab1:
        st.subheader("📋 Liste des Utilisateurs")
        conn = get_connection()
        try:
            users = pd.read_sql_query("SELECT id, username, email, role, actif, date_creation FROM utilisateurs ORDER BY id", conn)
            st.dataframe(users, use_container_width=True, hide_index=True)
            
            # Section suppression utilisateur
            if has_access("utilisateurs", "suppression"):
                st.subheader("🗑️ Gestion des Utilisateurs")
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    user_id = st.selectbox("Sélectionner l'utilisateur", 
                                         users['id'].tolist(),
                                         format_func=lambda x: f"{users[users['id']==x]['username'].iloc[0]} ({users[users['id']==x]['role'].iloc[0]})")
                with col2:
                    nouvelle_activite = st.selectbox("Statut", ["Actif", "Inactif"])
                with col3:
                    st.write("")
                    if st.button("🔄 Mettre à jour"):
                        try:
                            update_record("utilisateurs", int(user_id), 
                                        {'actif': nouvelle_activite == "Actif"}, 
                                        st.session_state.user_id, "utilisateurs")
                            st.success("✅ Statut utilisateur mis à jour")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de la mise à jour : {e}")
                    
                    st.write("")
                    if st.button("🗑️ Supprimer"):
                        if users[users['id']==user_id]['username'].iloc[0] == st.session_state.username:
                            st.error("❌ Impossible de vous auto-supprimer")
                        else:
                            try:
                                delete_record("utilisateurs", int(user_id), st.session_state.user_id, "utilisateurs")
                                st.success("✅ Utilisateur supprimé")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Erreur lors de la suppression : {e}")
        finally:
            release_connection(conn)
    
    with tab2:
        st.subheader("🔑 Gestion des Permissions")
        conn = get_connection()
        try:
            users = pd.read_sql_query("SELECT id, username, role FROM utilisateurs WHERE actif = true", conn)
            user_sel = st.selectbox("Utilisateur", users['id'].tolist(),
                                   format_func=lambda x: f"{users[users['id']==x]['username'].iloc[0]} ({users[users['id']==x]['role'].iloc[0]})",
                                   key="perm_user")
            
            st.divider()
            
            c = conn.cursor()
            c.execute("SELECT module, acces_lecture, acces_ecriture, acces_suppression FROM permissions WHERE user_id=%s", (user_sel,))
            perms = {r[0]: {'lecture': bool(r[1]), 'ecriture': bool(r[2]), 'suppression': bool(r[3])} for r in c.fetchall()}
            
            modules = ["tableau_bord", "clients", "categories", "produits", "fournisseurs", "commandes", "achats", "rapports", "utilisateurs"]
            new_perms = {}
            
            for mod in modules:
                st.write(f"**{mod.replace('_', ' ').title()}**")
                col1, col2, col3 = st.columns(3)
                current = perms.get(mod, {'lecture': False, 'ecriture': False, 'suppression': False})
                with col1:
                    lec = st.checkbox(f"📖 Lecture", value=current['lecture'], key=f"{mod}_lec")
                with col2:
                    ecr = st.checkbox(f"✏️ Écriture", value=current['ecriture'], key=f"{mod}_ecr")
                with col3:
                    supp = st.checkbox(f"🗑️ Suppression", value=current['suppression'], key=f"{mod}_supp")
                new_perms[mod] = {'lecture': lec, 'ecriture': ecr, 'suppression': supp}
                st.divider()
            
            if st.button("💾 Enregistrer Permissions", type="primary", use_container_width=True):
                user_sel_py = int(user_sel)
                c.execute("DELETE FROM permissions WHERE user_id=%s", (user_sel_py,))
                for mod, p in new_perms.items():
                    if p['lecture'] or p['ecriture'] or p['suppression']:
                        c.execute("INSERT INTO permissions (user_id, module, acces_lecture, acces_ecriture, acces_suppression) VALUES (%s, %s, %s, %s, %s)",
                                  (user_sel_py, mod, p['lecture'], p['ecriture'], p['suppression']))
                conn.commit()
                log_access(st.session_state.user_id, "utilisateurs", f"MAJ permissions ID:{user_sel}")
                st.success("✅ Permissions mises à jour")
                st.rerun()
        finally:
            release_connection(conn)
    
    with tab3:
        st.subheader("📊 Logs d'Activité")
        conn = get_connection()
        try:
            logs = pd.read_sql_query("""
                SELECT l.date_heure, u.username, l.module, l.action, l.details
                FROM logs_acces l
                JOIN utilisateurs u ON l.user_id = u.id
                ORDER BY l.date_heure DESC
                LIMIT 200
            """, conn)
            
            if not logs.empty:
                st.dataframe(logs, use_container_width=True, hide_index=True)
            else:
                st.info("Aucun log d'activité")
        finally:
            release_connection(conn)
    
    with tab4:
        st.subheader("➕ Créer un Nouvel Utilisateur")
        if has_access("utilisateurs", "ecriture"):
            with st.form("form_nouvel_utilisateur"):
                col1, col2 = st.columns(2)
                
                with col1:
                    username = st.text_input("Nom d'utilisateur *")
                    email = st.text_input("Email")
                    role = st.selectbox("Rôle", ["user", "manager", "admin"])
                
                with col2:
                    password = st.text_input("Mot de passe *", type="password")
                    password_confirm = st.text_input("Confirmer le mot de passe *", type="password")
                    actif = st.checkbox("Utilisateur actif", value=True)
                
                if st.form_submit_button("💾 Créer l'Utilisateur"):
                    if username and password:
                        if password == password_confirm:
                            try:
                                data = {
                                    'username': username,
                                    'password': hash_password(password),
                                    'email': email,
                                    'role': role,
                                    'actif': actif
                                }
                                user_id = create_record("utilisateurs", data, st.session_state.user_id, "utilisateurs")
                                st.success(f"✅ Utilisateur '{username}' créé avec succès (ID: {user_id})")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Erreur lors de la création : {e}")
                        else:
                            st.error("❌ Les mots de passe ne correspondent pas")
                    else:
                        st.error("❌ Le nom d'utilisateur et le mot de passe sont obligatoires")
        else:
            st.warning("⚠️ Pas de droits d'écriture pour créer des utilisateurs")

# ========== À PROPOS ==========
elif menu == "ℹ️ À Propos":
    st.header("ℹ️ À Propos de SYGEP ERP")
    
    st.success("""
    ### 🏢 SYGEP ERP - Système de Gestion d'Entreprise Professionnel
    
    **Version 4.0 - ERP Complet avec Gestion Intégrée**
    
    ✅ **Fonctionnalités Principales :**
    - Gestion complète des clients et fournisseurs
    - Catalogue produits avec catégories
    - Gestion des stocks avec alertes automatiques
    - Commandes clients et achats fournisseurs
    - Tableaux de bord et rapports analytiques
    - Gestion des utilisateurs et permissions
    - Logs d'activité complets
    
    ✅ **Nouvelles Améliorations :**
    - CRUD complet (Create, Read, Update, Delete)
    - Interface utilisateur améliorée
    - Gestion des relations entre tables
    - Validation des données avancée
    - Export des données
    - Gestion des états et statuts
    """)
    
    st.markdown("""
    ### 🎯 Objectifs Professionnels
    
    Ce système ERP permet de :
    - Centraliser toutes les données de l'entreprise
    - Automatiser les processus métier
    - Améliorer la productivité et la traçabilité
    - Prendre des décisions basées sur des données fiables
    - Collaborer efficacement entre départements
    
    ### 📚 Modules Implémentés
    
    - **Tableau de Bord** : KPIs et indicateurs en temps réel
    - **CRM** : Gestion complète de la relation client
    - **Catalogue** : Produits, catégories et stocks
    - **Fournisseurs** : Gestion des partenaires
    - **Ventes** : Commandes clients et facturation
    - **Achats** : Approvisionnements et réceptions
    - **Rapports** : Business Intelligence et analytics
    - **Administration** : Sécurité et paramétrage
    
    ### 🔧 Architecture Technique
    
    - **Frontend** : Streamlit (Interface moderne)
    - **Backend** : PostgreSQL (Base de données relationnelle)
    - **Sécurité** : Authentification SHA-256, permissions granulaires
    - **Hébergement** : Compatible Streamlit Cloud, Heroku, etc.
    
    ### 👨‍💼 Développeur
    
    **ISMAILI ALAOUI MOHAMED**  
    Expert en Développement d'Applications de Gestion
    
    ---
    
    *SYGEP ERP v4.0 - Système Professionnel de Gestion Intégrée*
    """)

# Footer sidebar
st.sidebar.markdown("---")
date_footer = datetime.now().strftime('%d/%m/%Y')
st.sidebar.markdown(f"""
<div style="background-color: #f8fafc; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0;">
    <p style="margin: 0; font-size: 11px; color: #64748b; text-align: center;">
        <strong style="color: #1e40af;">SYGEP ERP v4.0</strong><br>
        🏢 Mode Professionnel
    </p>
    <hr style="margin: 10px 0; border: 0; border-top: 1px solid #cbd5e1;">
    <p style="margin: 0; font-size: 10px; color: #64748b; text-align: center;">
        Développé par<br>
        <strong style="color: #1e3a8a;">ISMAILI ALAOUI MOHAMED</strong><br>
        Expert en Systèmes de Gestion
    </p>
    <hr style="margin: 10px 0; border: 0; border-top: 1px solid #cbd5e1;">
    <p style="margin: 0; font-size: 10px; color: #64748b; text-align: center;">
        📅 {date_footer}<br>
        Session: <strong>{st.session_state.username}</strong>
    </p>
</div>
""", unsafe_allow_html=True)

with st.sidebar.expander("ℹ️ Info Session"):
    st.write(f"**User ID:** {st.session_state.user_id}")
    st.write(f"**Rôle:** {st.session_state.role}")
    if st.session_state.session_id:
        st.write(f"**Session ID:** {st.session_state.session_id[:8]}...")
    st.write("**Statut:** 🟢 Connecté")
    st.write("**Mode:** 🏢 Professionnel")
    st.caption("Base de données PostgreSQL relationnelle")
