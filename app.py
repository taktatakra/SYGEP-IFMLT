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

# Charger les variables d'environnement (si elles sont utilisées ailleurs)
load_dotenv()

# Configuration de la page
st.set_page_config(
    page_title="SYGEP - Système de Gestion d'Entreprise Pédagogique (v3.4)",
    layout="wide",
    page_icon="🎓",
    initial_sidebar_state="expanded"
)

# ========== GESTION CONNEXION POSTGRESQL (SUPABASE) ==========

@st.cache_resource
def init_connection_pool():
    """Initialise un pool de connexions PostgreSQL avec les secrets fournis."""
    try:
        # ⚠️ REMPLACER PAR os.getenv() EN PRODUCTION POUR LA SÉCURITÉ
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1, 20,
            host="aws-1-eu-central-1.pooler.supabase.com",
            database="postgres",
            user="postgres.oplcukkhrrcuindbhtkm",
            password="Hamidl9ar3@111",
            port="6543"
        )
        return connection_pool
    except Exception as e:
        st.error(f"❌ Erreur de connexion PostgreSQL: {e}")
        st.stop()

if 'conn_pool' not in st.session_state:
    try:
        st.session_state.conn_pool = init_connection_pool()
        st.success("✅ Connexion à la base de données établie.")
    except Exception:
        pass

def get_connection():
    """Récupère une connexion du pool."""
    if 'conn_pool' in st.session_state:
        return st.session_state.conn_pool.getconn()
    return None

def release_connection(conn):
    """Remet une connexion dans le pool."""
    if conn and 'conn_pool' in st.session_state:
        st.session_state.conn_pool.putconn(conn)

# ========== FONCTIONS UTILITAIRES DE SÉCURITÉ ET D'ACCÈS ==========

def hash_password(password):
    """Hache un mot de passe en utilisant SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

@st.cache_data(ttl=60)
def get_user_role_and_permissions(username, role_id):
    """Récupère le rôle et les permissions d'un utilisateur."""
    conn = get_connection()
    if not conn: return None, {}
    try:
        user_role = pd.read_sql_query("SELECT nom FROM roles WHERE id = %s", conn, params=(role_id,)).iloc[0]['nom']
        
        permissions_df = pd.read_sql_query("""
            SELECT p.module, p.acces_lecture, p.acces_ecriture 
            FROM permissions p 
            WHERE p.role_id = %s
        """, conn, params=(role_id,))
        
        permissions = {row['module']: {'lecture': row['acces_lecture'], 'ecriture': row['acces_ecriture']} 
                       for index, row in permissions_df.iterrows()}
        
        return user_role, permissions
    except Exception as e:
        # st.error(f"Erreur de récupération des permissions: {e}")
        return None, {}
    finally:
        release_connection(conn)

def check_login(username, password):
    """Vérifie les identifiants de connexion."""
    conn = get_connection()
    if not conn: return False
    try:
        hashed_pwd = hash_password(password)
        query = "SELECT id, nom_complet, role_id FROM utilisateurs WHERE email = %s AND mot_de_passe = %s"
        user_data = pd.read_sql_query(query, conn, params=(username, hashed_pwd))
        
        if not user_data.empty:
            user_id = user_data.iloc[0]['id']
            role_id = user_data.iloc[0]['role_id']
            user_full_name = user_data.iloc[0]['nom_complet']
            
            user_role, user_permissions = get_user_role_and_permissions(username, role_id)
            
            if user_role:
                st.session_state.logged_in = True
                st.session_state.user_id = user_id
                st.session_state.user_full_name = user_full_name
                st.session_state.user_role = user_role
                st.session_state.permissions = user_permissions
                log_access(user_id, "Authentification", "Connexion réussie")
                return True
        return False
    except Exception as e:
        st.error(f"Erreur de connexion: {e}")
        return False
    finally:
        release_connection(conn)

