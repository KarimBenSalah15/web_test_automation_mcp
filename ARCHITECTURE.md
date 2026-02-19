# 📚 Architecture du Système d'Automatisation Web MCP

## 🎯 Vue d'ensemble

Ce système est un **agent autonome Python** qui pilote Chrome via le **Model Context Protocol (MCP)** pour exécuter des tests web automatisés. Contrairement à Playwright/Selenium, il ne génère pas de scripts : il **raisonne et agit directement** via des appels MCP.

## 📁 Structure des dossiers et rôles

```
web_test_automation_mcp/
│
├── src/                          # Code source principal
│   ├── mcp_client/               # 🔌 Client MCP (communication avec serveur)
│   ├── browser/                  # 🌐 Adaptateur navigateur Chrome
│   ├── agent/                    # 🤖 Logique agent autonome
│   ├── llm/                      # 🧠 Intégration LLM (Groq)
│   ├── ocr/                      # 👁️ Vision OCR (extraction texte)
│   └── main.py                   # 🚀 Point d'entrée CLI
│
├── tests/                        # ✅ Tests unitaires
├── artifacts/                    # 📸 Screenshots & logs (généré au runtime)
├── .venv/                        # 🐍 Environnement virtuel Python
├── .env                          # ⚙️ Configuration (clés API, ports)
├── requirements.txt              # 📦 Dépendances Python
└── README.md                     # 📖 Documentation
```

---

## 🔍 Détail de chaque dossier

### 📂 `src/mcp_client/` - Client MCP (Protocole de communication)

**Rôle** : Établir et gérer la connexion avec le serveur MCP Chrome DevTools.

#### Fichiers :
- **`jsonrpc.py`** : Implémente le protocole JSON-RPC 2.0
  - Construit les requêtes avec IDs uniques
  - Parse les réponses et gère les erreurs
  - Distingue réponses (avec `id`) et notifications (sans `id`)

- **`transport.py`** : Gestion du transport STDIO
  - Lance le serveur MCP en subprocess (`npx -y chrome-devtools-mcp@latest`)
  - Envoie/reçoit des messages JSON via stdin/stdout
  - Gère la terminaison propre du subprocess

- **`session.py`** : Session MCP haut niveau
  - Initialisation handshake (`initialize`)
  - Liste des outils disponibles (`tools/list`)
  - Appel d'outils (`tools/call`)
  - Boucle asynchrone de lecture des messages

**Flux** :
```
Python Agent → JSON-RPC Request → STDIO → MCP Server (npx) → Chrome DevTools → Browser
                                    ↓
                              JSON Response
```

---

### 📂 `src/browser/` - Adaptateur navigateur

**Rôle** : Encapsuler les appels MCP spécifiques au navigateur Chrome.

#### Fichiers :
- **`devtools_adapter.py`** : API haut niveau pour piloter Chrome
  - `open_url(url)` : Ouvre une page
  - `query_dom(selector)` : Inspecte le DOM
  - `click(selector)` : Clique sur un élément
  - `type_text(selector, text)` : Remplit un champ
  - `wait_for(event)` : Attend un événement
  - `read_console()` : Lit les logs console
  - `accessibility_tree()` : Récupère l'arbre d'accessibilité
  - `screenshot(path)` : Capture d'écran

- **`actions.py`** : Structures de données pour les actions
  - `BrowserAction` : Définit une action (type, sélecteur, valeur, URL)
  - `ActionResult` : Résultat d'exécution (succès, message, données brutes)

- **`observe.py`** : Observations du navigateur
  - `Observation` : Agrège DOM, console, accessibility, OCR
  - `has_errors()` : Détecte les erreurs console

**Abstraction** : Le reste du code ne voit que des méthodes Python simples, pas les détails MCP/JSON-RPC.

---

### 📂 `src/agent/` - Agent autonome (cœur logique)

**Rôle** : Boucle autonome `observe → act → learn → retry`.

#### Fichiers :
- **`loop.py`** : Boucle d'exécution principale
  - `run(prompt, plan)` : Exécute un plan de test
  - Pour chaque étape :
    1. **Act** : Exécute l'action (open, click, type, etc.)
    2. **Observe** : Capture screenshot + OCR + DOM + console
    3. **Learn** : Détecte erreurs/succès
    4. **Retry** : Retente si échec (max 2 fois par étape)
  - Limite globale : `MAX_STEPS` (défaut 20)

- **`planner.py`** : Génère le plan de test via LLM
  - Appelle Groq LLM avec le prompt utilisateur
  - Reçoit un plan structuré JSON : `{objective, success_criteria, steps[]}`

- **`memory.py`** : Mémoire d'exécution
  - Stocke le prompt, le plan, l'historique des actions
  - Trace les erreurs et le statut final

- **`retry.py`** : Politique de retry
  - `should_retry(attempt, max, has_error)` : Décide si on retente

- **`policy.py`** : Conversion plan → actions
  - `to_browser_action(step)` : Transforme un step JSON en `BrowserAction`

**Flux autonome** :
```
Prompt utilisateur
    ↓
LLM génère plan JSON
    ↓
Pour chaque step:
    Execute action → Screenshot+OCR → Détecte erreurs → Retry si besoin
    ↓
Rapport final (succès/échec)
```

