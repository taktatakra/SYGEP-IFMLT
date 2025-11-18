import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import hashlib
import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Configuration de la page
st.set_page_config(
    page_title="SYGEP - Système de Gestion d'Entreprise Pédagogique (v7.3 INTÉGRAL)",
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

def release_connection(conn):
    """Libère une connexion vers le pool."""
    if conn:
        st.session_state.conn_pool.putconn(conn)

# ========== 2. FONCTIONS UTILITAIRES ET SÉCURITÉ (Identiques à v7.2) ==========

def hash_password(password):
    """Hache un mot de passe en utilisant SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

def log_access(entity_id, entity_type, module, action):
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
        release_connection(conn)


def get_user_role_and_name(username, password_hash):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT id, nom_complet, role
            FROM utilisateurs
            WHERE username = %s AND password = %s
        """, (username, password_hash))
        
        user_data = c.fetchone()
        
        if user_data:
            user_id = str(user_data[0]) 
            nom_complet = user_data[1] 
            role_name = user_data[2]
            return user_id, nom_complet, role_name
        return None, None, None
    finally:
        release_connection(conn)


def has_access(module, access_type="lecture"):
    if st.session_state.get('is_client'):
        return module in ["espace_client", "notifications", "dashboard"] 

    if st.session_state.role_name == 'admin': 
        return True
    
    if module in ["dashboard", "notifications"]:
        return True
    
    conn = get_connection()
    try:
        c = conn.cursor()
        access_column = "acces_lecture" if access_type == "lecture" else "acces_ecriture"

        c.execute(f"""
            SELECT {access_column}
            FROM permissions
            WHERE user_id = %s AND module = %s
        """, (st.session_state.user_id, module))
        
        permission = c.fetchone()
        
        if permission and permission[0] is True:
            return True
        return False
    except Exception:
        return False
    finally:
        release_connection(conn)

# Fonctions d'authentification et de déconnexion (Identiques à v7.2)
def authenticate_internal():
    username = st.session_state.auth_username
    password = st.session_state.auth_password
    hashed_password = hash_password(password)
    user_id, nom_complet, role_name = get_user_role_and_name(username, hashed_password)
    
    if user_id:
        st.session_state.logged_in = True
        st.session_state.is_client = False 
        st.session_state.user_id = user_id
        st.session_state.user_name = nom_complet
        st.session_state.role_name = role_name
        log_access(user_id, "user", "Authentification", "Connexion réussie")
        st.rerun()
    else:
        st.session_state.login_error_internal = "Nom d'utilisateur ou mot de passe incorrect."

def authenticate_client():
    client_name = st.session_state.auth_client_name
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT id, nom FROM clients WHERE nom ILIKE %s", (client_name.strip(),))
        client_data = c.fetchone()
        
        if client_data:
            client_id = client_data[0]
            client_name_db = client_data[1]
            
            st.session_state.logged_in = True
            st.session_state.is_client = True 
            st.session_state.client_id = client_id
            st.session_state.user_name = client_name_db
            st.session_state.role_name = 'client'
            st.rerun()
        else:
            st.session_state.login_error_client = "Nom de client non trouvé."
    except Exception as e:
        st.error(f"Erreur d'accès à la table 'clients' : {e}")
    finally:
        release_connection(conn)

def logout():
    if not st.session_state.get('is_client') and 'user_id' in st.session_state:
        log_access(st.session_state.user_id, "user", "Authentification", "Déconnexion")
    st.session_state.clear()
    st.rerun()


# ========== 3. FONCTIONS DE GESTION DE DONNÉES (CRUD COMPLET) ==========

# --- CRUD Clients (Rétabli au schéma complet) ---
@st.cache_data(ttl=60)
def get_clients():
    conn = get_connection()
    try:
        # ** Rétabli au schéma complet **
        clients_df = pd.read_sql_query("SELECT id, nom, email, telephone, adresse, ville, pays FROM clients ORDER BY nom", conn) 
        return clients_df
    except Exception as e:
        st.error(f"Erreur lors de la lecture de la table 'clients' (schéma complet attendu) : {e}")
        return pd.DataFrame({'id':[], 'nom':[]})
    finally:
        release_connection(conn)

