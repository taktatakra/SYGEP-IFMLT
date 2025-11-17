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
    page_title="SYGEP - Système de Gestion d'Entreprise Pédagogique",
    layout="wide",
    page_icon="🎓",
    initial_sidebar_state="expanded"
)

# ========== GESTION CONNEXION POSTGRESQL (SUPABASE) ==========

# Pool de connexions pour de meilleures performances
@st.cache_resource
def init_connection_pool():
    """Initialise un pool de connexions PostgreSQL"""
    try:
        # Essayer avec les variables d'environnement
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
    pool = init_connection_pool()
    return pool.getconn()

def release_connection(conn):
    """Libère une connexion vers le pool"""
    pool = init_connection_pool()
    pool.putconn(conn)

# ========== INITIALISATION BASE DE DONNÉES ==========
def init_database():
    """Initialise les tables PostgreSQL"""
    conn = get_connection()
    try:
        c = conn.cursor()
        
        # Table Utilisateurs
        c.execute('''CREATE TABLE IF NOT EXISTS utilisateurs
                     (id SERIAL PRIMARY KEY,
                      username VARCHAR(100) UNIQUE NOT NULL,
                      password VARCHAR(255) NOT NULL,
                      role VARCHAR(50) NOT NULL,
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
                      date_creation DATE)''')
        
        # Table Produits
        c.execute('''CREATE TABLE IF NOT EXISTS produits
                     (id SERIAL PRIMARY KEY,
                      nom VARCHAR(255) NOT NULL,
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
        
        # Table Commandes
        c.execute('''CREATE TABLE IF NOT EXISTS commandes
                     (id SERIAL PRIMARY KEY,
                      client_id INTEGER REFERENCES clients(id),
                      produit_id INTEGER REFERENCES produits(id),
                      quantite INTEGER,
                      date DATE,
                      statut VARCHAR(50))''')
        
        # Table Achats
        c.execute('''CREATE TABLE IF NOT EXISTS achats
                     (id SERIAL PRIMARY KEY,
                      fournisseur_id INTEGER REFERENCES fournisseurs(id),
                      produit_id INTEGER REFERENCES produits(id),
                      quantite INTEGER,
                      prix_unitaire DECIMAL(10,2),
                      date DATE,
                      statut VARCHAR(50))''')
        
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
        
        # Créer utilisateur admin par défaut si n'existe pas
        c.execute("SELECT COUNT(*) FROM utilisateurs WHERE username = %s", ('admin',))
        if c.fetchone()[0] == 0:
            password_hash = hashlib.sha256("admin123".encode()).hexdigest()
            c.execute("INSERT INTO utilisateurs (username, password, role) VALUES (%s, %s, %s) RETURNING id",
                      ('admin', password_hash, 'admin'))
            user_id = c.fetchone()[0]
            
            # Donner tous les droits à l'admin
            modules = ["tableau_bord", "clients", "produits", "fournisseurs", "commandes", "achats", "rapports", "utilisateurs"]
            for module in modules:
                c.execute("INSERT INTO permissions (user_id, module, acces_lecture, acces_ecriture) VALUES (%s, %s, %s, %s)",
                          (user_id, module, True, True))
            
            conn.commit()
        
        # Ajouter données de démonstration si tables vides
        c.execute("SELECT COUNT(*) FROM clients")
        if c.fetchone()[0] == 0:
            # Clients
            c.execute("""INSERT INTO clients (nom, email, telephone, date_creation) VALUES 
                        ('Entreprise Alpha', 'contact@alpha.com', '0612345678', CURRENT_DATE),
                        ('Société Beta', 'info@beta.com', '0698765432', CURRENT_DATE)""")
            
            # Produits
            c.execute("""INSERT INTO produits (nom, prix, stock, seuil_alerte) VALUES 
                        ('Ordinateur Portable', 899.99, 15, 5),
                        ('Souris Sans Fil', 29.99, 50, 20),
                        ('Clavier Mécanique', 79.99, 30, 10)""")
            
            # Fournisseurs
            c.execute("""INSERT INTO fournisseurs (nom, email, telephone, adresse, date_creation) VALUES 
                        ('TechSupply Co', 'contact@techsupply.com', '0511223344', '12 Rue de la Tech, Paris', CURRENT_DATE),
                        ('GlobalParts', 'info@globalparts.com', '0522334455', '45 Avenue du Commerce, Lyon', CURRENT_DATE)""")
            
            # Commandes
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
    if st.session_state.role == "admin":
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
        df = pd.read_sql_query("SELECT * FROM commandes ORDER BY id", conn)
        return df
    finally:
        release_connection(conn)

def get_achats():
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM achats ORDER BY id", conn)
        return df
    finally:
        release_connection(conn)

def save_session_to_db(user_id, username, role):
    conn = get_connection()
    session_id = hashlib.sha256(os.urandom(60)).hexdigest()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO sessions (session_id, user_id, username, role, last_activity) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)",
                  (session_id, user_id, username, role))
        conn.commit()
        return session_id
    finally:
        release_connection(conn)

def load_session_from_db(session_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT user_id, username, role FROM sessions WHERE session_id=%s AND last_activity > CURRENT_TIMESTAMP - INTERVAL '1 day'", (session_id,))
        result = c.fetchone()
        if result:
            c.execute("UPDATE sessions SET last_activity=CURRENT_TIMESTAMP WHERE session_id=%s", (session_id,))
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
            log_access(user_id, "connexion", "Reconnexion via session persistante")
            st.rerun()

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
            <h1 style="color: #1e3a8a;">🎓 SYGEP v3.0</h1>
            <h3 style="color: #3b82f6;">Système de Gestion d'Entreprise Pédagogique</h3>
            <h4 style="color: #64748b;">Version PostgreSQL</h4>
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
            <p style="margin: 0; font-size: 13px;">📅 {datetime.now().strftime('%d/%m/%Y')}</p>
            <p style="font-size: 13px;">🕐 {datetime.now().strftime('%H:%M:%S')}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    
    col_login, col_info = st.columns(2)
    
    with col_login:
        st.subheader("🔑 Connexion Utilisateur")
        with st.form("login_form"):
            username = st.text_input("Nom d'utilisateur")
            password = st.text_input("Mot de passe", type="password")
            remember = st.checkbox("Se souvenir de moi")
            
            submitted = st.form_submit_button("Se connecter", use_container_width=True)
            
            if submitted:
                user_data = verify_login(username, password)
                if user_data:
                    user_id, role = user_data
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.user_id = user_id
                    st.session_state.role = role
                    st.session_state.permissions = get_user_permissions(user_id)
                    
                    if remember:
                        session_id = save_session_to_db(user_id, username, role)
                        st.session_state.session_id = session_id
                        # Mettre à jour l'URL (Streamlit Cloud ne supporte pas toujours les query params en local)
                        # st.query_params['session_id'] = session_id
                    
                    log_access(user_id, "connexion", "Connexion réussie")
                    st.success("✅ Connexion réussie!")
                    st.rerun()
                else:
                    st.error("❌ Nom d'utilisateur ou mot de passe incorrect.")

    with col_info:
        st.subheader("ℹ️ Informations")
        st.info("Utilisez le compte administrateur par défaut:\n\n- **Username:** `admin`\n- **Password:** `admin123`")
        st.markdown("""
        Ce système est un outil pédagogique simulant un Progiciel de Gestion Intégré (ERP).
        
        **Modules disponibles:**
        - **Tableau de Bord** : Indicateurs clés
        - **Clients** : Gestion des fiches clients
        - **Produits** : Inventaire et gestion des stocks
        - **Fournisseurs** : Partenaires d'approvisionnement
        - **Commandes** : Commandes clients
        - **Achats** : Achats fournisseurs
        - **Rapports** : Analyse et exports
        - **Utilisateurs** : Gestion des accès (Admin)
        """)

# ========== APPLICATION PRINCIPALE ==========
else:
    # Barre latérale
    st.sidebar.markdown(f"## Bienvenue, {st.session_state.username} ({st.session_state.role})")
    
    # Bouton déconnexion
    if st.sidebar.button("🚪 Se déconnecter", use_container_width=True):
        if st.session_state.session_id:
            delete_session_from_db(st.session_state.session_id)
        log_access(st.session_state.user_id, "deconnexion", "Déconnexion")
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    
    st.sidebar.divider()
    
    # Menu navigation
    menu_items = []
    if has_access("tableau_bord"):
        menu_items.append("🏠 Tableau de Bord")
    if has_access("clients"):
        menu_items.append("👥 Gestion Clients")
    if has_access("produits"):
        menu_items.append("📦 Gestion Produits")
    if has_access("fournisseurs"):
        menu_items.append("🏭 Gestion Fournisseurs")
    if has_access("commandes"):
        menu_items.append("🛒 Gestion Commandes")
    if has_access("achats"):
        menu_items.append("📈 Gestion Achats")
    if has_access("rapports"):
        menu_items.append("📊 Rapports & Analytics")
    if has_access("utilisateurs"):
        menu_items.append("⚙️ Administration Utilisateurs")
    
    menu = st.sidebar.selectbox("Navigation", menu_items)
    st.sidebar.markdown("---")

    # Contenu de la page
    
    # ========== TABLEAU DE BORD ==========
    if menu == "🏠 Tableau de Bord":
        if not has_access("tableau_bord"):
            st.error("❌ Accès refusé")
            st.stop()
            
        log_access(st.session_state.user_id, "tableau_bord", "Consultation")
        st.title("🏠 Tableau de Bord")
        
        # Exemple de métriques
        
        col1, col2, col3, col4 = st.columns(4)
        
        conn = get_connection()
        
        with col1:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM clients")
            nb_clients = c.fetchone()[0]
            st.metric("Clients", nb_clients)

        with col2:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM produits WHERE stock <= seuil_alerte")
            nb_alertes_stock = c.fetchone()[0]
            st.metric("Alertes Stock", nb_alertes_stock, delta_color="inverse")

        with col3:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM commandes WHERE statut='En cours'")
            nb_cmd_cours = c.fetchone()[0]
            st.metric("Commandes en cours", nb_cmd_cours)
        
        with col4:
            c = conn.cursor()
            c.execute("SELECT SUM(quantite * prix) FROM commandes JOIN produits ON commandes.produit_id = produits.id WHERE date >= CURRENT_DATE - INTERVAL '30 days'")
            ca_mois = c.fetchone()[0] or 0
            st.metric("CA (30 jours)", f"{ca_mois:.2f} DH")
            
        release_connection(conn)
            
        st.markdown("---")
        
        # Graphiques
        st.subheader("Tendances")
        col_graph1, col_graph2 = st.columns(2)
        
        with col_graph1:
            st.write("Évolution des Stocks")
            produits = get_produits()
            if not produits.empty:
                st.bar_chart(produits, x='nom', y='stock')
        
        with col_graph2:
            st.write("Statut des Commandes")
            commandes = get_commandes()
            if not commandes.empty:
                statut_counts = commandes['statut'].value_counts()
                st.pie_chart(statut_counts)

    # ========== GESTION DES CLIENTS ==========
    elif menu == "👥 Gestion Clients":
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
                        client_id = st.selectbox("Supprimer", clients['id'].tolist(),
                                                format_func=lambda x: clients[clients['id']==x]['nom'].iloc[0])
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
                        if nom:
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("""INSERT INTO clients (nom, email, telephone, date_creation) 
                                            VALUES (%s, %s, %s, CURRENT_DATE)""",
                                         (nom, email, telephone))
                                conn.commit()
                                log_access(st.session_state.user_id, "clients", f"Ajout: {nom}")
                                st.success(f"✅ Client '{nom}' ajouté !")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erreur d'insertion: {e}")
                                conn.rollback()
                            finally:
                                release_connection(conn)
                        else:
                            st.error("Nom requis")

    # ========== GESTION DES PRODUITS ==========
    elif menu == "📦 Gestion Produits":
        if not has_access("produits"):
            st.error("❌ Accès refusé")
            st.stop()
            
        log_access(st.session_state.user_id, "produits", "Consultation")
        st.header("📦 Gestion des Produits")
        
        tab1, tab2 = st.tabs(["Liste", "Ajouter"])
        
        with tab1:
            produits = get_produits()
            if not produits.empty:
                produits['Statut Stock'] = produits.apply(
                    lambda r: '🔴 Alerte' if r['stock'] <= r['seuil_alerte'] else '🟢 OK', axis=1)
                st.dataframe(produits, use_container_width=True, hide_index=True)
                
                if has_access("produits", "ecriture"):
                    st.divider()
                    st.subheader("📝 Ajuster Stock")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        prod_id = st.selectbox("Produit", produits['id'].tolist(),
                                              format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0])
                    with col2:
                        ajust = st.number_input("Ajustement (+/-)", value=0, step=1)
                    with col3:
                        st.write("")
                        st.write("")
                        if st.button("✅ Appliquer"):
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s", (ajust, prod_id))
                                conn.commit()
                                log_access(st.session_state.user_id, "produits", f"Ajustement stock {prod_id} par {ajust}")
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
                    prix = st.number_input("Prix (DH) *", min_value=0.01, step=0.01)
                    stock = st.number_input("Stock initial", min_value=0, step=1)
                    seuil = st.number_input("Seuil d'alerte", min_value=0, step=1, value=10)
                    
                    if st.form_submit_button("Enregistrer"):
                        if nom and prix > 0:
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("""INSERT INTO produits (nom, prix, stock, seuil_alerte) 
                                            VALUES (%s, %s, %s, %s)""",
                                         (nom, prix, stock, seuil))
                                conn.commit()
                                log_access(st.session_state.user_id, "produits", f"Ajout: {nom}")
                                st.success(f"✅ Produit '{nom}' ajouté !")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erreur d'insertion: {e}")
                                conn.rollback()
                            finally:
                                release_connection(conn)
                        else:
                            st.error("Nom et prix > 0 requis")

    # ========== GESTION DES FOURNISSEURS ==========
    elif menu == "🏭 Gestion Fournisseurs":
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
                                c.execute("""INSERT INTO fournisseurs (nom, email, telephone, adresse, date_creation) 
                                            VALUES (%s, %s, %s, %s, CURRENT_DATE)""",
                                         (nom, email, telephone, adresse))
                                conn.commit()
                                log_access(st.session_state.user_id, "fournisseurs", f"Ajout: {nom}")
                                st.success(f"✅ Fournisseur '{nom}' ajouté !")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erreur d'insertion: {e}")
                                conn.rollback()
                            finally:
                                release_connection(conn)
                        else:
                            st.error("Nom requis")

    # ========== GESTION DES COMMANDES ==========
    elif menu == "🛒 Gestion Commandes":
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
                    st.subheader("📝 Changer Statut")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        cmd_id = st.selectbox("Commande N°", commandes['id'].tolist())
                    with col2:
                        statut = st.selectbox("Statut", ["En attente", "En cours", "Livrée", "Annulée"])
                    with col3:
                        st.write("")
                        st.write("")
                        if st.button("✅ Mettre à jour"):
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("UPDATE commandes SET statut = %s WHERE id = %s", (statut, cmd_id))
                                conn.commit()
                                log_access(st.session_state.user_id, "commandes", f"Mise à jour statut CMD:{cmd_id} à {statut}")
                                st.success("✅ Statut mis à jour")
                                st.rerun()
                            finally:
                                release_connection(conn)
            else:
                st.info("Aucune commande")
        
        with tab2:
            if not has_access("commandes", "ecriture"):
                st.warning("⚠️ Pas de droits d'écriture")
            else:
                clients = get_clients()
                produits = get_produits()
                
                if clients.empty or produits.empty:
                    st.error("❌ Veuillez d'abord ajouter des clients et des produits.")
                else:
                    with st.form("form_commande"):
                        client_id = st.selectbox("Client *", clients['id'].tolist(),
                                                 format_func=lambda x: clients[clients['id']==x]['nom'].iloc[0])
                        produit_id = st.selectbox("Produit *", produits['id'].tolist(),
                                                  format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0])
                        quantite = st.number_input("Quantité *", min_value=1, step=1)
                        date = st.date_input("Date de la commande", datetime.now())
                        statut = st.selectbox("Statut initial", ["En attente", "En cours"])
                        
                        if st.form_submit_button("Créer la Commande"):
                            if quantite > 0:
                                conn = get_connection()
                                try:
                                    c = conn.cursor()
                                    c.execute("""INSERT INTO commandes (client_id, produit_id, quantite, date, statut) 
                                                VALUES (%s, %s, %s, %s, %s)""",
                                             (client_id, produit_id, quantite, date, statut))
                                    conn.commit()
                                    log_access(st.session_state.user_id, "commandes", f"Création CMD pour client:{client_id}")
                                    st.success("✅ Commande créée !")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erreur d'insertion: {e}")
                                    conn.rollback()
                                finally:
                                    release_connection(conn)
                            else:
                                st.error("La quantité doit être supérieure à zéro")

    # ========== GESTION DES ACHATS ==========
    elif menu == "📈 Gestion Achats":
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
                        fournisseur_id = st.selectbox("Fournisseur *", fournisseurs['id'].tolist(),
                                                      format_func=lambda x: fournisseurs[fournisseurs['id']==x]['nom'].iloc[0])
                        produit_id = st.selectbox("Produit *", produits['id'].tolist(),
                                                  format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0])
                        quantite = st.number_input("Quantité *", min_value=1, step=1)
                        prix_unitaire = st.number_input("Prix Unitaire (DH) *", min_value=0.01, step=0.01)
                        date = st.date_input("Date de l'achat", datetime.now())
                        statut = st.selectbox("Statut initial", ["En attente", "Commandé"])
                        
                        if st.form_submit_button("Enregistrer l'Achat"):
                            if quantite > 0 and prix_unitaire > 0:
                                conn = get_connection()
                                try:
                                    c = conn.cursor()
                                    c.execute("""INSERT INTO achats (fournisseur_id, produit_id, quantite, prix_unitaire, date, statut) 
                                                VALUES (%s, %s, %s, %s, %s, %s)""",
                                             (fournisseur_id, produit_id, quantite, prix_unitaire, date, statut))
                                    conn.commit()
                                    log_access(st.session_state.user_id, "achats", f"Création Achat pour fournisseur:{fournisseur_id}")
                                    st.success("✅ Achat enregistré !")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erreur d'insertion: {e}")
                                    conn.rollback()
                                finally:
                                    release_connection(conn)
                            else:
                                st.error("Quantité et prix unitaire doivent être supérieurs à zéro")

    # ========== RAPPORTS & ANALYTICS ==========
    elif menu == "📊 Rapports & Analytics":
        if not has_access("rapports"):
            st.error("❌ Accès refusé")
            st.stop()
            
        log_access(st.session_state.user_id, "rapports", "Consultation")
        st.header("📊 Rapports & Analytics")
        
        tab1, tab2 = st.tabs(["KPIs et Graphiques", "Logs d'Accès"])
        
        with tab1:
            st.subheader("Indicateurs Clés")
            col1, col2, col3 = st.columns(3)
            
            commandes = get_commandes()
            achats = get_achats()
            
            with col1:
                # Total Commandes Livrées
                nb_livrees = len(commandes[commandes['statut'] == 'Livrée'])
                st.metric("Commandes Livrées (Total)", nb_livrees)
            
            with col2:
                # Valeur des achats commandés (non reçus)
                valeur_achats_encours = (achats[achats['statut'] == 'Commandé']['quantite'] * achats[achats['statut'] == 'Commandé']['prix_unitaire']).sum()
                st.metric("Valeur Achats Commandés", f"{valeur_achats_encours:.2f} DH")
                
            with col3:
                # Top Client (simplifié)
                if not commandes.empty:
                    top_client_id = commandes['client_id'].value_counts().idxmax()
                    client_nom = get_clients()[get_clients()['id'] == top_client_id]['nom'].iloc[0]
                    st.metric("Meilleur Client (par commandes)", client_nom)
            
            st.divider()
            
            st.subheader("Visualisations")
            
            col_viz1, col_viz2 = st.columns(2)
            
            with col_viz1:
                st.write("Répartition des Statuts de Commandes")
                if not commandes.empty:
                    statut_counts = commandes['statut'].value_counts()
                    st.bar_chart(statut_counts)

            with col_viz2:
                st.write("Répartition des Statuts d'Achats")
                if not achats.empty:
                    statut_counts = achats['statut'].value_counts()
                    st.pie_chart(statut_counts)
        
        with tab2:
            st.subheader("Logs d'Accès Système")
            conn = get_connection()
            try:
                logs = pd.read_sql_query("""
                    SELECT 
                        l.date_heure, 
                        u.username, 
                        l.module, 
                        l.action
                    FROM logs_acces l
                    JOIN utilisateurs u ON l.user_id = u.id
                    ORDER BY l.date_heure DESC
                    LIMIT 100
                """, conn)
                
                if not logs.empty:
                    st.dataframe(logs, use_container_width=True)
                else:
                    st.info("Aucun log d'accès enregistré")
            finally:
                release_connection(conn)

    # ========== ADMINISTRATION UTILISATEURS ==========
    elif menu == "⚙️ Administration Utilisateurs":
        if not has_access("utilisateurs", "ecriture"):
            st.error("❌ Accès refusé (écriture requis)")
            st.stop()
            
        log_access(st.session_state.user_id, "utilisateurs", "Consultation")
        st.header("⚙️ Administration Utilisateurs")
        
        tab1, tab2 = st.tabs(["Gestion", "Permissions"])
        
        with tab1:
            st.subheader("Liste et Suppression")
            conn = get_connection()
            try:
                users = pd.read_sql_query("SELECT id, username, role, date_creation FROM utilisateurs ORDER BY id", conn)
                
                if not users.empty:
                    st.dataframe(users, use_container_width=True, hide_index=True)
                    
                    st.divider()
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        user_id = st.selectbox("Supprimer Utilisateur (sauf Admin)", users[users['role'] != 'admin']['id'].tolist(),
                                                format_func=lambda x: users[users['id']==x]['username'].iloc[0] if x else "Sélectionner")
                    with col2:
                        st.write("")
                        st.write("")
                        if st.button("🗑️ Supprimer Utilisateur"):
                            if user_id and users[users['id']==user_id]['role'].iloc[0] != 'admin':
                                c = conn.cursor()
                                c.execute("DELETE FROM utilisateurs WHERE id=%s", (user_id,))
                                conn.commit()
                                log_access(st.session_state.user_id, "utilisateurs", f"Suppression ID:{user_id}")
                                st.success("✅ Utilisateur supprimé")
                                st.rerun()
                            else:
                                st.error("Impossible de supprimer l'utilisateur Admin.")
                else:
                    st.info("Aucun utilisateur dans la base")
            finally:
                release_connection(conn)
        
        with tab2:
            st.subheader("🔑 Gérer les Permissions (Fonctionnalité Avancée)")
            st.info("Cette section permet de visualiser les permissions actuelles. Pour une gestion complète des droits, veuillez consulter le fichier `app.py`.")
            
            conn = get_connection()
            try:
                users = pd.read_sql_query("SELECT id, username, role FROM utilisateurs", conn)
                
                if not users.empty:
                    user_sel = st.selectbox("Utilisateur", users['id'].tolist(), 
                                            format_func=lambda x: f"{users[users['id']==x]['username'].iloc[0]} ({users[users['id']==x]['role'].iloc[0]})")
                    st.divider()
                    
                    permissions = get_user_permissions(user_sel)
                    
                    st.write(f"**Permissions pour {users[users['id']==user_sel]['username'].iloc[0]} ({users[users['id']==user_sel]['role'].iloc[0]}):**")
                    
                    perms_df = pd.DataFrame([
                        {'Module': mod, 'Lecture': perms['lecture'], 'Écriture': perms['ecriture']}
                        for mod, perms in permissions.items()
                    ])
                    st.dataframe(perms_df, use_container_width=True, hide_index=True)
                else:
                    st.info("Aucun utilisateur")
            finally:
                release_connection(conn)


    # Footer sidebar
    st.sidebar.markdown("---")
    date_footer = datetime.now().strftime('%d/%m/%Y')
    st.sidebar.markdown(f"""
    <div style="background-color: #f8fafc; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0;">
        <p style="margin: 0; font-size: 11px; color: #64748b; text-align: center;">
            <strong style="color: #1e40af;">SYGEP v3.0</strong><br>
            🌐 Mode Temps Réel Activé
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
            Tél : <strong style="color: #1e3a8a;">+212 600-000000</strong><br>
            Email : <strong style="color: #1e3a8a;">sygep.ofppt@gmail.com</strong>
        </p>
        <hr style="margin: 10px 0; border: 0; border-top: 1px solid #cbd5e1;">
        <p style="margin: 0; font-size: 10px; color: #64748b; text-align: center;">
            &copy; 2024 - {date_footer}<br>
            <strong style="color: #1e40af;">IFMLT ZENATA</strong>
        </p>
    </div>
    """
    )
