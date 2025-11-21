finally:
                                    release_connection(conn)

# ========== GESTION DES COMMANDES ==========
elif menu == "Gestion des Commandes":
    if not has_access("commandes"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "commandes", "Consultation")
    st.header("🛒 Gestion des Commandes")
    
    tab1, tab2 = st.tabs(["📋 Liste", "➕ Créer"])
    
    with tab1:
        commandes = get_commandes()
        if not commandes.empty:
            st.dataframe(commandes, use_container_width=True, hide_index=True)
            
            if has_access("commandes", "ecriture"):
                st.divider()
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("🔄 Changer Statut")
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        cmd_id = st.selectbox("Commande N°", commandes['id'].tolist())
                    with col_b:
                        statut = st.selectbox("Statut", ["En attente", "En cours", "Livrée", "Annulée"])
                    with col_c:
                        st.write("")
                        st.write("")
                        if st.button("✅ Mettre à jour"):
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("SELECT statut, produit_id, quantite FROM commandes WHERE id = %s", (int(cmd_id),))
                                cmd_data = c.fetchone()
                                
                                if cmd_data:
                                    ancien_statut = cmd_data[0]
                                    produit_id = int(cmd_data[1])
                                    quantite = int(cmd_data[2])
                                    
                                    if ancien_statut == "En attente" and statut in ["En cours", "Livrée"]:
                                        c.execute("SELECT stock FROM produits WHERE id = %s", (produit_id,))
                                        stock_actuel = int(c.fetchone()[0])
                                        
                                        if stock_actuel >= quantite:
                                            c.execute("UPDATE produits SET stock = stock - %s WHERE id = %s", (quantite, produit_id))
                                        else:
                                            st.error(f"❌ Stock insuffisant ! Disponible: {stock_actuel}, Requis: {quantite}")
                                            conn.rollback()
                                            release_connection(conn)
                                            st.stop()
                                    
                                    elif ancien_statut in ["En cours", "Livrée"] and statut == "Annulée":
                                        c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s", (quantite, produit_id))
                                    
                                    c.execute("UPDATE commandes SET statut = %s WHERE id = %s", (statut, int(cmd_id)))
                                    conn.commit()
                                    st.success(f"✅ Statut changé: {statut}")
                                    get_pending_orders_count.clear()
                                    get_commandes.clear()
                                    get_produits.clear()
                                    st.rerun()
                                    
                            except Exception as e:
                                conn.rollback()
                                st.error(f"❌ Erreur: {e}")
                            finally:
                                release_connection(conn)
                
                with col2:
                    st.subheader("🗑️ Supprimer une Commande")
                    col_x, col_y = st.columns([3, 1])
                    with col_x:
                        cmd_del_id = st.selectbox("Commande à supprimer", commandes['id'].tolist(),
                                                 format_func=lambda x: f"Commande #{x}")
                    with col_y:
                        st.write("")
                        st.write("")
                        if st.button("🗑️ Supprimer", type="secondary", key="del_cmd"):
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("SELECT statut, produit_id, quantite FROM commandes WHERE id = %s", (int(cmd_del_id),))
                                cmd_data = c.fetchone()
                                
                                if cmd_data:
                                    statut_cmd = cmd_data[0]
                                    produit_id = int(cmd_data[1])
                                    quantite = int(cmd_data[2])
                                    
                                    if statut_cmd in ["En cours", "Livrée"]:
                                        c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s", (quantite, produit_id))
                                
                                c.execute("DELETE FROM commandes WHERE id=%s", (int(cmd_del_id),))
                                conn.commit()
                                st.success("✅ Commande supprimée!")
                                get_commandes.clear()
                                get_pending_orders_count.clear()
                                get_produits.clear()
                                st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"❌ Erreur: {e}")
                            finally:
                                release_connection(conn)
        else:
            st.info("🔭 Aucune commande")
    
    with tab2:
        if not has_access("commandes", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            st.subheader("➕ Créer une Nouvelle Commande")
            clients = get_clients()
            produits = get_produits()
            
            if clients.empty or produits.empty:
                st.warning("⚠️ Il faut au moins 1 client et 1 produit")
            else:
                with st.form("form_commande"):
                    client_id = st.selectbox("Client *", clients['id'].tolist(),
                                            format_func=lambda x: clients[clients['id']==x]['nom'].iloc[0])
                    produit_id = st.selectbox("Produit *", produits['id'].tolist(),
                                             format_func=lambda x: f"{produits[produits['id']==x]['nom'].iloc[0]} - {produits[produits['id']==x]['prix'].iloc[0]:.2f} €")
                    
                    produit_selectionne = produits[produits['id'] == produit_id].iloc[0]
                    stock_max = int(produit_selectionne['stock'])
                    
                    quantite = st.number_input("Quantité *", min_value=1, max_value=stock_max, step=1, value=1, key="quantite_interne")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        submit = st.form_submit_button("✅ Créer", use_container_width=True, type="primary")
                    with col2:
                        cancel = st.form_submit_button("❌ Annuler", use_container_width=True)
                    
                    if submit:
                        produit = produits[produits['id'] == produit_id].iloc[0]
                        stock_actuel = int(produit['stock'])
                        quantite_int = int(quantite)
                        
                        if stock_actuel >= quantite_int:
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                client_id_py = int(client_id)
                                produit_id_py = int(produit_id)
                                
                                c.execute("""INSERT INTO commandes (client_id, produit_id, quantite, date, statut) 
                                            VALUES (%s, %s, %s, CURRENT_DATE, 'En cours')""",
                                          (client_id_py, produit_id_py, quantite_int))
                                c.execute("UPDATE produits SET stock = stock - %s WHERE id = %s", (quantite_int, produit_id_py))
                                conn.commit()
                                
                                montant = float(produit['prix']) * quantite_int
                                st.success(f"✅ Commande créée ! Montant: {montant:.2f} €")
                                get_commandes.clear()
                                get_produits.clear()
                                st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"❌ Erreur: {e}")
                            finally:
                                release_connection(conn)
                        else:
                            st.error(f"❌ Stock insuffisant ! Dispo: {stock_actuel}")