# --- CRUD Produits (Rétabli au schéma complet) ---
@st.cache_data(ttl=60)
def get_products():
    conn = get_connection()
    try:
        # ** Rétabli au schéma complet **
        produits_df = pd.read_sql_query("SELECT id, nom, reference, stock, prix_vente, prix_achat FROM produits ORDER BY nom", conn)
        return produits_df
    except Exception as e:
        st.error(f"Erreur lors de la lecture de la table 'produits' (schéma complet attendu) : {e}")
        return pd.DataFrame({'id':[], 'nom':[]})
    finally:
        release_connection(conn)

# --- CRUD Fournisseurs (Rétabli au schéma complet) ---
@st.cache_data(ttl=60)
def get_fournisseurs():
    conn = get_connection()
    try:
        # ** Rétabli au schéma complet **
        fournisseurs_df = pd.read_sql_query("SELECT id, nom, email, telephone, adresse FROM fournisseurs ORDER BY nom", conn)
        return fournisseurs_df
    except Exception as e:
        st.error(f"Erreur lors de la lecture de la table 'fournisseurs' (schéma complet attendu) : {e}")
        return pd.DataFrame({'id':[], 'nom':[]})
    finally:
        release_connection(conn)


# ========== 4. MODULES DE GESTION DE FLUX DE TRAVAIL (Intégration) ==========

def update_product_stock(product_id, quantity_change, operation='sub'):
    """Met à jour le stock du produit. operation='sub' pour soustraire (vente), 'add' pour ajouter (achat)."""
    conn = get_connection()
    try:
        c = conn.cursor()
        
        if operation == 'sub':
            c.execute("UPDATE produits SET stock = stock - %s WHERE id = %s RETURNING stock", 
                      (quantity_change, product_id))
        elif operation == 'add':
            c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s RETURNING stock", 
                      (quantity_change, product_id))
        
        new_stock = c.fetchone()[0]
        conn.commit()
        get_products.clear() # Vider le cache
        return new_stock
    except Exception as e:
        conn.rollback()
        raise Exception(f"Erreur de mise à jour du stock : {e}")
    finally:
        release_connection(conn)