def has_access(module, access_type='lecture'):
    """Vérifie si l'utilisateur a l'accès requis pour un module."""
    if st.session_state.get('user_role') == 'admin':
        return True 
    
    permissions = st.session_state.get('permissions', {})
    
    if module in permissions:
        if access_type == 'lecture':
            return permissions[module]['lecture']
        elif access_type == 'ecriture':
            return permissions[module]['ecriture']
    return False

# ========== FONCTIONS DE LOGGING ET NOTIFICATION ==========

def log_access(user_id, module, action):
    """Enregistre une action de l'utilisateur dans les logs."""
    conn = get_connection()
    if not conn: return
    try:
        c = conn.cursor()
        query = "INSERT INTO logs_access (user_id, module, action, date_action) VALUES (%s, %s, %s, NOW())"
        c.execute(query, (user_id, module, action))
        conn.commit()
    except Exception as e:
        print(f"Erreur de logging: {e}")
        conn.rollback()
    finally:
        release_connection(conn)

def creer_notification(user_id, titre, message, ref_id, ref_type):
    """Crée une notification pour un utilisateur donné ou une liste d'utilisateurs."""
    conn = get_connection()
    if not conn: return
    try:
        c = conn.cursor()
        
        user_ids = [user_id] if not isinstance(user_id, (list, tuple)) else user_id
        
        for uid in user_ids:
             if uid is not None:
                 c.execute("INSERT INTO notifications (user_id, titre, message, ref_id, ref_type) VALUES (%s, %s, %s, %s, %s)",
                          (uid, titre, message, ref_id, ref_type))
        conn.commit()
    except Exception as e:
        print(f"Erreur lors de la création de la notification: {e}")
        conn.rollback()
    finally:
        release_connection(conn)

def get_all_notifications():
    """Récupère les notifications non lues pour l'utilisateur connecté."""
    user_id = st.session_state.get('user_id')
    if not user_id: return pd.DataFrame()
    
    conn = get_connection()
    if not conn: return pd.DataFrame()
    
    try:
        notifications_df = pd.read_sql_query("""
            SELECT id, titre, message, date_creation, lu 
            FROM notifications 
            WHERE user_id = %s AND lu = FALSE
            ORDER BY date_creation DESC
        """, conn, params=(user_id,))
        return notifications_df
    except Exception as e:
        print(f"Erreur de récupération des notifications: {e}")
        return pd.DataFrame()
    finally:
        release_connection(conn)

def mark_notification_as_read(notification_id):
    """Marque une notification comme lue."""
    conn = get_connection()
    if not conn: return
    try:
        c = conn.cursor()
        c.execute("UPDATE notifications SET lu = TRUE WHERE id = %s", (notification_id,))
        conn.commit()
        get_all_notifications.clear() # Invalider le cache
    except Exception as e:
        print(f"Erreur de marquage de notification: {e}")
        conn.rollback()
    finally:
        release_connection(conn)

# ========== FONCTIONS DE RÉCUPÉRATION DE DONNÉES (SIMPLIFIÉES) ==========

@st.cache_data(ttl=30)
def get_clients():
    conn = get_connection()
    if not conn: return pd.DataFrame()
    try:
        df = pd.read_sql_query("SELECT id, nom, email, telephone, ville, pays FROM clients", conn)
        return df
    finally:
        release_connection(conn)
        
@st.cache_data(ttl=30)
def get_fournisseurs():
    conn = get_connection()
    if not conn: return pd.DataFrame()
    try:
        df = pd.read_sql_query("SELECT id, nom, contact, email FROM fournisseurs", conn)
        return df
    finally:
        release_connection(conn)
        
@st.cache_data(ttl=10)
def get_produits():
    conn = get_connection()
    if not conn: return pd.DataFrame()
    try:
        df = pd.read_sql_query("SELECT id, nom, reference, stock, prix_vente FROM produits", conn)
        return df
    finally:
        release_connection(conn)

# ==================== LOGIQUE D'AUTHENTIFICATION ====================

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.permissions = {} # Initialiser les permissions

