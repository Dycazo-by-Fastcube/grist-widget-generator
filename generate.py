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


def sql_type_for(grist_type):
    if grist_type in ('Int',):
        return 'INTEGER'
    if grist_type in ('Numeric', 'Date', 'DateTime'):
        return 'NUMERIC'
    if grist_type == 'Bool':
        return 'INTEGER'
    return 'TEXT'


def get_anthropic_client():
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return None
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# 1. Générer le schéma de colonnes pour chaque table
# ---------------------------------------------------------------------------

def generer_schema_tables(spec):
    """Demande à Claude les colonnes adaptées à chaque table de la spec."""
    client = get_anthropic_client()
    if not client:
        print("⚠️  ANTHROPIC_API_KEY absent, colonnes génériques utilisées")
        return {}

    tables = spec.get('tables', [])
    if not tables:
        return {}

    prompt = f"""Tu es un expert Grist. Analyse cette spec et génère les colonnes pour chaque table.

SPEC :
{json.dumps(spec, indent=2, ensure_ascii=False)}

Tables à définir : {tables}

Types Grist disponibles : Text, Int, Numeric, Date, DateTime, Bool, Choice, Ref:NomTable

Réponds UNIQUEMENT avec un JSON valide, sans markdown :
{{
  "NomTable": [
    {{"colId": "snake_case", "type": "Text", "label": "Libellé", "choices": null}},
    ...
  ]
}}

Règles strictes :
- colId en snake_case sans accents ni espaces
- Toujours commencer par un champ identifiant (nom, titre, reference…) de type Text
- Pour Choice : "choices" = ["val1","val2",...], sinon null
- Pour Ref : type = "Ref:NomAutreTable" (nom exact de la table cible)
- Entre 3 et 7 colonnes par table, pertinentes pour le besoin exprimé
- Ne PAS inclure : id, manualSort, acl_viewers, acl_editors, acl_deleters"""

    try:
        message = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()
        start = raw.index('{')
        end = raw.rindex('}') + 1
        schema = json.loads(raw[start:end])
        print(f"✅ Schéma colonnes généré : {list(schema.keys())}")
        return schema
    except Exception as e:
        print(f"⚠️  Erreur schéma colonnes ({e}), colonnes génériques utilisées")
        return {}


def colonnes_par_defaut():
    """Colonnes génériques si Claude ne répond pas."""
    return [
        {"colId": "nom",         "type": "Text",   "label": "Nom",         "choices": None},
        {"colId": "description", "type": "Text",   "label": "Description", "choices": None},
        {"colId": "statut",      "type": "Choice", "label": "Statut",
         "choices": ["Actif", "Inactif", "Archivé"]},
        {"colId": "responsable", "type": "Text",   "label": "Responsable", "choices": None},
    ]


# ---------------------------------------------------------------------------
# 2. Générer le code widget HTML via Claude
# ---------------------------------------------------------------------------

def generer_code_widget(spec, skills):
    """Appel Claude API pour générer le HTML/JS du widget, sauvegardé dans widget.html."""
    client = get_anthropic_client()
    if not client:
        print("⚠️  ANTHROPIC_API_KEY absent, widget HTML non généré")
        return None

    try:
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
5. Inclut maximum 3 écrans/vues (onglets ou sections) dans l'interface — reste simple
6. A un design propre avec CSS intégré

CONTRAINTE CRITIQUE : ta réponse ne doit pas dépasser 3800 tokens.
CSS minimal (pas de règles redondantes), JS sans commentaires,
pas de bibliothèques externes inutiles, fonctionnalités essentielles seulement.
Le fichier DOIT être syntaxiquement complet — ne jamais laisser une fonction ou balise ouverte.

