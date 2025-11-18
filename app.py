import streamlit as st
import pandas as pd
from datetime import datetime
import hashlib
import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration de la page
st.set_page_config(
    page_title="SYGEP - Système de Gestion d'Entreprise Pédagogique (v6.0)",
    layout="wide",
    page_icon="🎓",
    initial_sidebar_state="expanded"
)

# ========== 1. GESTION CONNEXION POSTGRESQL (SUPABASE) ==========

# Paramètres de connexion
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
    """Enregistre l'action de l'utilisateur/client dans la table logs_access (uniquement pour les utilisateurs UUID)."""
    if entity_type == 'user' and 'user_id' in st.session_state:
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
    """Vérifie les permissions de l'utilisateur."""
    if st.session_state.get('is_client'):
        return module in ["espace_client", "notifications", "dashboard"] 

    if st.session_state.role_id == 1: # Admin a tout
        return True
    
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
        st.session_state.is_client = False
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
        c.execute("SELECT id, nom FROM clients WHERE nom ILIKE %s", (client_name.strip(),))
        client_data = c.fetchone()
        
        if client_data:
            client_id = client_data[0]
            client_name_db = client_data[1]
            
            c.execute("SELECT id FROM roles WHERE nom = 'client' LIMIT 1") 
            role_result = c.fetchone()
            
            role_id = role_result[0] if role_result else 99 
            
            st.session_state.logged_in = True
            st.session_state.is_client = True 
            st.session_state.client_id = client_id
            st.session_state.user_name = client_name_db
            st.session_state.role_name = 'client'
            st.session_state.role_id = role_id
            st.rerun()
        else:
            st.session_state.login_error_client = "Nom de client non trouvé."
    finally:
        st.session_state.conn_pool.putconn(conn)


def logout():
    if not st.session_state.get('is_client') and 'user_id' in st.session_state:
        log_access(st.session_state.user_id, "user", "Authentification", "Déconnexion")
    st.session_state.clear()
    st.rerun()


# ========== 4. FONCTIONS DE GESTION DE DONNÉES (CRUD) ==========

# --- CRUD Clients ---

@st.cache_data(ttl=60)
def get_clients():
    conn = get_connection()
    try:
        clients_df = pd.read_sql_query("SELECT id, nom, email, telephone, ville, pays FROM clients ORDER BY nom", conn)
        return clients_df
    finally:
        st.session_state.conn_pool.putconn(conn)

def insert_client(nom, email, telephone, ville, pays):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""INSERT INTO clients (nom, email, telephone, ville, pays) VALUES (%s, %s, %s, %s, %s)""", 
                  (nom, email, telephone, ville, pays))
        conn.commit()
        get_clients.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur lors de l'ajout du client : {e}")
        return False
    finally:
        st.session_state.conn_pool.putconn(conn)
        
def update_client(client_id, nom, email, telephone, ville, pays):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""UPDATE clients SET nom=%s, email=%s, telephone=%s, ville=%s, pays=%s WHERE id=%s""", 
                  (nom, email, telephone, ville, pays, client_id))
        conn.commit()
        get_clients.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur lors de la mise à jour du client : {e}")
        return False
    finally:
        st.session_state.conn_pool.putconn(conn)

def delete_client(client_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        # Suppression potentielle de commandes associées (ou utiliser CASCADE sur la DB)
        c.execute("DELETE FROM clients WHERE id=%s", (client_id,))
        conn.commit()
        get_clients.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur lors de la suppression du client : {e}. (Vérifiez les commandes liées.)")
        return False
    finally:
        st.session_state.conn_pool.putconn(conn)

# --- CRUD Produits ---

@st.cache_data(ttl=60)
def get_products():
    conn = get_connection()
    try:
        produits_df = pd.read_sql_query("SELECT id, nom, reference, stock, prix_vente FROM produits ORDER BY nom", conn)
        return produits_df
    finally:
        st.session_state.conn_pool.putconn(conn)
        
def insert_product(nom, reference, stock, prix_vente):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""INSERT INTO produits (nom, reference, stock, prix_vente) VALUES (%s, %s, %s, %s)""", 
                  (nom, reference, stock, prix_vente))
        conn.commit()
        get_products.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur lors de l'ajout du produit : {e}")
        return False
    finally:
        st.session_state.conn_pool.putconn(conn)

def update_product(product_id, nom, reference, stock, prix_vente):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""UPDATE produits SET nom=%s, reference=%s, stock=%s, prix_vente=%s WHERE id=%s""", 
                  (nom, reference, stock, prix_vente, product_id))
        conn.commit()
        get_products.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur lors de la mise à jour du produit : {e}")
        return False
    finally:
        st.session_state.conn_pool.putconn(conn)

