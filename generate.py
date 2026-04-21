#!/usr/bin/env python3
"""
Générateur de widget Grist avec intégration des skills
"""

import sqlite3
import shutil
import sys
import json
import os

def generer_widget(nom_module, description, type_app, template_path, skills_path):
    """
    Génère un .grist personnalisé basé sur le formulaire
    """
    output_path = f"{nom_module.lower().replace(' ', '_')}.grist"
    
    # Copier le template
    shutil.copy(template_path, output_path)
    
    conn = sqlite3.connect(output_path)
    c = conn.cursor()
    
    print(f"✅ Template chargé")
    
    # Charger les skills
    skills = {}
    if os.path.exists(skills_path):
        for skill_file in ['grist-widget.md', 'grist-rls.md']:
            skill_path = os.path.join(skills_path, skill_file)
            if os.path.exists(skill_path):
                with open(skill_path, 'r', encoding='utf-8') as f:
                    skills[skill_file] = f.read()
                print(f"✅ Skill chargé: {skill_file}")
    
    # Supprimer Table1 du template
    c.execute("DROP TABLE IF EXISTS Table1")
    c.execute("DELETE FROM _grist_Tables WHERE tableId='Table1'")
    c.execute("DELETE FROM _grist_Tables_column WHERE parentId=1")
    c.execute("DELETE FROM _grist_Views WHERE name='Table1'")
    c.execute("DELETE FROM _grist_Views_section WHERE tableRef=1")
    c.execute("DELETE FROM _grist_Views_section_field WHERE parentId IN (1,2,3)")
    c.execute("DELETE FROM _grist_Pages WHERE viewRef=1")
    c.execute("DELETE FROM _grist_TabBar WHERE viewRef=1")
    
    print(f"✅ Template nettoyé")
    
    # Créer les tables métier
    c.execute('''
        CREATE TABLE Projets (
            id INTEGER PRIMARY KEY,
            nom TEXT NOT NULL,
            description TEXT,
            statut TEXT DEFAULT 'En cours',
            responsable_email TEXT,
            acl_viewers TEXT,
            acl_editors TEXT,
            acl_deleters TEXT,
            manualSort NUMERIC
        )
    ''')
    
    c.execute('''
        CREATE TABLE Taches (
            id INTEGER PRIMARY KEY,
            projet_id INTEGER,
            titre TEXT NOT NULL,
            statut TEXT DEFAULT 'A faire',
            priorite TEXT DEFAULT 'Moyenne',
            assignee_email TEXT,
            acl_viewers TEXT,
            acl_editors TEXT,
            acl_deleters TEXT,
            manualSort NUMERIC
        )
    ''')
    
    print(f"✅ Tables créées")
    
    # Métadonnées tables
    c.execute("INSERT INTO _grist_Tables VALUES (1, 'Projets', 1, 0, 0, 2, 3)")
    c.execute("INSERT INTO _grist_Tables VALUES (2, 'Taches', 4, 0, 0, 5, 6)")
    
    # Colonnes Projets
    colonnes_projets = [
        (1, 1, 1.0, 'manualSort', 'ManualSortPos', '', 0, '', ''),
        (2, 1, 2.0, 'nom', 'Text', '', 0, '', 'Nom'),
        (3, 1, 3.0, 'description', 'Text', '', 0, '', 'Description'),
        (4, 1, 4.0, 'statut', 'Choice', '{"choices":["En cours","Terminé","Suspendu"]}', 0, '', 'Statut'),
        (5, 1, 5.0, 'responsable_email', 'Text', '', 0, '', 'Responsable'),
        (6, 1, 6.0, 'acl_viewers', 'Text', '', 1, '$responsable_email', 'ACL Viewers'),
        (7, 1, 7.0, 'acl_editors', 'Text', '', 1, '$responsable_email', 'ACL Editors'),
        (8, 1, 8.0, 'acl_deleters', 'Text', '', 1, '$responsable_email', 'ACL Deleters'),
    ]
    
    for col in colonnes_projets:
        c.execute('''
            INSERT INTO _grist_Tables_column 
            (id, parentId, parentPos, colId, type, widgetOptions, isFormula, formula, label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', col)
    
    # Colonnes Taches
    colonnes_taches = [
        (9, 2, 1.0, 'manualSort', 'ManualSortPos', '', 0, '', ''),
        (10, 2, 2.0, 'projet_id', 'Ref:Projets', '', 0, '', 'Projet'),
        (11, 2, 3.0, 'titre', 'Text', '', 0, '', 'Titre'),
        (12, 2, 4.0, 'statut', 'Choice', '{"choices":["A faire","En cours","Terminé"]}', 0, '', 'Statut'),
        (13, 2, 5.0, 'priorite', 'Choice', '{"choices":["Basse","Moyenne","Haute"]}', 0, '', 'Priorité'),
        (14, 2, 6.0, 'assignee_email', 'Text', '', 0, '', 'Assigné'),
        (15, 2, 7.0, 'acl_viewers', 'Text', '', 1, '",".join(filter(None,[$projet_id.responsable_email,$assignee_email]))', 'ACL Viewers'),
        (16, 2, 8.0, 'acl_editors', 'Text', '', 1, '",".join(filter(None,[$projet_id.responsable_email,$assignee_email]))', 'ACL Editors'),
        (17, 2, 9.0, 'acl_deleters', 'Text', '', 1, '$projet_id.responsable_email', 'ACL Deleters'),
    ]
    
    for col in colonnes_taches:
        c.execute('''
            INSERT INTO _grist_Tables_column 
            (id, parentId, parentPos, colId, type, widgetOptions, isFormula, formula, label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', col)
    
    # Vues
    c.execute("INSERT INTO _grist_Views VALUES (1, 'Projets', 'raw_data', '')")
    c.execute("INSERT INTO _grist_Views VALUES (4, 'Taches', 'raw_data', '')")
    
    # Sections
    for section_id, table_ref, parent_id, parent_key in [
        (1, 1, 1, 'record'), (2, 1, 0, 'record'), (3, 1, 0, 'single'),
        (4, 2, 4, 'record'), (5, 2, 0, 'record'), (6, 2, 0, 'single')
    ]:
        c.execute(f'''
            INSERT INTO _grist_Views_section 
            (id, tableRef, parentId, parentKey, title, defaultWidth, borderWidth)
            VALUES ({section_id}, {table_ref}, {parent_id}, '{parent_key}', '', 100, 1)
        ''')
    
    # Fields (colonnes visibles)
    fields = [
        # Section 1 (Projets)
        (1, 1, 2), (2, 1, 3), (3, 1, 4), (4, 1, 5),
        # Section 2 (Projets)
        (5, 2, 2), (6, 2, 3), (7, 2, 4), (8, 2, 5),
        # Section 4 (Taches)
        (9, 4, 10), (10, 4, 11), (11, 4, 12), (12, 4, 13), (13, 4, 14),
        # Section 5 (Taches)
        (14, 5, 10), (15, 5, 11), (16, 5, 12), (17, 5, 13),
    ]
    
    for field_id, parent_id, col_ref in fields:
        c.execute(f'''
            INSERT INTO _grist_Views_section_field (id, parentId, colRef, width)
            VALUES ({field_id}, {parent_id}, {col_ref}, 0)
        ''')
    
    # Pages
    c.execute("INSERT INTO _grist_Pages VALUES (1, 1, 0, 1, 0, '')")
    c.execute("INSERT INTO _grist_Pages VALUES (2, 4, 0, 2, 0, '')")
    
    # TabBar
    c.execute("INSERT INTO _grist_TabBar VALUES (1, 1, 1)")
    c.execute("INSERT INTO _grist_TabBar VALUES (2, 4, 2)")
    
    print(f"✅ Métadonnées configurées")
    
    # Données de démo
    c.execute(f'''
        INSERT INTO Projets (id, nom, description, statut, responsable_email, manualSort)
        VALUES (1, '{nom_module}', '{description}', 'En cours', 'demo@example.com', 1)
    ''')
    
    c.execute(f'''
        INSERT INTO Taches (id, projet_id, titre, statut, priorite, assignee_email, manualSort)
        VALUES 
        (1, 1, 'Tâche exemple 1', 'A faire', 'Haute', 'demo@example.com', 1),
        (2, 1, 'Tâche exemple 2', 'En cours', 'Moyenne', 'demo@example.com', 2)
    ''')
    
    print(f"✅ Données de démo ajoutées")
    
    conn.commit()
    conn.close()
    
    print(f"\n🎉 Fichier généré : {output_path}")
    print(f"📊 Module : {nom_module}")
    print(f"📝 Description : {description}")
    print(f"🎨 Type : {type_app}")
    print(f"📚 Skills chargés : {len(skills)}")
    
    return output_path

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python generate.py <nom_module> <description> <type_app> [template_path] [skills_path]")
        sys.exit(1)
    
    nom_module = sys.argv[1]
    description = sys.argv[2]
    type_app = sys.argv[3]
    template_path = sys.argv[4] if len(sys.argv) > 4 else 'Document_sans_titre.grist'
    skills_path = sys.argv[5] if len(sys.argv) > 5 else 'skills'
    
    generer_widget(nom_module, description, type_app, template_path, skills_path)
