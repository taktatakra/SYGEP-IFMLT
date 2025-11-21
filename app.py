import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import hashlib
from PIL import Image
import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# ==============================================================================
# 1. CONFIGURATION & IMPORTS
# ==============================================================================

# Charger les variables d'environnement (assurez-vous d'avoir un fichier .env ou st.secrets)
load_dotenv()

st.set_page_config(
    page_title="SYGEP - Système de Gestion d'Entreprise Pédagogique",
    layout="wide",
    page_icon="🎓",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# 2. GESTION CONNEXION POSTGRESQL (SUPABASE)
# ==============================================================================

# NOTE: La gestion de la connexion est laissée identique
@st.cache_resource
def init_connection_pool():
    """Initialise un pool de connexions PostgreSQL"""
    try:
        # Tente de se connecter avec les variables d'environnement
        return psycopg2.pool.SimpleConnectionPool(
            1, 20,
            host=os.getenv('SUPABASE_HOST'),
            database=os.getenv('SUPABASE_DB', 'postgres'),
            user=os.getenv('SUPABASE_USER', 'postgres'),
            password=os.getenv('SUPABASE_PASSWORD'),
            port=os.getenv('SUPABASE_PORT', '5432')
        )
    except Exception:
        try:
            # Tente de se connecter avec st.secrets
            return psycopg2.pool.SimpleConnectionPool(
                1, 20,
                host=st.secrets["supabase"]["host"],
                database=st.secrets["supabase"]["database"],
                user=st.secrets["supabase"]["user"],
                password=st.secrets["supabase"]["password"],
                port=st.secrets["supabase"]["port"]
            )
        except Exception as e2:
            st.error(f"❌ Erreur critique de connexion à la base de données: {e2}")
            # st.stop() 

def get_connection():
    pool_instance = init_connection_pool()
    return pool_instance.getconn()

def release_connection(conn):
    pool_instance = init_connection_pool()
    pool_instance.putconn(conn)

# ==============================================================================
# 3. INITIALISATION DE LA BASE DE DONNÉES & DONNÉES DÉMO
# ==============================================================================

def init_database():
    """Crée les tables et l'utilisateur admin par défaut."""
    conn = get_connection()
    try:
        c = conn.cursor()
        
        # Création des tables (Schema basique pour la démonstration)
        c.execute("""
            CREATE TABLE IF NOT EXISTS utilisateurs (
                id SERIAL PRIMARY KEY, username VARCHAR(50) UNIQUE NOT NULL, 
                password CHAR(64) NOT NULL, role VARCHAR(50) NOT NULL, 
                date_creation DATE DEFAULT CURRENT_DATE
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS permissions (
                id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES utilisateurs(id),
                module VARCHAR(50) NOT NULL, acces_lecture BOOLEAN DEFAULT FALSE,
                acces_ecriture BOOLEAN DEFAULT FALSE
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY, nom VARCHAR(100) NOT NULL, 
                email VARCHAR(100) UNIQUE, telephone VARCHAR(20), 
                date_creation DATE DEFAULT CURRENT_DATE
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS produits (
                id SERIAL PRIMARY KEY, nom VARCHAR(100) NOT NULL, 
                prix NUMERIC(10, 2) NOT NULL, stock INTEGER DEFAULT 0, 
                seuil_alerte INTEGER DEFAULT 10
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS fournisseurs (
                id SERIAL PRIMARY KEY, nom VARCHAR(100) NOT NULL, 
                email VARCHAR(100), telephone VARCHAR(20), 
                date_creation DATE DEFAULT CURRENT_DATE
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS commandes (
                id SERIAL PRIMARY KEY, client_id INTEGER REFERENCES clients(id),
                produit_id INTEGER REFERENCES produits(id), quantite INTEGER NOT NULL,
                date DATE DEFAULT CURRENT_DATE, statut VARCHAR(50) DEFAULT 'En attente'
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS achats (
                id SERIAL PRIMARY KEY, fournisseur_id INTEGER REFERENCES fournisseurs(id),
                produit_id INTEGER REFERENCES produits(id), quantite INTEGER NOT NULL,
                date DATE DEFAULT CURRENT_DATE, cout_unitaire NUMERIC(10, 2) NOT NULL
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id CHAR(32) PRIMARY KEY, user_id INTEGER REFERENCES utilisateurs(id),
                username VARCHAR(50), role VARCHAR(50), 
                expiration_date TIMESTAMP NOT NULL
            );
        """)
        c.execute('''CREATE TABLE IF NOT EXISTS logs_acces (
                id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES utilisateurs(id),
                module VARCHAR(50), action TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );''')
        
        # Créer utilisateur admin par défaut si n'existe pas
        c.execute("SELECT COUNT(*) FROM utilisateurs WHERE username = %s", ('admin',))
        if c.fetchone()[0] == 0:
            password_hash = hashlib.sha256("admin123".encode()).hexdigest()
            c.execute("INSERT INTO utilisateurs (username, password, role) VALUES (%s, %s, %s) RETURNING id",
                      ('admin', password_hash, 'admin'))
            user_id = c.fetchone()[0]
            
            modules = ["tableau_bord", "clients", "produits", "fournisseurs", "commandes", "achats", "rapports", "utilisateurs"]
            for module in modules:
                c.execute("INSERT INTO permissions (user_id, module, acces_lecture, acces_ecriture) VALUES (%s, %s, %s, %s)",
                          (user_id, module, True, True))
            
            # Ajouter des données de démonstration
            c.execute("SELECT COUNT(*) FROM clients")
            if c.fetchone()[0] == 0:
                c.execute("INSERT INTO clients (nom, email) VALUES (%s, %s) RETURNING id", ('Client Démo', 'demo@exemple.com'))
                client_id_demo = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM produits")
            if c.fetchone()[0] == 0:
                c.execute("INSERT INTO produits (nom, prix, stock) VALUES (%s, %s, %s) RETURNING id", ('Produit A', 15.50, 50))
                produit_id_demo = c.fetchone()[0]

                # Commande de démo
                c.execute("""INSERT INTO commandes (client_id, produit_id, quantite, date, statut) 
                             VALUES (%s, %s, %s, CURRENT_DATE, 'En attente')""",
                          (client_id_demo, produit_id_demo, 5))
            
            conn.commit()
        
    except Exception as e:
        # st.error(f"Erreur initialisation BDD: {e}")
        conn.rollback()
    finally:
        release_connection(conn)

# ==============================================================================
# 4. FONCTIONS UTILITAIRES DE GESTION DES DONNÉES ET D'ACCÈS
# ==============================================================================
# (Les fonctions utilitaires comme hash_password, verify_login, get_user_permissions, 
# has_access, log_access, db_read_all, db_add, save_session_to_db, load_session_from_db, 
# delete_session_from_db sont laissées inchangées)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_login(username, password):
    conn = get_connection()
    try:
        c = conn.cursor()
        password_hash = hash_password(password)
        c.execute("SELECT id, role FROM utilisateurs WHERE username=%s AND password=%s", (username, password_hash))
        return c.fetchone()
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
    return permissions.get(module, {}).get(access_type, False)

def log_access(user_id, module, action):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("INSERT INTO logs_acces (user_id, module, action) VALUES (%s, %s, %s)",
                  (user_id, module, action))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        release_connection(conn)

def db_read_all(table_name, order_by='id'):
    conn = get_connection()
    try:
        return pd.read_sql_query(f"SELECT * FROM {table_name} ORDER BY {order_by}", conn)
    except Exception:
        return pd.DataFrame()
    finally:
        release_connection(conn)

def db_add(table_name, columns, values):
    conn = get_connection()
    try:
        c = conn.cursor()
        placeholders = ', '.join(['%s'] * len(columns))
        cols_str = ', '.join(columns)
        c.execute(f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders}) RETURNING id", values)
        conn.commit()
        return c.fetchone()[0]
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        release_connection(conn)

