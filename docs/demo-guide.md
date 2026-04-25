# CosmoLog Demo Recording Guide

Step-by-step guide for recording the assignment demo video.

## Assignment Requirements Checklist

Before recording, confirm your demo will cover all four requirements:

- [ ] **Internet data / API**: Agent fetches live data from an external API
- [ ] **CRUD on local file**: Agent performs create/read/update/delete on a local file
- [ ] **UI via Prefab**: Agent renders a Prefab UI dashboard in the browser
- [ ] **Single prompt triggers all 3 tools**: One prompt forces the agent to use all three MCP tools including Prefab UI

## How CosmoLog Maps to Requirements

| Requirement | CosmoLog tool | What to show in demo |
|---|---|---|
| Internet data / API | `fetch_space_data` -- calls NASA APIs (APOD, Mars Rover, NeoWs) | Agent fetches live NASA data and displays results |
| CRUD on local file | `manage_space_journal` -- CRUD on `space_journal.json` | Agent creates and reads journal entries |
| UI via Prefab | `show_space_dashboard` -- renders a Prefab UI dashboard | Dashboard appears in the right panel iframe |
| Single prompt triggers all 3 | System prompt chains: Fetch -> Save -> Display | Use the "full pipeline" prompt (see Scene 3 below) |

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) installed
- Google Cloud account with Vertex AI API enabled
- `gcloud auth application-default login` completed
- (Optional) NASA API key from https://api.nasa.gov -- `DEMO_KEY` works but is rate-limited to 30 req/hr

### Required environment variables

Create a `.env` file from the example:

```
NASA_API_KEY=DEMO_KEY
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=global
GEMINI_MODEL=gemini-3-flash-preview
LOG_LEVEL=INFO
```

Only `GOOGLE_CLOUD_PROJECT` is strictly required (the others have defaults).

## Setup Steps (Before Recording)

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Copy and configure environment:
   ```bash
   cp .env.example .env
   # Edit .env and set GOOGLE_CLOUD_PROJECT to your GCP project ID
   ```

3. Delete any existing journal to start fresh:
   ```bash
   rm -f space_journal.json
   ```

4. Start the agent:
   ```bash
   uv run python agent.py
   ```
   Verify the server starts on `http://localhost:8000`.

5. Open `http://localhost:8000` in your browser and verify the mission console loads -- you should see the starfield background, split layout, and "Awaiting your transmission" placeholder.

6. **Recording setup tips:**
   - Browser at 90% zoom for better fit on screen
   - Hide browser extensions and bookmark bar
   - Clean tab bar (only the CosmoLog tab)
   - Use a screen recorder that captures the browser window

## Demo Script (Scene by Scene)

### Scene 1: Show the App (~15 sec)

**What to show:** The mission console UI in its initial state.

- Point out the **Chat panel** on the left with the orbit animation and "Awaiting your transmission" message
- Point out the **Dashboard panel** on the right with "Your dashboard renders the moment data arrives"
- Mention the four **suggested prompt buttons** at the bottom of the chat panel

**Narrate:** "This is CosmoLog, a NASA Space Mission Journal built as an MCP application with three tools. On the left is the chat interface, and on the right is where the Prefab UI dashboard will render."

---

### Scene 2: Fetch NASA Data -- Internet Requirement (~30 sec)

**Action:** Click the first suggested prompt button: **"Fetch today's APOD and show it on the dashboard"**

This sends: `Fetch today's APOD and show it on the dashboard`

**What to watch for in the chat:**
1. Your message appears in the chat
2. A **Thinking** card expands (agent planning)
3. A **Tool call** card shows `fetch_space_data` with its arguments
4. A **Tool result** card shows the NASA API response
5. A second tool call: `show_space_dashboard`
6. The dashboard renders in the right panel iframe

**Key moment:** The APOD image (or video) rendering live in the dashboard.

**Narrate:** "The agent calls `fetch_space_data`, which hits the NASA API to get today's Astronomy Picture of the Day. Then it calls `show_space_dashboard` to render the Prefab UI dashboard. This demonstrates fetching live data from the internet."

---

### Scene 3: Full Pipeline -- All 3 Tools + Prefab (~45 sec)

> This is the most important scene -- it satisfies the "single prompt triggers all 3 tools" requirement.

**Action:** Click the second suggested prompt button: **"Run full pipeline & log to journal"**