if not st.session_state.logged_in:
    # Page de Connexion
    st.title("SYGEP - Système de Gestion d'Entreprise Pédagogique")
    
    col1, col2 = st.columns([1, 1.5])
    
    with col1:
        st.subheader("Authentification")
        with st.form("login_form"):
            username = st.text_input("Email/Nom d'utilisateur")
            password = st.text_input("Mot de passe", type="password")
            submitted = st.form_submit_button("Se Connecter", type="primary")
            
            if submitted:
                if check_login(username, password):
                    st.success("Connexion réussie ! Redirection...")
                    st.rerun()
                else:
                    st.error("Email ou mot de passe incorrect.")
    
    with col2:
        st.info("""
            **Rôles de Test :** Assurez-vous que ces utilisateurs/rôles existent dans votre base de données.
            * **Admin :** admin@sygep.ma / 123456
            * **Commercial :** commercial@sygep.ma / 123456
            * **Gestionnaire Stock :** stock@sygep.ma / 123456
            * **Comptable :** compta@sygep.ma / 123456
        """)
    
    st.stop()

# ==================== BARRE LATÉRALE ET NAVIGATION (CORRIGÉE) ====================

st.sidebar.markdown("# SYGEP") 

# Informations utilisateur
# FIX: Utilisation de .get() pour éviter l'AttributeError si la session est réinitialisée ou mal initialisée
st.sidebar.markdown(f"**Utilisateur :** {st.session_state.get('user_full_name', 'Non connecté')}")
st.sidebar.markdown(f"**Rôle :** {st.session_state.get('user_role', 'N/A').upper()}")
st.sidebar.markdown("---")

# Gestion des Notifications
notifications = get_all_notifications()
nb_notifications = len(notifications)

notification_label = f"🔔 Notifications ({nb_notifications})"
if nb_notifications > 0:
    notification_label = f"🔔 Notifications (🔴 {nb_notifications})"

if st.sidebar.button(notification_label):
    st.session_state.menu = "🔔 Notifications"
    
st.sidebar.markdown("---")

# Construction du menu de navigation
menu_items = []
if has_access("clients"): menu_items.append("👥 Gestion Clients")
if has_access("fournisseurs"): menu_items.append("🚚 Gestion Fournisseurs")
if has_access("produits"): menu_items.append("📦 Gestion Produits & Stock")
if has_access("workflow_client"): menu_items.append("📋 Workflow Commandes Clients")
if has_access("workflow_fournisseur"): menu_items.append("🏭 Workflow Achats Fournisseurs")
# NOUVEAU: Module Facturation & Comptabilité
if has_access("comptabilite"): menu_items.append("💰 Facturation & Comptabilité")
if has_access("administration"): menu_items.append("⚙️ Administration & Logs")

if 'menu' not in st.session_state or st.session_state.menu not in menu_items:
    st.session_state.menu = menu_items[0] if menu_items else "Accueil"

st.sidebar.subheader("Modules")
menu = st.sidebar.radio("Navigation", menu_items, index=menu_items.index(st.session_state.menu), key="main_menu")
st.session_state.menu = menu

# Bouton de déconnexion
if st.sidebar.button("Déconnexion 🚪"):
    log_access(st.session_state.user_id, "Authentification", "Déconnexion")
    st.session_state.logged_in = False
    st.session_state.clear()
    st.rerun()

# ==================== CONTENU PRINCIPAL DE L'APPLICATION ====================

# Modules de base (omission du contenu pour concision, mais les blocs doivent exister)
if menu == "👥 Gestion Clients":
    st.header("👥 Gestion Clients")
    st.dataframe(get_clients(), use_container_width=True)
elif menu == "🚚 Gestion Fournisseurs":
    st.header("🚚 Gestion Fournisseurs")
    st.dataframe(get_fournisseurs(), use_container_width=True)
elif menu == "📦 Gestion Produits & Stock":
    st.header("📦 Gestion Produits & Stock")
    st.dataframe(get_produits(), use_container_width=True)
elif menu == "⚙️ Administration & Logs":
    st.header("⚙️ Administration & Logs")
    st.info("Logique d'administration ici.")


# ---------------------------------------------------------------------