def save_session_to_db(user_id, username, role):
    session_id = hashlib.md5(os.urandom(32)).hexdigest()
    conn = get_connection()
    try:
        c = conn.cursor()
        expiration = datetime.now() + pd.Timedelta(hours=4)
        c.execute("INSERT INTO sessions (id, user_id, username, role, expiration_date) VALUES (%s, %s, %s, %s, %s)",
                  (session_id, user_id, username, role, expiration))
        conn.commit()
        return session_id
    except Exception:
        conn.rollback()
        return None
    finally:
        release_connection(conn)

def load_session_from_db(session_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT user_id, username, role FROM sessions WHERE id = %s AND expiration_date > NOW()", (session_id,))
        return c.fetchone()
    except Exception:
        return None
    finally:
        release_connection(conn)

def delete_session_from_db(session_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        release_connection(conn)


# ==============================================================================
# 5. FONCTIONS DE CACHE POUR LA LECTURE DES DONNÉES (Performance)
# ==============================================================================

@st.cache_data(ttl=60)
def get_clients():
    return db_read_all('clients', 'nom')

@st.cache_data(ttl=60)
def get_produits():
    return db_read_all('produits', 'nom')

@st.cache_data(ttl=60)
def get_fournisseurs():
    return db_read_all('fournisseurs', 'nom')

@st.cache_data(ttl=60)
def get_commandes():
    conn = get_connection()
    try:
        query = """
        SELECT c.id, cl.nom as client, p.nom as produit, p.prix, c.quantite, 
               (c.quantite * p.prix) as montant, c.date, c.statut, c.client_id, c.produit_id
        FROM commandes c
        JOIN clients cl ON c.client_id = cl.id
        JOIN produits p ON c.produit_id = p.id
        ORDER BY c.date DESC
        """
        return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame()
    finally:
        release_connection(conn)

@st.cache_data(ttl=5) 
def get_pending_orders_count():
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM commandes WHERE statut = 'En attente'")
        return c.fetchone()[0]
    except Exception:
        return 0
    finally:
        release_connection(conn)

# ==============================================================================
# 6. PAGES DE L'APPLICATION (Refactorées)
# ==============================================================================

def page_passer_commande_publique():
    # ************************************************************
    # CORRECTION : Quantité et rafraîchissement du cache Client
    # ************************************************************
    st.title("🛍️ Passer une Nouvelle Commande (Espace Client)")
    st.markdown("---")
    
    clients = get_clients() 
    produits = get_produits() 
    
    if produits.empty:
        st.warning("⚠️ Service temporairement indisponible (aucun produit en vente).")
        return
        
    produits_disponibles = produits[produits['stock'] > 0]
    
    if produits_disponibles.empty:
        st.error("❌ Aucun produit en stock disponible pour la commande actuellement.")
        return

    # Préparation des options pour le selectbox
    produits_map = {f"{r['nom']} - {r['prix']:.2f} € (Stock: {r['stock']})": r['id'] for _, r in produits_disponibles.iterrows()}
    
    # Création de la liste d'options avec un message explicite en premier
    options_produits = ["--- Sélectionnez un produit ---"] + list(produits_map.keys())
    
    with st.form("form_commande_client"):
        st.subheader("1. Vos Informations")
        
        nom_client = st.text_input("Votre Nom/Nom de Société *")
        email_client = st.text_input("Votre Email *")
        
        st.subheader("2. Votre Commande")
        
        # Le selectbox n'a plus d'option sélectionnée par défaut qui est un produit réel
        selected_product_label = st.selectbox("Produit *", options_produits, index=0)
        
        # Initialisation par défaut
        quantite = 0
        produit_id = None
        montant_estime = 0.0

        # Vérifie si un produit réel a été sélectionné
        if selected_product_label != "--- Sélectionnez un produit ---":
            produit_id = produits_map[selected_product_label]
            produit_data = produits_disponibles[produits_disponibles['id'] == produit_id].iloc[0]
            
            quantite_max = produit_data['stock']
            
            # Correction: Le widget de quantité est affiché ici pour que l'utilisateur puisse le saisir
            quantite = st.number_input("Quantité *", 
                                        min_value=1, 
                                        max_value=int(quantite_max), 
                                        step=1, 
                                        value=1)

            montant_estime = produit_data['prix'] * quantite
            st.info(f"Montant estimé de la commande : **{montant_estime:.2f} €** (hors taxes et livraison)")
        else:
             st.info("Veuillez sélectionner un produit pour afficher les détails et la quantité.")

        submit = st.form_submit_button("Envoyer la Commande", type="primary", use_container_width=True)
        
        if submit:
            if not nom_client or not email_client or quantite <= 0 or selected_product_label == "--- Sélectionnez un produit ---":
                st.error("❌ Veuillez remplir tous les champs obligatoires (Nom, Email, Produit et Quantité > 0).")
                return

            conn = get_connection()
            try:
                c = conn.cursor()
                
                # 1. Vérifier/Créer le client
                c.execute("SELECT id FROM clients WHERE email = %s", (email_client,))
                client_data = c.fetchone()
                if client_data:
                    client_id = client_data[0]
                else:
                    c.execute("INSERT INTO clients (nom, email, date_creation) VALUES (%s, %s, CURRENT_DATE) RETURNING id",
                              (nom_client, email_client))
                    client_id = c.fetchone()[0]
                    # Correction: Vider le cache des clients pour que le nouveau soit visible
                    get_clients.clear() 

                produit_id_py = int(produit_id)
                quantite_py = int(quantite)
                client_id_py = int(client_id)
                
                # 2. Vérifier le stock
                c.execute("SELECT stock FROM produits WHERE id = %s", (produit_id_py,))
                current_stock = c.fetchone()[0]
                
                if current_stock >= quantite_py:
                    # 3. Insérer la commande et mettre à jour le stock
                    c.execute("""INSERT INTO commandes (client_id, produit_id, quantite, date, statut) 
                                VALUES (%s, %s, %s, CURRENT_DATE, 'En attente')""",
                              (client_id_py, produit_id_py, quantite_py))
                    
                    c.execute("UPDATE produits SET stock = stock - %s WHERE id = %s", (quantite_py, produit_id_py))
                    
                    conn.commit()
                    
                    st.success(f"✅ Commande envoyée avec succès ! Montant estimé: {montant_estime:.2f} €.")
                    # Vider les caches pertinents
                    get_pending_orders_count.clear()
                    get_produits.clear()
                    get_commandes.clear()
                    st.balloons()
                else:
                    conn.rollback()
                    st.error(f"❌ Erreur: Stock insuffisant ! Disponible: {current_stock}")
                
            except Exception as e:
                conn.rollback()
                st.error(f"❌ Une erreur est survenue lors de l'enregistrement de la commande: {e}")
            finally:
                release_connection(conn)

def page_tableau_de_bord():
    # La logique du tableau de bord est laissée identique
    if not has_access("tableau_bord"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "tableau_bord", "Consultation")
    st.header("📈 Tableau de Bord")
    
    pending_count = get_pending_orders_count()
    produits = get_produits()
    
    if pending_count > 0:
        st.error(f"🔔 **URGENT : {pending_count} NOUVELLE(S) COMMANDE(S) CLIENT EN ATTENTE !**")
    
    produits_alerte = produits[produits['stock'] <= produits['seuil_alerte']]
    if not produits_alerte.empty:
        st.warning(f"⚠️ **{len(produits_alerte)} produit(s) en stock faible !**")
    
    col1, col2, col3, col4 = st.columns(4)
    clients = get_clients()
    commandes = get_commandes()
    
    ca_total = commandes['montant'].sum() if not commandes.empty else 0
    
    col1.metric("👥 Clients", len(clients))
    col2.metric("📦 Produits", len(produits))
    col3.metric("🛒 Commandes", len(commandes))
    col4.metric("💰 CA Total", f"{ca_total:.2f} €")
    
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📦 Niveau de Stock")
        if not produits.empty:
            st.bar_chart(produits.set_index('nom')['stock'])
    
    with col2:
        st.subheader("📊 Statut des Commandes")
        if not commandes.empty:
            st.bar_chart(commandes['statut'].value_counts())

def page_clients():
    # La logique de gestion des clients est laissée identique
    if not has_access("clients"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "clients", "Consultation")
    st.header("👥 Gestion des Clients")
    
    tab1, tab2, tab3 = st.tabs(["📋 Liste", "➕ Ajouter", "✏️ Modifier/Supprimer"])
    
    clients = get_clients()
    
    # Onglet Liste
    with tab1:
        if not clients.empty:
            st.dataframe(clients, use_container_width=True, hide_index=True)
        else:
            st.info("📭 Aucun client enregistré")

    # Onglet Ajouter
    with tab2:
        if not has_access("clients", "ecriture"):
            st.warning("⚠️ Vous n'avez pas les droits d'écriture sur ce module")
        else:
            with st.form("form_add_client"):
                nom = st.text_input("Nom du Client *", placeholder="Ex: Entreprise ABC")
                email = st.text_input("Email *", placeholder="contact@exemple.com")
                telephone = st.text_input("Téléphone", placeholder="0612345678")
                submit = st.form_submit_button("✅ Enregistrer", use_container_width=True, type="primary")
                
                if submit:
                    if nom and email:
                        try:
                            db_add('clients', ['nom', 'email', 'telephone', 'date_creation'], 
                                   (nom, email, telephone if telephone else None, datetime.now()))
                            log_access(st.session_state.user_id, "clients", f"Ajout: {nom}")
                            st.success(f"✅ Client '{nom}' ajouté avec succès!")
                            get_clients.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur: {e}")
                    else:
                        st.error("❌ Le nom et l'email sont obligatoires")
    
    # Onglet Modifier/Supprimer
    with tab3:
        if not has_access("clients", "ecriture"):
            st.warning("⚠️ Vous n'avez pas les droits d'écriture sur ce module")
        elif clients.empty:
            st.info("📭 Aucun client à modifier/supprimer")
        else:
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("✏️ Modifier un Client")
                client_id_update = st.selectbox("Sélectionner le client à modifier", 
                                               clients['id'].tolist(),
                                               format_func=lambda x: f"{clients[clients['id']==x]['nom'].iloc[0]}")
                
                if client_id_update:
                    client_data = clients[clients['id'] == client_id_update].iloc[0]
                    
                    with st.form("form_update_client"):
                        nom_update = st.text_input("Nom *", value=client_data['nom'])
                        email_update = st.text_input("Email *", value=client_data['email'] if pd.notna(client_data['email']) else "")
                        telephone_update = st.text_input("Téléphone", value=client_data['telephone'] if pd.notna(client_data['telephone']) else "")
                        
                        submit_update = st.form_submit_button("✅ Mettre à Jour", use_container_width=True, type="primary")
                        
                        if submit_update:
                            if nom_update and email_update:
                                conn = get_connection()
                                try:
                                    c = conn.cursor()
                                    c.execute("""UPDATE clients SET nom=%s, email=%s, telephone=%s WHERE id=%s""",
                                              (nom_update, email_update, telephone_update if telephone_update else None, int(client_id_update)))
                                    conn.commit()
                                    log_access(st.session_state.user_id, "clients", f"Modification ID:{client_id_update}")
                                    st.success(f"✅ Client '{nom_update}' modifié avec succès!")
                                    get_clients.clear()
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"❌ Erreur: {e}")
                                finally:
                                    release_connection(conn)
                            else:
                                st.error("❌ Le nom et l'email sont obligatoires")

            with col2:
                st.subheader("🗑️ Supprimer un Client")
                client_id_del = st.selectbox("Client à supprimer", clients['id'].tolist(), key="del_client",
                                            format_func=lambda x: f"{clients[clients['id']==x]['nom'].iloc[0]}")
                st.write("")
                if st.button("🗑️ Supprimer Définitivement", type="secondary"):
                    conn = get_connection()
                    try:
                        c = conn.cursor()
                        c.execute("SELECT COUNT(*) FROM commandes WHERE client_id=%s", (int(client_id_del),))
                        nb_commandes = c.fetchone()[0]
                        
                        if nb_commandes > 0:
                            st.error(f"❌ Impossible de supprimer ce client ! Il possède {nb_commandes} commande(s).")
                        else:
                            c.execute("DELETE FROM clients WHERE id=%s", (int(client_id_del),))
                            conn.commit()
                            log_access(st.session_state.user_id, "clients", f"Suppression ID:{client_id_del}")
                            st.success("✅ Client supprimé avec succès!")
                            get_clients.clear()
                            st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"❌ Erreur technique: {e}")
                    finally:
                        release_connection(conn)

