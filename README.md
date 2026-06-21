# MAYA AI Assistant

Welcome to the MAYA project! MAYA is a powerful, extensible AI assistant equipped with a collection of specialized Python agents. It is designed to perform a wide variety of tasks including web browsing, file management, fetching weather and news, and managing projects and todos. 

It now also features a fully-integrated **Voice Orchestrator** for hands-free voice interaction, allowing you to wake the assistant, issue commands, and receive spoken responses.

## Table of Contents
- [Features](#features)
- [Project Structure](#project-structure)
- [Getting Started (Installation)](#getting-started)
- [Voice Interaction](#voice-interaction)
- [Agent Architecture & Customization](#agent-architecture--customization)
- [Detailed Agent Notes](#detailed-agent-notes)

## Features

- **Multi-Agent System:** Specialized agents for Gmail, YouTube, News, Weather, Files, Memory, and more.
- **Voice Orchestration:** Wake-word detection, continuous listening, and text-to-speech feedback with interruption support.
- **Dynamic Registry:** Automatically discover and register new agents using `build_registry.py`.
- **Long-Term Memory:** Persistent context tracking and conversational memory.

---

## Project Structure

```text
c:\PROGRAMMING\MAYA\
├── agents/                      # Directory containing all agent modules
│   ├── browser_agent.py         # DuckDuckGo search and webpage retrieval
│   ├── file_agent.py            # File system and document access
│   ├── gmail_agent.py           # Gmail retrieval and search
│   ├── memory_agent.py          # Long-term memory management
│   ├── news_agent.py            # News retrieval using NewsAPI
│   ├── notes_generator_agent.py # Notes and presentation generation
│   ├── project_tracker_agent.py # Project, milestone, and task tracking
│   ├── todo_agent.py            # Persistent todo management
│   ├── weather_agent.py         # Weather retrieval using Open-Meteo
│   └── youtube_agent.py         # YouTube search and playback
├── brain/                       # Core system logic and processing
├── voice/                       # Voice interaction components (Orchestrator, STT, TTS)
├── memory/                      # Memory management logic
├── system/                      # Generated system registry and docs (via build_registry.py)
├── data/                        # Directory for local data storage
├── generated_notes/             # Directory where generated notes are saved
├── tests/                       # Unit and integration tests
├── build_registry.py            # Script to scan agents and generate system docs/registry
├── requirements.txt             # Python dependencies
├── .env                         # Environment variables configuration (API Keys)
├── credentials.json             # Google/API credentials
└── token.json                   # Authentication tokens
```

---

## Getting Started

### 1. Install Dependencies
Ensure you have Python 3.9+ installed. Install the required packages via `pip`:
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
You need to provide your API keys for the agents to function properly. 
Create or edit the `.env` file in the root directory and add the necessary credentials (e.g., LLM keys, NewsAPI, Google credentials).

If using Google APIs (like Gmail or YouTube), ensure `credentials.json` and `token.json` are properly configured in the root directory.

### 3. Build the Agent Registry
Whenever you add or modify an agent, you should update the internal registry:
```bash
python build_registry.py
```

---

## Voice Interaction

MAYA includes a powerful voice orchestrator that ties wake word detection, Speech-to-Text (STT), the core Brain, filler sounds, and Text-to-Speech (TTS) into one continuous loop.

To start the voice orchestrator:
```bash
python voice/voice_orchestrator.py
```

**Flow per turn:**
1. Wait for wake word.
2. Speak acknowledgment.
3. Capture command (Speech-to-Text).
4. Start filler voice ("Thinking...") while processing.
5. Send command to the Brain.
6. Speak the final response (Text-to-Speech).
7. If in continuous conversation mode, skip the wake word for the next turn.

---

## Agent Architecture & Customization

All agents in this repository follow a standardized plugin architecture. They act as "tools" that accept a JSON-compatible dictionary as input and return a JSON-compatible dictionary as output. 

The public entry point for every agent is the `execute(request_json: dict) -> dict` function.

### Input JSON Format
To give input to any agent, you must provide a JSON object (or dictionary) that contains an `action` string and a `parameters` object matching the required parameters for that action.
```json
{
  "action": "action_name_here",
  "parameters": {
    "param1": "value1",
    "param2": "value2"
  }
}
```

### Output JSON Format
Agents will typically return a success or error envelope:
```json
{
  "status": "success",
  "action": "action_name_here",
  "data": { ... }
}
```

---

## Detailed Agent Notes

Below is a detailed breakdown of each agent, its purpose, and the actions it supports along with their required parameters.

### 1. Browser Agent (`browser_agent.py`)
**Description:** DuckDuckGo search and webpage retrieval plugin.
**Supported Actions:**
- `web_search`: Requires `query`
- `multi_search`: Requires `queries`
- `fetch_page`: Requires `url`
- `fetch_multiple_pages`: Requires `urls`
- `extract_text`: Requires `url`
- `extract_links`: Requires `url`
- `extract_images`: Requires `url`
- `get_page_metadata`: Requires `url`
- `crawl_website`: Requires `url`
- `check_url`: Requires `url`
- `research_bundle`: Requires `queries`
- `get_raw_html`: Requires `url`

### 2. File Agent (`file_agent.py`)
**Description:** File system and document access plugin.
**Supported Actions:**
- `list_directory`: Requires `path`
- `list_directory_recursive`: Requires `path`
- `search_files`: Requires `path`, `pattern`
- `get_file_info`: Requires `path`
- `read_text_file`: Requires `path`
- `read_pdf`: Requires `path`
- `read_excel`: Requires `path`
- `read_word`: Requires `path`
- `read_powerpoint`: Requires `path`
- `read_multiple_files`: Requires `paths`
- `get_folder_tree`: Requires `path`
- `file_exists`: Requires `path`
- `directory_exists`: Requires `path`
- `get_supported_files`: *No required parameters*
- `get_recent_files`: Requires `path`
- `read_folder_contents`: Requires `path`

### 3. Gmail Agent (`gmail_agent.py`)
**Description:** Gmail retrieval and search plugin.
**Supported Actions:**
- `count_emails`: Requires `query`
- `get_attachments`: *No required parameters*
- `get_drafts`: *No required parameters*
- `get_email_by_id`: Requires `message_id`
- `get_important_emails`: *No required parameters*
- `get_latest_emails`: *No required parameters*
- `get_sent_emails`: *No required parameters*
- `get_starred_emails`: *No required parameters*
- `get_unread_emails`: *No required parameters*
- `search_date_range`: Requires `start_date`, `end_date`
- `search_gmail_query`: Requires `query`
- `search_sender`: Requires `sender`
- `search_subject`: Requires `subject`

### 4. News Agent (`news_agent.py`)
**Description:** News retrieval plugin using NewsAPI.
**Supported Actions:**
- `get_category_news`: Requires `category`
- `get_latest_news`: *No required parameters*
- `get_source_news`: Requires `source`
- `get_sources`: *No required parameters*
- `search_combined`: *No required parameters*
- `search_date_range`: Requires `query`
- `search_multiple_queries`: Requires `queries`
- `search_multiple_topics`: Requires `topics`
- `search_news`: Requires `query`
- `top_headlines`: *No required parameters*

### 5. Notes Generator Agent (`notes_generator_agent.py`)
**Description:** Generates structured notes, presentations, and reports.
**Supported Actions:**
- `generate_notes`: Requires `topic`
- `generate_exam_notes`: Requires `topic`
- `generate_detailed_notes`: Requires `topic`
- `generate_short_notes`: Requires `topic`
- `generate_presentation`: Requires `topic`
- `generate_report`: Requires `topic`
- `generate_from_structure`: Requires `topic`, `structure`
- `generate_from_prompt`: Requires `prompt`
- `generate_from_file`: *No required parameters*

### 6. Project Tracker Agent (`project_tracker_agent.py`)
**Description:** Manages projects, notes, todos, milestones, meetings, and risks.
**Supported Actions:**
- `create_project`: Requires `project_name`
- `update_project`: Requires `project_id`
- `delete_project`: Requires `project_id`
- `get_project`: Requires `project_id`
- `list_projects`: *No required parameters*
- `search_projects`: Requires `query`
- `add_note`: Requires `project_id`, `title`
- `update_note`: Requires `project_id`, `note_id`
- `delete_note`: Requires `project_id`, `note_id`
- `list_notes`: Requires `project_id`
- `add_todo`: Requires `project_id`, `title`
- `update_todo`: Requires `project_id`, `todo_id`
- `complete_todo`: Requires `project_id`, `todo_id`
- `delete_todo`: Requires `project_id`, `todo_id`
- `list_todos`: Requires `project_id`
- `add_milestone`: Requires `project_id`, `title`
- `update_milestone`: Requires `project_id`, `milestone_id`
- `complete_milestone`: Requires `project_id`, `milestone_id`
- `list_milestones`: Requires `project_id`
- `add_meeting`: Requires `project_id`, `title`
- `update_meeting`: Requires `project_id`, `meeting_id`
- `delete_meeting`: Requires `project_id`, `meeting_id`
- `list_meetings`: Requires `project_id`
- `add_decision`: Requires `project_id`, `title`
- `list_decisions`: Requires `project_id`
- `add_risk`: Requires `project_id`, `title`
- `update_risk`: Requires `project_id`, `risk_id`
- `close_risk`: Requires `project_id`, `risk_id`
- `list_risks`: Requires `project_id`
- `add_link`: Requires `project_id`, `url`
- `remove_link`: Requires `project_id`, `link_id`
- `list_links`: Requires `project_id`
- `add_file_reference`: Requires `project_id`, `path`
- `remove_file_reference`: Requires `project_id`, `file_id`
- `list_files`: Requires `project_id`
- `add_progress_update`: Requires `project_id`, `content`
- `list_progress_updates`: Requires `project_id`
- `get_project_dashboard`: Requires `project_id`
- `bulk_add_todos`: Requires `project_id`, `todos`
- `bulk_complete_todos`: Requires `project_id`, `todo_ids`
- `bulk_add_notes`: Requires `project_id`, `notes`
- `bulk_add_files`: Requires `project_id`, `files`

### 7. Todo Agent (`todo_agent.py`)
**Description:** Persistent todo management plugin.
**Supported Actions:**
- `add_todo`: Requires `title`
- `update_todo`: Requires `id`
- `complete_todo`: Requires `id`
- `reopen_todo`: Requires `id`
- `delete_todo`: Requires `id`
- `get_todo`: Requires `id`
- `list_all_todos`: *No required parameters*
- `list_pending_todos`: *No required parameters*
- `list_completed_todos`: *No required parameters*
- `search_todos`: Requires `query`
- `filter_by_tag`: Requires `tag`
- `clear_completed`: *No required parameters*
- `get_stats`: *No required parameters*
- `bulk_add`: Requires `todos`
- `bulk_complete`: Requires `ids`
- `bulk_delete`: Requires `ids`

### 8. Weather Agent (`weather_agent.py`)
**Description:** Weather retrieval plugin using Open-Meteo API.
**Supported Actions:**
- `current_weather`: Requires `location`
- `weather_today`: Requires `location`
- `hourly_forecast`: Requires `location`
- `daily_forecast`: Requires `location`
- `weather_tomorrow`: Requires `location`
- `weather_next_days`: Requires `location`
- `weather_multiple_locations`: Requires `locations`
- `compare_locations`: Requires `locations`
- `search_location`: Requires `location`
- `weather_by_coordinates`: Requires `latitude`, `longitude`
- `weather_bulk_request`: Requires `requests`

### 9. YouTube Agent (`youtube_agent.py`)
**Description:** YouTube search and playback plugin.
**Supported Actions:**
- `search_videos`: Requires `query`
- `search_multiple`: Requires `queries`
- `get_video_details`: *No required parameters*
- `play_video`: *No required parameters*
- `search_and_play`: Requires `query`
- `open_channel`: Requires `channel_url`
- `get_channel_videos`: Requires `channel_url`
- `get_trending`: *No required parameters*
- `open_playlist`: Requires `playlist_url`
- `get_playlist_videos`: Requires `playlist_url`
- `open_url`: Requires `url`
- `search_bundle`: Requires `queries`

### 10. Memory Agent (`memory_agent.py`)
**Description:** Long-term memory management — store, search, and retrieve memories.
**Supported Actions:**
- `store_memory`: Requires `category`, `content`
- `retrieve_memory`: *No required parameters*
- `search_memory`: Requires `query`
- `archive_chat`: *No required parameters*
- `create_summary`: *No required parameters*
- `update_memory`: Requires `memory_id`
- `delete_memory`: Requires `memory_id`
- `get_status`: *No required parameters*
