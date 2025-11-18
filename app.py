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
        
        # Table Logs améliorée - CORRECTION DE LA COLONNE DETAILS
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
    """Fonction de logging améliorée avec gestion des erreurs"""
    conn = get_connection()
    try:
        c = conn.cursor()
        
        # Vérifier si la colonne details existe
        c.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='logs_acces' AND column_name='details'
        """)
        has_details_column = c.fetchone() is not None
        
        if has_details_column:
            details_json = json.dumps(details) if details else None
            c.execute("INSERT INTO logs_acces (user_id, module, action, details) VALUES (%s, %s, %s, %s)",
                     (user_id, module, action, details_json))
        else:
            # Fallback si la colonne details n'existe pas
            action_with_details = action
            if details:
                action_with_details = f"{action} - {json.dumps(details)}"
            c.execute("INSERT INTO logs_acces (user_id, module, action) VALUES (%s, %s, %s)",
                     (user_id, module, action_with_details))
        
        conn.commit()
    except Exception as e:
        # Log l'erreur mais ne pas bloquer l'application
        print(f"Erreur lors du logging: {e}")
        conn.rollback()
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
                            st
