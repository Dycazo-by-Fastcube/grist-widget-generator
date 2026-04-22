# Architecture — Grist Widget Generator

## Vue d'ensemble

Ce projet génère automatiquement des documents Grist (`.grist`) et des widgets HTML personnalisés à partir d'un formulaire web. L'utilisateur décrit son besoin, le système produit un fichier Grist prêt à l'emploi avec les bonnes tables et un widget interactif.

## Pipeline de génération

```
Formulaire web  →  Vercel API  →  GitHub Issue  →  Workflow CI  →  .grist + widget.html
(public/)          (api/)         (label: widget-    (.github/        (artifact +
                                  generation)        workflows/)       GitHub Pages)
```

### 1. Formulaire (`public/index.html`)

Formulaire multi-étapes (5 étapes) :
1. Description du besoin
2. Définition des rôles utilisateurs
3. User stories par rôle
4. Permissions par table et par rôle
5. Description des écrans souhaités

L'étape 3 déclenche un appel à `api/analyze-spec` (Claude API) pour identifier automatiquement les tables de données nécessaires.

À la soumission, la spec complète est envoyée à `api/create-issue` sous forme de JSON.

### 2. API Vercel (`api/`)

- **`create-issue.ts`** : reçoit la spec JSON, crée une GitHub Issue avec le label `widget-generation`. Le body de l'issue contient la spec JSON complète.
- **`analyze-spec.ts`** : analyse la description + user stories et retourne la liste des tables Grist à créer (appelé depuis le formulaire à l'étape 3).

### 3. Workflow GitHub Actions (`.github/workflows/generate-widget.yml`)

Déclenché automatiquement à l'ouverture d'une issue avec le label `widget-generation`.

Étapes :
1. Checkout du repo public
2. Checkout du repo privé skills (`Dycazo-by-Fastcube/fastc-internal-tools`)
3. Installation des dépendances Python (`anthropic`)
4. Calcul du slug et de l'URL GitHub Pages
5. Génération du `.grist` et du `widget.html` via `generate.py`
6. Publication du `widget.html` dans `widgets/{slug}/index.html` (GitHub Pages)
7. Upload du `.grist` en artifact GitHub Actions
8. Commentaire sur l'issue avec les liens

### 4. Générateur (`generate.py`)

Reçoit la spec JSON (via fichier temporaire), effectue trois opérations dans l'ordre :

**a) Schéma de colonnes** — appel Claude API (`claude-opus-4-7`, max_tokens=2048)
Génère les colonnes adaptées à chaque table en fonction du besoin exprimé. Produit un JSON `{NomTable: [{colId, type, label, choices}]}`.

**b) Création du `.grist`** — manipulation SQLite directe
Copie un template `.grist`, crée les tables et métadonnées Grist avec les colonnes générées. Le fichier `.grist` est un SQLite avec des tables de métadonnées (`_grist_Tables`, `_grist_Views`, `_grist_Views_section`, etc.).

**c) Génération du widget HTML** — appel Claude API (`claude-opus-4-7`, max_tokens=4096)
Génère un widget HTML/JS autonome utilisant l'API `grist-plugin-api.js`. Si la réponse est tronquée (`stop_reason=max_tokens`), des appels de continuation sont effectués automatiquement (jusqu'à 3 fois).

### 5. Hébergement du widget

Le `widget.html` est committé dans `widgets/{slug}/index.html` et servi par GitHub Pages à l'URL :
```
https://{owner}.github.io/grist-widget-generator/widgets/{slug}/
```
Cette URL est stockée dans le champ `customDef` de la section custom widget du `.grist`.

## Secrets requis

| Secret | Repo | Usage |
|--------|------|-------|
| `ANTHROPIC_API_KEY` | `grist-widget-generator` (public) | Appels Claude API dans `generate.py` |
| `PRIVATE_REPO_TOKEN` | `grist-widget-generator` (public) | Checkout du repo privé skills |
| `GITHUB_TOKEN` | automatique | Création d'issues, push widgets/ |

## Structure des fichiers

```
grist-widget-generator/
├── public/
│   └── index.html          # Formulaire multi-étapes
├── api/
│   ├── create-issue.ts     # Endpoint Vercel : crée l'issue GitHub
│   └── analyze-spec.ts     # Endpoint Vercel : analyse le besoin → tables
├── generate.py             # Générateur principal .grist + widget
├── Document_sans_titre.grist  # Template Grist de base
├── widgets/                # Widgets HTML générés (servis par GitHub Pages)
│   └── {slug}/
│       └── index.html
└── .github/
    └── workflows/
        └── generate-widget.yml
```

## Bonnes pratiques et pièges

### GitHub Actions — transmission de données

Ne jamais interpoler `${{ github.event.issue.body }}` directement dans un script bash. Utiliser `env:` et un fichier temporaire pour préserver l'intégrité du JSON multi-lignes.

```yaml
env:
  ISSUE_BODY: ${{ github.event.issue.body }}
run: |
  printf '%s' "$ISSUE_BODY" > /tmp/spec_body.txt
  python3 generate.py ... "/tmp/spec_body.txt"
```

### Schéma SQLite Grist

- La colonne `customDef` dans `_grist_Views_section` peut être absente des anciens templates → vérifier avec `PRAGMA table_info()` et ajouter avec `ALTER TABLE` si nécessaire
- Les `data:` URI sont bloqués dans les iframes Grist (CSP) → héberger le widget sur GitHub Pages
- Les IDs Grist doivent suivre la formule : `view_id = i * 3 + 1` (3 sections par table)

### Génération de code avec Claude API

- Toujours vérifier `stop_reason == 'max_tokens'` et implémenter la continuation pour éviter les fichiers tronqués
- Faire l'appel de génération des colonnes (`generer_schema_tables`) AVANT la création des tables SQLite
