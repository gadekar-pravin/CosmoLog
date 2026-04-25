# Functional Specification: NASA Space Mission Journal Dashboard

## 1. Document Overview

### 1.1 Project Name

**NASA Space Mission Journal Dashboard**

### 1.2 Purpose

The purpose of this project is to build a demo MCP application using **Prefab** that fetches live NASA space data, stores selected results in a local journal file, and displays the saved and fetched data in an interactive dashboard UI.

The application will demonstrate three required MCP functions:

1. Fetching data from the internet using NASA APIs.
2. Performing CRUD operations on a local file.
3. Rendering a user-facing dashboard using Prefab.

### 1.3 Assignment Goal

The application must show that an AI agent can use all three MCP tools in sequence:

1. Retrieve data from external internet APIs.
2. Save, read, update, or delete data in a local file.
3. Display the results through a Prefab-based UI.

---

## 2. Product Summary

The NASA Space Mission Journal Dashboard allows a user to fetch current NASA astronomy data, save selected items into a local space journal, and view the saved journal entries alongside fresh space-related data in a dashboard.

The dashboard will include:

* Astronomy Picture of the Day hero section.
* Mars rover photo grid.
* Near-Earth object table.
* Local journal entries saved by the user.
* Tag-based organization for saved entries.
* Basic update and delete controls for journal items.

---

## 3. Target Users

### 3.1 Primary User

A student or developer demonstrating an MCP application for an assignment.

### 3.2 Secondary User

An evaluator or instructor reviewing whether the application satisfies the MCP, CRUD, internet/API, and Prefab UI requirements.

---

## 4. Functional Requirements

## 4.1 MCP Server Requirements

The application must expose an MCP server with exactly three main tools:

1. `fetch_space_data`
2. `manage_space_journal`
3. `show_space_dashboard`

Each tool must have a clear responsibility and must be invokable by an AI agent.

---

## 4.2 Function 1: Fetch Space Data

### Tool Name

`fetch_space_data`

### Purpose

Fetch live data from NASA APIs and return normalized data to the agent.

### Requirement Covered

This function satisfies the assignment requirement for a function related to the internet, such as search, fetching a page, or getting API data.

### APIs Used

The tool should use the following NASA APIs:

1. NASA Astronomy Picture of the Day API, also known as APOD.
2. NASA Mars Rover Photos API.
3. NASA Near Earth Object Web Service, also known as NeoWs.

### Inputs

| Field         | Type    | Required | Description                                                   |
| ------------- | ------- | -------: | ------------------------------------------------------------- |
| `date`        | string  |       No | Date for APOD lookup. Defaults to today.                      |
| `rover`       | string  |       No | Mars rover name. Defaults to `curiosity`.                     |
| `sol`         | integer |       No | Martian sol used for rover photos.                            |
| `photo_count` | integer |       No | Number of rover photos to fetch. Defaults to 3.               |
| `neo_days`    | integer |       No | Number of upcoming days to check for NEO data. Defaults to 7. |

### Processing Rules

The function must:

1. Call the APOD API and retrieve the title, date, explanation, media type, URL, and copyright if available.
2. Call the Mars Rover Photos API and retrieve recent photos for the selected rover and sol.
3. Call the NeoWs API and retrieve upcoming near-Earth objects.
4. Normalize all API responses into a predictable JSON structure.
5. Handle NASA APOD responses where the media type is video instead of image.
6. Return error messages when an API call fails, rather than crashing the MCP server.

### Output

The function returns a JSON object containing:

```json
{
  "apod": {
    "title": "string",
    "date": "string",
    "explanation": "string",
    "media_type": "image | video",
    "url": "string",
    "thumbnail_url": "string | null"
  },
  "rover_photos": [
    {
      "id": "string",
      "rover": "string",
      "camera": "string",
      "earth_date": "string",
      "sol": 0,
      "img_src": "string"
    }
  ],
  "near_earth_objects": [
    {
      "id": "string",
      "name": "string",
      "close_approach_date": "string",
      "miss_distance_km": 0,
      "relative_velocity_kph": 0,
      "is_potentially_hazardous": false
    }
  ]
}
```

### Error Handling

The function must handle:

* Invalid API key.
* API rate limits.
* Empty rover photo results.
* APOD video response instead of image response.
* Network failure.
* Invalid or missing API response fields.

---

## 4.3 Function 2: Manage Space Journal

### Tool Name

`manage_space_journal`

### Purpose

Perform CRUD operations on a local JSON file named `space_journal.json`.

### Requirement Covered

This function satisfies the assignment requirement for CRUD operations on a local file.

### Local File

```text
space_journal.json
```

### Supported Operations

The tool must support four operations:

1. Create
2. Read
3. Update
4. Delete

### Inputs

| Field        | Type   |    Required | Description                                     |
| ------------ | ------ | ----------: | ----------------------------------------------- |
| `operation`  | string |         Yes | One of `create`, `read`, `update`, or `delete`. |
| `entry_id`   | string | Conditional | Required for update and delete.                 |
| `payload`    | object | Conditional | Required for create and update.                 |
| `tag_filter` | string |          No | Optional tag used when reading entries.         |

### Data Model

Each journal entry must follow this structure:

```json
{
  "id": "2026-04-25-apod",
  "type": "apod",
  "title": "Astronomy Picture of the Day",
  "date": "2026-04-25",
  "tags": ["mars-week"],
  "notes": "Saved during assignment demo",
  "source_url": "https://example.com/image.jpg",
  "created_at": "2026-04-25T10:30:00+05:30",
  "updated_at": "2026-04-25T10:30:00+05:30"
}
```

### Create Behavior

When `operation` is `create`, the function must:

1. Open or create `space_journal.json`.
2. Add the new journal entry.
3. Generate a unique `id` if one is not provided.
4. Add `created_at` and `updated_at` timestamps.
5. Save the updated file.
6. Return the created entry.

### Read Behavior

When `operation` is `read`, the function must:

1. Open `space_journal.json`.
2. Return all entries if no filter is provided.
3. Return only matching entries if `tag_filter` is provided.
4. Return an empty list if the file does not exist or no entries match.

### Update Behavior

When `operation` is `update`, the function must:

1. Locate the entry by `entry_id`.
2. Update allowed fields such as `tags`, `notes`, or `title`.
3. Refresh the `updated_at` timestamp.
4. Save the updated file.
5. Return the updated entry.

### Delete Behavior

When `operation` is `delete`, the function must:

1. Locate the entry by `entry_id`.
2. Remove the entry from `space_journal.json`.
3. Save the updated file.
4. Return a confirmation response.

### Error Handling

The function must handle:

* Missing local file.
* Invalid JSON file contents.
* Unknown operation.
* Missing `entry_id` for update or delete.
* Entry not found.
* File read/write permission errors.

---

## 4.4 Function 3: Show Space Dashboard

### Tool Name

`show_space_dashboard`

### Purpose

Render a Prefab dashboard UI that displays the fetched NASA data and saved local journal entries.

### Requirement Covered

This function satisfies the assignment requirement that the MCP app communicates back through a UI and uses Prefab to push the UI to a host such as a Chrome plugin, web app, or desktop app.

### Inputs

| Field             | Type   | Required | Description                                            |
| ----------------- | ------ | -------: | ------------------------------------------------------ |
| `space_data`      | object |       No | Data returned from `fetch_space_data`.                 |
| `journal_entries` | array  |       No | Entries returned from `manage_space_journal`.          |
| `tag_filter`      | string |       No | Optional tag used to filter displayed journal entries. |

### UI Components

The Prefab dashboard must include the following sections.

#### 4.4.1 APOD Hero Section

Displays:

* APOD title.
* APOD image or video fallback card.
* APOD date.
* APOD explanation.
* Source link.

#### 4.4.2 Mars Rover Photo Grid

Displays:

* Three recent Curiosity rover photos.
* Rover name.
* Camera name.
* Sol.
* Earth date.

#### 4.4.3 Near-Earth Object Table

Displays:

* Object name.
* Close approach date.
* Miss distance in kilometers.
* Relative velocity in kilometers per hour.
* Hazard status badge.

Hazard badge behavior:

* Show a warning badge when `is_potentially_hazardous` is true.
* Show a safe badge when `is_potentially_hazardous` is false.