def delete_product(product_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM produits WHERE id=%s", (product_id,))
        conn.commit()
        get_products.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur lors de la suppression du produit : {e}. (Vérifiez les commandes liées.)")
        return False
    finally:
        st.session_state.conn_pool.putconn(conn)

# --- CRUD Fournisseurs (NOUVEAU) ---

@st.cache_data(ttl=60)
def get_fournisseurs():
    """Récupère la liste de tous les fournisseurs."""
    conn = get_connection()
    try:
        fournisseurs_df = pd.read_sql_query("SELECT id, nom, contact, email FROM fournisseurs ORDER BY nom", conn)
        return fournisseurs_df
    finally:
        st.session_state.conn_pool.putconn(conn)

def insert_fournisseur(nom, contact, email):
    """Ajoute un nouveau fournisseur."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""INSERT INTO fournisseurs (nom, contact, email) VALUES (%s, %s, %s)""", 
                  (nom, contact, email))
        conn.commit()
        get_fournisseurs.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur lors de l'ajout du fournisseur : {e}")
        return False
    finally:
        st.session_state.conn_pool.putconn(conn)
        
def update_fournisseur(fournisseur_id, nom, contact, email):
    """Met à jour les informations d'un fournisseur existant."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""UPDATE fournisseurs SET nom=%s, contact=%s, email=%s WHERE id=%s""", 
                  (nom, contact, email, fournisseur_id))
        conn.commit()
        get_fournisseurs.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur lors de la mise à jour du fournisseur : {e}")
        return False
    finally:
        st.session_state.conn_pool.putconn(conn)

def delete_fournisseur(fournisseur_id):
    """Supprime un fournisseur."""
    conn = get_connection()
    try:
        c = conn.cursor()
        # Suppression potentielle des achats associés (ou utiliser CASCADE sur la DB)
        c.execute("DELETE FROM fournisseurs WHERE id=%s", (fournisseur_id,))
        conn.commit()
        get_fournisseurs.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erreur lors de la suppression du fournisseur : {e}. (Vérifiez les achats liés.)")
        return False
    finally:
        st.session_state.conn_pool.putconn(conn)


# ========== 5. DÉFINITION DES MODULES DE L'APPLICATION (CRUD INTÉGRÉ) ==========

# --- Module Gestion Fournisseurs (NOUVEAU - CRUD) ---

