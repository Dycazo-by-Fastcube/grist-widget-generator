# Grist Widget Generator — Contexte pour Claude Code

## Pipeline complet

1. **Formulaire** (`public/index.html`) — collecte la spec (description, rôles, tables, user stories, permissions, écrans) avec persistance `formData` entre les étapes
2. **Vercel API** (`api/create-issue.ts`) — reçoit la spec en JSON, crée une GitHub Issue avec le label `widget-generation` et le body `**Description :** {JSON.stringify(spec)}`
3. **Workflow** (`.github/workflows/generate-widget.yml`) — déclenché par l'issue, checkout le repo privé skills, calcule le slug/URL GitHub Pages, appelle `generate.py`
4. **generate.py** — parse le JSON de la spec, appelle Claude API pour (a) le schéma de colonnes par table, (b) le code widget HTML, génère le `.grist` SQLite + `widget.html`
5. **Artifacts** — `.grist` uploadé en artifact GitHub Actions ; `widget.html` committé dans `widgets/{slug}/index.html` et servi par GitHub Pages

La spec JSON complète transite via le body de l'issue GitHub. Toute modification de son format doit être cohérente entre `index.html`, `create-issue.ts` et `generate.py`.

## Secrets GitHub requis

- `ANTHROPIC_API_KEY` — clé API Claude (repo public `grist-widget-generator`)
- `PRIVATE_REPO_TOKEN` — token d'accès au repo privé `Dycazo-by-Fastcube/fastc-internal-tools`

## Repo privé skills

Checké dans le workflow à `skills-repo/01-skills-universels/` :
- `skill-grist-widget.md` — API grist-plugin-api.js, patterns widget
- `skill-grist-rls.md` — Row Level Security Grist

Attention : les noms de fichiers incluent le préfixe `skill-` — une erreur de nom = 0 skills chargés.

## Pièges connus — GitHub Actions

Ne jamais interpoler `${{ github.event.issue.body }}` directement dans un script bash : GitHub Actions interpole AVANT l'exécution, un JSON multi-lignes casse la syntaxe shell (exit code 127).

Règle : toujours passer via `env:` + fichier temp :
```yaml
env:
  ISSUE_BODY: ${{ github.event.issue.body }}
run: |
  printf '%s' "$ISSUE_BODY" > /tmp/spec_body.txt
  python3 generate.py ... "/tmp/spec_body.txt"
```

## Pièges connus — Schéma SQLite Grist

- **Template** : utiliser `default.grist` (validé via UI Grist, contient les bonnes colonnes de schéma). Faire un cleanup complet de toutes les tables méta (`_grist_Tables`, `_grist_Views`, `_grist_Views_section`, `_grist_Views_section_field`, `_grist_Pages`, `_grist_TabBar`) avant de reconstruire.
- **Section custom widget** : stocker l'URL dans la colonne `options` de `_grist_Views_section` (pas `customDef`), avec le JSON imbriqué suivant :
  ```python
  options = json.dumps({
      "verticalGridlines": True, "horizontalGridlines": True, "zebraStripes": False,
      "customView": json.dumps({"mode": "url", "url": widget_url, "access": "full",
                                "widgetDef": None, "pluginId": "", "sectionId": "",
                                "renderAfterReady": False, "widgetId": None,
                                "widgetOptions": None, "columnsMapping": None}),
      "numFrozen": 0
  })
  ```
- **Type de vue** : `_grist_Views.type` doit être `'raw_data'` (pas `'custom'`) pour la vue widget
- **`layoutSpec` obligatoire** : `_grist_Views.layoutSpec = {"children":[{"leaf":SECTION_ID}],"collapsed":[]}` — sans ça Grist ne sait pas quelle section afficher
- **Field obligatoire** : la section custom doit avoir au moins 1 entrée dans `_grist_Views_section_field` pointant vers une colonne visible, sinon la section est considérée vide
- **`parentId` des sections** : raw (`record`) et card (`single`) ont `parentId=0` ; seule la section affichée dans la page a `parentId=view_id`
- **`data:` URI bloqué** : Grist bloque les URI `data:text/html;base64,...` en iframe — héberger sur GitHub Pages et référencer l'URL https
- **Calcul des IDs** : `table_ref = i+1`, `view_id = i*3+1`, sections = `view_id`, `view_id+1`, `view_id+2` ; vue widget = `n_tables*3+1` — utiliser des compteurs globaux pour `col_id` et `field_id`
- **Colonnes** : ne pas créer les mêmes colonnes génériques pour toutes les tables — appeler Claude API (`generer_schema_tables`) pour obtenir les colonnes adaptées à chaque table AVANT de créer le .grist

## Pièges connus — Appels Claude API dans generate.py

Deux appels distincts :
1. `generer_schema_tables(spec)` — schéma de colonnes JSON par table (`max_tokens=2048`), fait AVANT la création des tables SQLite
2. `generer_code_widget(spec, skills)` — HTML/JS widget (`max_tokens=4096`), fait APRÈS

Toujours vérifier `stop_reason == 'max_tokens'` et implémenter la continuation (jusqu'à 3 fois) :
```python
if message.stop_reason == 'max_tokens':
    messages.append({"role": "assistant", "content": chunk})
    messages.append({"role": "user", "content": "Continue exactement où tu t'es arrêté. Termine jusqu'à </html>."})
```