def page_produits():
    # La logique de gestion des produits est laissée identique
    if not has_access("produits"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "produits", "Consultation")
    st.header("📦 Gestion des Produits")
    
    tab1, tab2, tab3 = st.tabs(["📋 Liste & Stock", "➕ Ajouter", "✏️ Modifier/Supprimer"])
    
    produits = get_produits()
    
    # Onglet Liste & Stock (Logique identique)
    with tab1:
        if not produits.empty:
            produits_display = produits.copy()
            produits_display['statut'] = produits_display.apply(
                lambda r: '🔴 Stock Faible' if r['stock'] <= r['seuil_alerte'] else '🟢 Stock OK', axis=1)
            st.dataframe(produits_display, use_container_width=True, hide_index=True)
            
            if has_access("produits", "ecriture"):
                st.divider()
                st.subheader("📝 Ajuster le Stock")
                
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    if not produits.empty:
                        prod_id = st.selectbox("Produit", produits['id'].tolist(),
                                              format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0])
                    else:
                        prod_id = None
                with col_b:
                    ajust = st.number_input("Ajustement", value=0, step=1, help="Positif pour ajouter, négatif pour retirer")
                with col_c:
                    st.write("")
                    st.write("")
                    if prod_id is not None and st.button("✅ Appliquer"):
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s", (int(ajust), int(prod_id)))
                            conn.commit()
                            log_access(st.session_state.user_id, "produits", f"Ajustement stock ID:{prod_id} ({ajust:+d})")
                            st.success(f"✅ Stock ajusté de {ajust:+d}")
                            get_produits.clear()
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"❌ Erreur: {e}")
                        finally:
                            release_connection(conn)
        else:
            st.info("📭 Aucun produit enregistré")

    # Onglet Ajouter (Logique identique)
    with tab2:
        if not has_access("produits", "ecriture"):
            st.warning("⚠️ Vous n'avez pas les droits d'écriture")
        else:
            with st.form("form_add_produit"):
                nom = st.text_input("Nom du Produit *")
                col1, col2 = st.columns(2)
                with col1:
                    prix = st.number_input("Prix Unitaire (€) *", min_value=0.01, step=0.01, format="%.2f")
                with col2:
                    stock = st.number_input("Stock Initial", min_value=0, step=1, value=0)
                seuil = st.number_input("Seuil d'Alerte", min_value=0, step=1, value=10)
                
                submit = st.form_submit_button("✅ Enregistrer", use_container_width=True, type="primary")
                
                if submit:
                    if nom and prix > 0:
                        try:
                            db_add('produits', ['nom', 'prix', 'stock', 'seuil_alerte'],
                                   (nom, float(prix), int(stock), int(seuil)))
                            log_access(st.session_state.user_id, "produits", f"Ajout: {nom}")
                            st.success(f"✅ Produit '{nom}' ajouté!")
                            get_produits.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur: {e}")
                    else:
                        st.error("❌ Nom et prix > 0 requis")
    
    # Onglet Modifier/Supprimer (Logique identique)
    with tab3:
        if not has_access("produits", "ecriture"):
            st.warning("⚠️ Vous n'avez pas les droits d'écriture")
        elif produits.empty:
            st.info("📭 Aucun produit à modifier/supprimer")
        else:
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("✏️ Modifier un Produit")
                prod_id_update = st.selectbox("Produit à modifier", produits['id'].tolist(), key="mod_prod",
                                             format_func=lambda x: f"{produits[produits['id']==x]['nom'].iloc[0]}")
                if prod_id_update:
                    prod_data = produits[produits['id'] == prod_id_update].iloc[0]
                    
                    with st.form("form_update_produit"):
                        nom_update = st.text_input("Nom *", value=prod_data['nom'])
                        col_up1, col_up2 = st.columns(2)
                        with col_up1:
                            prix_update = st.number_input("Prix (€) *", min_value=0.01, step=0.01, 
                                                         value=float(prod_data['prix']), format="%.2f")
                        with col_up2:
                            stock_update = st.number_input("Stock", min_value=0, step=1, 
                                                          value=int(prod_data['stock']))
                        seuil_update = st.number_input("Seuil d'Alerte", min_value=0, step=1, 
                                                      value=int(prod_data['seuil_alerte']))
                        
                        submit_update = st.form_submit_button("✅ Mettre à Jour", use_container_width=True, type="primary")
                        
                        if submit_update:
                            if nom_update and prix_update > 0:
                                conn = get_connection()
                                try:
                                    c = conn.cursor()
                                    c.execute("""UPDATE produits 
                                                SET nom=%s, prix=%s, stock=%s, seuil_alerte=%s 
                                                WHERE id=%s""",
                                              (nom_update, float(prix_update), int(stock_update), 
                                               int(seuil_update), int(prod_id_update)))
                                    conn.commit()
                                    log_access(st.session_state.user_id, "produits", f"Modification ID:{prod_id_update}")
                                    st.success(f"✅ Produit '{nom_update}' modifié!")
                                    get_produits.clear()
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"❌ Erreur: {e}")
                                finally:
                                    release_connection(conn)
                            else:
                                st.error("❌ Nom et prix > 0 requis")

            with col2:
                st.subheader("🗑️ Supprimer un Produit")
                prod_del_id = st.selectbox("Produit à supprimer", produits['id'].tolist(), key="del_prod",
                                            format_func=lambda x: f"{produits[produits['id']==x]['nom'].iloc[0]}")
                st.write("")
                if st.button("🗑️ Supprimer Définitivement", type="secondary"):
                    conn = get_connection()
                    try:
                        c = conn.cursor()
                        c.execute("SELECT COUNT(*) FROM commandes WHERE produit_id=%s", (int(prod_del_id),))
                        nb_commandes = c.fetchone()[0]
                        
                        if nb_commandes > 0:
                            st.error("❌ Impossible de supprimer ce produit ! Il est lié à des commandes.")
                        else:
                            c.execute("DELETE FROM produits WHERE id=%s", (int(prod_del_id),))
                            conn.commit()
                            log_access(st.session_state.user_id, "produits", f"Suppression ID:{prod_del_id}")
                            st.success("✅ Produit supprimé!")
                            get_produits.clear()
                            st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"❌ Erreur technique: {e}")
                    finally:
                        release_connection(conn)