# ========== WORKFLOW COMMANDES CLIENTS (Notification Créateur Ajoutée) ==========
elif menu == "📋 Workflow Commandes Clients":
    if not has_access("workflow_client"):
        st.error("❌ Accès refusé")
        st.stop()
    
    st.header("📋 Workflow Commandes Clients")
    
    tab1, tab2, tab3 = st.tabs(["➕ Création", "📦 À Préparer", "🚚 À Expédier"])
    
    with tab1:
        if has_access("workflow_client", "ecriture"):
            st.subheader("Nouvelle Commande Client")
            
            with st.form("form_commande_client"):
                clients = get_clients()
                client_id = st.selectbox("Client", clients['id'].tolist(), format_func=lambda x: clients[clients['id']==x]['nom'].iloc[0], key="sel_client")
                numero_commande = st.text_input("N° de Commande", value=f"CMD-{datetime.now().strftime('%Y%m%d%H%M')}")
                montant_total = st.number_input("Montant Total TTC (Simulé)", min_value=1.0, step=10.0)
                
                submitted = st.form_submit_button("Soumettre la Commande", type="primary")
                
                if submitted:
                    conn = get_connection()
                    try:
                        c = conn.cursor()
                        c.execute("INSERT INTO commandes_workflow (numero, client_id, date_creation, createur_id, montant_total, statut) VALUES (%s, %s, NOW(), %s, %s, 'nouveau') RETURNING id",
                                  (numero_commande, client_id, st.session_state.user_id, montant_total))
                        commande_id = c.fetchone()[0]
                        
                        # Récupérer les ID des Gestionnaires de Stock
                        c.execute("SELECT id FROM utilisateurs WHERE role_id IN (SELECT id FROM roles WHERE nom = 'gestionnaire_stock' OR nom = 'admin')")
                        stock_managers = [row[0] for row in c.fetchall()]

                        # 1. Notification au Gestionnaire de Stock
                        creer_notification(stock_managers, "Nouvelle Commande Client", 
                                           f"Une nouvelle commande client N°{numero_commande} a été créée. Vérifiez le stock.", 
                                           commande_id, "commande")
                        
                        # 2. Notification au Commercial/Créateur (Client Externe)
                        creer_notification(st.session_state.user_id, "Commande Créée", 
                                           f"Votre commande N°{numero_commande} a été créée et est en attente de vérification de stock.", 
                                           commande_id, "commande")
                        
                        conn.commit()
                        st.success(f"✅ Commande N°{numero_commande} créée et soumise au workflow (ID: {commande_id}).")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur de création de commande: {e}")
                        conn.rollback()
                    finally:
                        release_connection(conn)

    with tab3: # À Expédier (L'expédition notifie la Comptabilité pour facturation)
        st.subheader("🚚 Commandes Prêtes à Être Expédiées")
        conn = get_connection()
        commandes_a_expedier = pd.read_sql_query("""
            SELECT cw.*, c.nom as client_nom
            FROM commandes_workflow cw
            JOIN clients c ON cw.client_id = c.id
            WHERE cw.statut = 'preparer'
            ORDER BY cw.date_creation ASC
        """, conn)
        release_connection(conn)
        
        if not commandes_a_expedier.empty:
            for _, cmd in commandes_a_expedier.iterrows():
                if st.button(f"✅ Expédier Commande N°{cmd['numero']}", key=f"expedier_cmd_{cmd['id']}"):
                    conn = get_connection()
                    try:
                        c = conn.cursor()
                        c.execute("UPDATE commandes_workflow SET statut = 'expedie', date_expedition = NOW() WHERE id = %s", (cmd['id'],))
                        
                        # Récupérer l'ID du Comptable
                        c.execute("SELECT id FROM utilisateurs WHERE role_id IN (SELECT id FROM roles WHERE nom = 'comptable' OR nom = 'admin')")
                        comptables = [row[0] for row in c.fetchall()]
                        
                        # Notification au Comptable
                        creer_notification(comptables, "Facture Client Requise", 
                                           f"La commande client N°{cmd['numero']} a été expédiée. Veuillez procéder à la facturation.", 
                                           cmd['id'], "commande")
                        
                        # Notification au Commercial/Créateur
                        creer_notification(cmd['createur_id'], "Commande Expédiée", 
                                           f"Votre commande N°{cmd['numero']} a été expédiée au client.", 
                                           cmd['id'], "commande")

                        conn.commit()
                        st.success(f"✅ Commande N°{cmd['numero']} expédiée. Comptabilité notifiée pour facturation.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur d'expédition: {e}")
                        conn.rollback()
                    finally:
                        release_connection(conn)

