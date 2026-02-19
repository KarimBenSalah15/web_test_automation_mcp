# Web Test Automation MCP

Agent Python autonome pour piloter Chrome via un serveur MCP Chrome DevTools.

## 1) Installation

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2) Lancer Chrome avec remote debugging

```powershell
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=".chrome-profile"
```

## 3) Configurer l’environnement

1. Copier `.env.example` en `.env`
2. Définir `GROQ_API_KEY`
3. Vérifier les paramètres `MCP_SERVER_COMMAND` et `MCP_SERVER_ARGS`

## 4) Lancer l’agent

```powershell
python -m src.main --prompt "Teste le formulaire de création de compte sur https://exemple.com"
```

## Workflow général

1. Le prompt utilisateur est reçu par la CLI.
2. Le planner LLM (Groq) génère des test cases structurés.
3. Le client MCP se connecte au serveur Chrome DevTools MCP.
4. L’agent boucle `observe -> act -> learn -> retry` jusqu’au succès, ou arrêt selon limite.
5. Le rapport final résume actions, validations, erreurs console et statut.

## Bonnes pratiques

- Utiliser un profil Chrome dédié (`--user-data-dir`) pour isoler les sessions.
- Garder `MAX_STEPS` raisonnable pour éviter les boucles infinies.
- Journaliser systématiquement les événements MCP et les erreurs console.
- Utiliser l’OCR pour compléter l’observation visuelle quand le DOM est insuffisant.

## Dépannage rapide

- Si la connexion MCP échoue, vérifier que le serveur MCP démarre via `MCP_SERVER_COMMAND` + `MCP_SERVER_ARGS`.
- Si Chrome n’est pas détecté, valider `CHROME_PATH` et le port `9222`.
- Si le planner LLM échoue, contrôler `GROQ_API_KEY` et `GROQ_MODEL`.