def page_fournisseurs():
    if not has_access("fournisseurs"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "fournisseurs", "Consultation")
    st.header("🚚 Gestion des Fournisseurs")
    st.info("Contenu de la gestion des fournisseurs (Ajout, Modification, Suppression).")
    
    fournisseurs = get_fournisseurs()
    if not fournisseurs.empty:
        st.dataframe(fournisseurs, use_container_width=True, hide_index=True)
    else:
        st.info("📭 Aucun fournisseur enregistré.")
    
def page_commandes():
    # ************************************************************
    # CORRECTION : Ajout de la page Gestion des Commandes
    # ************************************************************
    if not has_access("commandes"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "commandes", "Consultation")
    st.header("🛒 Gestion des Commandes Clients")
    
    commandes = get_commandes()
    
    if commandes.empty:
        st.info("📭 Aucune commande client enregistrée.")
        return

    tab1, tab2 = st.tabs(["📋 Liste", "✏️ Traitement"])

    with tab1:
        st.subheader("Liste des Commandes")
        # Affichage simplifié des commandes
        st.dataframe(commandes.drop(columns=['client_id', 'produit_id']), use_container_width=True, hide_index=True)
        
    with tab2:
        if not has_access("commandes", "ecriture"):
            st.warning("⚠️ Vous n'avez pas les droits de traitement des commandes.")
        else:
            st.subheader("Mise à jour du Statut")
            
            # Utiliser un dictionnaire pour mapper l'ID aux détails pour l'affichage
            commandes_map = {r['id']: f"Commande n°{r['id']} - {r['client']} - {r['montant']:.2f} €" for _, r in commandes.iterrows()}
            
            cmd_id_update = st.selectbox("Sélectionner la commande à traiter", 
                                         list(commandes_map.keys()),
                                         format_func=lambda x: commandes_map[x] if x in commandes_map else 'Sélectionnez...')
            
            if cmd_id_update:
                current_status = commandes[commandes['id'] == cmd_id_update]['statut'].iloc[0]
                new_status = st.selectbox("Nouveau Statut", 
                                          ['En attente', 'En cours de préparation', 'Expédiée', 'Livrée', 'Annulée'],
                                          index=['En attente', 'En cours de préparation', 'Expédiée', 'Livrée', 'Annulée'].index(current_status))

                if st.button("✅ Mettre à Jour le Statut", type="primary"):
                    conn = get_connection()
                    try:
                        c = conn.cursor()
                        c.execute("UPDATE commandes SET statut=%s WHERE id=%s", (new_status, int(cmd_id_update)))
                        conn.commit()
                        log_access(st.session_state.user_id, "commandes", f"Mise à jour statut ID:{cmd_id_update} vers {new_status}")
                        st.success(f"✅ Statut de la commande n°{cmd_id_update} mis à jour : **{new_status}**")
                        get_commandes.clear()
                        get_pending_orders_count.clear()
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"❌ Erreur: {e}")
                    finally:
                        release_connection(conn)


