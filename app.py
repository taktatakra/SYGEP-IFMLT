import streamlit as st
import pandas as pd
from datetime import datetime
import hashlib
import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# Charger les variables d'environnement (si vous utilisez un .env local)
load_dotenv()

# Configuration de la page
st.set_page_config(
    page_title="SYGEP - Système de Gestion d'Entreprise Pédagogique (v4.0)", # Version mise à jour
    layout="wide",
    page_icon="🎓",
    initial_sidebar_state="expanded"
)

# ========== 1. GESTION CONNEXION POSTGRESQL (SUPABASE) ==========

# Paramètres de connexion basés sur votre configuration
SUPABASE_CONFIG = {
    'host': os.getenv('SUPABASE_HOST', 'aws-1-eu-central-1.pooler.supabase.com'),
    'database': os.getenv('SUPABASE_DB', 'postgres'),
    'user': os.getenv('SUPABASE_USER', 'postgres.oplcukkhrrcuindbhtkm'),
    'password': os.getenv('SUPABASE_PASSWORD', 'Hamidl9ar3@111'), 
    'port': os.getenv('SUPABASE_PORT', '6543'),
    'sslmode': 'require'
}

@st.cache_resource
def init_connection_pool():
    """Initialise un pool de connexions PostgreSQL."""
    try:
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20, 
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

def log_access(entity_id, entity_type, module, action):
    """Enregistre l'action de l'utilisateur/client dans la table logs_access."""
    # Seuls les utilisateurs internes (avec un UUID) sont loggués ici.
    # Les logs clients (par nom) nécessiteraient une table de logs séparée ou une gestion spécifique.
    if entity_type == 'user':
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("""
                INSERT INTO logs_access (user_id, module, action) 
                VALUES (%s, %s, %s)
            """, (entity_id, module, action))
            conn.commit()
        except Exception:
            pass
        finally:
            st.session_state.conn_pool.putconn(conn)


def get_user_role_and_name(email, password_hash):
    """Vérifie les identifiants de l'utilisateur interne."""
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
            user_id = str(user_data[0]) 
            return user_id, user_data[1], user_data[2], user_data[3]
        return None, None, None, None
    finally:
        st.session_state.conn_pool.putconn(conn)


@st.cache_data(ttl=3600)
def get_user_uuid_by_role(role_name):
    """Récupère l'UUID du premier utilisateur ayant un rôle donné (utile pour la notification Admin)."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT u.id
            FROM utilisateurs u
            JOIN roles r ON u.role_id = r.id
            WHERE r.nom = %s
            LIMIT 1
        """, (role_name,))
        result = c.fetchone()
        return result[0] if result else None
    finally:
        st.session_state.conn_pool.putconn(conn)


def has_access(module, access_type="lecture"):
    """Vérifie les permissions de l'utilisateur interne."""
    # Si c'est un client sans mot de passe, l'accès est géré par is_client dans le menu
    if st.session_state.get('is_client'):
        return module in ["espace_client", "notifications", "dashboard"] # Limite les modules accessibles

    # L'Admin a toujours accès complet (role_id 1)
    if st.session_state.role_id == 1:
        return True
    
    # Récupérer les permissions du rôle de l'utilisateur
    conn = get_connection()
    try:
        c = conn.cursor()
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

def authenticate_internal():
    """Authentification pour le personnel (avec mot de passe)."""
    email = st.session_state.auth_email
    password = st.session_state.auth_password
    
    hashed_password = hash_password(password)
    user_id, nom_complet, role_name, role_id = get_user_role_and_name(email, hashed_password)
    
    if user_id:
        st.session_state.logged_in = True
        st.session_state.is_client = False # Non client
        st.session_state.user_id = user_id
        st.session_state.user_name = nom_complet
        st.session_state.role_name = role_name
        st.session_state.role_id = role_id
        log_access(user_id, "user", "Authentification", "Connexion réussie")
        st.rerun()
    else:
        st.session_state.login_error_internal = "Email ou mot de passe incorrect."


def authenticate_client():
    """Authentification pour le client (sans mot de passe)."""
    client_name = st.session_state.auth_client_name
    
    conn = get_connection()
    try:
        c = conn.cursor()
        # Recherche insensible à la casse
        c.execute("SELECT id, nom FROM clients WHERE nom ILIKE %s", (client_name.strip(),))
        client_data = c.fetchone()
        
        if client_data:
            client_id = client_data[0]
            client_name_db = client_data[1]
            
            # Chercher le rôle 'client' (pour le nom affiché)
            c.execute("SELECT id FROM roles WHERE nom = 'client' LIMIT 1") 
            role_result = c.fetchone()
            
            # Si le rôle 'client' existe, on utilise son ID, sinon on utilise un ID factice
            role_id = role_result[0] if role_result else 99 
            
            # Établir la session client
            st.session_state.logged_in = True
            st.session_state.is_client = True # Flag spécifique
            st.session_state.client_id = client_id # ID du client (INT)
            st.session_state.user_name = client_name_db # Nom du client
            st.session_state.role_name = 'client'
            st.session_state.role_id = role_id
            st.rerun()
        else:
            st.session_state.login_error_client = "Nom de client non trouvé."
    finally:
        st.session_state.conn_pool.putconn(conn)