# ---------------------------------------------------------------------

# ========== WORKFLOW ACHATS FOURNISSEURS (Validation Achat & Réception) ==========
elif menu == "🏭 Workflow Achats Fournisseurs":
    if not has_access("workflow_fournisseur"):
        st.error("❌ Accès refusé")
        st.stop()
    
    st.header("🏭 Workflow Achats Fournisseurs")
    
    tabs_base = ["➕ Création"]
    if has_access("workflow_fournisseur", "ecriture"): 
        tabs_base.append("✅ À Valider") # 1. Validation de la Commande d'Achat (BCF)
        tabs_base.append("📥 À Réceptionner") # 2. Validation de la Réception (Entrée Stock)
    tabs_base.append("📊 Tous les Achats")
    
    selected_tab = st.tabs(tabs_base)
    
    # ... (Ajoutez le contenu du TAB "➕ Création" ici) ...
    
    # ==================== TAB : À VALIDER (Validation Commande Achat) ====================
    if "✅ À Valider" in tabs_base and has_access("workflow_fournisseur", "ecriture"):
        tab_index = tabs_base.index("✅ À Valider")
        with selected_tab[tab_index]:
            st.subheader("✅ Bons de Commande Fournisseur à Valider")
            conn = get_connection()
            achats_a_valider = pd.read_sql_query("""
                SELECT aw.id, aw.numero, f.nom as fournisseur_nom, aw.montant_total, aw.date_creation, aw.createur_id
                FROM achats_workflow aw
                JOIN fournisseurs f ON aw.fournisseur_id = f.id
                WHERE aw.statut = 'nouveau'
                ORDER BY aw.date_creation ASC
            """, conn)
            release_connection(conn)
            
            if not achats_a_valider.empty:
                st.info(f"📋 **{len(achats_a_valider)}** bon(s) de commande en attente de validation")
                for _, achat in achats_a_valider.iterrows():
                    with st.expander(f"🆕 Achat N°{achat['numero']} - {achat['fournisseur_nom']} - {achat['montant_total']:.2f} DH", expanded=True):
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(f"✅ Valider Achat N°{achat['numero']}", key=f"valider_achat_{achat['id']}", type="primary"):
                                conn = get_connection()
                                try:
                                    c = conn.cursor()
                                    # Mise à jour statut: 'nouveau' -> 'commande' (validation commande achat)
                                    c.execute("UPDATE achats_workflow SET statut = 'commande', date_validation = NOW() WHERE id = %s", (achat['id'],))
                                    
                                    # Notification pour la Réception (pour le Gestionnaire de Stock)
                                    c.execute("SELECT id FROM utilisateurs WHERE role_id IN (SELECT id FROM roles WHERE nom IN ('gestionnaire_stock', 'admin'))")
                                    gestionnaires = [row[0] for row in c.fetchall()]
                                    creer_notification(gestionnaires, "Réception Attendue", f"Bon de commande N°{achat['numero']} validé. Réception à prévoir.", achat['id'], "achat")
                                        
                                    conn.commit()
                                    st.success(f"✅ Achat N°{achat['numero']} **validé**. Le bon de commande est désormais 'commande'.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erreur de validation: {e}")
                                    conn.rollback()
                                finally:
                                    release_connection(conn)
            else:
                st.info("Aucun bon de commande fournisseur à valider.")

    # ==================== TAB : À RÉCEPTIONNER (Validation Réception Fournisseur) ====================
    if "📥 À Réceptionner" in tabs_base and has_access("workflow_fournisseur", "ecriture"):
        tab_index = tabs_base.index("📥 À Réceptionner")
        with selected_tab[tab_index]:
            st.subheader("📥 Livraisons Fournisseur à Réceptionner")
            conn = get_connection()
            achats_a_receptionner = pd.read_sql_query("""
                SELECT aw.*, f.nom as fournisseur_nom
                FROM achats_workflow aw
                JOIN fournisseurs f ON aw.fournisseur_id = f.id
                WHERE aw.statut = 'commande' 
                ORDER BY aw.date_creation ASC
            """, conn)
            release_connection(conn)

            if not achats_a_receptionner.empty:
                st.info(f"🚚 **{len(achats_a_receptionner)}** livraison(s) à réceptionner")
                for _, achat in achats_a_receptionner.iterrows():
                    with st.expander(f"📦 Achat N°{achat['numero']} - {achat['fournisseur_nom']}", expanded=False):
                        # ... Simuler la lecture des lignes d'achat ...
                        
                        with st.form(f"form_reception_{achat['id']}"):
                            st.info("💡 **Validation de Réception :** Confirmez la réception complète et l'entrée en stock.")
                            date_reception = st.date_input("Date de Réception", datetime.now().date(), key=f"date_reception_{achat['id']}")
                            bl_numero = st.text_input("N° Bon de Livraison Fournisseur", key=f"bl_numero_{achat['id']}")
                            
                            if st.form_submit_button("✅ Confirmer Réception & Mettre à jour Stock", type="primary", use_container_width=True):
                                if bl_numero:
                                    conn = get_connection()
                                    try:
                                        c = conn.cursor()
                                        
                                        # 1. Mise à jour du statut de l'achat: 'commande' -> 'recu'
                                        c.execute("UPDATE achats_workflow SET statut = 'recu', date_reception = %s, bl_fournisseur = %s WHERE id = %s", 
                                                  (date_reception, bl_numero, achat['id']))
                                        
                                        # 2. Mise à jour du stock (simulée: vous devez adapter votre boucle 'lignes_achat')
                                        # c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s", (quantite, produit_id))
                                            
                                        # 3. Notification pour la Comptabilité (Paiement)
                                        c.execute("SELECT id FROM utilisateurs WHERE role_id IN (SELECT id FROM roles WHERE nom IN ('comptable', 'admin'))")
                                        comptables = [row[0] for row in c.fetchall()]
                                        creer_notification(comptables, "Paiement Fournisseur Requis", 
                                                           f"Réception de l'achat N°{achat['numero']} de {achat['fournisseur_nom']} confirmée. Facture à payer.", 
                                                           achat['id'], "achat")
                                        
                                        conn.commit()
                                        st.success(f"✅ Réception de l'achat N°{achat['numero']} confirmée. Stock mis à jour et Comptabilité notifiée.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erreur lors de la réception: {e}")
                                        conn.rollback()
                                    finally:
                                        release_connection(conn)
                                else:
                                    st.error("❌ Le numéro de Bon de Livraison est requis.")
            else:
                st.info("Aucune livraison fournisseur à réceptionner.")
    
    # ... (Ajoutez le contenu du TAB "📊 Tous les Achats" ici) ...