---

### 📂 `src/llm/` - Intégration LLM (Groq)

**Rôle** : Générer des test cases structurés depuis un prompt en langage naturel.

#### Fichiers :
- **`groq_client.py`** : Client API Groq Cloud
  - `generate_test_plan(prompt)` : Envoie le prompt au LLM
  - Gère le retry (3 tentatives avec backoff exponentiel)
  - Fallback si `response_format: json_object` échoue (400)
  - Parse le JSON retourné (ou l'extrait via regex si nécessaire)

**Exemple de plan généré** :
```json
{
  "objective": "Tester le formulaire de connexion",
  "success_criteria": ["Redirection vers dashboard", "Pas d'erreur console"],
  "steps": [
    {"action": "open", "url": "https://example.com/login"},
    {"action": "type", "selector": "#email", "value": "test@example.com"},
    {"action": "type", "selector": "#password", "value": "password123"},
    {"action": "click", "selector": "button[type=submit]"},
    {"action": "wait", "wait_event": "navigation"}
  ]
}
```

---

### 📂 `src/ocr/` - Vision OCR (extraction texte depuis images)

**Rôle** : Compléter l'observation DOM avec du texte extrait visuellement.

#### Fichiers :
- **`engine.py`** : Wrapper EasyOCR
  - `extract_text_from_image(path)` : Extrait texte d'une image
  - Cache le lecteur OCR (lent à initialiser)
  - Support français et anglais

- **`preprocess.py`** : Prétraitement OpenCV
  - Conversion niveaux de gris
  - Égalisation histogramme
  - Seuillage (threshold) pour améliorer précision OCR

**Cas d'usage** : Éléments canvas, images, texte stylisé non accessible via DOM.

---

### 📂 `src/main.py` - Point d'entrée CLI

**Rôle** : Orchestrer le flux complet.

#### Étapes :
1. **Parse arguments** : `--prompt "ton objectif de test"`
2. **Charge config** : `.env` (clés API, chemins Chrome, ports)
3. **Démarre session MCP** : Lance serveur Chrome DevTools MCP
4. **Appelle planner LLM** : Génère le plan de test
5. **Exécute boucle agent** : `loop.run(prompt, plan)`
6. **Affiche rapport** : Succès/échec, nombre d'actions, erreurs

**Variables d'environnement importantes** :
```bash
GROQ_API_KEY=gsk_...         # Clé API Groq Cloud
GROQ_MODEL=llama-3.3-70b-versatile
MCP_SERVER_COMMAND=npx       # Commande pour lancer serveur MCP
MCP_SERVER_ARGS=-y chrome-devtools-mcp@latest
MAX_STEPS=20                 # Limite de sécurité
STEP_TIMEOUT_SECONDS=20      # Timeout par action
```

---

## 🔄 Workflow complet (de bout en bout)

```
1. Utilisateur lance :
   python -m src.main --prompt "Teste le formulaire de contact sur example.com"

2. main.py charge .env et démarre MCP session
   → Lance subprocess: npx -y chrome-devtools-mcp@latest
   → Connexion STDIO établie

3. Planner LLM (Groq) génère plan
   → API Groq : prompt → JSON structuré
   → Plan: {objective, success_criteria, steps[]}

4. Agent loop démarre
   Pour chaque step:
     a) Execute action (open, click, type...)
        → Appel MCP → Chrome DevTools → Browser
     b) Capture screenshot → OCR extraction
     c) Lit console + DOM + accessibility tree
     d) Détecte erreurs → Decide retry

5. Rapport final
   → Affiche: succès, historique, erreurs
   → Fichiers artifacts/*.png générés
```

---

## 🚀 Comment lancer la pipeline

### Option 1 : Script batch (Windows)
```cmd
run_agent.bat "Teste le formulaire de contact sur https://example.com"
```

### Option 2 : Commande directe
```powershell
# 1. Ouvrir PowerShell dans le dossier projet

# 2. Activer venv
.venv\Scripts\activate

# 3. Configurer Node.js PATH
$env:Path = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.13.1-win-x64;$env:Path"

# 4. Lancer agent
python -m src.main --prompt "Ouvre https://example.com et vérifie que le titre contient Example"
```

---

## 🛠️ Dépannage rapide

| Problème | Solution |
|----------|----------|
| `npx` introuvable | Relancer terminal OU configurer PATH manuellement |
| Erreur GROQ 400 | Vérifier clé API + modèle disponible sur console.groq.com |
| OCR lent | Normal 1ère fois (télécharge modèles). Ensuite mis en cache |
| MCP timeout | Augmenter `STEP_TIMEOUT_SECONDS` dans .env |

---

## 📊 Fichiers générés

- `artifacts/step_0.png`, `step_1.png`... : Screenshots de chaque étape
- `.chrome-profile/` : Profil Chrome isolé (cookies, cache)

---

Cette architecture sépare clairement **communication** (mcp_client), **actions** (browser), **intelligence** (agent + llm), et **vision** (ocr) pour une maintenabilité optimale.
