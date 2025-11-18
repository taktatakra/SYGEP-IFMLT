import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import hashlib
from PIL import Image
import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# Charger les variables d'environnement (si vous utilisez un .env local)
load_dotenv()

# Configuration de la page
st.set_page_config(
    page_title="SYGEP - Système de Gestion d'Entreprise Pédagogique (v3.5)",
    layout="wide",
    page_icon="🎓",
    initial_sidebar_state="expanded"
)

# ========== 1. GESTION CONNEXION POSTGRESQL (SUPABASE) ==========

# Paramètres de connexion basés sur votre configuration
# Attention : Le mot de passe est celui trouvé dans vos fichiers.
SUPABASE_CONFIG = {
    'host': os.getenv('SUPABASE_HOST', 'aws-1-eu-central-1.pooler.supabase.com'),
    'database': os.getenv('SUPABASE_DB', 'postgres'),
    'user': os.getenv('SUPABASE_USER', 'postgres.oplcukkhrrcuindbhtkm'),
    'password': os.getenv('SUPABASE_PASSWORD', 'Hamidl9ar3@111'), # Votre mot de passe
    'port': os.getenv('SUPABASE_PORT', '6543'),
    'sslmode': 'require'
}

@st.cache_resource
def init_connection_pool():
    """Initialise un pool de connexions PostgreSQL."""
    try:
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20, # min et max connexions
            **SUPABASE_CONFIG
        )
        return connection_pool
    except Exception as e:
        st.error(f"❌ Erreur critique de connexion PostgreSQL : {e}")
        st.stop()

if 'conn_pool' not in st.session_state:
    st.session_state.conn_pool = init_connection_pool()
    st.info("Tentative de connexion à la base de données...")

def get_connection():
    """Récupère une connexion du pool."""
    try:
        return st.session_state.conn_pool.getconn()
    except Exception as e:
        st.error(f"Erreur lors de la récupération de la connexion : {e}")
        st.stop()

# ========== 2. FONCTIONS UTILITAIRES ET SÉCURITÉ ==========

