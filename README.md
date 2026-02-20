# Web Test Automation MCP

Agent Python autonome qui pilote Chrome via le Model Context Protocol (MCP) pour executer des tests web en langage naturel. L'agent observe le DOM via Chrome DevTools MCP, decide des actions (navigate, click, type, press, wait) et boucle jusqu'au succes ou la limite d'etapes.

## Fonctionnalites principales

- Pilotage de Chrome via MCP (Chrome DevTools MCP, transport STDIO).
- Boucle autonome observe -> decide -> execute -> retry.
- Observation riche: DOM, console, arbre d'accessibilite, screenshots.
- Gestion robuste des erreurs MCP et des retries.
- Mode verbose optionnel pour debug.
- Artifacts de run (screenshots par step).

## Architecture (vue rapide)

- src/agent: boucle autonome, memoire, policy, retry.
- src/browser: adaptateur DevTools, actions, observation.
- src/llm: client Groq (generation de plan et actions).
- src/mcp_client: JSON-RPC, transport STDIO, session MCP.
- src/ocr: extraction texte image (optionnel).

Voir ARCHITECTURE.md pour le detail complet.

## Pre-requis

- Python 3.10+
- Node.js + npx (pour lancer chrome-devtools-mcp)
- Chrome ou Edge installe
- Cle API Groq (GROQ_API_KEY)

## Installation

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

1. Copier `.env.example` vers `.env`.
2. Definir `GROQ_API_KEY`.
3. Verifier `MCP_SERVER_COMMAND` et `MCP_SERVER_ARGS`.
4. (Optionnel) Definir `CHROME_PATH`, `MAX_STEPS`, `STEP_TIMEOUT_SECONDS`, `VERBOSE`.

## Execution

```powershell
python -m src.main --prompt "Teste le formulaire de creation de compte sur https://exemple.com"
```

## Workflow global

1. CLI recoit le prompt utilisateur.
2. Le LLM (Groq) decide les actions a partir de l'etat courant.
3. Le client MCP appelle Chrome DevTools MCP.
4. L'agent execute l'action, observe, et fait retry si besoin.
5. Rapport final: statut, erreurs, historique et artifacts.

## Bonnes pratiques

- Utiliser un profil navigateur dedie (`--user-data-dir`) pour isoler les sessions.
- Garder `MAX_STEPS` raisonnable pour eviter les boucles.
- Activer `VERBOSE=1` pour diagnostiquer les erreurs MCP/DOM.
- Verifier les outils MCP disponibles si un site ne repond pas.

## Depannage rapide

- MCP ne demarre pas: verifier `MCP_SERVER_COMMAND` et `MCP_SERVER_ARGS`.
- Chrome introuvable: verifier `CHROME_PATH` ou installer Edge/Chrome.
- Echecs LLM: verifier `GROQ_API_KEY` et le modele `GROQ_MODEL`.
- Timeouts: augmenter `STEP_TIMEOUT_SECONDS`.

## Dossiers generes

- artifacts/: screenshots par step.
- .chrome-profile/: profil navigateur isole (si utilise).