# ========== GESTION DES ACHATS ==========
elif menu == "Gestion des Achats":
    if not has_access("achats"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "achats", "Consultation")
    st.header("🛍️ Gestion des Achats")
    
    tab1, tab2 = st.tabs(["📋 Liste", "➕ Créer"])
    
    with tab1:
        achats = get_achats()
        if not achats.empty:
            st.dataframe(achats, use_container_width=True, hide_index=True)
            
            if has_access("achats", "ecriture"):
                st.divider()
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("🔍 Valider Réception")
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        achat_id = st.selectbox("Achat N°", achats['id'].tolist())
                    with col_b:
                        st.write("")
                        st.write("")
                        if st.button("✅ Valider"):
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("SELECT produit_id, quantite, statut FROM achats WHERE id = %s", (int(achat_id),)) 
                                achat_data = c.fetchone()
                                
                                if achat_data and achat_data[2] != 'Reçue':
                                    produit_id, quantite, _ = achat_data
                                    c.execute("UPDATE achats SET statut = 'Reçue' WHERE id = %s", (int(achat_id),))
                                    c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s", (int(quantite), int(produit_id)))
                                    conn.commit()
                                    st.success("✅ Réception validée et stock mis à jour.")
                                    get_achats.clear()
                                    get_produits.clear()
                                    st.rerun()
                                elif achat_data and achat_data[2] == 'Reçue':
                                    st.warning("⚠️ Cet achat est déjà marqué comme reçu.")
                                else:
                                    st.error("❌ Achat non trouvé.")
                            except Exception as e:
                                st.error(f"❌ Erreur: {e}")
                                conn.rollback()
                            finally:
                                release_connection(conn)
                
                with col2:
                    st.subheader("🗑️ Supprimer un Achat")
                    col_x, col_y = st.columns([3, 1])
                    with col_x:
                        achat_del_id = st.selectbox("Achat à supprimer", achats['id'].tolist(),
                                                   format_func=lambda x: f"Achat #{x}", key="del_select")
                    with col_y:
                        st.write("")
                        st.write("")
                        if st.button("🗑️ Supprimer", type="secondary", key="del_achat"):
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("DELETE FROM achats WHERE id=%s", (int(achat_del_id),))
                                conn.commit()
                                st.success("✅ Achat supprimé!")
                                get_achats.clear()
                                st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"❌ Erreur: {e}")
                            finally:
                                release_connection(conn)
        else:
            st.info("🔭 Aucun achat")
    
    with tab2:
        if not has_access("achats", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            st.subheader("➕ Créer un Nouvel Achat")
            fournisseurs = get_fournisseurs()
            produits = get_produits()
            
            if fournisseurs.empty or produits.empty:
                st.warning("⚠️ Il faut au moins 1 fournisseur et 1 produit")
            else:
                with st.form("form_achat"):
                    fournisseur_id = st.selectbox("Fournisseur *", fournisseurs['id'].tolist(),
                                            format_func=lambda x: fournisseurs[fournisseurs['id']==x]['nom'].iloc[0])
                    produit_id = st.selectbox("Produit *", produits['id'].tolist(),
                                            format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0])
                    quantite = st.number_input("Quantité *", min_value=1, step=1, value=1)
                    prix_unitaire = st.number_input("Prix Unitaire (€) *", min_value=0.01, step=0.01, format="%.2f")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        submit = st.form_submit_button("✅ Créer l'Achat", use_container_width=True, type="primary")
                    with col2:
                        cancel = st.form_submit_button("❌ Annuler", use_container_width=True)
                    
                    if submit:
                        if quantite > 0 and prix_unitaire > 0:
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                fournisseur_id_py = int(fournisseur_id)
                                produit_id_py = int(produit_id)
                                quantite_py = int(quantite)
                                prix_unitaire_py = float(prix_unitaire)
                                
                                c.execute("""INSERT INTO achats (fournisseur_id, produit_id, quantite, prix_unitaire, date, statut) 
                                            VALUES (%s, %s, %s, %s, CURRENT_DATE, 'En attente')""",
                                          (fournisseur_id_py, produit_id_py, quantite_py, prix_unitaire_py))
                                conn.commit()
                                st.success(f"✅ Commande d'achat créée !")
                                get_achats.clear()
                                st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"❌ Erreur: {e}")
                            finally:
                                release_connection(conn)
                        else:
                            st.error("❌ Quantité et Prix Unitaire requis")

# ========== RAPPORTS & EXPORTS ==========
elif menu == "Rapports & Exports":
    if not has_access("rapports"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "rapports", "Consultation")
    st.header("📊 Rapports & Exports")
    
    tab1, tab2, tab3 = st.tabs(["📈 Statistiques", "💾 Exports", "📉 Analyses"])
    
    with tab1:
        st.subheader("📊 Vue d'Ensemble")
        
        clients = get_clients()
        produits = get_produits()
        commandes = get_commandes()
        achats = get_achats()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("👥 Total Clients", len(clients))
        with col2:
            st.metric("📦 Total Produits", len(produits))
        with col3:
            st.metric("🛒 Total Commandes", len(commandes))
        with col4:
            if not commandes.empty:
                ca = commandes['montant'].sum()
                st.metric("💰 CA Total", f"{ca:.2f} €")
            else:
                st.metric("💰 CA Total", "0.00 €")
        
        st.divider()
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📊 Commandes par Statut")
            if not commandes.empty:
                st.bar_chart(commandes['statut'].value_counts())
            else:
                st.info("Pas de données")
        
        with col2:
            st.subheader("📦 Top 5 Produits")
            if not commandes.empty:
                top_produits = commandes.groupby('produit')['quantite'].sum().sort_values(ascending=False).head(5)
                st.bar_chart(top_produits)
            else:
                st.info("Pas de données")
    
    with tab2:
        st.subheader("💾 Exporter les Données")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Export Clients**")
            clients = get_clients()
            if not clients.empty:
                csv_clients = clients.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Télécharger Clients (CSV)",
                    data=csv_clients,
                    file_name=f"clients_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("Pas de données")
            
            st.write("**Export Produits**")
            produits = get_produits()
            if not produits.empty:
                csv_produits = produits.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Télécharger Produits (CSV)",
                    data=csv_produits,
                    file_name=f"produits_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("Pas de données")
        
        with col2:
            st.write("**Export Commandes**")
            commandes = get_commandes()
            if not commandes.empty:
                csv_commandes = commandes.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Télécharger Commandes (CSV)",
                    data=csv_commandes,
                    file_name=f"commandes_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("Pas de données")
            
            st.write("**Export Achats**")
            achats = get_achats()
            if not achats.empty:
                csv_achats = achats.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Télécharger Achats (CSV)",
                    data=csv_achats,
                    file_name=f"achats_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
            else:
                st.info("Pas de données")
    
    with tab3:
        st.subheader("📉 Analyses Avancées")
        commandes = get_commandes()
        
        if not commandes.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Évolution des Commandes**")
                if 'date' in commandes.columns:
                    commandes_par_date = commandes.groupby('date').size()
                    st.line_chart(commandes_par_date)
            
            with col2:
                st.write("**CA par Client**")
                ca_par_client = commandes.groupby('client')['montant'].sum().sort_values(ascending=False).head(10)
                st.bar_chart(ca_par_client)
        else:
            st.info("Pas assez de données pour les analyses")