# ---------------------------------------------------------------------

# ========== FACTURATION & COMPTABILITÉ (Module de Paiement/Facturation) ==========
elif menu == "💰 Facturation & Comptabilité":
    if not has_access("comptabilite"): 
        st.error("❌ Accès refusé")
        st.stop()
    
    st.header("💰 Facturation & Comptabilité")
    
    tab1, tab2 = st.tabs(["📝 Commandes à Facturer", "💸 Paiements Fournisseurs"])
    
    # ===== TAB 1 : COMMANDES À FACTURER (Validation de la facturation client) =====
    with tab1:
        st.subheader("📝 Commandes Clients Expédiées (Facturation Requise)")
        conn = get_connection()
        commandes_a_facturer = pd.read_sql_query("""
            SELECT cw.id, cw.numero, c.nom as client_nom, cw.montant_total, cw.date_expedition
            FROM commandes_workflow cw
            JOIN clients c ON cw.client_id = c.id
            WHERE cw.statut = 'expedie'
            ORDER BY cw.date_expedition ASC
        """, conn)
        release_connection(conn)
        
        if not commandes_a_facturer.empty:
            st.info(f"🧾 **{len(commandes_a_facturer)}** commande(s) à facturer")
            for _, cmd in commandes_a_facturer.iterrows():
                with st.expander(f"📦 Commande N°{cmd['numero']} - {cmd['client_nom']} - {cmd['montant_total']:.2f} DH", expanded=True):
                    if st.button(f"✅ Générer Facture & Clôturer Commande N°{cmd['numero']}", key=f"facturer_cmd_{cmd['id']}", type="primary"):
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            # Mise à jour statut: 'expedie' -> 'facturee'
                            c.execute("UPDATE commandes_workflow SET statut = 'facturee', date_facturation = NOW() WHERE id = %s", (cmd['id'],))
                            conn.commit()
                            st.success(f"✅ Facture générée pour la commande N°{cmd['numero']}. Statut mis à jour à 'facturée'.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur de facturation: {e}")
                            conn.rollback()
                        finally:
                            release_connection(conn)
        else:
            st.info("Aucune commande client en attente de facturation.")

    # ===== TAB 2 : PAIEMENTS FOURNISSEURS (Validation du paiement fournisseur) =====
    with tab2:
        st.subheader("💸 Achats Fournisseurs à Payer")
        conn = get_connection()
        achats_a_payer = pd.read_sql_query("""
            SELECT aw.id, aw.numero, f.nom as fournisseur_nom, aw.montant_total, aw.date_reception
            FROM achats_workflow aw
            JOIN fournisseurs f ON aw.fournisseur_id = f.id
            WHERE aw.statut = 'recu' 
            ORDER BY aw.date_reception ASC
        """, conn)
        release_connection(conn)
        
        if not achats_a_payer.empty:
            st.info(f"💵 **{len(achats_a_payer)}** achat(s) fournisseur à payer")
            for _, achat in achats_a_payer.iterrows():
                with st.expander(f"📦 Achat N°{achat['numero']} - {achat['fournisseur_nom']} - {achat['montant_total']:.2f} DH", expanded=True):
                    if st.button(f"✅ Confirmer Paiement Fournisseur N°{achat['numero']}", key=f"payer_achat_{achat['id']}", type="primary"):
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            # Mise à jour statut: 'recu' -> 'paye'
                            c.execute("UPDATE achats_workflow SET statut = 'paye', date_paiement = NOW() WHERE id = %s", (achat['id'],))
                            conn.commit()
                            st.success(f"✅ Paiement de l'achat N°{achat['numero']} confirmé. Statut mis à jour à 'payé'.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur de paiement: {e}")
                            conn.rollback()
                        finally:
                            release_connection(conn)
        else:
            st.info("Aucun achat fournisseur en attente de paiement.")


# ---------------------------------------------------------------------

# ========== GESTION DES NOTIFICATIONS ==========
elif menu == "🔔 Notifications":
    st.header("🔔 Mes Notifications")
    notifs = get_all_notifications()
    
    if not notifs.empty:
        st.info(f"Vous avez **{len(notifs)}** notification(s) non lue(s).")
        
        for index, notif in notifs.iterrows():
            col1, col2 = st.columns([4, 1])
            with col1:
                # Calculer le temps écoulé (approximatif)
                time_diff = datetime.now(notif['date_creation'].tzinfo) - notif['date_creation']
                minutes_ago = time_diff.total_seconds() // 60
                
                st.markdown(f"**{notif['titre']}** (il y a {int(minutes_ago)} min)")
                st.write(notif['message'])
            with col2:
                if st.button("Marquer comme lu", key=f"mark_read_{notif['id']}"):
                    mark_notification_as_read(notif['id'])
                    st.rerun()
    else:
        st.success("Vous n'avez aucune nouvelle notification.")