def module_gestion_fournisseurs():
    if not has_access("fournisseurs"):
        st.error("❌ Accès refusé à la Gestion Fournisseurs.")
        log_access(st.session_state.user_id, "user", "fournisseurs", "Tentative d'accès refusée")
        return
        
    log_access(st.session_state.user_id, "user", "fournisseurs", "Consultation")
    st.header("👤 Gestion des Fournisseurs")
    
    fournisseurs_df = get_fournisseurs()
    
    tab1, tab2, tab3 = st.tabs(["📋 Liste / Supprimer", "➕ Ajouter", "✏️ Modifier"])
    
    # 1. Liste / Supprimer
    with tab1:
        if fournisseurs_df.empty:
            st.info("Aucun fournisseur enregistré.")
        else:
            st.dataframe(fournisseurs_df, use_container_width=True, hide_index=True)
            
            if has_access("fournisseurs", "ecriture"):
                st.divider()
                st.subheader("🗑️ Suppression d'un Fournisseur")
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    fournisseur_map = {row['id']: f"{row['nom']} (ID: {row['id']})" for index, row in fournisseurs_df.iterrows()}
                    
                    if not fournisseur_map:
                        st.info("Aucun fournisseur à supprimer.")
                        fournisseur_id_to_delete = None
                    else:
                        fournisseur_id_to_delete = st.selectbox("Sélectionnez le fournisseur à supprimer", 
                                                           options=list(fournisseur_map.keys()),
                                                           format_func=lambda x: fournisseur_map[x],
                                                           key="delete_fournisseur_id")
                with col2:
                    st.write("")
                    if fournisseur_id_to_delete and st.button("🗑️ Confirmer la Suppression Fournisseur", type="primary"):
                        if delete_fournisseur(fournisseur_id_to_delete):
                            st.success(f"✅ Fournisseur ID {fournisseur_id_to_delete} supprimé.")
                            log_access(st.session_state.user_id, "user", "fournisseurs", f"Suppression fournisseur ID {fournisseur_id_to_delete}")
                            st.rerun()
            else:
                st.info("Vous n'avez pas les permissions d'écriture pour supprimer des fournisseurs.")

    # 2. Ajouter
    with tab2:
        if has_access("fournisseurs", "ecriture"):
            st.subheader("➕ Ajouter un Nouveau Fournisseur")
            with st.form("add_fournisseur_form"):
                n_nom = st.text_input("Nom de l'Entreprise", max_chars=100)
                n_contact = st.text_input("Nom du Contact", max_chars=100)
                n_email = st.text_input("Email", max_chars=100)
                
                if st.form_submit_button("✅ Enregistrer le Fournisseur"):
                    if n_nom and insert_fournisseur(n_nom, n_contact, n_email):
                        st.success(f"Fournisseur '{n_nom}' ajouté avec succès.")
                        log_access(st.session_state.user_id, "user", "fournisseurs", f"Ajout fournisseur {n_nom}")
                        st.rerun()
                    elif not n_nom:
                        st.error("Le nom du fournisseur est obligatoire.")
        else:
            st.warning("Vous n'avez pas les permissions d'écriture pour ajouter des fournisseurs.")

    # 3. Modifier
    with tab3:
        if has_access("fournisseurs", "ecriture") and not fournisseurs_df.empty:
            st.subheader("✏️ Modifier les Informations d'un Fournisseur")
            
            fournisseur_map_mod = {row['id']: f"{row['nom']} (ID: {row['id']})" for index, row in fournisseurs_df.iterrows()}
            fournisseur_id_to_update = st.selectbox("Sélectionnez le fournisseur à modifier", 
                                               options=list(fournisseur_map_mod.keys()),
                                               format_func=lambda x: fournisseur_map_mod[x],
                                               key="update_fournisseur_id")
                                               
            if fournisseur_id_to_update:
                current_data = fournisseurs_df[fournisseurs_df['id'] == fournisseur_id_to_update].iloc[0]
                
                with st.form("update_fournisseur_form"):
                    u_nom = st.text_input("Nom de l'Entreprise", value=current_data['nom'], max_chars=100)
                    u_contact = st.text_input("Nom du Contact", value=current_data['contact'], max_chars=100)
                    u_email = st.text_input("Email", value=current_data['email'], max_chars=100)
                    
                    if st.form_submit_button("💾 Enregistrer les Modifications Fournisseur"):
                        if u_nom and update_fournisseur(fournisseur_id_to_update, u_nom, u_contact, u_email):
                            st.success(f"Fournisseur '{u_nom}' (ID: {fournisseur_id_to_update}) mis à jour avec succès.")
                            log_access(st.session_state.user_id, "user", "fournisseurs", f"Mise à jour fournisseur ID {fournisseur_id_to_update}")
                            st.rerun()
                        elif not u_nom:
                            st.error("Le nom du fournisseur est obligatoire.")
        elif not has_access("fournisseurs", "ecriture"):
            st.warning("Vous n'avez pas les permissions d'écriture pour modifier des fournisseurs.")
        else:
            st.info("Aucun fournisseur à modifier.")


# --- Module Gestion Clients (CRUD) ---

