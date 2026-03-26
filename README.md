# Web Test Automation MCP

## What is This Project?

This is an **automated web testing tool** that uses AI (Large Language Models) to generate and execute test cases on websites. You describe what you want to test in natural language, and the system automatically explores the website, creates test cases, runs them, and generates a report.

Think of it like having an intelligent bot that can:
1. Understand what interactive elements exist on a webpage (buttons, forms, links, etc.)
2. Generate realistic test scenarios based on those elements
3. Execute those scenarios step-by-step
4. Record everything that happened (screenshots, logs, results)

## How It Works: The 4-Step Pipeline

The project works in a linear pipeline with 4 stages:

### Step 1: Extract Interactive Elements (Selector Extraction)

**What it does:** Scans the target webpage and identifies all interactive elements (buttons, input fields, links, forms, etc.).

**How:**
1. Fetches the HTML of the webpage
2. Parses the HTML to find every interactive element
3. Generates CSS selectors for each element (a unique way to identify it)
4. Uses AI (Groq LLM) to understand what each element does (search box, login button, etc.)
5. Validates and stabilizes the selectors to ensure they'll work reliably

**Result:** A map of all selectors on the page with metadata (what they do, whether they're clickable, etc.)

**Example:**
- Found: `#search-input` (search box)
- Found: `button[type='submit']` (submit button)
- Found: `a[href='/cart']` (cart link)

### Step 2: Generate Test Cases

**What it does:** Creates realistic test scenarios (test cases) that would test the website's functionality.

**How:**
1. Takes the selector map from Step 1
2. Uses AI (Cerebras LLM) to generate test cases based on the objective
3. Each test case contains a series of steps: "type in search box", "click button", "verify result", etc.
4. AI (Mistral LLM) refines the test cases for quality

**Result:** A structured list of test cases with step-by-step instructions

**Example Test Case:**
```
Test: Search for "mesh routers"
Step 1: Type "mesh routers" in #search-input
Step 2: Click button[type='submit']
Step 3: Wait for results to load
Step 4: Assert that at least one result is visible
```

### Step 3: Execute Test Cases

**What it does:** Actually runs the test cases on the real website using a browser.

**How:**
1. Opens a browser and navigates to the target website
2. For each test case:
   - Takes a screenshot of the page
   - Captures the current state (what elements are visible, console errors, etc.)
   - Asks AI (Groq LLM) what action to take next
   - Executes that action (click, type, scroll, etc.)
   - Observes the result and repeats
3. Handles failures gracefully (retries, waits, error detection)

**Result:** A record of what happened at each step (success/failure, screenshots, errors)

### Step 4: Log & Summarize

**What it does:** Saves all results and generates a summary report.

**How:**
1. Collects execution trace from Step 3
2. Saves:
   - `execution_trace.json` - detailed log of every action
   - `test_cases.json` - the test cases that were generated
   - `selector_map.json` - the map of page elements
   - `summary.json` - high-level results (passed/failed/errors)
   - `terminal_output.log` - console output

**Result:** Complete artifacts saved in `artifacts/runs/run_YYYYMMDD_HHMMSS/`

---

## Quick Start

### Prerequisites

- **Python 3.12+** (or newer)
- **Node.js** (for MCP server)
- **Chrome or Edge browser**
- **API Keys** for LLMs:
  - `GROQ_API_KEY` (required - for Steps 1 and 3)
  - `CEREBRAS_API_KEY` or `MISTRAL_API_KEY` (for Step 2)
  - Optionally: `GEMINI_API_KEY` (for fallbacks)

### Installation

```powershell
# Create virtual environment
python -m venv .venv

# Activate it
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
# Required API Keys
GROQ_API_KEY=your_groq_api_key_here
CEREBRAS_API_KEY=your_cerebras_api_key_here
MISTRAL_API_KEY=your_mistral_api_key_here

# Optional: LLM Model Selection
STEP1_MODEL=llama-3.3-70b-versatile
STEP2_MODEL=zai-glm-4.7
STEP3_MODEL=llama-3.3-70b-versatile

# Optional: Chrome path (auto-detected if not set)
# CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
```

### Running the Tool

**Option 1: With a natural-language prompt**

```powershell
python -m src.main --prompt "Go to YouTube and find the 3 trending videos in the US"
```

The system will:
1. Parse your prompt to extract URL and objective
2. Navigate to the website
3. Extract selectors
4. Generate test cases
5. Execute the test
6. Save results

**Option 2: With explicit URL and objective**

```powershell
python -m src.main --url "https://www.youtube.com" --objective "Find the 3 trending videos"
```

### Understanding the Output

After running, check `artifacts/runs/` for the latest run folder:

```
artifacts/
└── runs/
    └── run_20260326_142530/
        ├── selector_map.json       # Map of all page elements found
        ├── test_cases.json         # Generated test cases
        ├── execution_trace.json    # Detailed execution log
        ├── summary.json            # Pass/fail summary
        └── terminal_output.log     # Console output
```

### Example: Console Output

```
======================================================================
STEP 1: SELECTOR EXTRACTION SUMMARY
======================================================================

✓ Extracted: 42 interactive element(s)
✗ Discarded: 3 element(s)

Elements by type:

  BUTTON (8):
    - search_submit              | search button           | button[type='submit']
    - load_more                  | load more button        | a.load-more

  INPUT (5):
    - search_input               | search query input      | #search-input

  LINK (12):
    - trending_video_1           | first trending link     | a[href*='watch']
    ...

======================================================================
Run completed with status: pass
```

---

## Project Structure

```
web_test_automation_mcp/
├── src/
│   ├── main.py                    # Entry point, CLI argument parsing
│   ├── pipeline/
│   │   ├── runner.py              # Main 4-step pipeline orchestrator
│   │   └── context.py             # Shared context across steps
│   ├── step1_extract/             # Selector extraction
│   │   ├── extractor.py           # Main extraction logic
│   │   ├── selector_refiner.py    # LLM refinement of selectors
│   │   ├── selector_validator.py  # Validation of refined selectors
│   │   └── models.py              # Data models
│   ├── step2_generate/            # Test case generation
│   │   ├── generator.py           # LLM-based test generation
│   │   ├── test_case_refiner.py   # Refinement of test cases
│   │   └── models.py              # Test case models
│   ├── step3_execute/             # Test execution
│   │   ├── executor.py            # Main execution loop
│   │   ├── reasoning_loop.py      # LLM reasoning for next action
│   │   ├── action_dispatcher.py   # Converts LLM decisions to browser actions
│   │   ├── state_observer.py      # Captures page state (screenshots, DOM, etc.)
│   │   └── models.py              # Execution models
│   ├── step4_log/                 # Results logging
│   │   ├── writer.py              # Writes results to JSON
│   │   ├── summarizer.py          # Generates summary report
│   │   └── models.py              # Log models
│   ├── config/                    # Configuration
│   │   ├── settings.py            # Runtime settings
│   │   ├── schemas.py             # Data validation schemas
│   │   └── providers.py           # LLM provider configuration
│   ├── llm/                       # LLM provider clients
│   │   ├── providers.py           # Multi-provider support
│   │   └── base.py                # Base LLM interface
│   └── mcp/                       # Model Context Protocol client
│       ├── client.py              # MCP connection and tool invocation
│       └── tools.py               # Tool result handling
├── tests/
│   ├── unit/                      # Unit tests for each step
│   └── integration/               # End-to-end tests
├── artifacts/                     # Output folder (auto-created)
│   └── runs/                      # Logs from each run
├── pyproject.toml                 # Python project config
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

---

## How Each Step Uses AI

**Step 1 - Element Understanding:**
- AI identifies what each element does (e.g., "this is a search box", "this is a submit button")
- AI determines if a selector is fragile (might break) and suggests stable alternatives

**Step 2 - Test Generation:**
- AI creates realistic test scenarios (e.g., "Search for trending videos")
- AI refines those scenarios to ensure they use valid selectors

**Step 3 - Smart Execution:**
- AI observes the page state and decides what to do next
- AI handles edge cases (element not found → try waiting → then click)
- AI can retry and recover from failures

**Step 4 - Reporting:**
- Summarizes results into human-readable format

---

## Common Scenarios

### Scenario 1: Test a Search Feature

```powershell
python -m src.main --prompt "Go to Google, search for 'Python programming', and verify results"
```

**What happens:**
1. Step 1 extracts the search box, submit button, results area
2. Step 2 generates: "Type query → Click search → Verify results shown"
3. Step 3 executes each step with screenshots
4. Step 4 reports success/failure

### Scenario 2: Test a Login Flow

```powershell
python -m src.main --url "https://example.com/login" --objective "Login with valid credentials and verify dashboard access"
```

### Scenario 3: Test Form Submission

```powershell
python -m src.main --prompt "Fill out the contact form and submit"
```

---

## Troubleshooting

### "Missing GROQ_API_KEY"
- Check your `.env` file has the correct key
- Test: `echo $env:GROQ_API_KEY` in PowerShell

### "Step 1 extraction returned 0 elements"
- The webpage might be dynamic (requires JavaScript to load elements)
- Try a different URL
- Check selector_map.json for rejection reasons

### "LLM rate limit exceeded"
- Wait a moment and try again
- Consider limiting test scope (shorter objective)

### "Browser won't start"
- Verify Chrome is installed
- Set `CHROME_PATH` explicitly if needed

---

## Technical Details

### Selector Strategy
- Prefers ID selectors (most reliable)
- Falls back to attribute selectors (name, aria-label, etc.)
- Uses CSS path as last resort (least reliable)

### Fallback Strategy
- **Step 1**: If LLM fails, uses raw extracted selectors as fallback
- **Step 2**: If Cerebras fails, tries Mistral
- **Step 3**: If Groq fails, tries Mistral for reasoning

### Validation
- All selectors are validated to ensure they map to real elements
- Test cases are validated to use only known selectors
- Execution results are validated before logging

---