#### 4.4.4 Space Journal Section

Displays entries from `space_journal.json`.

Each entry should show:

* Title.
* Type.
* Date.
* Tags.
* Notes.
* Source URL.
* Created and updated timestamps.

#### 4.4.5 Dashboard Stat Tiles

The dashboard should include summary tiles such as:

* Number of journal entries.
* Number of rover photos fetched.
* Number of potentially hazardous near-Earth objects.
* Closest upcoming NEO approach date.
* APOD media type.

### UI Actions

The UI should support or expose controls for:

* Filtering journal entries by tag.
* Deleting a journal entry.
* Updating notes or tags for a journal entry.
* Refreshing the dashboard.

### Output

The function must return a Prefab UI object that can be rendered by the MCP host.

---

## 5. End-to-End User Flow

### 5.1 Primary Demo Flow

The user gives this prompt:

```text
Fetch today’s NASA APOD, 3 recent Curiosity rover photos, and upcoming near-Earth objects. Save the APOD and rover photos into space_journal.json with the tag mars-week. Then read the saved journal entries and display them in a Prefab dashboard with the APOD hero image, rover photo grid, and a near-Earth asteroid table.
```

### Expected Agent Behavior

The agent must:

1. Call `fetch_space_data` to retrieve NASA data.
2. Call `manage_space_journal` with `operation: create` to save the APOD entry.
3. Call `manage_space_journal` with `operation: create` to save rover photo entries.
4. Call `manage_space_journal` with `operation: read` to retrieve entries tagged `mars-week`.
5. Call `show_space_dashboard` to render the Prefab UI.

---

## 6. CRUD Demonstration Flow

To prove full CRUD support, the demo should include a second prompt:

```text
Update the notes for the APOD entry to “favorite image of the week,” delete one rover photo from the journal, then refresh the Prefab dashboard.
```

### Expected Agent Behavior

The agent must:

1. Call `manage_space_journal` with `operation: update` for the APOD entry.
2. Call `manage_space_journal` with `operation: delete` for one rover photo entry.
3. Call `manage_space_journal` with `operation: read` to retrieve updated journal entries.
4. Call `show_space_dashboard` to refresh the Prefab UI.

---

## 7. Non-Functional Requirements

### 7.1 Reliability

The application must handle failed API requests gracefully and show useful fallback messages.

### 7.2 Demo Stability

The application should cache or reuse successful API responses when possible to avoid failures during the live demo.

### 7.3 Performance

The dashboard should load within a reasonable time after the APIs return data. The application should avoid fetching excessive numbers of rover photos or near-Earth objects.

### 7.4 Usability

The UI should be visually clear, easy to understand, and organized into obvious sections.

### 7.5 Maintainability

The MCP tools should be separated by responsibility:

* API fetching logic should not perform file operations.
* File CRUD logic should not render UI.
* Prefab UI rendering should consume already prepared data.

---

## 8. Assumptions

1. The application will run locally.
2. The MCP host supports Prefab-rendered UI output.
3. A NASA API key will be available through an environment variable or configuration file.
4. NASA `DEMO_KEY` may be used for testing, but a personal API key is recommended for the live demo.
5. The local file `space_journal.json` will be stored in the project directory.
6. If APOD returns a video, the UI will display a video card or fallback message instead of an image hero.

---

## 9. Out of Scope

The following features are not required for the assignment:

* User authentication.
* Cloud database storage.
* Multi-user journal support.
* Permanent hosted deployment.
* Advanced image search.
* Real-time streaming updates.
* Mars weather data.

Mars weather is intentionally excluded because the most common NASA Mars weather source is not ideal for a reliable live demo.

---

## 10. Data Storage Specification

### 10.1 File Name

```text
space_journal.json
```

### 10.2 File Structure

```json
{
  "entries": [
    {
      "id": "string",
      "type": "apod | rover_photo",
      "title": "string",
      "date": "string",
      "tags": ["string"],
      "notes": "string",
      "source_url": "string",
      "metadata": {},
      "created_at": "string",
      "updated_at": "string"
    }
  ]
}
```

### 10.3 Entry Types

Supported entry types:

* `apod`
* `rover_photo`

Optional future entry types:

* `neo`
* `article`
* `favorite`