Réponds UNIQUEMENT avec le code HTML complet, sans bloc markdown ni explication."""

        messages = [{"role": "user", "content": prompt}]
        html = ""

        for attempt in range(3):
            message = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=4096,
                messages=messages
            )
            chunk = message.content[0].text
            html += chunk
            print(f"✅ Chunk {attempt + 1} reçu ({len(chunk)} chars), stop_reason={message.stop_reason}")

            if message.stop_reason != 'max_tokens':
                break

            messages.append({"role": "assistant", "content": chunk})
            messages.append({"role": "user", "content": "Continue exactement où tu t'es arrêté. Ne répète aucune ligne déjà écrite. Termine jusqu'à </html>."})

        html = html.strip()
        if html.startswith("```"):
            html = re.sub(r'^```[a-z]*\n?', '', html)
            html = re.sub(r'\n?```$', '', html)

        with open('widget.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"✅ widget.html sauvegardé ({len(html)} chars)")
        return html

    except Exception as e:
        print(f"⚠️  Erreur génération widget : {e}")
        return None


# ---------------------------------------------------------------------------
# 3. Ajouter la page widget custom dans le .grist
# ---------------------------------------------------------------------------

def ajouter_section_custom_widget(cur, widget_url, n_tables, field_id, first_visible_col_ref):
    """Ajoute une page 'Widget' avec une section custom dans le .grist."""
    SECTIONS_PER_TABLE = 3
    view_id    = n_tables * SECTIONS_PER_TABLE + 1
    section_id = n_tables * SECTIONS_PER_TABLE + 1
    page_id    = n_tables + 1

    layout_spec = json.dumps({"children": [{"leaf": section_id}], "collapsed": []})

    custom_view_json = json.dumps({
        "mode": "url",
        "url": widget_url or "",
        "widgetDef": None,
        "access": "full",
        "pluginId": "",
        "sectionId": "",
        "renderAfterReady": False,
        "widgetId": None,
        "widgetOptions": None,
        "columnsMapping": None,
    })
    options_json = json.dumps({
        "verticalGridlines": True,
        "horizontalGridlines": True,
        "zebraStripes": False,
        "customView": custom_view_json,
        "numFrozen": 0,
    })

    cur.execute(
        "INSERT INTO _grist_Views (id, name, type, layoutSpec) VALUES (?,?,?,?)",
        (view_id, 'Widget', 'raw_data', layout_spec)
    )
    cur.execute(
        "INSERT INTO _grist_Views_section "
        "(id, tableRef, parentId, parentKey, title, defaultWidth, borderWidth, options) "
        "VALUES (?,?,?,'custom','',100,1,?)",
        (section_id, 1, view_id, options_json)
    )
    cur.execute(
        "INSERT INTO _grist_Views_section_field (id, parentId, colRef, width) VALUES (?,?,?,?)",
        (field_id, section_id, first_visible_col_ref, 0)
    )

    cur.execute("INSERT INTO _grist_Pages VALUES (?,?,0,?,0,'')", (page_id, view_id, n_tables + 1))
    cur.execute("INSERT INTO _grist_TabBar VALUES (?,?,?)", (page_id, view_id, n_tables + 1))
    print(f"✅ Page widget custom ajoutée (view_id={view_id}, section_id={section_id}, url={widget_url})")


# ---------------------------------------------------------------------------
# 4. Générer le .grist complet
# ---------------------------------------------------------------------------

def generer_widget(nom_module, description, type_app, template_path, skills_path, widget_url=None):
    # Lire depuis un fichier si description est un chemin
    if os.path.isfile(description):
        with open(description, 'r', encoding='utf-8') as f:
            raw = f.read()
    else:
        raw = description

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

    # Charger les skills
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

    # Générer le schéma de colonnes adapté à la spec
    schema = generer_schema_tables(spec)

    # Nettoyer entièrement le template (toutes les tables user + toutes les métadonnées Grist)
    existing_tables = cur.execute("SELECT tableId FROM _grist_Tables").fetchall()
    for (tid,) in existing_tables:
        cur.execute(f'DROP TABLE IF EXISTS "{tid}"')
    for meta in ['_grist_Tables', '_grist_Tables_column', '_grist_Views',
                 '_grist_Views_section', '_grist_Views_section_field',
                 '_grist_Pages', '_grist_TabBar']:
        cur.execute(f'DELETE FROM {meta}')
    print(f"✅ Template nettoyé ({len(existing_tables)} tables supprimées)")

    SECTIONS_PER_TABLE = 3
    col_id   = 1  # compteur global croissant
    field_id = 1  # compteur global croissant
    acl_formula = '$responsable_email'
    first_visible_col_ref = None  # colRef de la 1re colonne visible (pour la section custom)

    for i, table_name in enumerate(tables_list):
        table_ref = i + 1
        view_id   = i * SECTIONS_PER_TABLE + 1
        main_sec  = view_id
        raw_sec   = view_id + 1
        card_sec  = view_id + 2

        table_id = sanitize_table_id(table_name)
        data_cols = schema.get(table_name) or colonnes_par_defaut()

        # --- Créer la table SQL ---
        sql_cols = ", ".join(
            f'"{c["colId"]}" {sql_type_for(c["type"])}'
            for c in data_cols
        )
        cur.execute(f'''
            CREATE TABLE IF NOT EXISTS "{table_id}" (
                id INTEGER PRIMARY KEY,
                {sql_cols},
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

        # --- Colonnes Grist ---
        # manualSort (système, non visible)
        cur.execute(
            'INSERT INTO _grist_Tables_column (id, parentId, parentPos, colId, type, widgetOptions, isFormula, formula, label) VALUES (?,?,?,?,?,?,?,?,?)',
            (col_id, table_ref, 0.0, 'manualSort', 'ManualSortPos', '', 0, '', '')
        )
        col_id += 1

        # colonnes de données (visibles)
        visible_col_ids = []
        for pos, c in enumerate(data_cols, start=1):
            if first_visible_col_ref is None:
                first_visible_col_ref = col_id
            widget_opts = ''
            if c['type'] == 'Choice' and c.get('choices'):
                widget_opts = json.dumps({"choices": c['choices']})
            cur.execute(
                'INSERT INTO _grist_Tables_column (id, parentId, parentPos, colId, type, widgetOptions, isFormula, formula, label) VALUES (?,?,?,?,?,?,?,?,?)',
                (col_id, table_ref, float(pos), c['colId'], c['type'], widget_opts, 0, '', c['label'])
            )
            visible_col_ids.append(col_id)
            col_id += 1

        # ACL (système, non visibles)
        for acl_col in ['acl_viewers', 'acl_editors', 'acl_deleters']:
            cur.execute(
                'INSERT INTO _grist_Tables_column (id, parentId, parentPos, colId, type, widgetOptions, isFormula, formula, label) VALUES (?,?,?,?,?,?,?,?,?)',
                (col_id, table_ref, float(len(data_cols) + 1), acl_col, 'Text', '', 1, acl_formula, acl_col)
            )
            col_id += 1

        # --- Vue et sections ---
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

        # Fields visibles dans main_sec et raw_sec
        for section_id in [main_sec, raw_sec]:
            for cref in visible_col_ids:
                cur.execute(
                    "INSERT INTO _grist_Views_section_field (id, parentId, colRef, width) VALUES (?,?,?,?)",
                    (field_id, section_id, cref, 0)
                )
                field_id += 1

        cur.execute("INSERT INTO _grist_Pages VALUES (?,?,0,?,0,'')", (table_ref, view_id, i + 1))
        cur.execute("INSERT INTO _grist_TabBar VALUES (?,?,?)", (table_ref, view_id, i + 1))

        # Donnée de démo : insérer une ligne avec la première colonne de données
        first_col = data_cols[0]['colId'] if data_cols else 'nom'
        cur.execute(
            f'INSERT INTO "{table_id}" ("{first_col}", manualSort) VALUES (?, 1)',
            (f'Exemple {table_name}',)
        )

        col_labels = ', '.join(c['label'] for c in data_cols)
        print(f"✅ Table créée : {table_name} → {table_id} [{col_labels}]")

    # Générer le code widget HTML et l'intégrer
    widget_html = generer_code_widget(spec, skills)
    if widget_url:
        ajouter_section_custom_widget(cur, widget_url, len(tables_list), field_id, first_visible_col_ref)

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
        print("Usage: python generate.py <nom_module> <description_json> <type_app> [template_path] [skills_path] [widget_url]")
        sys.exit(1)

    nom_module    = sys.argv[1]
    description   = sys.argv[2]
    type_app      = sys.argv[3]
    template_path = sys.argv[4] if len(sys.argv) > 4 else 'Document_sans_titre.grist'
    skills_path   = sys.argv[5] if len(sys.argv) > 5 else 'skills'
    widget_url    = sys.argv[6] if len(sys.argv) > 6 else None

    generer_widget(nom_module, description, type_app, template_path, skills_path, widget_url)