def page_achats():
    if not has_access("achats"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "achats", "Consultation")
    st.header("💲 Gestion des Achats (Réapprovisionnement)")
    st.info("Contenu de la gestion des achats (Commandes fournisseurs et réception).")

def page_rapports():
    if not has_access("rapports"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "rapports", "Consultation")
    st.header("📊 Rapports & Exports")
    st.info("Contenu des rapports de performance (CA, Marge, Stock) et l'export de données.")

def page_utilisateurs():
    if not has_access("utilisateurs"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "utilisateurs", "Consultation")
    st.header("🔑 Gestion des Utilisateurs et Permissions")
    st.info("Cette section permet de gérer les utilisateurs, leurs rôles et les permissions d'accès aux modules (Lecture/Écriture).")
    
    # Affichage des utilisateurs
    conn = get_connection()
    try:
        df_users = pd.read_sql_query("SELECT id, username, role, date_creation FROM utilisateurs ORDER BY id", conn)
        st.subheader("Liste des Utilisateurs")
        st.dataframe(df_users, use_container_width=True)
    except Exception:
         st.warning("Impossible d'afficher les utilisateurs.")
    finally:
        release_connection(conn)

def page_a_propos():
    st.header("ℹ️ À Propos du SYGEP")
    st.info("Application pédagogique développée...")