---

## 11. API Response Normalization

The MCP server should not expose raw NASA API responses directly to the UI. Instead, it should normalize the responses into simplified objects.

### 11.1 APOD Object

```json
{
  "title": "string",
  "date": "string",
  "explanation": "string",
  "media_type": "image | video",
  "url": "string",
  "thumbnail_url": "string | null",
  "copyright": "string | null"
}
```

### 11.2 Rover Photo Object

```json
{
  "id": "string",
  "rover": "Curiosity",
  "camera": "NAVCAM",
  "earth_date": "string",
  "sol": 0,
  "img_src": "string"
}
```

### 11.3 Near-Earth Object

```json
{
  "id": "string",
  "name": "string",
  "close_approach_date": "string",
  "miss_distance_km": 0,
  "relative_velocity_kph": 0,
  "estimated_diameter_meters_min": 0,
  "estimated_diameter_meters_max": 0,
  "is_potentially_hazardous": false
}
```

---

## 12. UI Layout Specification

### 12.1 Dashboard Header

Displays:

* App name: NASA Space Mission Journal.
* Last refreshed timestamp.
* Active tag filter.

### 12.2 Top Stat Row

Displays:

1. Journal entries count.
2. Rover photos fetched.
3. Upcoming near-Earth objects count.
4. Potentially hazardous object count.

### 12.3 Main Content Area

The main content area should use a two-column layout where possible.

Left side:

* APOD hero card.
* Rover photo grid.

Right side:

* Journal entries.
* Tag filter.
* Update/delete controls.

### 12.4 Lower Section

Displays:

* Near-Earth object table.

---

## 13. Acceptance Criteria

### 13.1 Internet/API Requirement

The application is accepted if:

* The agent calls `fetch_space_data`.
* The tool retrieves live or cached NASA data.
* The returned data includes APOD, rover photos, and near-Earth object information.

### 13.2 CRUD Requirement

The application is accepted if:

* The agent creates entries in `space_journal.json`.
* The agent reads entries from `space_journal.json`.
* The agent updates at least one entry.
* The agent deletes at least one entry.

### 13.3 Prefab UI Requirement

The application is accepted if:

* The agent calls `show_space_dashboard`.
* The tool returns a Prefab dashboard UI.
* The dashboard displays data from both NASA APIs and the local journal file.

### 13.4 Forced Tool Usage Requirement

The application is accepted if the provided prompt causes the agent to use all three tools:

1. `fetch_space_data`
2. `manage_space_journal`
3. `show_space_dashboard`

---

## 14. Recommended Demo Script

### Step 1: Start MCP Server

Run the local MCP server.

### Step 2: Give the Primary Prompt

```text
Fetch today’s NASA APOD, 3 recent Curiosity rover photos, and upcoming near-Earth objects. Save the APOD and rover photos into space_journal.json with the tag mars-week. Then read the saved journal entries and display them in a Prefab dashboard with the APOD hero image, rover photo grid, and a near-Earth asteroid table.
```

### Step 3: Show Dashboard

Verify that the dashboard shows:

* APOD hero section.
* Three rover photos.
* Journal entries tagged `mars-week`.
* NEO table.
* Dashboard summary stats.

### Step 4: Demonstrate Update and Delete

Give the second prompt:

```text
Update the notes for the APOD entry to “favorite image of the week,” delete one rover photo from the journal, then refresh the Prefab dashboard.
```

### Step 5: Show Updated Dashboard

Verify that:

* The APOD note changed.
* One rover photo was removed from the journal.
* The dashboard reflects the updated file state.

---

## 15. Risks and Mitigations

| Risk                             | Impact                     | Mitigation                                          |
| -------------------------------- | -------------------------- | --------------------------------------------------- |
| NASA API rate limit              | Demo may fail              | Use personal API key or cached fallback response.   |
| APOD returns video               | Hero image may not display | Show video card or fallback to previous APOD image. |
| No rover photos for selected sol | Empty grid                 | Try a known sol or fetch latest available photos.   |
| Invalid local JSON file          | CRUD failure               | Validate and repair file structure when loading.    |
| UI host does not render Prefab   | Demo failure               | Test Prefab rendering before presentation.          |

---