# --- Gestion des Commandes Clients (Ventes) ---
def module_gestion_commandes_clients():
    if not has_access("workflow_client"):
        st.error("❌ Accès refusé à la Gestion des Commandes Clients.")
        log_access(st.session_state.user_id, "user", "workflow_client", "Tentative d'accès refusée")
        return
    
    log_access(st.session_state.user_id, "user", "workflow_client", "Consultation")
    st.header("📝 Gestion des Commandes Clients (Ventes)")
    
    clients_df = get_clients()
    products_df = get_products()
    
    tab1, tab2 = st.tabs(["📋 Historique des Commandes", "➕ Nouvelle Commande"])
    
    with tab1:
        st.subheader("Historique et Statut")
        conn = get_connection()
        try:
            # Requête pour joindre les commandes avec le nom du client et de l'utilisateur
            commandes_df = pd.read_sql_query("""
                SELECT 
                    cc.numero, 
                    cl.nom AS client_nom, 
                    u.nom_complet AS vendeur, 
                    cc.date_commande, 
                    cc.statut,
                    cc.montant_total
                FROM commandes_clients cc
                JOIN clients cl ON cc.client_id = cl.id
                JOIN utilisateurs u ON cc.user_id = u.id
                ORDER BY cc.date_commande DESC
            """, conn)
            
            if not commandes_df.empty:
                st.dataframe(commandes_df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucune commande enregistrée.")
        except Exception as e:
            st.error(f"❌ Erreur lors de la lecture de la table 'commandes_clients' ou du schéma : {e}. **Vérifiez que la table existe.**")
        finally:
            release_connection(conn)


    with tab2:
        if not has_access("workflow_client", "ecriture"):
            st.warning("Vous n'avez pas les permissions d'écriture pour créer des commandes.")
            return

        st.subheader("Créer une Nouvelle Commande")

        with st.form("new_commande_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                client_options = {row['id']: row['nom'] for index, row in clients_df.iterrows()}
                selected_client_id = st.selectbox("Sélectionnez le Client", 
                                                options=list(client_options.keys()), 
                                                format_func=lambda x: client_options[x], 
                                                key="client_id_commande")
                
            with col2:
                # La date est pré-remplie
                st.date_input("Date de la Commande", value=datetime.now().date(), disabled=True)
                
            st.divider()
            st.write("Détails de la Commande (Lignes)")
            
            # Initialisation de la liste des lignes de commande dans session_state
            if 'lignes_commande' not in st.session_state:
                st.session_state.lignes_commande = []

            # Affichage des lignes de commande actuelles
            if st.session_state.lignes_commande:
                lignes_data = []
                for idx, ligne in enumerate(st.session_state.lignes_commande):
                    lignes_data.append({
                        'Produit': products_df[products_df['id'] == ligne['produit_id']]['nom'].iloc[0] if not products_df.empty else 'N/A',
                        'Qté': ligne['quantite'],
                        'Prix Unitaire': f"{ligne['prix_unitaire']:.2f} DH",
                        'Total Ligne': f"{(ligne['quantite'] * ligne['prix_unitaire']):.2f} DH",
                        'Action': f"Supprimer {idx}"
                    })
                st.dataframe(pd.DataFrame(lignes_data), use_container_width=True, hide_index=True)
                st.caption(f"**Montant Total Provisoire :** {sum(l['quantite'] * l['prix_unitaire'] for l in st.session_state.lignes_commande):.2f} DH")


            st.markdown("##### Ajouter un Article")
            col_add_1, col_add_2, col_add_3 = st.columns([4, 2, 1])
            with col_add_1:
                product_options = {row['id']: f"{row['nom']} (Stock: {row['stock']})" for index, row in products_df.iterrows() if row['stock'] > 0}
                new_produit_id = st.selectbox("Produit", options=list(product_options.keys()), format_func=lambda x: product_options[x], key="new_produit_id")
            
            if new_produit_id:
                produit_info = products_df[products_df['id'] == new_produit_id].iloc[0]
                prix_vente_default = produit_info['prix_vente']
                max_stock = produit_info['stock']
                
                with col_add_2:
                    new_quantite = st.number_input(f"Quantité (Max: {max_stock})", min_value=1, max_value=int(max_stock) if max_stock is not None else 1000, value=1, key="new_quantite")
                with col_add_3:
                    st.write("")
                    if st.button("Ajouter à la Commande", key="add_ligne_btn"):
                        if new_quantite > 0 and new_quantite <= max_stock:
                            st.session_state.lignes_commande.append({
                                'produit_id': new_produit_id,
                                'quantite': new_quantite,
                                'prix_unitaire': float(prix_vente_default)
                            })
                            st.rerun() 
                        else:
                            st.error("Quantité invalide ou supérieure au stock disponible.")
            else:
                st.info("Aucun produit disponible en stock pour la vente.")

            
            st.divider()
            submitted = st.form_submit_button("✅ Valider et Enregistrer la Commande", type="primary", disabled=not st.session_state.lignes_commande)

            if submitted:
                if not st.session_state.lignes_commande:
                    st.error("Veuillez ajouter au moins une ligne de commande.")
                    st.stop()
                    
                total_montant = sum(l['quantite'] * l['prix_unitaire'] for l in st.session_state.lignes_commande)
                conn = get_connection()
                
                try:
                    c = conn.cursor()
                    
                    # 1. Génération du numéro de commande (Ex: CMM-YYYYMMDD-ID)
                    c.execute("SELECT nextval('commande_numero_seq')")
                    next_id = c.fetchone()[0]
                    numero_commande = f"CMM-{datetime.now().strftime('%Y%m%d')}-{next_id}"
                    
                    # 2. Insertion de la Commande Principale
                    c.execute("""
                        INSERT INTO commandes_clients (numero, client_id, user_id, date_commande, statut, montant_total) 
                        VALUES (%s, %s, %s, NOW(), %s, %s)
                        RETURNING id
                    """, (numero_commande, selected_client_id, st.session_state.user_id, 'en_attente', total_montant))
                    commande_id = c.fetchone()[0]
                    
                    # 3. Insertion des Lignes et Mise à jour du Stock
                    for ligne in st.session_state.lignes_commande:
                        # Insertion Ligne
                        montant_ligne = ligne['quantite'] * ligne['prix_unitaire']
                        c.execute("""
                            INSERT INTO lignes_commande (commande_id, produit_id, quantite, prix_unitaire, montant_ligne)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (commande_id, ligne['produit_id'], ligne['quantite'], ligne['prix_unitaire'], montant_ligne))

                        # Mise à jour du stock (en soustrayant) - Utilisation directe du curseur pour la transaction
                        c.execute("UPDATE produits SET stock = stock - %s WHERE id = %s", 
                                (ligne['quantite'], ligne['produit_id']))

                    conn.commit()
                    log_access(st.session_state.user_id, "user", "workflow_client", f"Création commande {numero_commande}")
                    st.success(f"🎉 Commande **{numero_commande}** enregistrée avec succès! Stock mis à jour.")
                    st.session_state.lignes_commande = [] # Vider le panier
                    get_products.clear() # Vider le cache des produits pour la maj du stock
                    st.rerun()

                except Exception as e:
                    conn.rollback()
                    st.error(f"❌ Erreur critique lors de l'enregistrement de la commande : {e}")
                finally:
                    release_connection(conn)


# --- Gestion des Achats Fournisseurs ---
def module_gestion_achats_fournisseurs():
    if not has_access("workflow_fournisseur"):
        st.error("❌ Accès refusé à la Gestion des Achats Fournisseurs.")
        log_access(st.session_state.user_id, "user", "workflow_fournisseur", "Tentative d'accès refusée")
        return
    
    log_access(st.session_state.user_id, "user", "workflow_fournisseur", "Consultation")
    st.header("🛒 Gestion des Achats Fournisseurs")
    
    fournisseurs_df = get_fournisseurs()
    products_df = get_products()
    
    tab1, tab2 = st.tabs(["📋 Historique des Achats", "➕ Nouvel Achat"])
    
    with tab1:
        st.subheader("Historique des Achats")
        conn = get_connection()
        try:
            # Requête pour joindre les achats avec le nom du fournisseur et de l'utilisateur
            achats_df = pd.read_sql_query("""
                SELECT 
                    af.numero, 
                    f.nom AS fournisseur_nom, 
                    u.nom_complet AS approvisionneur, 
                    af.date_creation, 
                    af.statut,
                    af.montant_total
                FROM achats_fournisseur af
                JOIN fournisseurs f ON af.fournisseur_id = f.id
                JOIN utilisateurs u ON af.user_id = u.id
                ORDER BY af.date_creation DESC
            """, conn)
            
            if not achats_df.empty:
                st.dataframe(achats_df, use_container_width=True, hide_index=True)
            else:
                st.info("Aucun achat enregistré.")
        except Exception as e:
            st.error(f"❌ Erreur lors de la lecture de la table 'achats_fournisseur' ou du schéma : {e}. **Vérifiez que la table existe.**")
        finally:
            release_connection(conn)

    with tab2:
        if not has_access("workflow_fournisseur", "ecriture"):
            st.warning("Vous n'avez pas les permissions d'écriture pour créer des achats.")
            return

        st.subheader("Créer un Nouvel Ordre d'Achat")

        with st.form("new_achat_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                fournisseur_options = {row['id']: row['nom'] for index, row in fournisseurs_df.iterrows()}
                selected_fournisseur_id = st.selectbox("Sélectionnez le Fournisseur", 
                                                options=list(fournisseur_options.keys()), 
                                                format_func=lambda x: fournisseur_options[x], 
                                                key="fournisseur_id_achat")
                
            with col2:
                st.date_input("Date de l'Achat", value=datetime.now().date(), disabled=True)
                
            st.divider()
            st.write("Détails de l'Achat (Lignes)")
            
            if 'lignes_achat' not in st.session_state:
                st.session_state.lignes_achat = []

            if st.session_state.lignes_achat:
                lignes_data = []
                for idx, ligne in enumerate(st.session_state.lignes_achat):
                    lignes_data.append({
                        'Produit': products_df[products_df['id'] == ligne['produit_id']]['nom'].iloc[0] if not products_df.empty else 'N/A',
                        'Qté': ligne['quantite'],
                        'Prix Achat Unitaire': f"{ligne['prix_unitaire_achat']:.2f} DH",
                        'Total Ligne': f"{(ligne['quantite'] * ligne['prix_unitaire_achat']):.2f} DH",
                        'Action': f"Supprimer {idx}"
                    })
                st.dataframe(pd.DataFrame(lignes_data), use_container_width=True, hide_index=True)
                st.caption(f"**Montant Total Provisoire :** {sum(l['quantite'] * l['prix_unitaire_achat'] for l in st.session_state.lignes_achat):.2f} DH")

            st.markdown("##### Ajouter un Article à Acheter")
            col_add_1, col_add_2, col_add_3 = st.columns([4, 2, 2])
            with col_add_1:
                product_options = {row['id']: row['nom'] for index, row in products_df.iterrows()}
                new_produit_id = st.selectbox("Produit", options=list(product_options.keys()), format_func=lambda x: product_options[x], key="new_produit_id_achat")
            
            if new_produit_id:
                produit_info = products_df[products_df['id'] == new_produit_id].iloc[0]
                prix_achat_default = produit_info['prix_achat'] if produit_info['prix_achat'] else 1.0 # Fallback 
                
                with col_add_2:
                    new_quantite = st.number_input(f"Quantité", min_value=1, value=1, key="new_quantite_achat")
                with col_add_3:
                    new_prix_achat = st.number_input(f"Prix Unitaire Achat", min_value=0.01, value=float(prix_achat_default), key="new_prix_achat_unitaire")

                if st.button("Ajouter à l'Achat", key="add_ligne_achat_btn"):
                    if new_quantite > 0 and new_prix_achat > 0:
                        st.session_state.lignes_achat.append({
                            'produit_id': new_produit_id,
                            'quantite': new_quantite,
                            'prix_unitaire_achat': new_prix_achat
                        })
                        st.rerun() 
                    else:
                        st.error("Quantité ou prix d'achat invalide.")
            else:
                st.info("Aucun produit disponible.")

            st.divider()
            submitted = st.form_submit_button("✅ Valider et Enregistrer l'Ordre d'Achat", type="primary", disabled=not st.session_state.lignes_achat)

            if submitted:
                if not st.session_state.lignes_achat:
                    st.error("Veuillez ajouter au moins une ligne d'achat.")
                    st.stop()
                    
                total_montant = sum(l['quantite'] * l['prix_unitaire_achat'] for l in st.session_state.lignes_achat)
                conn = get_connection()
                
                try:
                    c = conn.cursor()
                    
                    # 1. Génération du numéro d'achat (Ex: ACH-YYYYMMDD-ID)
                    c.execute("SELECT nextval('achat_numero_seq')")
                    next_id = c.fetchone()[0]
                    numero_achat = f"ACH-{datetime.now().strftime('%Y%m%d')}-{next_id}"
                    
                    # 2. Insertion de l'Achat Principal
                    # L'achat est créé en statut 'commande' (commandé), le stock est mis à jour à la réception (non implémentée ici)
                    c.execute("""
                        INSERT INTO achats_fournisseur (numero, fournisseur_id, user_id, date_creation, statut, montant_total) 
                        VALUES (%s, %s, %s, NOW(), %s, %s)
                        RETURNING id
                    """, (numero_achat, selected_fournisseur_id, st.session_state.user_id, 'commande', total_montant))
                    achat_id = c.fetchone()[0]
                    
                    # 3. Insertion des Lignes d'Achat
                    for ligne in st.session_state.lignes_achat:
                        montant_ligne = ligne['quantite'] * ligne['prix_unitaire_achat']
                        c.execute("""
                            INSERT INTO lignes_achat (achat_id, produit_id, quantite, prix_unitaire_achat, montant_ligne)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (achat_id, ligne['produit_id'], ligne['quantite'], ligne['prix_unitaire_achat'], montant_ligne))
                        
                        # Note: La mise à jour du stock est typiquement faite lors de la RÉCEPTION, pas de la COMMANDE.
                        # Pour simplifier, nous ne mettons pas le stock à jour ici.

                    conn.commit()
                    log_access(st.session_state.user_id, "user", "workflow_fournisseur", f"Création achat {numero_achat}")
                    st.success(f"🎉 Ordre d'Achat **{numero_achat}** enregistré avec succès! Statut: 'commande'.")
                    st.session_state.lignes_achat = [] # Vider la liste
                    st.rerun()

                except Exception as e:
                    conn.rollback()
                    st.error(f"❌ Erreur critique lors de l'enregistrement de l'achat : {e}")
                finally:
                    release_connection(conn)

# --- Autres modules (placeholders) ---

def module_espace_client():
    if not (st.session_state.get('is_client') or st.session_state.role_name == 'admin'):
        st.error("❌ Accès refusé à l'Espace Client.")
        return
        
    st.header(f"🛒 Passer votre Commande, {st.session_state.user_name}")
    st.warning("Pour un client, ce module sera la même logique que 'Nouvelle Commande' dans la Gestion des Commandes.") 

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
    st.info("Affichage des notifications pour le personnel.") 

def module_placeholder(module_key, menu_label):
    if not has_access(module_key, "lecture"):
        st.error("❌ Accès refusé à ce module.")
        return
    
    st.title(f"🛠️ Module : {menu_label.split()[1]} (ID: {module_key})")
    st.info(f"Le contenu du module **{menu_label}** est en cours de développement.")

# NOTE: Les modules CRUD de Clients/Produits/Fournisseurs restent ceux de v7.2 simplifiés si vous n'avez pas re-créé les tables, 
# mais les fonctions CRUD DANS le fichier v7.3 ci-dessus ont été rétablies au schéma COMPLET. 
# Si vous copiez/collez le code ci-dessus, il faudra s'assurer que les tables de base ont aussi le schéma complet.
# Pour le flux de travail, on utilise les nouvelles fonctions ci-dessus.

# ========== 5. APPLICATION PRINCIPALE STREAMLIT (Routage) ==========

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.is_client = False

if not st.session_state.logged_in:
    # --- Écran de Connexion ---
    st.image("https://upload.wikimedia.org/wikipedia/commons/0/0e/Ofppt.png", width=150)
    st.title("🎓 SYGEP - Connexion")
    
    tab_interne, tab_client = st.tabs(["🔒 Personnel (Nom d'utilisateur/Mot de Passe)", "👤 Accès Client (Nom uniquement)"])
    
    with tab_interne:
        st.write("Réservé au personnel interne.")
        with st.form("login_form_internal"):
            st.text_input("Nom d'utilisateur (Ex: etudiant1)", key="auth_username") 
            st.text_input("Mot de passe (Ex: pass1)", type="password", key="auth_password")
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
                if module_key == "dashboard" or module_key == "notifications" or has_access(module_key, "lecture"): 
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
                <strong style="color: #1e40af;">SYGEP v7.3 INTÉGRAL</strong><br>
                🌐 Mode Intégral Activé
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
    # Modules de Flux de Travail NOUVEAUX/CORRIGÉS
    elif current_module == "workflow_client":
        module_gestion_commandes_clients()
    elif current_module == "workflow_fournisseur":
        module_gestion_achats_fournisseurs()
    # Les autres modules, si non implémentés, restent des placeholders
    else:
        module_placeholder(current_module, menu)
