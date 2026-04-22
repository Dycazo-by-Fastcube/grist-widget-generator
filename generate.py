#!/usr/bin/env python3
"""
Générateur de widget Grist dynamique basé sur la spec JSON
"""

import sqlite3
import shutil
import sys
import json
import os
import re


def sanitize_table_id(name):
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if sanitized and sanitized[0].isdigit():
        sanitized = 'T_' + sanitized
    return sanitized[:50] or 'Table'


def generer_code_widget(spec, skills):
    """Appel Claude API pour générer le HTML/JS du widget, sauvegardé dans widget.html."""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("⚠️  ANTHROPIC_API_KEY absent, widget HTML non généré")
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        skill_widget = skills.get('skill-grist-widget.md', '')
        skill_rls    = skills.get('skill-grist-rls.md', '')

        prompt = f"""Tu es un expert Grist. Génère un widget HTML/JS/CSS autonome pour Grist.

SPEC DU BESOIN :
{json.dumps(spec, indent=2, ensure_ascii=False)}

SKILL GRIST WIDGET :
{skill_widget}

SKILL GRIST RLS :
{skill_rls}

Génère un fichier HTML complet et autonome qui :
1. Utilise l'API Grist (grist.ready(), grist.onRecords(), grist.onRecord(), etc.)
2. Affiche et permet de gérer les données des tables : {', '.join(spec.get('tables', []))}
3. Respecte les rôles : {', '.join(spec.get('roles', []))}
4. Respecte les permissions : {json.dumps(spec.get('permissions', {}), ensure_ascii=False)}
5. Correspond aux écrans demandés : {spec.get('screens', '')}
6. A un design propre avec CSS intégré

Réponds UNIQUEMENT avec le code HTML complet, sans bloc markdown ni explication."""

        message = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        html = message.content[0].text.strip()
        if html.startswith("```"):
            html = re.sub(r'^```[a-z]*\n?', '', html)
            html = re.sub(r'\n?```$', '', html)

        with open('widget.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"✅ Code widget généré et sauvegardé dans widget.html ({len(html)} caractères)")
        return html

    except Exception as e:
        print(f"⚠️  Erreur génération widget : {e}")
        return None


def ajouter_section_custom_widget(cur, widget_url, n_tables):
    """Ajoute une page 'Widget' avec une section custom dans le .grist."""
    custom_def = json.dumps({
        "url": widget_url,
        "access": "full",
        "widgetId": None,
        "pluginId": ""
    })

    # IDs qui suivent les tables de données
    SECTIONS_PER_TABLE = 3
    view_id    = n_tables * SECTIONS_PER_TABLE + 1
    section_id = view_id
    page_id    = n_tables + 1

    # Vérifier si la colonne customDef existe dans le schéma
    cur.execute("PRAGMA table_info(_grist_Views_section)")
    col_names = {row[1] for row in cur.fetchall()}

    cur.execute("INSERT INTO _grist_Views VALUES (?, 'Widget', 'custom', '')", (view_id,))

    if 'customDef' not in col_names:
        cur.execute("ALTER TABLE _grist_Views_section ADD COLUMN customDef TEXT DEFAULT ''")
        print("✅ Colonne customDef ajoutée au schéma")

    cur.execute(
        "INSERT INTO _grist_Views_section "
        "(id, tableRef, parentId, parentKey, title, defaultWidth, borderWidth, customDef) "
        "VALUES (?,0,?,'custom','Widget',100,1,?)",
        (section_id, view_id, custom_def)
    )

    cur.execute("INSERT INTO _grist_Pages VALUES (?,?,0,?,0,'')", (page_id, view_id, n_tables + 1))
    cur.execute("INSERT INTO _grist_TabBar VALUES (?,?,?)", (page_id, view_id, n_tables + 1))
    print(f"✅ Page widget custom ajoutée (view_id={view_id})")


def generer_widget(nom_module, description, type_app, template_path, skills_path, widget_url=None):
    # Lire depuis un fichier si description est un chemin
    if os.path.isfile(description):
        with open(description, 'r', encoding='utf-8') as f:
            raw = f.read()
    else:
        raw = description

    # Extraire le JSON depuis le body (qui peut contenir "**Description :** {...}")
    spec = {}
    try:
        start = raw.index('{')
        end = raw.rindex('}') + 1
        spec = json.loads(raw[start:end])
        tables_list = spec.get('tables', [])
        roles       = spec.get('roles', [])
        print(f"✅ Spec JSON parsée : {len(tables_list)} tables, {len(roles)} rôles")
    except (ValueError, json.JSONDecodeError) as e:
        print(f"⚠️  Impossible de parser le JSON ({e}), fallback générique")
        tables_list = []
        roles       = []

    if not tables_list:
        tables_list = ['Données']

    output_name = re.sub(r'[^a-z0-9_]', '_', nom_module.lower())[:40]
    output_path = f"{output_name}.grist"

    shutil.copy(template_path, output_path)
    conn = sqlite3.connect(output_path)
    cur = conn.cursor()

    print("✅ Template chargé")

    # Charger les skills (noms corrects dans le repo privé)
    skills = {}
    print(f"📁 Chemin skills : {skills_path} (existe: {os.path.exists(skills_path)})")
    if os.path.exists(skills_path):
        for skill_file in ['skill-grist-widget.md', 'skill-grist-rls.md']:
            skill_path = os.path.join(skills_path, skill_file)
            if os.path.exists(skill_path):
                with open(skill_path, 'r', encoding='utf-8') as f:
                    skills[skill_file] = f.read()
                print(f"✅ Skill chargé : {skill_file} ({len(skills[skill_file])} chars)")
            else:
                print(f"⚠️  Skill introuvable : {skill_path}")

    # Nettoyer Table1 du template
    cur.execute("DROP TABLE IF EXISTS Table1")
    cur.execute("DELETE FROM _grist_Tables WHERE tableId='Table1'")
    cur.execute("DELETE FROM _grist_Tables_column WHERE parentId=1")
    cur.execute("DELETE FROM _grist_Views WHERE name='Table1'")
    cur.execute("DELETE FROM _grist_Views_section WHERE tableRef=1")
    cur.execute("DELETE FROM _grist_Views_section_field WHERE parentId IN (1,2,3)")
    cur.execute("DELETE FROM _grist_Pages WHERE viewRef=1")
    cur.execute("DELETE FROM _grist_TabBar WHERE viewRef=1")

    print("✅ Template nettoyé")

    SECTIONS_PER_TABLE = 3
    COLS_PER_TABLE     = 8
    VISIBLE_COLS       = 4
    FIELDS_PER_TABLE   = VISIBLE_COLS * 2  # main + raw sections

    for i, table_name in enumerate(tables_list):
        table_ref  = i + 1
        view_id    = i * SECTIONS_PER_TABLE + 1
        main_sec   = view_id
        raw_sec    = view_id + 1
        card_sec   = view_id + 2
        col_base   = i * COLS_PER_TABLE + 1
        field_base = i * FIELDS_PER_TABLE + 1

        table_id = sanitize_table_id(table_name)

        cur.execute(f'''
            CREATE TABLE IF NOT EXISTS "{table_id}" (
                id INTEGER PRIMARY KEY,
                nom TEXT,
                description TEXT,
                statut TEXT DEFAULT 'Actif',
                responsable_email TEXT,
                acl_viewers TEXT,
                acl_editors TEXT,
                acl_deleters TEXT,
                manualSort NUMERIC
            )
        ''')

        cur.execute(
            "INSERT INTO _grist_Tables VALUES (?, ?, ?, 0, 0, ?, ?)",
            (table_ref, table_id, view_id, raw_sec, card_sec)
        )

        acl_formula = '$responsable_email'
        cols = [
            (col_base,   table_ref, 1.0, 'manualSort',        'ManualSortPos', '',                                          0, '',          ''),
            (col_base+1, table_ref, 2.0, 'nom',               'Text',          '',                                          0, '',          'Nom'),
            (col_base+2, table_ref, 3.0, 'description',       'Text',          '',                                          0, '',          'Description'),
            (col_base+3, table_ref, 4.0, 'statut',            'Choice',        '{"choices":["Actif","Inactif","Archivé"]}', 0, '',          'Statut'),
            (col_base+4, table_ref, 5.0, 'responsable_email', 'Text',          '',                                          0, '',          'Responsable'),
            (col_base+5, table_ref, 6.0, 'acl_viewers',       'Text',          '',                                          1, acl_formula, 'ACL Viewers'),
            (col_base+6, table_ref, 7.0, 'acl_editors',       'Text',          '',                                          1, acl_formula, 'ACL Editors'),
            (col_base+7, table_ref, 8.0, 'acl_deleters',      'Text',          '',                                          1, acl_formula, 'ACL Deleters'),
        ]
        for col in cols:
            cur.execute(
                'INSERT INTO _grist_Tables_column (id, parentId, parentPos, colId, type, widgetOptions, isFormula, formula, label) VALUES (?,?,?,?,?,?,?,?,?)',
                col
            )

        cur.execute("INSERT INTO _grist_Views VALUES (?, ?, 'raw_data', '')", (view_id, table_name))

        for sid, pid, pkey in [
            (main_sec, view_id, 'record'),
            (raw_sec,  0,       'record'),
            (card_sec, 0,       'single'),
        ]:
            cur.execute(
                "INSERT INTO _grist_Views_section (id, tableRef, parentId, parentKey, title, defaultWidth, borderWidth) VALUES (?,?,?,?,?,?,?)",
                (sid, table_ref, pid, pkey, '', 100, 1)
            )

        visible_col_refs = [col_base+1, col_base+2, col_base+3, col_base+4]
        fid = field_base
        for section_id in [main_sec, raw_sec]:
            for col_ref in visible_col_refs:
                cur.execute(
                    "INSERT INTO _grist_Views_section_field (id, parentId, colRef, width) VALUES (?,?,?,?)",
                    (fid, section_id, col_ref, 0)
                )
                fid += 1

        cur.execute("INSERT INTO _grist_Pages VALUES (?,?,0,?,0,'')", (table_ref, view_id, i + 1))
        cur.execute("INSERT INTO _grist_TabBar VALUES (?,?,?)", (table_ref, view_id, i + 1))

        cur.execute(
            f'INSERT INTO "{table_id}" (id, nom, description, statut, responsable_email, manualSort) VALUES (1, ?, ?, ?, ?, 1)',
            (f'Exemple {table_name}', 'Description exemple', 'Actif', 'demo@example.com')
        )

        print(f"✅ Table créée : {table_name} → {table_id}")

    # Générer le code widget via Claude et l'intégrer
    widget_html = generer_code_widget(spec, skills)
    if widget_html and widget_url:
        ajouter_section_custom_widget(cur, widget_url, len(tables_list))

    conn.commit()
    conn.close()

    print(f"\n🎉 Fichier généré : {output_path}")
    print(f"📊 Module : {nom_module}")
    print(f"📋 Tables : {', '.join(tables_list)}")
    print(f"👥 Rôles : {', '.join(roles)}")
    print(f"📚 Skills chargés : {len(skills)}")

    return output_path


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: python generate.py <nom_module> <description_json> <type_app> [template_path] [skills_path]")
        sys.exit(1)

    nom_module    = sys.argv[1]
    description   = sys.argv[2]
    type_app      = sys.argv[3]
    template_path = sys.argv[4] if len(sys.argv) > 4 else 'Document_sans_titre.grist'
    skills_path   = sys.argv[5] if len(sys.argv) > 5 else 'skills'
    widget_url    = sys.argv[6] if len(sys.argv) > 6 else None

    generer_widget(nom_module, description, type_app, template_path, skills_path, widget_url)