def hash_password(password):
    """Hache un mot de passe en utilisant SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

def log_access(user_id, module, action):
    """Enregistre l'action de l'utilisateur dans la table logs_access."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO logs_access (user_id, module, action) 
            VALUES (%s, %s, %s)
        """, (user_id, module, action))
        conn.commit()
    except Exception as e:
        # st.warning(f"Impossible d'enregistrer le log : {e}")
        pass # Ignorer les erreurs de log pour ne pas bloquer l'app
    finally:
        st.session_state.conn_pool.putconn(conn)


def get_user_role_and_name(email, password_hash):
    """
    Vérifie les identifiants et récupère les informations de l'utilisateur.
    🚨 Utilise nom_complet et role_id pour le code.
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT u.id, u.nom_complet, r.nom AS role_name, r.id AS role_id
            FROM utilisateurs u
            JOIN roles r ON u.role_id = r.id
            WHERE u.email = %s AND u.mot_de_passe = %s
        """, (email, password_hash))
        
        user_data = c.fetchone()
        
        if user_data:
            # Conversion de l'UUID en string pour Streamlit Session State
            user_id = str(user_data[0]) 
            return user_id, user_data[1], user_data[2], user_data[3]
        return None, None, None, None
    finally:
        st.session_state.conn_pool.putconn(conn)


def has_access(module, access_type="lecture"):
    """
    Vérifie les permissions de l'utilisateur pour un module spécifique.
    """
    # L'Admin a toujours accès complet (role_id 1)
    if st.session_state.role_id == 1:
        return True
    
    # Récupérer les permissions du rôle de l'utilisateur
    conn = get_connection()
    try:
        c = conn.cursor()
        
        # Le champ de la permission à vérifier dépend du type d'accès demandé
        access_column = "acces_lecture" if access_type == "lecture" else "acces_ecriture"

        c.execute(f"""
            SELECT {access_column}
            FROM permissions
            WHERE role_id = %s AND module = %s
        """, (st.session_state.role_id, module))
        
        permission = c.fetchone()
        
        if permission and permission[0] is True:
            return True
        return False
    finally:
        st.session_state.conn_pool.putconn(conn)


# ========== 3. FONCTIONS D'AUTHENTIFICATION ET DE DÉCONNEXION ==========

def authenticate():
    email = st.session_state.auth_email
    password = st.session_state.auth_password
    
    # 1. Hacher le mot de passe fourni par l'utilisateur
    hashed_password = hash_password(password)
    
    # 2. Vérifier les identifiants
    user_id, nom_complet, role_name, role_id = get_user_role_and_name(email, hashed_password)
    
    if user_id:
        st.session_state.logged_in = True
        st.session_state.user_id = user_id
        st.session_state.user_name = nom_complet # Utilisation de nom_complet
        st.session_state.role_name = role_name
        st.session_state.role_id = role_id
        log_access(user_id, "Authentification", "Connexion réussie")
        st.rerun()
    else:
        st.session_state.login_error = "Email ou mot de passe incorrect."

def logout():
    log_access(st.session_state.user_id, "Authentification", "Déconnexion")
    st.session_state.clear()
    st.rerun()


# ========== 4. FONCTIONS DE RÉCUPÉRATION DE DONNÉES (EXEMPLES) ==========

@st.cache_data(ttl=60)
def get_clients():
    conn = get_connection()
    try:
        clients_df = pd.read_sql_query("SELECT id, nom, email, telephone, ville, pays FROM clients ORDER BY nom", conn)
        return clients_df
    finally:
        st.session_state.conn_pool.putconn(conn)

@st.cache_data(ttl=60)
def get_products():
    conn = get_connection()
    try:
        produits_df = pd.read_sql_query("SELECT id, nom, reference, stock, prix_vente FROM produits ORDER BY nom", conn)
        return produits_df
    finally:
        st.session_state.conn_pool.putconn(conn)

# ========== 5. DÉFINITION DES MODULES DE L'APPLICATION ==========

def module_dashboard():
    st.title(f"🚀 Tableau de Bord - Bienvenue, {st.session_state.user_name.split()[0]}!")
    log_access(st.session_state.user_id, "Dashboard", "Consultation")
    
    st.markdown(f"**Rôle actuel :** `{st.session_state.role_name.upper()}`")
    
    # Section simple pour vérifier la connexion et l'accès
    st.divider()
    
    col1, col2, col3 = st.columns(3)
    
    # Exemple de vérification de permission
    with col1:
        if has_access("clients", "lecture"):
            st.success("✔️ Accès Lecture Clients : OK")
        else:
            st.error("❌ Accès Lecture Clients : Refusé")

    with col2:
        if has_access("workflow_client", "ecriture"):
            st.success("✔️ Accès Écriture Commandes : OK")
        else:
            st.error("❌ Accès Écriture Commandes : Refusé")
            
    with col3:
        if has_access("administration", "lecture"):
            st.success("✔️ Accès Admin : OK")
        else:
            st.info("ℹ️ Accès Admin : Non requis")
            
    st.markdown("""
        <div style="margin-top: 30px; padding: 20px; border: 1px solid #ddd; border-left: 5px solid #1e40af; border-radius: 5px;">
            <p style="margin: 0; font-size: 1.1em; color: #1e40af;">
                Votre application est connectée à la base de données !
            </p>
            <p style="margin-top: 5px; font-size: 0.9em;">
                Les fonctions de base sont opérationnelles. Continuez à développer chaque module (Clients, Produits, etc.) en utilisant les fonctions <code>get_connection()</code> et <code>has_access()</code>.
            </p>
        </div>
    """, unsafe_allow_html=True)


def module_gestion_clients():
    if not has_access("clients", "lecture"):
        st.error("❌ Accès refusé à la Gestion Clients.")
        log_access(st.session_state.user_id, "clients", "Tentative d'accès refusée")
        return
        
    log_access(st.session_state.user_id, "clients", "Consultation")
    st.header("👥 Gestion des Clients")
    
    tab1, tab2 = st.tabs(["📋 Liste", "➕ Ajouter"])
    
    with tab1:
        clients = get_clients()
        if not clients.empty:
            st.dataframe(clients, use_container_width=True, hide_index=True)
            
            # Afficher le bouton de suppression uniquement si l'utilisateur a le droit d'écrire
            if has_access("clients", "ecriture"):
                st.divider()
                st.subheader("Supprimer un client")
                col1, col2 = st.columns([3, 1])
                with col1:
                    client_id = st.selectbox("Sélectionnez le client à supprimer", clients['id'].tolist(),
                                            format_func=lambda x: clients[clients['id']==x]['nom'].iloc[0])
                with col2:
                    st.write("") # Espace pour alignement
                    if st.button("🗑️ Confirmer la suppression"):
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            # Attention: Supprimer un client avec des commandes actives peut causer une erreur FK.
                            # Le 'DELETE FROM clients WHERE id=%s' est une base.
                            c.execute("DELETE FROM clients WHERE id=%s", (client_id,))
                            conn.commit()
                            log_access(st.session_state.user_id, "clients", f"Suppression client ID: {client_id}")
                            st.success("✅ Client supprimé avec succès.")
                            st.cache_data.clear() # Vider le cache des clients
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur lors de la suppression : {e}. Assurez-vous qu'il n'a pas de commandes.")
                        finally:
                            st.session_state.conn_pool.putconn(conn)
            else:
                st.info("Vous n'avez pas la permission d'ajouter ou modifier les clients.")
        else:
            st.info("Aucun client enregistré.")

    with tab2:
        if has_access("clients", "ecriture"):
            with st.form("ajouter_client"):
                nom = st.text_input("Nom du client", max_chars=100)
                email = st.text_input("Email", max_chars=100)
                telephone = st.text_input("Téléphone", max_chars=50)
                
                submitted = st.form_submit_button("➕ Enregistrer le Client")
                if submitted and nom:
                    conn = get_connection()
                    try:
                        c = conn.cursor()
                        c.execute("""
                            INSERT INTO clients (nom, email, telephone) 
                            VALUES (%s, %s, %s)
                        """, (nom, email, telephone))
                        conn.commit()
                        log_access(st.session_state.user_id, "clients", f"Ajout client : {nom}")
                        st.success(f"✅ Client '{nom}' ajouté avec succès.")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Erreur d'enregistrement : {e}")
                    finally:
                        st.session_state.conn_pool.putconn(conn)
        else:
             st.warning("Vous n'avez pas la permission d'ajouter des clients.")


def module_gestion_produits():
    if not has_access("produits", "lecture"):
        st.error("❌ Accès refusé aux Produits.")
        return
    
    st.header("📦 Gestion des Produits")
    st.info("Code de ce module à implémenter. Utilisez `get_products()` pour les données.")
    # ... Implémentation du code (Ajouter, Modifier, Liste)


# ========== 6. APPLICATION PRINCIPALE STREAMLIT ==========

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    # --- Écran de Connexion ---
    st.image("https://upload.wikimedia.org/wikipedia/commons/0/0e/Ofppt.png", width=150)
    st.title("🎓 SYGEP - Connexion")
    st.write("Veuillez vous connecter pour accéder au système.")
    
    with st.form("login_form"):
        email = st.text_input("Email", key="auth_email")
        password = st.text_input("Mot de passe", type="password", key="auth_password")
        
        submitted = st.form_submit_button("🔒 Se connecter")
        
        if submitted:
            authenticate()
            
        if 'login_error' in st.session_state and st.session_state.login_error:
            st.error(st.session_state.login_error)
            st.session_state.login_error = "" # Clear error after display

else:
    # --- Application Principale (Connecté) ---
    
    # 7. Sidebar et Menu
    with st.sidebar:
        st.header(f"Bonjour, {st.session_state.user_name}")
        st.caption(f"Rôle : **{st.session_state.role_name.upper()}**")
        st.divider()

        # Construction du menu en fonction des permissions de lecture
        menu_options = {
            "🏠 Tableau de Bord": "dashboard",
            "👥 Gestion Clients": "clients",
            "👤 Gestion Fournisseurs": "fournisseurs",
            "📦 Gestion Produits": "produits",
            "📝 Commandes Clients (Ventes)": "workflow_client",
            "🛒 Achats Fournisseurs": "workflow_fournisseur",
            "💰 Comptabilité": "comptabilite",
            "📊 Rapports & KPIs": "rapports",
            "⚙️ Administration": "administration"
        }
        
        allowed_options = {}
        for label, module_key in menu_options.items():
            # Le dashboard est toujours accessible
            if module_key == "dashboard" or has_access(module_key, "lecture"):
                allowed_options[label] = module_key

        menu = st.radio("Navigation", list(allowed_options.keys()))
        
        st.divider()
        st.button("Déconnexion", on_click=logout)

        # 8. Footer Sidebar (reprise de votre code existant)
        st.sidebar.markdown("---")
        date_footer = datetime.now().strftime('%d/%m/%Y')
        st.sidebar.markdown(f"""
        <div style="background-color: #f8fafc; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0;">
            <p style="margin: 0; font-size: 11px; color: #64748b; text-align: center;">
                <strong style="color: #1e40af;">SYGEP v3.5</strong><br>
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
                Date du jour : {date_footer}
            </p>
        </div>
        """, unsafe_allow_html=True)


    # 9. Logique de Routage (Contenu principal)
    
    current_module = allowed_options[menu]
    
    if current_module == "dashboard":
        module_dashboard()
    elif current_module == "clients":
        module_gestion_clients()
    elif current_module == "produits":
        module_gestion_produits()
    else:
        # Placeholder pour les autres modules
        if has_access(current_module, "lecture"):
             st.title(f"🛠️ Module : {menu.split()[1]} (ID: {current_module})")
             st.info(f"Le contenu du module **{menu}** est en cours de développement.")
             log_access(st.session_state.user_id, current_module, "Consultation (Placeholder)")
        else:
            st.error("❌ Accès refusé à ce module.")
            log_access(st.session_state.user_id, current_module, "Tentative d'accès refusée")