# ========== GESTION DES UTILISATEURS ==========
elif menu == "Gestion des Utilisateurs":
    if not has_access("utilisateurs"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "utilisateurs", "Consultation")
    st.header("👤 Gestion des Utilisateurs & Permissions")
    
    tab1, tab2, tab3 = st.tabs(["📋 Utilisateurs", "🔒 Permissions", "📊 Logs"])
    
    with tab1:
        st.subheader("📋 Liste des Utilisateurs")
        conn = get_connection()
        try:
            users = pd.read_sql_query("SELECT id, username, role, date_creation FROM utilisateurs ORDER BY id", conn)
            st.dataframe(users, use_container_width=True, hide_index=True)
            
            st.divider()
            col1, col2 = st.columns([3, 1])
            with col1:
                user_id = st.selectbox("Supprimer", users['id'].tolist(),
                                      format_func=lambda x: users[users['id']==x]['username'].iloc[0])
            with col2:
                st.write("")
                st.write("")
                if st.button("🗑️ Supprimer"):
                    if users[users['id']==user_id]['username'].iloc[0] == st.session_state.username:
                        st.error("❌ Impossible de vous auto-supprimer")
                    else:
                        c = conn.cursor()
                        c.execute("DELETE FROM utilisateurs WHERE id=%s", (int(user_id),))
                        conn.commit()
                        st.success("✅ Utilisateur supprimé")
                        st.rerun()
        except Exception as e:
            st.error(f"❌ Erreur: {e}")
        finally:
            release_connection(conn)
    
    with tab2:
        st.subheader("🔒 Gérer les Permissions")
        conn = get_connection()
        try:
            users = pd.read_sql_query("SELECT id, username, role FROM utilisateurs", conn)
            user_sel = st.selectbox("Utilisateur", users['id'].tolist(),
                                   format_func=lambda x: f"{users[users['id']==x]['username'].iloc[0]} ({users[users['id']==x]['role'].iloc[0]})")
            
            st.divider()
            
            c = conn.cursor()
            c.execute("SELECT module, acces_lecture, acces_ecriture FROM permissions WHERE user_id=%s", (user_sel,))
            perms = {r[0]: {'lecture': bool(r[1]), 'ecriture': bool(r[2])} for r in c.fetchall()}
            
            modules = ["tableau_bord", "clients", "produits", "fournisseurs", "commandes", "achats", "rapports", "utilisateurs"]
            new_perms = {}
            
            for mod in modules:
                st.write(f"**{mod.replace('_', ' ').title()}**")
                col1, col2 = st.columns(2)
                current = perms.get(mod, {'lecture': False, 'ecriture': False})
                with col1:
                    lec = st.checkbox(f"📖 Lecture", value=current['lecture'], key=f"{mod}_lec")
                with col2:
                    ecr = st.checkbox(f"✏️ Écriture", value=current['ecriture'], key=f"{mod}_ecr")
                new_perms[mod] = {'lecture': lec, 'ecriture': ecr}
                st.divider()
            
            if st.button("💾 Enregistrer Permissions", type="primary", use_container_width=True):
                user_sel_py = int(user_sel)
                c.execute("DELETE FROM permissions WHERE user_id=%s", (user_sel_py,))
                for mod, p in new_perms.items():
                    if p['lecture'] or p['ecriture']:
                        c.execute("INSERT INTO permissions (user_id, module, acces_lecture, acces_ecriture) VALUES (%s, %s, %s, %s)",
                                  (user_sel_py, mod, p['lecture'], p['ecriture']))
                conn.commit()
                st.success("✅ Permissions mises à jour")
                st.rerun()
        except Exception as e:
            st.error(f"❌ Erreur: {e}")
        finally:
            release_connection(conn)
    
    with tab3:
        st.subheader("📊 Logs d'Accès")
        conn = get_connection()
        try:
            logs = pd.read_sql_query("""
                SELECT l.date_heure, u.username, l.module, l.action
                FROM logs_acces l
                JOIN utilisateurs u ON l.user_id = u.id
                ORDER BY l.date_heure DESC
                LIMIT 100
            """, conn)
            
            if not logs.empty:
                st.dataframe(logs, use_container_width=True, hide_index=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("📈 Actions par Module")
                    st.bar_chart(logs['module'].value_counts())
                with col2:
                    st.subheader("👥 Actions par Utilisateur")
                    st.bar_chart(logs['username'].value_counts().head(10))
            else:
                st.info("Aucun log")
        except Exception as e:
            st.error(f"❌ Erreur: {e}")
        finally:
            release_connection(conn)

# ========== À PROPOS ==========
elif menu == "À Propos":
    st.header("ℹ️ À Propos de SYGEP")
    
    st.success("""
    ### 🌐 Mode Multi-Utilisateurs Temps Réel Activé !
    
    ✅ **Base de données partagée PostgreSQL (Supabase)**
    - Tous les étudiants travaillent sur les mêmes données
    - Synchronisation en temps réel
    - Aucune perte de données lors de l'actualisation
    
    ✅ **Gestion collaborative**
    - Chaque utilisateur avec ses permissions spécifiques
    - Traçabilité complète des actions
    - Workflow coordonné entre rôles
    """)
    
    st.markdown("""
    ### 🎓 Objectifs Pédagogiques
    
    Ce système ERP permet aux étudiants de :
    - Comprendre le fonctionnement d'un ERP réel
    - Travailler en mode collaboratif
    - Gérer des rôles et permissions
    - Suivre les flux logistiques complets
    
    ### 📚 Modules Implémentés
    
    - **Tableau de Bord** : Vue synthétique KPIs
    - **CRM** : Gestion clients avec CRUD complet
    - **Inventaire** : Stocks et produits avec alertes
    - **Fournisseurs** : Partenaires commerciaux
    - **Ventes** : Commandes clients avec suivi
    - **Achats** : Approvisionnements et réceptions
    - **Rapports** : BI et exports CSV
    - **Administration** : Utilisateurs et sécurité
    
    ### 🔧 Technologies
    
    - **Frontend** : Streamlit (Python)
    - **Backend** : PostgreSQL via Supabase
    - **Hébergement** : Streamlit Cloud
    - **Sécurité** : SHA-256, Permissions granulaires
    
    ### ✨ Nouvelles Fonctionnalités v3.2
    
    - ✅ CRUD complet (Create, Read, Update, Delete)
    - ✅ Menu navigation avec emojis et boutons radio
    - ✅ Protection des contraintes de clé étrangère
    - ✅ Interface utilisateur modernisée
    - ✅ Gestion intelligente du cache
    
    ### 👨‍🏫 Développeur
    
    **ISMAILI ALAOUI MOHAMED**  
    Formateur en Logistique et Transport  
    IFMLT ZENATA - OFPPT
    
    ---
    
    Version 3.2 - CRUD Complet avec Navigation Améliorée
    """)

# ========== FOOTER SIDEBAR ==========
st.sidebar.markdown("---")
date_footer = datetime.now().strftime('%d/%m/%Y')
st.sidebar.markdown(f"""
<div style="background-color: #f8fafc; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0;">
    <p style="margin: 0; font-size: 11px; color: #64748b; text-align: center;">
        <strong style="color: #1e3a8a;">ISMAILI ALAOUI MOHAMED</strong><br>
        Formateur en Logistique et Transport<br>
        <strong>IFMLT ZENATA - OFPPT</strong>
    </p>
    <hr style="margin: 10px 0; border: 0; border-top: 1px solid #cbd5e1;">
    <p style="margin: 0; font-size: 10px; color: #64748b; text-align: center;">
        📅 {date_footer}<br>
        Session: <strong>{st.session_state.username if st.session_state.logged_in else 'N/A'}</strong>
    </p>
</div>
""", unsafe_allow_html=True)

if st.session_state.logged_in:
    with st.sidebar.expander("ℹ️ Info Session"):
        st.write(f"**User ID:** {st.session_state.user_id}")
        st.write(f"**Rôle:** {st.session_state.role}")
        if st.session_state.session_id:
            st.write(f"**Session ID:** {st.session_state.session_id[:8]}...")
        st.write("**Statut:** 🟢 Connecté")
        st.write("**Mode:** 🌐 Temps Réel")
        st.caption("Base de données partagée PostgreSQL/Supabase"): #1e40af;">SYGEP v3.2</strong><br>
        🌐 Mode Temps Réel Activé
    </p>
    <hr style="margin: 10px 0; border: 0; border-top: 1px solid #cbd5e1;">
    <p style="margin: 0; font-size: 10px; color: #64748b; text-align: center;">
        Développé par<br>
        <strong style="colorimport streamlit as st
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
        
        # Vérification utilisateur admin par défaut
        c.execute("SELECT COUNT(*) FROM utilisateurs WHERE username = %s", ('admin',))
        if c.fetchone()[0] == 0:
            password_hash = hashlib.sha256("admin123".encode()).hexdigest()
            c.execute(
                "INSERT INTO utilisateurs (username, password, role) VALUES (%s, %s, %s) RETURNING id",
                ('admin', password_hash, 'admin')
            )
            user_id = c.fetchone()[0]
            
            modules = ["tableau_bord", "clients", "produits", "fournisseurs", "commandes", "achats", "rapports", "utilisateurs"]
            for module in modules:
                c.execute("INSERT INTO permissions (user_id, module, acces_lecture, acces_ecriture) VALUES (%s, %s, %s, %s)",
                          (user_id, module, True, True))
            
            conn.commit()
        
        # Ajouter données de démonstration si tables vides
        c.execute("SELECT COUNT(*) FROM clients")
        if c.fetchone()[0] == 0:
            c.execute("""INSERT INTO clients (nom, email, telephone, date_creation) VALUES 
                        ('Entreprise Alpha', 'contact@alpha.com', '0612345678', CURRENT_DATE),
                        ('Société Beta', 'info@beta.com', '0698765432', CURRENT_DATE)""")
            
            c.execute("""INSERT INTO produits (nom, prix, stock, seuil_alerte) VALUES 
                        ('Ordinateur Portable', 899.99, 15, 5),
                        ('Souris Sans Fil', 29.99, 50, 20),
                        ('Clavier Mécanique', 79.99, 30, 10)""")
            
            c.execute("""INSERT INTO fournisseurs (nom, email, telephone, adresse, date_creation) VALUES 
                        ('TechSupply Co', 'contact@techsupply.com', '0511223344', '12 Rue de la Tech, Paris', CURRENT_DATE),
                        ('GlobalParts', 'info@globalparts.com', '0522334455', '45 Avenue du Commerce, Lyon', CURRENT_DATE)""")
            
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
        c.execute("INSERT INTO logs_acces (user_id, module, action) VALUES (%s, %s, %s)",
                  (user_id, module, action))
        conn.commit()
    finally:
        release_connection(conn)

@st.cache_data(ttl=60)
def get_clients():
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM clients ORDER BY id", conn)
        return df
    finally:
        release_connection(conn)

@st.cache_data(ttl=60)
def get_produits():
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM produits ORDER BY id", conn)
        return df
    finally:
        release_connection(conn)

@st.cache_data(ttl=60)
def get_fournisseurs():
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM fournisseurs ORDER BY id", conn)
        return df
    finally:
        release_connection(conn)

@st.cache_data(ttl=60)
def get_commandes():
    conn = get_connection()
    try:
        query = """
        SELECT c.id, cl.nom as client, p.nom as produit, c.quantite, 
               (c.quantite * p.prix) as montant, c.date, c.statut
        FROM commandes c
        JOIN clients cl ON c.client_id = cl.id
        JOIN produits p ON c.produit_id = p.id
        ORDER BY c.date DESC
        """
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        release_connection(conn)

@st.cache_data(ttl=60)
def get_achats():
    conn = get_connection()
    try:
        query = """
        SELECT a.id, f.nom as fournisseur, p.nom as produit, a.quantite, 
               a.prix_unitaire, (a.quantite * a.prix_unitaire) as montant_total, a.date, a.statut
        FROM achats a
        JOIN fournisseurs f ON a.fournisseur_id = f.id
        JOIN produits p ON a.produit_id = p.id
        ORDER BY a.date DESC
        """
        df = pd.read_sql_query(query, conn)
        return df
    finally:
        release_connection(conn)

@st.cache_data(ttl=60)
def get_produits_stock_faible():
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM produits WHERE stock <= seuil_alerte", conn)
        return df
    finally:
        release_connection(conn)

@st.cache_data(ttl=5) 
def get_pending_orders_count():
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM commandes WHERE statut = 'En attente'")
        count = c.fetchone()[0]
        return count
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

# ========== FONCTION DE COMMANDE PUBLIQUE ==========
def page_passer_commande_publique():
    st.title("🛒 Passer une Nouvelle Commande (Espace Client)")
    st.markdown("---")
    
    produits = get_produits()
    
    if produits.empty:
        st.warning("⚠️ Service temporairement indisponible (aucun produit en vente).")
        return
        
    produits_disponibles = produits[produits['stock'] > 0]
    
    if produits_disponibles.empty:
        st.error("❌ Aucun produit en stock disponible pour la commande actuellement.")
        return

    with st.form("form_commande_client"):
        st.subheader("1. Vos Informations")
        
        nom_client = st.text_input("Votre Nom/Nom de Société *")
        email_client = st.text_input("Votre Email *")
        telephone_client = st.text_input("Votre Téléphone")
        
        st.subheader("2. Votre Commande")
        
        produits_list = [(int(r['id']), f"{r['nom']} - {float(r['prix']):.2f} € (Stock: {int(r['stock'])})", int(r['stock']), float(r['prix'])) 
                         for _, r in produits_disponibles.iterrows()]
        
        produits_labels = [p[1] for p in produits_list]
        selected_index = st.selectbox("Produit *", range(len(produits_labels)), 
                                      format_func=lambda i: produits_labels[i])
        
        produit_id = produits_list[selected_index][0]
        produit_stock = produits_list[selected_index][2]
        produit_prix = produits_list[selected_index][3]
        
        quantite = st.number_input("Quantité *", 
                                   min_value=1, 
                                   max_value=produit_stock, 
                                   step=1, 
                                   value=1, 
                                   key="quantite_publique_form")

        montant_estime = produit_prix * quantite
        st.info(f"Montant estimé de la commande : **{montant_estime:.2f} €** (hors taxes et livraison)")

        submit = st.form_submit_button("Envoyer la Commande", type="primary", use_container_width=True)
        
        if submit:
            if not nom_client or not email_client:
                st.error("❌ Veuillez remplir tous les champs obligatoires (Nom et Email).")
                return

            conn = get_connection()
            try:
                c = conn.cursor()
                
                c.execute("SELECT id FROM clients WHERE email = %s", (email_client,))
                client_data = c.fetchone()
                
                if client_data:
                    client_id = client_data[0]
                else:
                    st.info(f"Client '{nom_client}' non trouvé. Création d'un nouveau client.")
                    c.execute("""INSERT INTO clients (nom, email, telephone, date_creation) 
                                VALUES (%s, %s, %s, CURRENT_DATE) RETURNING id""",
                              (nom_client, email_client, telephone_client if telephone_client else None))
                    client_id = c.fetchone()[0]
                    conn.commit()
                
                produit_id_py = int(produit_id)
                quantite_py = int(quantite)
                client_id_py = int(client_id)
                
                c.execute("SELECT stock FROM produits WHERE id = %s", (produit_id_py,))
                stock_result = c.fetchone()
                
                if not stock_result:
                    st.error("❌ Produit introuvable.")
                    return
                    
                current_stock = int(stock_result[0])
                
                if current_stock >= quantite_py:
                    c.execute("""INSERT INTO commandes (client_id, produit_id, quantite, date, statut) 
                                VALUES (%s, %s, %s, CURRENT_DATE, 'En attente')""",
                              (client_id_py, produit_id_py, quantite_py))
                    
                    conn.commit()
                    
                    st.success(f"✅ Commande envoyée avec succès ! Quantité: {quantite_py}, Montant estimé: {montant_estime:.2f} €.")
                    st.info("📋 Votre commande est en attente de validation par notre équipe.")
                    st.balloons()
                    
                    get_pending_orders_count.clear()
                    get_commandes.clear()
                    get_clients.clear()
                else:
                    conn.rollback()
                    st.error(f"❌ Stock insuffisant ! Disponible: {current_stock}, Demandé: {quantite_py}")
                
            except Exception as e:
                conn.rollback()
                st.error(f"❌ Une erreur est survenue: {e}")
            finally:
                release_connection(conn)


# ========== INITIALISATION ==========
init_database()

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_id = None
    st.session_state.role = None
    st.session_state.permissions = {}
    st.session_state.session_id = None

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

# ========== PAGE DE CONNEXION / COMMANDE PUBLIQUE ==========
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
            <h1 style="color: #1e3a8a;">🎓 SYGEP</h1>
            <h3 style="color: #3b82f6;">Système de Gestion d'Entreprise Pédagogique</h3>
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
    
    tab_login, tab_client_order = st.tabs(["🔐 Authentification Utilisateur", "🛒 Passer une Commande (Client)"])

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
                        st.info("💡 Votre session est maintenant persistante.")
                        st.rerun()
                    else:
                        st.error("❌ Identifiants incorrects")
            
            st.success("🌐 Mode Multi-Utilisateurs Temps Réel Activé")

    with tab_client_order:
        page_passer_commande_publique()

    st.stop()

# ========== INTERFACE PRINCIPALE ==========
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
        <h1 style="color: #1e3a8a;">🎓 SYGEP - Système de Gestion d'Entreprise Pédagogique</h1>
        <p style="color: #64748b; font-size: 14px;">
            Développé par <strong>ISMAILI ALAOUI MOHAMED</strong> - Formateur en Logistique et Transport - IFMLT ZENATA
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
        👤 Connecté : {st.session_state.username} ({st.session_state.role.upper()}) | 🌐 Mode Temps Réel
    </h2>
</div>
""", unsafe_allow_html=True)

pending_count = get_pending_orders_count()
if pending_count > 0:
    st.sidebar.error(f"📢 **{pending_count} NOUVELLE(S) COMMANDE(S)** en attente de validation!")

if st.session_state.role != "admin":
    with st.sidebar.expander("🔒 Mes Permissions"):
        for module, perms in st.session_state.permissions.items():
            icon = "✅" if perms['lecture'] or perms['ecriture'] else "❌"
            lecture = "📖" if perms['lecture'] else ""
            ecriture = "✏️" if perms['ecriture'] else ""
            st.write(f"{icon} **{module.replace('_', ' ').title()}** {lecture} {ecriture}")

if st.sidebar.button("🚪 Se déconnecter", use_container_width=True):
    log_access(st.session_state.user_id, "deconnexion", "Déconnexion")
    if st.session_state.session_id:
        delete_session_from_db(st.session_state.session_id)
    st.query_params.clear()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

st.sidebar.divider()

# ========== MENU NAVIGATION ==========
st.sidebar.markdown("### 🧭 Navigation")

if 'selected_menu' not in st.session_state:
    st.session_state.selected_menu = "Tableau de Bord"

menu_options = []
menu_icons = {
    "Tableau de Bord": "📈",
    "Gestion des Clients": "👥",
    "Gestion des Produits": "📦",
    "Gestion des Fournisseurs": "🚚",
    "Gestion des Commandes": "🛒",
    "Gestion des Achats": "🛍️",
    "Rapports & Exports": "📊",
    "Gestion des Utilisateurs": "👤",
    "À Propos": "ℹ️"
}

if has_access("tableau_bord"): 
    menu_options.append("Tableau de Bord")
if has_access("clients"): 
    menu_options.append("Gestion des Clients")
if has_access("produits"): 
    menu_options.append("Gestion des Produits")
if has_access("fournisseurs"): 
    menu_options.append("Gestion des Fournisseurs")
if has_access("commandes"): 
    menu_options.append("Gestion des Commandes")
if has_access("achats"): 
    menu_options.append("Gestion des Achats")
if has_access("rapports"): 
    menu_options.append("Rapports & Exports")
if has_access("utilisateurs"): 
    menu_options.append("Gestion des Utilisateurs")
menu_options.append("À Propos")

menu_labels = [f"{menu_icons[opt]} {opt}" for opt in menu_options]

selected_label = st.sidebar.radio(
    "Sélectionnez un module",
    menu_labels,
    index=menu_options.index(st.session_state.selected_menu) if st.session_state.selected_menu in menu_options else 0,
    label_visibility="collapsed"
)

menu = selected_label.split(" ", 1)[1]
st.session_state.selected_menu = menu

# ========== TABLEAU DE BORD ==========
if menu == "Tableau de Bord":
    if not has_access("tableau_bord"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "tableau_bord", "Consultation")
    st.header("📈 Tableau de Bord")
    
    pending_count = get_pending_orders_count()
    if pending_count > 0:
        st.error(f"📢 **URGENT : {pending_count} NOUVELLE(S) COMMANDE(S) CLIENT EN ATTENTE !**")
    
    produits_alerte = get_produits_stock_faible()
    if not produits_alerte.empty:
        st.warning(f"⚠️ **{len(produits_alerte)} produit(s) en stock faible !**")
    
    col1, col2, col3, col4 = st.columns(4)
    clients = get_clients()
    produits = get_produits()
    commandes = get_commandes()
    
    with col1:
        st.metric("👥 Clients", len(clients))
    with col2:
        st.metric("📦 Produits", len(produits))
    with col3:
        st.metric("🛒 Commandes", len(commandes))
    with col4:
        ca_total = commandes['montant'].sum() if not commandes.empty else 0
        st.metric("💰 CA Total", f"{ca_total:.2f} €")
    
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

# ========== GESTION DES CLIENTS ==========
elif menu == "Gestion des Clients":
    if not has_access("clients"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "clients", "Consultation")
    st.header("👥 Gestion des Clients")
    
    tab1, tab2, tab3 = st.tabs(["📋 Liste", "➕ Ajouter", "✏️ Modifier"])
    
    with tab1:
        clients = get_clients()
        if not clients.empty:
            st.dataframe(clients, use_container_width=True, hide_index=True)
            
            if has_access("clients", "ecriture"):
                st.divider()
                st.subheader("🗑️ Supprimer un Client")
                col1, col2 = st.columns([3, 1])
                with col1:
                    client_id = st.selectbox("Sélectionner le client à supprimer", clients['id'].tolist(),
                                            format_func=lambda x: f"{clients[clients['id']==x]['nom'].iloc[0]} - {clients[clients['id']==x]['email'].iloc[0]}")
                with col2:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Supprimer", type="secondary"):
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("SELECT COUNT(*) FROM commandes WHERE client_id=%s", (int(client_id),))
                            nb_commandes = c.fetchone()[0]
                            
                            if nb_commandes > 0:
                                st.error(f"❌ Impossible de supprimer ce client ! Il possède {nb_commandes} commande(s).")
                            else:
                                c.execute("DELETE FROM clients WHERE id=%s", (int(client_id),))
                                conn.commit()
                                log_access(st.session_state.user_id, "clients", f"Suppression ID:{client_id}")
                                st.success("✅ Client supprimé avec succès!")
                                get_clients.clear()
                                st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"❌ Erreur: {e}")
                        finally:
                            release_connection(conn)
        else:
            st.info("🔭 Aucun client enregistré")
    
    with tab2:
        if not has_access("clients", "ecriture"):
            st.warning("⚠️ Vous n'avez pas les droits d'écriture")
        else:
            st.subheader("➕ Ajouter un Nouveau Client")
            with st.form("form_add_client"):
                nom = st.text_input("Nom du Client *")
                email = st.text_input("Email *")
                telephone = st.text_input("Téléphone")
                
                col1, col2 = st.columns(2)
                with col1:
                    submit = st.form_submit_button("✅ Enregistrer", use_container_width=True, type="primary")
                with col2:
                    cancel = st.form_submit_button("❌ Annuler", use_container_width=True)
                
                if submit:
                    if nom and email:
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("INSERT INTO clients (nom, email, telephone, date_creation) VALUES (%s, %s, %s, CURRENT_DATE)",
                                      (nom, email, telephone if telephone else None))
                            conn.commit()
                            log_access(st.session_state.user_id, "clients", f"Ajout: {nom}")
                            st.success(f"✅ Client '{nom}' ajouté!")
                            get_clients.clear()
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"❌ Erreur: {e}")
                        finally:
                            release_connection(conn)
                    else:
                        st.error("❌ Nom et email obligatoires")
    
    with tab3:
        if not has_access("clients", "ecriture"):
            st.warning("⚠️ Vous n'avez pas les droits d'écriture")
        else:
            st.subheader("✏️ Modifier un Client")
            clients = get_clients()
            
            if clients.empty:
                st.info("🔭 Aucun client à modifier")
            else:
                client_id_update = st.selectbox("Sélectionner le client", 
                                               clients['id'].tolist(),
                                               format_func=lambda x: f"{clients[clients['id']==x]['nom'].iloc[0]}")
                
                if client_id_update:
                    client_data = clients[clients['id'] == client_id_update].iloc[0]
                    
                    with st.form("form_update_client"):
                        nom_update = st.text_input("Nom *", value=client_data['nom'])
                        email_update = st.text_input("Email *", value=client_data['email'] if pd.notna(client_data['email']) else "")
                        telephone_update = st.text_input("Téléphone", value=client_data['telephone'] if pd.notna(client_data['telephone']) else "")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            submit_update = st.form_submit_button("✅ Mettre à Jour", use_container_width=True, type="primary")
                        with col2:
                            cancel_update = st.form_submit_button("❌ Annuler", use_container_width=True)
                        
                        if submit_update:
                            if nom_update and email_update:
                                conn = get_connection()
                                try:
                                    c = conn.cursor()
                                    c.execute("UPDATE clients SET nom=%s, email=%s, telephone=%s WHERE id=%s",
                                              (nom_update, email_update, telephone_update if telephone_update else None, int(client_id_update)))
                                    conn.commit()
                                    log_access(st.session_state.user_id, "clients", f"Modification ID:{client_id_update}")
                                    st.success(f"✅ Client modifié!")
                                    get_clients.clear()
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"❌ Erreur: {e}")
                                finally:
                                    release_connection(conn)
                            else:
                                st.error("❌ Nom et email obligatoires")

# ========== GESTION DES PRODUITS ==========
elif menu == "Gestion des Produits":
    if not has_access("produits"):
        st.error("❌ Accès refusé")
        st.stop()
    
    log_access(st.session_state.user_id, "produits", "Consultation")
    st.header("📦 Gestion des Produits")
    
    tab1, tab2, tab3 = st.tabs(["📋 Liste", "➕ Ajouter", "✏️ Modifier"])
    
    with tab1:
        produits = get_produits()
        if not produits.empty:
            produits_display = produits.copy()
            produits_display['statut'] = produits_display.apply(
                lambda r: '🔴 Stock Faible' if r['stock'] <= r['seuil_alerte'] else '🟢 Stock OK', axis=1)
            st.dataframe(produits_display, use_container_width=True, hide_index=True)
            
            if has_access("produits", "ecriture"):
                st.divider()
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("🔄 Ajuster le Stock")
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        prod_id = st.selectbox("Produit", produits['id'].tolist(),
                                              format_func=lambda x: produits[produits['id']==x]['nom'].iloc[0])
                    with col_b:
                        ajust = st.number_input("Ajustement", value=0, step=1)
                    with col_c:
                        st.write("")
                        st.write("")
                        if st.button("✅ Appliquer"):
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("UPDATE produits SET stock = stock + %s WHERE id = %s", (int(ajust), int(prod_id)))
                                conn.commit()
                                st.success(f"✅ Stock ajusté de {ajust:+d}")
                                get_produits.clear()
                                st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"❌ Erreur: {e}")
                            finally:
                                release_connection(conn)
                
                with col2:
                    st.subheader("🗑️ Supprimer un Produit")
                    col_x, col_y = st.columns([3, 1])
                    with col_x:
                        prod_del_id = st.selectbox("Produit à supprimer", produits['id'].tolist(),
                                                  format_func=lambda x: f"{produits[produits['id']==x]['nom'].iloc[0]}")
                    with col_y:
                        st.write("")
                        st.write("")
                        if st.button("🗑️ Supprimer", type="secondary"):
                            conn = get_connection()
                            try:
                                c = conn.cursor()
                                c.execute("SELECT COUNT(*) FROM commandes WHERE produit_id=%s", (int(prod_del_id),))
                                nb_commandes = c.fetchone()[0]
                                c.execute("SELECT COUNT(*) FROM achats WHERE produit_id=%s", (int(prod_del_id),))
                                nb_achats = c.fetchone()[0]
                                
                                if nb_commandes > 0 or nb_achats > 0:
                                    st.error(f"❌ Produit référencé dans {nb_commandes} commande(s) et {nb_achats} achat(s)")
                                else:
                                    c.execute("DELETE FROM produits WHERE id=%s", (int(prod_del_id),))
                                    conn.commit()
                                    st.success("✅ Produit supprimé!")
                                    get_produits.clear()
                                    st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"❌ Erreur: {e}")
                            finally:
                                release_connection(conn)
        else:
            st.info("🔭 Aucun produit enregistré")
    
    with tab2:
        if not has_access("produits", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            st.subheader("➕ Ajouter un Nouveau Produit")
            with st.form("form_add_produit"):
                nom = st.text_input("Nom du Produit *")
                col1, col2 = st.columns(2)
                with col1:
                    prix = st.number_input("Prix (€) *", min_value=0.01, step=0.01, format="%.2f")
                with col2:
                    stock = st.number_input("Stock Initial", min_value=0, step=1, value=0)
                seuil = st.number_input("Seuil d'Alerte", min_value=0, step=1, value=10)
                
                col_a, col_b = st.columns(2)
                with col_a:
                    submit = st.form_submit_button("✅ Enregistrer", use_container_width=True, type="primary")
                with col_b:
                    cancel = st.form_submit_button("❌ Annuler", use_container_width=True)
                
                if submit:
                    if nom and prix > 0:
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("INSERT INTO produits (nom, prix, stock, seuil_alerte) VALUES (%s, %s, %s, %s)",
                                      (nom, float(prix), int(stock), int(seuil)))
                            conn.commit()
                            st.success(f"✅ Produit '{nom}' ajouté!")
                            get_produits.clear()
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"❌ Erreur: {e}")
                        finally:
                            release_connection(conn)
                    else:
                        st.error("❌ Nom et prix > 0 requis")
    
    with tab3:
        if not has_access("produits", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            st.subheader("✏️ Modifier un Produit")
            produits = get_produits()
            
            if produits.empty:
                st.info("🔭 Aucun produit à modifier")
            else:
                prod_id_update = st.selectbox("Sélectionner le produit", 
                                             produits['id'].tolist(),
                                             format_func=lambda x: f"{produits[produits['id']==x]['nom'].iloc[0]}")
                
                if prod_id_update:
                    prod_data = produits[produits['id'] == prod_id_update].iloc[0]
                    
                    with st.form("form_update_produit"):
                        nom_update = st.text_input("Nom *", value=prod_data['nom'])
                        col1, col2 = st.columns(2)
                        with col1:
                            prix_update = st.number_input("Prix (€) *", min_value=0.01, step=0.01, 
                                                         value=float(prod_data['prix']), format="%.2f")
                        with col2:
                            stock_update = st.number_input("Stock", min_value=0, step=1, 
                                                          value=int(prod_data['stock']))
                        seuil_update = st.number_input("Seuil d'Alerte", min_value=0, step=1, 
                                                      value=int(prod_data['seuil_alerte']))
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            submit_update = st.form_submit_button("✅ Mettre à Jour", use_container_width=True, type="primary")
                        with col_b:
                            cancel_update = st.form_submit_button("❌ Annuler", use_container_width=True)
                        
                        if submit_update:
                            if nom_update and prix_update > 0:
                                conn = get_connection()
                                try:
                                    c = conn.cursor()
                                    c.execute("UPDATE produits SET nom=%s, prix=%s, stock=%s, seuil_alerte=%s WHERE id=%s",
                                              (nom_update, float(prix_update), int(stock_update), int(seuil_update), int(prod_id_update)))
                                    conn.commit()
                                    st.success(f"✅ Produit modifié!")
                                    get_produits.clear()
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"❌ Erreur: {e}")
                                finally:
                                    release_connection(conn)
                            else:
                                st.error("❌ Nom et prix > 0 requis")

# ========== GESTION DES FOURNISSEURS ==========
elif menu == "Gestion des Fournisseurs":
    if not has_access("fournisseurs"):
        st.error("❌ Accès refusé")
        st.stop()

    log_access(st.session_state.user_id, "fournisseurs", "Consultation")
    st.header("🚚 Gestion des Fournisseurs")

    tab1, tab2, tab3 = st.tabs(["📋 Liste", "➕ Ajouter", "✏️ Modifier"])

    with tab1:
        fournisseurs = get_fournisseurs()
        if not fournisseurs.empty:
            st.dataframe(fournisseurs, use_container_width=True, hide_index=True)

            if has_access("fournisseurs", "ecriture"):
                st.divider()
                st.subheader("🗑️ Supprimer un Fournisseur")
                col1, col2 = st.columns([3, 1])
                with col1:
                    fournisseur_id = st.selectbox("Sélectionner le fournisseur", fournisseurs['id'].tolist(),
                                            format_func=lambda x: f"{fournisseurs[fournisseurs['id']==x]['nom'].iloc[0]}")
                with col2:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ Supprimer", type="secondary"):
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("SELECT COUNT(*) FROM achats WHERE fournisseur_id=%s", (int(fournisseur_id),))
                            nb_achats = c.fetchone()[0]
                            
                            if nb_achats > 0:
                                st.error(f"❌ Fournisseur a {nb_achats} achat(s) enregistré(s)")
                            else:
                                c.execute("DELETE FROM fournisseurs WHERE id=%s", (int(fournisseur_id),)) 
                                conn.commit()
                                st.success("✅ Fournisseur supprimé!")
                                get_fournisseurs.clear()
                                st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"❌ Erreur: {e}")
                        finally:
                            release_connection(conn)
        else:
            st.info("🔭 Aucun fournisseur enregistré")

    with tab2:
        if not has_access("fournisseurs", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            st.subheader("➕ Ajouter un Nouveau Fournisseur")
            with st.form("form_add_fournisseur"):
                nom = st.text_input("Nom du Fournisseur *")
                email = st.text_input("Email")
                telephone = st.text_input("Téléphone")
                adresse = st.text_area("Adresse")

                col1, col2 = st.columns(2)
                with col1:
                    submit = st.form_submit_button("✅ Enregistrer", use_container_width=True, type="primary")
                with col2:
                    cancel = st.form_submit_button("❌ Annuler", use_container_width=True)
                
                if submit:
                    if nom:
                        conn = get_connection()
                        try:
                            c = conn.cursor()
                            c.execute("INSERT INTO fournisseurs (nom, email, telephone, adresse, date_creation) VALUES (%s, %s, %s, %s, CURRENT_DATE)",
                                    (nom, email if email else None, telephone if telephone else None, adresse if adresse else None))
                            conn.commit()
                            st.success(f"✅ Fournisseur '{nom}' ajouté!")
                            get_fournisseurs.clear()
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"❌ Erreur: {e}")
                        finally:
                            release_connection(conn)
                    else:
                        st.error("❌ Le nom est obligatoire")
    
    with tab3:
        if not has_access("fournisseurs", "ecriture"):
            st.warning("⚠️ Pas de droits d'écriture")
        else:
            st.subheader("✏️ Modifier un Fournisseur")
            fournisseurs = get_fournisseurs()
            
            if fournisseurs.empty:
                st.info("🔭 Aucun fournisseur à modifier")
            else:
                fournisseur_id_update = st.selectbox("Sélectionner le fournisseur", 
                                                    fournisseurs['id'].tolist(),
                                                    format_func=lambda x: f"{fournisseurs[fournisseurs['id']==x]['nom'].iloc[0]}")
                
                if fournisseur_id_update:
                    fournisseur_data = fournisseurs[fournisseurs['id'] == fournisseur_id_update].iloc[0]
                    
                    with st.form("form_update_fournisseur"):
                        nom_update = st.text_input("Nom *", value=fournisseur_data['nom'])
                        email_update = st.text_input("Email", value=fournisseur_data['email'] if pd.notna(fournisseur_data['email']) else "")
                        telephone_update = st.text_input("Téléphone", value=fournisseur_data['telephone'] if pd.notna(fournisseur_data['telephone']) else "")
                        adresse_update = st.text_area("Adresse", value=fournisseur_data['adresse'] if pd.notna(fournisseur_data['adresse']) else "")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            submit_update = st.form_submit_button("✅ Mettre à Jour", use_container_width=True, type="primary")
                        with col2:
                            cancel_update = st.form_submit_button("❌ Annuler", use_container_width=True)
                        
                        if submit_update:
                            if nom_update:
                                conn = get_connection()
                                try:
                                    c = conn.cursor()
                                    c.execute("UPDATE fournisseurs SET nom=%s, email=%s, telephone=%s, adresse=%s WHERE id=%s",
                                              (nom_update, email_update if email_update else None, 
                                               telephone_update if telephone_update else None,
                                               adresse_update if adresse_update else None, int(fournisseur_id_update)))
                                    conn.commit()
                                    st.success(f"✅ Fournisseur modifié!")
                                    get_fournisseurs.clear()
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"❌ Erreur: {e}")
                                finally:
                                    release_connection(conn)

# ========== SUITE DANS LE PROCHAIN MESSAGE =
