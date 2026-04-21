# 🎨 Générateur de Widgets Grist

Générez automatiquement des applications Grist personnalisées avec custom widgets.

## 🚀 Utilisation

### Via le formulaire web

1. Ouvrez `index.html` dans votre navigateur
2. Remplissez le formulaire
3. Cliquez sur "Générer mon widget"
4. Une issue GitHub est créée automatiquement
5. GitHub Actions génère le `.grist`
6. Téléchargez-le depuis la section Artifacts

### Configuration du formulaire

Dans `index.html`, modifiez ces lignes :

```javascript
const GITHUB_OWNER = 'TON_USERNAME';  // ← Votre username GitHub
const GITHUB_TOKEN = 'ghp_XXXXXXXXXX';  // ← PAT avec scope public_repo
```

**Créer le PAT pour le formulaire :**
1. https://github.com/settings/tokens
2. Generate new token (classic)
3. Scope : ✅ `public_repo` (uniquement)
4. Générer et copier le token

## 📁 Structure du projet

```
.
├── index.html                    # Formulaire web
├── generate.py                   # Générateur Python
├── Document_sans_titre.grist     # Template de base
├── .github/
│   └── workflows/
│       └── generate-widget.yml   # Action automatique
└── README.md
```

## 🔧 Configuration GitHub Actions

### 1. Secret PRIVATE_REPO_TOKEN

Déjà configuré ✅

### 2. Modifier le workflow

Dans `.github/workflows/generate-widget.yml`, ligne 21 :

```yaml
repository: TON_USERNAME/fastc-internal-tools  # ← Change TON_USERNAME
```

### 3. Créer le label

Dans ton repo :
- Issues → Labels → New label
- Name : `widget-generation`
- Color : `#7057ff`
- Create label

## 📦 Ce qui est généré

Chaque `.grist` contient :

- ✅ **Table Projets**
  - nom, description, statut
  - responsable_email
  - colonnes ACL (viewers/editors/deleters)

- ✅ **Table Taches**
  - projet_id (référence)
  - titre, statut, priorité
  - assignee_email
  - colonnes ACL héritées

- ✅ **Row Level Security**
  - Pattern ACL du skill `grist-rls.md`
  - Formules automatiques

- ✅ **Données de démo**
  - 1 projet avec le nom du module
  - 2 tâches d'exemple

## 🎯 Prochaines étapes

- [ ] Ajouter génération du custom widget React
- [ ] Parser plus finement les skills
- [ ] Support multi-tables via formulaire
- [ ] Templates de widgets (liste/kanban/formulaire)

## 📚 Skills utilisés

Les skills du repo `fastc-internal-tools/01-skills-universels/` sont :
- `grist-widget.md` - Patterns React + Grist API
- `grist-rls.md` - Patterns RLS/ACL

Actuellement : chargés mais pas encore utilisés pour générer du code widget.
**TODO :** Parser les skills et générer le widget custom automatiquement.

## 🐛 Debug

Si l'Action échoue :
1. Va sur l'onglet "Actions" du repo
2. Click sur le run qui a échoué
3. Regarde les logs détaillés

Problèmes courants :
- ❌ `PRIVATE_REPO_TOKEN` invalide → Regénérer le PAT
- ❌ Label manquant → Créer le label `widget-generation`
- ❌ Username incorrect dans le workflow → Vérifier ligne 21