def logout():
    if not st.session_state.get('is_client'):
        log_access(st.session_state.user_id, "user", "Authentification", "Déconnexion")
    st.session_state.clear()
    st.rerun()


# ========== 4. FONCTIONS DE RÉCUPÉRATION DE DONNÉES ET COMMANDE ==========

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

def create_notification(user_id, titre, message, ref_id=None, ref_type=None):
    """Crée une notification pour un utilisateur interne (UUID)."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO notifications (user_id, titre, message, ref_id, ref_type) 
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, titre, message, ref_id, ref_type))
        conn.commit()
    except Exception:
        pass
    finally:
        st.session_state.conn_pool.putconn(conn)

def get_notifications(user_id):
    """Récupère les notifications pour l'utilisateur (UUID ou Client ID)."""
    conn = get_connection()
    try:
        if st.session_state.get('is_client'):
            # Les clients devraient voir des notifications basées sur leur client_id ou une autre table dédiée
            # Pour l'instant, les clients n'ont pas de notifications dans cette implémentation simple (ils n'ont pas d'UUID)
            return pd.DataFrame() 
        else:
            user_id_str = str(user_id) 
            notifications_df = pd.read_sql_query(f"""
                SELECT id, titre, message, date_creation, lu 
                FROM notifications 
                WHERE user_id = '{user_id_str}' 
                ORDER BY date_creation DESC
            """, conn)
            return notifications_df
    finally:
        st.session_state.conn_pool.putconn(conn)
        
