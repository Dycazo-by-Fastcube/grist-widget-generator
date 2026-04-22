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

- **`customDef` absent** : vérifier avec `PRAGMA table_info(_grist_Views_section)` et ajouter via `ALTER TABLE ... ADD COLUMN customDef TEXT DEFAULT ''` si nécessaire
- **`data:` URI bloqué** : Grist bloque les URI `data:text/html;base64,...` en iframe — héberger sur GitHub Pages et référencer l'URL https dans `customDef`
- **Calcul des IDs** : `table_ref = i+1`, `view_id = i*3+1`, sections = `view_id`, `view_id+1`, `view_id+2` — utiliser des compteurs globaux pour `col_id` et `field_id`, pas d'offsets fixes
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