def module_gestion_clients():
    if not has_access("clients"):
        st.error("❌ Accès refusé à la Gestion Clients.")
        log_access(st.session_state.user_id, "user", "clients", "Tentative d'accès refusée")
        return
        
    log_access(st.session_state.user_id, "user", "clients", "Consultation")
    st.header("👥 Gestion des Clients")
    
    clients_df = get_clients()
    
    tab1, tab2, tab3 = st.tabs(["📋 Liste / Supprimer", "➕ Ajouter", "✏️ Modifier"])
    
    # 1. Liste / Supprimer
    with tab1:
        if clients_df.empty:
            st.info("Aucun client enregistré.")
        else:
            st.dataframe(clients_df, use_container_width=True, hide_index=True)
            
            if has_access("clients", "ecriture"):
                st.divider()
                st.subheader("🗑️ Suppression d'un Client")
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    client_map = {row['id']: f"{row['nom']} (ID: {row['id']})" for index, row in clients_df.iterrows()}
                    if not client_map:
                        client_id_to_delete = None
                    else:
                        client_id_to_delete = st.selectbox("Sélectionnez le client à supprimer", 
                                                       options=list(client_map.keys()),
                                                       format_func=lambda x: client_map[x],
                                                       key="delete_client_id")
                with col2:
                    st.write("")
                    if client_id_to_delete and st.button("🗑️ Confirmer la Suppression Client", type="primary"):
                        if delete_client(client_id_to_delete):
                            st.success(f"✅ Client ID {client_id_to_delete} supprimé.")
                            log_access(st.session_state.user_id, "user", "clients", f"Suppression client ID {client_id_to_delete}")
                            st.rerun()
            else:
                st.info("Vous n'avez pas les permissions d'écriture pour supprimer des clients.")

    # 2. Ajouter
    with tab2:
        if has_access("clients", "ecriture"):
            st.subheader("➕ Ajouter un Nouveau Client")
            with st.form("add_client_form"):
                n_nom = st.text_input("Nom de l'Entreprise/Contact", max_chars=100)
                n_email = st.text_input("Email", max_chars=100)
                n_telephone = st.text_input("Téléphone", max_chars=50)
                n_ville = st.text_input("Ville", max_chars=50)
                n_pays = st.text_input("Pays", max_chars=50)
                
                if st.form_submit_button("✅ Enregistrer le Client"):
                    if n_nom and insert_client(n_nom, n_email, n_telephone, n_ville, n_pays):
                        st.success(f"Client '{n_nom}' ajouté avec succès.")
                        log_access(st.session_state.user_id, "user", "clients", f"Ajout client {n_nom}")
                        st.rerun()
                    elif not n_nom:
                        st.error("Le nom du client est obligatoire.")
        else:
            st.warning("Vous n'avez pas les permissions d'écriture pour ajouter des clients.")

    # 3. Modifier
    with tab3:
        if has_access("clients", "ecriture") and not clients_df.empty:
            st.subheader("✏️ Modifier les Informations d'un Client")
            
            client_map_mod = {row['id']: f"{row['nom']} (ID: {row['id']})" for index, row in clients_df.iterrows()}
            client_id_to_update = st.selectbox("Sélectionnez le client à modifier", 
                                               options=list(client_map_mod.keys()),
                                               format_func=lambda x: client_map_mod[x],
                                               key="update_client_id")
                                               
            if client_id_to_update:
                current_data = clients_df[clients_df['id'] == client_id_to_update].iloc[0]
                
                with st.form("update_client_form"):
                    u_nom = st.text_input("Nom de l'Entreprise/Contact", value=current_data['nom'], max_chars=100)
                    u_email = st.text_input("Email", value=current_data['email'], max_chars=100)
                    u_telephone = st.text_input("Téléphone", value=current_data['telephone'], max_chars=50)
                    u_ville = st.text_input("Ville", value=current_data['ville'], max_chars=50)
                    u_pays = st.text_input("Pays", value=current_data['pays'], max_chars=50)
                    
                    if st.form_submit_button("💾 Enregistrer les Modifications Client"):
                        if u_nom and update_client(client_id_to_update, u_nom, u_email, u_telephone, u_ville, u_pays):
                            st.success(f"Client '{u_nom}' (ID: {client_id_to_update}) mis à jour avec succès.")
                            log_access(st.session_state.user_id, "user", "clients", f"Mise à jour client ID {client_id_to_update}")
                            st.rerun()
                        elif not u_nom:
                            st.error("Le nom du client est obligatoire.")
        elif not has_access("clients", "ecriture"):
            st.warning("Vous n'avez pas les permissions d'écriture pour modifier des clients.")
        else:
            st.info("Aucun client à modifier.")


# --- Module Gestion Produits (CRUD) ---