# ==============================================================================
# 7. INITIALISATION & LOGIQUE PRINCIPALE DE L'APPLICATION
# ==============================================================================

init_database()

# Initialisation de st.session_state
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_id = None
    st.session_state.role = None
    st.session_state.permissions = {}
    st.session_state.session_id = None

# Tente de charger la session via query_params
if not st.session_state.logged_in and 'session_id' in st.query_params:
    session_id = st.query_params['session_id']
    session_data = load_session_from_db(session_id)
    
    if session_data:
        user_id, username, role = session_data
        st.session_state.logged_in = True
        st.session_state.username = username
        st.session_state.user_id = user_id
        st.session_state.role = role
        st.session_state.permissions = get_user_permissions(user_id)
        st.session_state.session_id = session_id

# ==============================================================================
# 8. RENDU - Écran de Connexion ou Interface Principale
# ==============================================================================

if not st.session_state.logged_in:
    # Code d'affichage de la page de connexion (Identique)
    col_img, col_title, col_date = st.columns([1, 4, 1])
    # col_img.image(Image.open('image_d3b879.png'), width=80) 
    col_title.title("SYGEP - Espace d'Accès")
    col_date.write(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    st.markdown("---")
    
    tab_login, tab_client_order = st.tabs(["🔐 Authentification Utilisateur", "🛍️ Passer une Commande (Client)"])

    with tab_login:
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
                        st.error("❌ Identifiants incorrects")
            st.info("💡 **Compte par défaut**\nUsername: admin\nPassword: admin123")

    with tab_client_order:
        page_passer_commande_publique()

    st.stop()


# Interface Principale (pour les utilisateurs connectés)
else:
    # Code d'affichage de l'en-tête (Identique)
    col_img, col_title, col_date = st.columns([1, 4, 1])
    # col_img.image(Image.open('image_d3b879.png'), width=80) 
    col_title.title("SYGEP - Système de Gestion d'Entreprise Pédagogique")
    col_date.write(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    st.markdown("---")
    
    st.markdown(f"""
    <div style="background: linear-gradient(90deg, #3b82f6 0%, #1e40af 100%); 
                padding: 15px; border-radius: 10px;">
        <h2 style="color: white; margin: 0; text-align: center;">
            👤 Connecté : {st.session_state.username} ({st.session_state.role.upper()}) | 🌐 Mode Temps Réel
        </h2>
    </div>
    """, unsafe_allow_html=True)
    
    # ----------------------------------------------------------------------
    # SIDEBAR : LOGOUT (Identique)
    # ----------------------------------------------------------------------
    
    if st.sidebar.button("🚪 Se déconnecter", use_container_width=True):
        log_access(st.session_state.user_id, "deconnexion", "Déconnexion")
        
        if st.session_state.session_id:
            delete_session_from_db(st.session_state.session_id)
            
        st.query_params.clear()
        
        # Nettoyage de l'état de session
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.user_id = None
        st.session_state.role = None
        st.session_state.session_id = None
        st.session_state.permissions = {}

        st.rerun()
        st.stop() 
    
    # ----------------------------------------------------------------------
    # SIDEBAR : Navigation
    # ----------------------------------------------------------------------
    
    st.sidebar.divider()

    menu_items = []
    if has_access("tableau_bord"): menu_items.append("Tableau de Bord")
    if has_access("clients"): menu_items.append("Gestion des Clients")
    if has_access("produits"): menu_items.append("Gestion des Produits")
    if has_access("fournisseurs"): menu_items.append("Gestion des Fournisseurs")
    if has_access("commandes"): menu_items.append("Gestion des Commandes")
    if has_access("achats"): menu_items.append("Gestion des Achats")
    if has_access("rapports"): menu_items.append("Rapports & Exports")
    if st.session_state.role == "admin": menu_items.append("Gestion des Utilisateurs")
    menu_items.append("À Propos") # Ajout du module À Propos pour qu'il soit toujours disponible

    menu = st.sidebar.selectbox("🧭 Navigation", menu_items)
    
    # ----------------------------------------------------------------------
    # RENDU DES PAGES
    # ----------------------------------------------------------------------
    
    if menu == "Tableau de Bord":
        page_tableau_de_bord()
    elif menu == "Gestion des Clients":
        page_clients()
    elif menu == "Gestion des Produits":
        page_produits()
    elif menu == "Gestion des Fournisseurs":
        page_fournisseurs() 
    elif menu == "Gestion des Commandes":
        page_commandes()
    elif menu == "Gestion des Achats":
        page_achats()
    elif menu == "Rapports & Exports":
        page_rapports()
    elif menu == "Gestion des Utilisateurs":
        page_utilisateurs()
    elif menu == "À Propos":
        page_a_propos()