def mark_notification_as_read(notification_id):
    """Marque une notification comme lue (pour les utilisateurs internes)."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE notifications SET lu = TRUE WHERE id = %s", (notification_id,))
        conn.commit()
    except Exception as e:
        st.error(f"Erreur lors de la mise à jour de la notification : {e}")
        conn.rollback()
    finally:
        st.session_state.conn_pool.putconn(conn)

def insert_client_order(client_id, createur_id_uuid, montant_total):
    """Insère une nouvelle commande client. createur_id_uuid est l'UUID du créateur (Admin par défaut si c'est un client)."""
    conn = get_connection()
    try:
        c = conn.cursor()
        
        numero = f"CMD-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Assurez-vous que la colonne createur_id est NULLABLE dans la DB si vous voulez mettre NULL
        # Sinon, nous utilisons l'UUID de l'Admin par défaut
        c.execute("""
            INSERT INTO commandes_workflow 
            (numero, client_id, date_creation, createur_id, montant_total, statut) 
            VALUES (%s, %s, NOW(), %s, %s, 'nouveau') RETURNING id
        """, (numero, client_id, createur_id_uuid, montant_total))
        
        order_id = c.fetchone()[0]
        conn.commit()
        return order_id, numero
    except Exception as e:
        st.error(f"Erreur lors de la création de la commande : {e}")
        conn.rollback()
        return None, None
    finally:
        st.session_state.conn_pool.putconn(conn)


# ========== 5. DÉFINITION DES MODULES DE L'APPLICATION ==========

# --- Module Espace Client ---

def module_espace_client():
    # Accès pour le rôle 'client' et 'admin' (pour la démo)
    if not (st.session_state.get('is_client') or st.session_state.role_name == 'admin'):
        st.error("❌ Accès refusé à l'Espace Client.")
        return
        
    st.header(f"🛒 Passez votre Commande, {st.session_state.user_name}")
    
    # 🚨 Logique spécifique pour les clients (non utilisateurs UUID)
    current_client_id = st.session_state.get('client_id')
    
    if not current_client_id:
        st.error("Erreur : Impossible d'identifier votre compte client.")
        return

    # Récupérer l'UUID de l'Admin pour le champ createur_id (placeholer)
    admin_uuid = get_user_uuid_by_role('admin')
    if not admin_uuid:
        st.warning("Attention : L'utilisateur 'admin' est introuvable. Les commandes ne pourront pas être tracées correctement.")


    products_df = get_products()
    
    if 'order_items' not in st.session_state:
        st.session_state.order_items = []
        
    # --- Formulaire d'ajout d'article ---
    with st.expander("➕ Ajouter un Article à la Commande"):
        with st.form("add_item_form", clear_on_submit=True):
            product_selection = st.selectbox("Produit", products_df['nom'].tolist())
            
            selected_product = products_df[products_df['nom'] == product_selection].iloc[0]
            
            quantity = st.number_input("Quantité", min_value=1, value=1, step=1)
            
            add_submitted = st.form_submit_button("Ajouter à la liste")
            
            if add_submitted and quantity > 0:
                item = {
                    "product_id": selected_product['id'],
                    "product_name": selected_product['nom'],
                    "quantity": quantity,
                    "price_unit": selected_product['prix_vente'],
                    "price_total": quantity * selected_product['prix_vente']
                }
                st.session_state.order_items.append(item)
                st.success(f"Article ajouté : {quantity} x {selected_product['nom']}")


    # --- Récapitulatif et Validation de la Commande ---
    if st.session_state.order_items:
        st.subheader("Articles de la Commande")
        
        items_df = pd.DataFrame(st.session_state.order_items)
        items_df['price_total'] = items_df['price_total'].round(2)
        
        st.dataframe(items_df[['product_name', 'quantity', 'price_unit', 'price_total']], 
                     use_container_width=True, hide_index=True)
        
        total_amount = items_df['price_total'].sum()
        st.metric("Montant Total de la Commande", f"{total_amount:.2f} DH")

        if st.button("✅ Confirmer et Envoyer la Commande", type="primary"):
            
            order_id, order_numero = insert_client_order(
                client_id=current_client_id,
                # Utilise l'UUID de l'Admin comme créateur si le client n'a pas d'UUID
                createur_id_uuid=admin_uuid, 
                montant_total=total_amount
            )
            
            if order_id:
                # 2. Créer une notification pour l'Admin (si l'UUID a été trouvé)
                if admin_uuid:
                    create_notification(
                        user_id=admin_uuid, 
                        titre=f"🔔 Nouvelle Commande Client {order_numero}",
                        message=f"Le client {st.session_state.user_name} a soumis une commande de {total_amount:.2f} DH. Numéro: {order_numero}.",
                        ref_id=order_id,
                        ref_type='workflow_client'
                    )

                st.success(f"🎉 Commande **{order_numero}** soumise avec succès ! L'équipe commerciale a été notifiée.")
                st.session_state.order_items = [] 
                st.rerun() 
    else:
        st.info("Ajoutez des articles pour passer la commande.")

# --- Autres modules (raccourcis) ---
def module_dashboard():
    # ... (le contenu existant du dashboard)
    st.title(f"🚀 Tableau de Bord - Bienvenue, {st.session_state.user_name.split()[0]}!")
    if not st.session_state.get('is_client'):
        log_access(st.session_state.user_id, "user", "Dashboard", "Consultation")
        st.markdown(f"**Rôle actuel :** `{st.session_state.role_name.upper()}`")
    else:
        st.info("Mode Client Actif. Accès limité aux commandes.")
    st.divider()
    # ... (le reste du dashboard)
    
def module_notifications():
    # ... (le contenu existant des notifications)
    if st.session_state.get('is_client'):
        st.info("Les notifications ne sont pas disponibles pour l'accès client non authentifié.")
        return
    st.header("🔔 Vos Notifications")
    log_access(st.session_state.user_id, "user", "notifications", "Consultation")
    
    notifications = get_notifications(st.session_state.user_id)
    # ... (le reste du module de notification)
    if notifications.empty:
        st.info("Aucune notification non lue.")
        return
        
    notifications['date'] = notifications['date_creation'].dt.strftime('%d/%m/%Y %H:%M')

    for index, row in notifications.iterrows():
        # Affichage conditionnel
        if row['lu']:
            style = "background-color: #f8f9fa; border-left: 5px solid #6c757d;"
            icon = "⚪"
        else:
            style = "background-color: #fff3cd; border-left: 5px solid #ffc107; font-weight: bold;"
            icon = "🟡"

        col1, col2 = st.columns([5, 1])

        with col1:
            st.markdown(f"""
                <div style="{style} padding: 10px; border-radius: 4px; margin-bottom: 5px;">
                    <p style="margin: 0; font-size: 0.9em;">
                        {icon} <strong style="color: #0d6efd;">{row['titre']}</strong> 
                        <span style="float: right; font-size: 0.8em; color: #6c757d;">{row['date']}</span>
                    </p>
                    <p style="margin: 5px 0 0 0; font-size: 0.8em;">{row['message']}</p>
                </div>
            """, unsafe_allow_html=True)
            
        with col2:
            if not row['lu']:
                if st.button("✔️ Lu", key=f"mark_{row['id']}"):
                    mark_notification_as_read(row['id'])
                    st.success("Notification marquée comme lue.")
                    st.rerun()

    st.divider()
    if st.button("Afficher toutes les notifications"):
        st.info("Ici, vous afficherez toutes les notifications (lues et non lues).")

# Placeholder pour les autres modules
def module_placeholder(module_key, menu_label):
    if not has_access(module_key, "lecture"):
        st.error("❌ Accès refusé à ce module.")
        if not st.session_state.get('is_client'):
            log_access(st.session_state.user_id, "user", module_key, "Tentative d'accès refusée")
        return
    
    st.title(f"🛠️ Module : {menu_label.split()[1]} (ID: {module_key})")
    st.info(f"Le contenu du module **{menu_label}** est en cours de développement.")
    if not st.session_state.get('is_client'):
        log_access(st.session_state.user_id, "user", module_key, "Consultation (Placeholder)")


# ========== 6. APPLICATION PRINCIPALE STREAMLIT ==========

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.is_client = False

if not st.session_state.logged_in:
    # --- Écran de Connexion Multi-Modes ---
    st.image("https://upload.wikimedia.org/wikipedia/commons/0/0e/Ofppt.png", width=150)
    st.title("🎓 SYGEP - Connexion")
    
    tab_interne, tab_client = st.tabs(["🔒 Personnel (Email/Mot de Passe)", "👤 Accès Client (Nom uniquement)"])
    
    # --- Onglet Personnel ---
    with tab_interne:
        st.write("Réservé au personnel interne (Admin, Commercial, Stock, Comptable, etc.).")
        with st.form("login_form_internal"):
            email = st.text_input("Email", key="auth_email")
            password = st.text_input("Mot de passe", type="password", key="auth_password")
            
            submitted = st.form_submit_button("🔒 Se connecter")
            
            if submitted:
                authenticate_internal()
                
            if 'login_error_internal' in st.session_state and st.session_state.login_error_internal:
                st.error(st.session_state.login_error_internal)
                st.session_state.login_error_internal = "" 

    # --- Onglet Client ---
    with tab_client:
        st.write("Entrez le nom de votre entreprise/contact tel qu'il est enregistré dans le système.")
        with st.form("login_form_client"):
            client_name = st.text_input("Nom du Client (ex: Client Alpha)", key="auth_client_name")
            
            submitted_client = st.form_submit_button("🛒 Accéder à l'Espace Client")
            
            if submitted_client:
                authenticate_client()

            if 'login_error_client' in st.session_state and st.session_state.login_error_client:
                st.error(st.session_state.login_error_client)
                st.session_state.login_error_client = ""
                

else:
    # --- Application Principale (Connecté) ---
    
    # 7. Sidebar et Menu
    with st.sidebar:
        st.header(f"Bonjour, {st.session_state.user_name.split()[0]}")
        st.caption(f"Rôle : **{st.session_state.role_name.upper()}**")
        st.divider()

        # Options pour le personnel interne
        internal_menu_options = {
            "🏠 Tableau de Bord": "dashboard",
            "🔔 Notifications": "notifications",
            "👥 Gestion Clients": "clients",
            "👤 Gestion Fournisseurs": "fournisseurs",
            "📦 Gestion Produits": "produits",
            "📝 Commandes Clients (Ventes)": "workflow_client",
            "🛒 Achats Fournisseurs": "workflow_fournisseur",
            "💰 Comptabilité": "comptabilite",
            "📊 Rapports & KPIs": "rapports",
            "⚙️ Administration": "administration"
        }
        
        # Options pour le mode client
        client_menu_options = {
            "🏠 Tableau de Bord": "dashboard",
            "🛍️ Passer Commande": "espace_client",
            "🔔 Suivi Notifications": "notifications",
        }
        
        # Sélection des options en fonction du mode de connexion
        if st.session_state.is_client:
            menu_options = client_menu_options
            allowed_options = menu_options # Les clients voient tout de leur menu
        else:
            menu_options = internal_menu_options
            allowed_options = {}
            for label, module_key in menu_options.items():
                if module_key == "dashboard" or has_access(module_key, "lecture"):
                    allowed_options[label] = module_key


        menu = st.radio("Navigation", list(allowed_options.keys()))
        
        st.divider()
        st.button("Déconnexion", on_click=logout)

        # 8. Footer Sidebar 
        st.sidebar.markdown("---")
        date_footer = datetime.now().strftime('%d/%m/%Y')
        st.sidebar.markdown(f"""
        <div style="background-color: #f8fafc; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0;">
            <p style="margin: 0; font-size: 11px; color: #64748b; text-align: center;">
                <strong style="color: #1e40af;">SYGEP v4.0</strong><br>
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
    elif current_module == "notifications": 
        module_notifications()
    elif current_module == "espace_client":
        module_espace_client()
    elif current_module == "clients":
        module_gestion_clients()
    elif current_module == "produits":
        module_gestion_produits()
    else:
        # Utilisation de la fonction placeholder pour les autres modules
        module_placeholder(current_module, menu)

# --- Fin de l'application ---