def module_gestion_produits():
    if not has_access("produits"):
        st.error("❌ Accès refusé à la Gestion Produits.")
        log_access(st.session_state.user_id, "user", "produits", "Tentative d'accès refusée")
        return
        
    log_access(st.session_state.user_id, "user", "produits", "Consultation")
    st.header("📦 Gestion des Produits")
    
    products_df = get_products()
    
    tab1, tab2, tab3 = st.tabs(["📋 Liste / Supprimer", "➕ Ajouter", "✏️ Modifier"])

    # 1. Liste / Supprimer
    with tab1:
        if products_df.empty:
            st.info("Aucun produit enregistré.")
        else:
            st.dataframe(products_df, use_container_width=True, hide_index=True)

            if has_access("produits", "ecriture"):
                st.divider()
                st.subheader("🗑️ Suppression d'un Produit")
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    product_map = {row['id']: f"{row['nom']} ({row['reference']})" for index, row in products_df.iterrows()}
                    if not product_map:
                        product_id_to_delete = None
                    else:
                        product_id_to_delete = st.selectbox("Sélectionnez le produit à supprimer", 
                                                        options=list(product_map.keys()),
                                                        format_func=lambda x: product_map[x],
                                                        key="delete_product_id")
                with col2:
                    st.write("")
                    if product_id_to_delete and st.button("🗑️ Confirmer la Suppression Produit", type="primary"):
                        if delete_product(product_id_to_delete):
                            st.success(f"✅ Produit ID {product_id_to_delete} supprimé.")
                            log_access(st.session_state.user_id, "user", "produits", f"Suppression produit ID {product_id_to_delete}")
                            st.rerun()
            else:
                st.info("Vous n'avez pas les permissions d'écriture pour supprimer des produits.")
                
    # 2. Ajouter
    with tab2:
        if has_access("produits", "ecriture"):
            st.subheader("➕ Ajouter un Nouveau Produit")
            with st.form("add_product_form"):
                n_nom = st.text_input("Nom du Produit", max_chars=100)
                n_reference = st.text_input("Référence (Code Produit)", max_chars=50)
                n_stock = st.number_input("Stock Initial", min_value=0, value=0)
                n_prix_vente = st.number_input("Prix de Vente Unitaire (DH)", min_value=0.01, value=1.0, format="%.2f")
                
                if st.form_submit_button("✅ Enregistrer le Produit"):
                    if n_nom and n_reference and insert_product(n_nom, n_reference, n_stock, n_prix_vente):
                        st.success(f"Produit '{n_nom}' ajouté avec succès.")
                        log_access(st.session_state.user_id, "user", "produits", f"Ajout produit {n_nom}")
                        st.rerun()
                    elif not n_nom or not n_reference:
                        st.error("Le nom et la référence du produit sont obligatoires.")
        else:
            st.warning("Vous n'avez pas les permissions d'écriture pour ajouter des produits.")

    # 3. Modifier
    with tab3:
        if has_access("produits", "ecriture") and not products_df.empty:
            st.subheader("✏️ Modifier les Informations d'un Produit")
            
            product_map_mod = {row['id']: f"{row['nom']} ({row['reference']})" for index, row in products_df.iterrows()}
            product_id_to_update = st.selectbox("Sélectionnez le produit à modifier", 
                                                options=list(product_map_mod.keys()),
                                                format_func=lambda x: product_map_mod[x],
                                                key="update_product_id")
                                               
            if product_id_to_update:
                current_data = products_df[products_df['id'] == product_id_to_update].iloc[0]
                
                with st.form("update_product_form"):
                    u_nom = st.text_input("Nom du Produit", value=current_data['nom'], max_chars=100)
                    u_reference = st.text_input("Référence (Code Produit)", value=current_data['reference'], max_chars=50)
                    u_stock = st.number_input("Stock Actuel", min_value=0, value=int(current_data['stock']))
                    u_prix_vente = st.number_input("Prix de Vente Unitaire (DH)", value=float(current_data['prix_vente']), min_value=0.01, format="%.2f")
                    
                    if st.form_submit_button("💾 Enregistrer les Modifications Produit"):
                        if u_nom and u_reference and update_product(product_id_to_update, u_nom, u_reference, u_stock, u_prix_vente):
                            st.success(f"Produit '{u_nom}' mis à jour avec succès.")
                            log_access(st.session_state.user_id, "user", "produits", f"Mise à jour produit ID {product_id_to_update}")
                            st.rerun()
                        elif not u_nom or not u_reference:
                            st.error("Le nom et la référence du produit sont obligatoires.")
        elif not has_access("produits", "ecriture"):
            st.warning("Vous n'avez pas les permissions d'écriture pour modifier des produits.")
        else:
            st.info("Aucun produit à modifier.")


# --- Autres modules (placeholders) ---

def module_espace_client():
    if not (st.session_state.get('is_client') or st.session_state.role_name == 'admin'):
        st.error("❌ Accès refusé à l'Espace Client.")
        return
        
    st.header(f"🛒 Passez votre Commande, {st.session_state.user_name}")
    st.info("Ce module nécessite la logique de commande complète.") # Placeholder for brevity