This sends: `Fetch NASA data, save the APOD to my journal, and show the dashboard`

**What to watch for -- three tool calls in sequence:**
1. `fetch_space_data` -- fetches from NASA APIs (internet data)
2. `manage_space_journal` with `operation: "create"` -- saves to local JSON file (CRUD)
3. `show_space_dashboard` -- renders the Prefab UI dashboard

**Key moment:** The dashboard now shows journal entry card(s) with edit/delete buttons.

**Narrate:** "Now I'm triggering all three MCP tools with a single prompt. The agent fetches NASA data from the internet, saves it to a local JSON journal file, and renders the Prefab UI dashboard. This single prompt uses `fetch_space_data` for internet data, `manage_space_journal` for local file CRUD, and `show_space_dashboard` for the Prefab UI -- satisfying all three requirements at once."

---

### Scene 4: Show CRUD Operations (~30 sec)

**Action:** Click the third suggested prompt button: **"Read my space journal"**

This sends: `Show me what's in my space journal`

**What to watch for:**
1. `manage_space_journal` with `operation: "read"`
2. `show_space_dashboard` updates with journal contents

**Narrate:** "The journal supports full CRUD -- we can create, read, update, and delete entries. The data is persisted in a local JSON file called `space_journal.json`."

**Optional bonus:** Click an **Edit** or **Delete** button on a journal entry in the dashboard to show interactive Prefab UI components triggering further tool calls.

---

### Scene 5: Mars + NEOs -- More Internet Data (~30 sec)

**Action:** Click the fourth suggested prompt button: **"Mars rovers + near-Earth objects"**

This sends: `Fetch Mars rover photos and near-Earth objects, save them all, and display everything`

**What to watch for:**
- `fetch_space_data` returns Mars rover photos and NEO data
- `manage_space_journal` saves entries
- `show_space_dashboard` renders rover photo grid and NEO hazard table

**Narrate:** "CosmoLog can fetch multiple NASA data sources -- Mars rover photos and near-Earth object tracking. The dashboard uses Prefab UI components like image grids, tables with hazard badges, and interactive cards."

---

### Scene 6: Wrap-Up (~15 sec)

**What to show:** The final dashboard state with all sections populated (APOD, journal entries, rover photos, NEO table).

**Narrate:** "To summarize: CosmoLog is built with FastMCP for the three MCP tools, Prefab UI for the dashboard components, and a Gemini agent for the conversational interface. A single prompt triggers all three tools -- fetching internet data, performing CRUD on a local file, and rendering the Prefab UI dashboard."

## The Key Prompt

The single prompt that satisfies the assignment's requirement to "show a prompt that forces the Agent to use all 3 tools including Prefab UI":

> **"Fetch NASA data, save the APOD to my journal, and show the dashboard"**

This triggers:
1. `fetch_space_data` -- internet API call to NASA
2. `manage_space_journal` -- CRUD create on `space_journal.json`
3. `show_space_dashboard` -- Prefab UI dashboard render

This is the second suggested prompt button in the UI ("Run full pipeline & log to journal").

## Suggested Narration Points

Key phrases to work into your recording:

- "Three MCP tools: `fetch_space_data`, `manage_space_journal`, `show_space_dashboard`"
- "`fetch_space_data` calls live NASA APIs -- this satisfies the internet/API requirement"
- "`manage_space_journal` does CRUD on `space_journal.json` -- a local file"
- "`show_space_dashboard` uses Prefab UI components to render the dashboard in the browser"
- "A single prompt triggers all three tools in sequence"
- "The agent follows a workflow: fetch data, save to journal, display on dashboard"

## Troubleshooting

| Problem | Fix |
|---|---|
| Agent errors with "Missing GOOGLE_CLOUD_PROJECT" | Check `.env` has `GOOGLE_CLOUD_PROJECT` set to a valid GCP project ID |
| NASA data is slow or returns errors | `DEMO_KEY` allows 30 req/hr. Get a free key at https://api.nasa.gov for higher limits |
| Dashboard doesn't render in the right panel | Check the browser console for errors. Try clicking Reset and re-sending the prompt |
| Journal is cluttered from previous test runs | Delete `space_journal.json` and restart the agent |
| `gcloud` auth errors | Run `gcloud auth application-default login` and restart the agent |
| Port 8000 already in use | Set `PORT=8001` in `.env` or kill the process on 8000 |
