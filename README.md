# Web Test Automation MCP

Agent Python autonome qui pilote un navigateur via le Model Context Protocol (MCP) et Chrome DevTools MCP pour executer des tests web en langage naturel.

## Fonctionnalites implementees

- Pilotage navigateur via MCP avec transport STDIO.
- Boucle autonome dynamique: observer -> decider (LLM) -> executer -> retry.
- Decisions d'action en temps reel par Groq (`navigate`, `click`, `type`, `press`, `wait`, `query`, `done`).
- Observation a chaque step: screenshot, snapshot DOM/accessibilite, logs console.
- Heuristiques de robustesse:
	- retry par step,
	- detection d'erreurs MCP et metier,
	- fallback intelligent sur `wait` en cas de timeout,
	- detection DOM inchange (signal fail-fast pour l'LLM).
- Fallbacks d'interaction UI (script DOM puis resolution UID MCP pour `click`/`type`).
- Tracking des outils MCP utilises par action.
- Nettoyage de session en fin d'execution (fermeture des pages ouvertes).
- Artifacts de run: screenshots dans `artifacts/`.

## Structure actuelle

- `src/main.py`: point d'entree CLI et orchestration.
- `src/agent/`: boucle agent, memoire, conversion action, retry utilitaire.
- `src/browser/`: adaptateur DevTools, actions, observation, diff DOM.
- `src/llm/`: client Groq (plan JSON + decision prochaine action).
- `src/mcp_client/`: JSON-RPC, transport STDIO, session MCP.
- `tests/`: tests unitaires (retry).

## Pre-requis

- Python 3.12.x
- Node.js + `npx`
- Chrome ou Edge installe
- Cle API Groq (`GROQ_API_KEY`)

## Installation

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

Variables principales:

- `GROQ_API_KEY` (obligatoire)
- `GROQ_MODEL` (optionnel)
- `MCP_SERVER_COMMAND` (defaut: `npx`)
- `MCP_SERVER_ARGS` (defaut: `-y chrome-devtools-mcp@latest`)
- `CHROME_PATH` (optionnel)
- `MAX_STEPS` (defaut: `20`)
- `STEP_TIMEOUT_SECONDS` (defaut: `30`)
- `VERBOSE` (`1/true` pour logs detailles)

## Execution

```powershell
python -m src.main --prompt "Teste le formulaire de creation de compte sur https://example.com"
```

## Sortie

- Resume final en console: succes/echec, nombre d'etapes, derniere erreur.
- Details complets en mode verbose.
- Screenshots par step dans `artifacts/`.