def module_dashboard():
    st.title(f"🚀 Tableau de Bord - Bienvenue, {st.session_state.user_name.split()[0]}!")
    if not st.session_state.get('is_client'):
        log_access(st.session_state.user_id, "user", "Dashboard", "Consultation")
        st.markdown(f"**Rôle actuel :** `{st.session_state.role_name.upper()}`")
    else:
        st.info("Mode Client Actif. Utilisez l'option 'Passer Commande' pour commencer.")
    st.divider()

def module_notifications():
    if st.session_state.get('is_client'):
        st.header("🔔 Suivi des Commandes")
        st.info("Ce module est en cours de développement. Vous y verrez bientôt le statut de vos commandes.")
        return
    st.header("🔔 Vos Notifications")
    log_access(st.session_state.user_id, "user", "notifications", "Consultation")
    st.info("Affichage des notifications pour le personnel.") # Placeholder for brevity

def module_placeholder(module_key, menu_label):
    if not has_access(module_key, "lecture"):
        st.error("❌ Accès refusé à ce module.")
        return
    
    st.title(f"🛠️ Module : {menu_label.split()[1]} (ID: {module_key})")
    st.info(f"Le contenu du module **{menu_label}** est en cours de développement.")


# ========== 6. APPLICATION PRINCIPALE STREAMLIT (Routage) ==========

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.is_client = False

if not st.session_state.logged_in:
    # --- Écran de Connexion ---
    st.image("https://upload.wikimedia.org/wikipedia/commons/0/0e/Ofppt.png", width=150)
    st.title("🎓 SYGEP - Connexion")
    
    tab_interne, tab_client = st.tabs(["🔒 Personnel (Email/Mot de Passe)", "👤 Accès Client (Nom uniquement)"])
    
    with tab_interne:
        st.write("Réservé au personnel interne.")
        with st.form("login_form_internal"):
            st.text_input("Email", key="auth_email")
            st.text_input("Mot de passe", type="password", key="auth_password")
            submitted = st.form_submit_button("🔒 Se connecter")
            if submitted: authenticate_internal()
            if 'login_error_internal' in st.session_state and st.session_state.login_error_internal:
                st.error(st.session_state.login_error_internal)
                st.session_state.login_error_internal = "" 

    with tab_client:
        st.write("Accès direct pour les clients.")
        with st.form("login_form_client"):
            st.text_input("Nom du Client", key="auth_client_name")
            submitted_client = st.form_submit_button("🛒 Accéder à l'Espace Client")
            if submitted_client: authenticate_client()
            if 'login_error_client' in st.session_state and st.session_state.login_error_client:
                st.error(st.session_state.login_error_client)
                st.session_state.login_error_client = ""
                

else:
    # --- Application Principale (Menu et Routage) ---
    
    with st.sidebar:
        st.header(f"Bonjour, {st.session_state.user_name.split()[0]}")
        st.caption(f"Rôle : **{st.session_state.role_name.upper()}**")
        st.divider()

        # Options de navigation 
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
        client_menu_options = {
            "🏠 Tableau de Bord": "dashboard",
            "🛍️ Passer Commande": "espace_client",
            "🔔 Suivi Notifications": "notifications",
        }
        
        if st.session_state.is_client:
            menu_options = client_menu_options
            allowed_options = menu_options
        else:
            menu_options = internal_menu_options
            allowed_options = {}
            for label, module_key in menu_options.items():
                if module_key == "dashboard" or has_access(module_key, "lecture"):
                    allowed_options[label] = module_key


        menu = st.radio("Navigation", list(allowed_options.keys()))
        
        st.divider()
        st.button("Déconnexion", on_click=logout)

        # Footer Sidebar 
        st.sidebar.markdown("---")
        date_footer = datetime.now().strftime('%d/%m/%Y')
        st.sidebar.markdown(f"""
        <div style="background-color: #f8fafc; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0;">
            <p style="margin: 0; font-size: 11px; color: #64748b; text-align: center;">
                <strong style="color: #1e40af;">SYGEP v6.0</strong><br>
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


    # Logique de Routage
    
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
    elif current_module == "fournisseurs": # <-- Appel du nouveau module CRUD
        module_gestion_fournisseurs()
    else:
        module_placeholder(current_module, menu)
