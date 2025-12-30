# System Architecture - Cantril Ladder Quality of Life Measurement Platform

## 1. High-Level System Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        PH["🏥 Doctor Portal<br/>HTML/CSS/JS"]
        PP["👤 Patient Portal<br/>HTML/CSS/JS"]
    end
    
    subgraph "Web Server"
        WS["Django Web Server<br/>0.0.0.0:8000"]
    end
    
    subgraph "Application Layer"
        VI["Views & URLs<br/>Routing Logic"]
        AUTH["Authentication<br/>Session Management"]
        FORMS["Forms & Validation"]
    end
    
    subgraph "Business Logic Layer"
        QES["Question Manager<br/>Survey Creator"]
        RESP["Response Handler<br/>Data Processor"]
        ANAL["Analytics Engine<br/>Report Generator"]
    end
    
    subgraph "Data Layer"
        DB[(PostgreSQL/SQLite<br/>Django ORM)]
        JSON["JSON Files<br/>ankieta_pytania.json<br/>surveys/*.json"]
    end
    
    subgraph "External Services"
        N8N["🔗 n8n Webhook<br/>http://localhost:5678"]
        MAIL["📧 Email Service"]
    end
    
    subgraph "Storage"
        AUDIO["📁 Audio Files<br/>audio_answers/"]
        OUTBOX["📦 Outbox<br/>outbox/"]
    end
    
    PH -->|Create/Edit Surveys| WS
    PP -->|Answer Questions| WS
    WS -->|Route| VI
    VI -->|Authenticate| AUTH
    VI -->|Process| FORMS
    FORMS -->|Manage| QES
    FORMS -->|Handle| RESP
    RESP -->|Generate| ANAL
    
    QES -->|Save| DB
    QES -->|Backup| JSON
    RESP -->|Store| DB
    RESP -->|Save Audio| AUDIO
    RESP -->|Archive| OUTBOX
    
    OUTBOX -->|POST| N8N
    N8N -->|Process| MAIL
    ANAL -->|Query| DB
    
    style PH fill:#4A90E2,stroke:#2E5C8A,stroke-width:2px,color:#fff
    style PP fill:#7ED321,stroke:#5AA816,stroke-width:2px,color:#fff
    style WS fill:#F5A623,stroke:#C17F1A,stroke-width:2px,color:#fff
    style DB fill:#BD10E0,stroke:#9012FE,stroke-width:2px,color:#fff
    style N8N fill:#FF6B6B,stroke:#C92A2A,stroke-width:2px,color:#fff
```

## 2. Detailed Component Flow

```mermaid
graph LR
    subgraph "Patient Journey"
        P1["1️⃣ Enter PESEL"] --> P2["2️⃣ Choose Survey"]
        P2 --> P3["3️⃣ Answer Questions"]
        P3 --> P4["4️⃣ Submit Responses"]
        P4 --> P5["5️⃣ View Summary"]
    end
    
    subgraph "Doctor Workflow"
        D1["🔐 Login"] --> D2["📋 Panel Home"]
        D2 --> D3["✏️ Create/Edit Surveys"]
        D2 --> D4["📊 View Results"]
        D2 --> D5["👥 View Patient History"]
        D4 --> D6["📈 Analytics"]
    end
    
    subgraph "Backend Processing"
        B1["Save to Database"] --> B2["Create JSON Backup"]
        B2 --> B3["Generate Outbox JSON"]
        B3 --> B4["POST to n8n Webhook"]
        B4 --> B5["Archive Results"]
    end
    
    P4 -->|Process| B1
    D3 -->|Save| B1
```

## 3. Data Flow Architecture

```mermaid
graph TD
    subgraph "Survey Creation Flow"
        SC1["Admin Input<br/>Title, Design, Questions"] -->|POST /generator/| SC2["manage_questions View"]
        SC2 -->|Validate| SC3["Form Validation"]
        SC3 -->|Create| SC4["Survey Model<br/>UUID Primary Key"]
        SC4 -->|Create| SC5["Question Model<br/>Multiple Records"]
        SC5 -->|Serialize| SC6["ankieta_pytania.json"]
        SC6 -->|Backup| SC7["surveys/UUID.json"]
    end
    
    subgraph "Survey Response Flow"
        SR1["Patient Answer<br/>PESEL + Responses"] -->|POST /ankieta/question/| SR2["ankieta_cantril_question View"]
        SR2 -->|Store| SR3["Session['answers']"]
        SR3 -->|Submit| SR4["PatientResponse Model"]
        SR4 -->|Create| SR5["Multiple Response Records<br/>per Question"]
        SR5 -->|Generate| SR6["Outbox JSON<br/>survey_id_patient_id.json"]
        SR6 -->|Webhook| SR7["n8n Processing"]
    end
    
    subgraph "Analytics Flow"
        A1["Doctor Query<br/>GET /panel/results/"] -->|Filter| A2["PatientResponse Query"]
        A2 -->|Aggregate| A3["Count, Group By"]
        A3 -->|Calculate| A4["Statistics<br/>Avg, Min, Max"]
        A4 -->|Render| A5["HTML Report<br/>Charts"]
    end
```

## 4. Request/Response Cycle

```mermaid
sequenceDiagram
    participant User as User (Browser)
    participant Django as Django Views
    participant DB as Database
    participant JSON as JSON Files
    participant n8n as n8n Webhook
    
    User->>Django: POST /generator/ (Create Survey)
    Django->>Django: Validate Form Data
    Django->>DB: Create Survey Record
    Django->>DB: Create Question Records
    Django->>JSON: Write ankieta_pytania.json
    Django->>JSON: Write surveys/UUID.json
    Django->>User: Redirect + Success Message
    
    User->>Django: POST /ankieta/question/ (Answer)
    Django->>Django: Process Response
    Django->>DB: Create PatientResponse
    activate DB
    DB-->>Django: Response Saved
    deactivate DB
    Django->>JSON: Generate Outbox JSON
    Django->>n8n: POST webhook/UUID
    n8n->>n8n: Process & Archive
    Django->>User: Redirect to Next Question
    
    User->>Django: GET /panel/results/ (View Analytics)
    Django->>DB: Query PatientResponse
    activate DB
    DB-->>Django: Return Results
    deactivate DB
    Django->>Django: Aggregate & Calculate
    Django->>User: HTML Report
```

## 5. File Structure & Storage

```
/home/wiktor-kowalczyk/cantrilladder/
│
├── Cantril/                          # Django Project Root
│   ├── manage.py                     # Django Management
│   ├── requirements.txt              # Dependencies
│   ├── db.sqlite3                    # SQLite Database
│   ├── ankieta_pytania.json         # Active Survey Config
│   │
│   ├── Cantril/                      # Project Settings
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   │
│   ├── cantrilapp/                   # Main Application
│   │   ├── models.py                 # ORM Models
│   │   ├── views.py                  # Business Logic
│   │   ├── urls.py                   # URL Routing
│   │   ├── admin.py                  # Django Admin
│   │   │
│   │   ├── migrations/               # Database Migrations
│   │   │   ├── 0001_initial.py
│   │   │   └── ...
│   │   │
│   │   ├── templates/                # HTML Templates
│   │   │   ├── base.html
│   │   │   ├── generator.html        # Survey Creator
│   │   │   ├── ankieta_question.html # Patient Survey
│   │   │   ├── panel_home.html       # Doctor Dashboard
│   │   │   ├── panel_results.html    # Analytics
│   │   │   └── ...
│   │   │
│   │   └── management/               # Custom Commands
│   │
│   ├── surveys/                      # Archive (per-survey JSON)
│   │   ├── UUID1.json
│   │   ├── UUID2.json
│   │   └── ...
│   │
│   ├── audio_answers/                # Patient Audio Recordings
│   │   ├── PESEL_q1.wav
│   │   └── ...
│   │
│   ├── outbox/                       # Response Archives
│   │   ├── survey_id_patient_id.json
│   │   └── ...
│   │
│   ├── static/                       # CSS, JS, Images
│   │   ├── base.css
│   │   └── ...
│   │
│   └── venv/                         # Python Virtual Environment
│
└── README.md
```

## 6. API Endpoints Structure

```mermaid
graph LR
    subgraph "Patient Routes"
        P1["/"]
        P2["/ankieta/choice/"]
        P3["/ankieta/select-survey/"]
        P4["/ankieta/question/Q/"]
        P5["/ankieta/voice-question/Q/"]
        P6["/ankieta/done/"]
    end
    
    subgraph "Doctor Routes"
        D1["/panel/"]
        D2["/panel/results/"]
        D3["/panel/history/"]
        D4["/generator/"]
        D5["/panel/survey-completions/"]
    end
    
    subgraph "System Routes"
        S1["/webhook/n8n-callback/"]
        S2["/api/upload-audio/"]
    end
```

## 7. Technology Stack

```
┌─────────────────────────────────────────┐
│  Frontend                               │
├─────────────────────────────────────────┤
│ • HTML5                                 │
│ • CSS3 (Responsive Design)              │
│ • JavaScript (Vanilla + ES6)            │
│ • Audio Recording API                   │
│ • Drag & Drop File Upload               │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  Backend - Django Framework             │
├─────────────────────────────────────────┤
│ • Python 3.10+                          │
│ • Django 4.x                            │
│ • Django ORM                            │
│ • Built-in Admin Panel                  │
│ • Middleware for Auth                   │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  Database Layer                         │
├─────────────────────────────────────────┤
│ • SQLite (Development)                  │
│ • PostgreSQL (Production-ready)         │
│ • JSONField for scale_labels            │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  External Services                      │
├─────────────────────────────────────────┤
│ • n8n (Workflow Automation)             │
│ • Webhook for Data Processing           │
└─────────────────────────────────────────┘
```

## 8. Key Design Patterns

| Pattern | Implementation | Purpose |
|---------|----------------|---------|
| **MVC** | Django Views → Models → Templates | Separation of concerns |
| **Session** | Django Sessions | Patient state management |
| **Repository** | ORM Models | Data abstraction |
| **Outbox** | JSON files in outbox/ | Reliable message delivery |
| **Webhook** | n8n callback | Async data processing |
| **Factory** | Question creation | Dynamic survey building |

## 9. Security Architecture

```mermaid
graph TB
    USER["👤 User Request"]
    CSRF["🔒 CSRF Token Validation"]
    AUTH["🔐 Session Authentication"]
    PERM["📋 Permission Check<br/>Patient vs Doctor"]
    VALID["✅ Input Validation"]
    DB["🗄️ Sanitized Query"]
    
    USER -->|Check| CSRF
    CSRF -->|Validate| AUTH
    AUTH -->|Verify Role| PERM
    PERM -->|Sanitize| VALID
    VALID -->|Execute| DB
```

## 10. Scalability Considerations

- **Horizontal**: Load balancing with Gunicorn/uWSGI
- **Database**: PostgreSQL with indexes on json_survey_id, patient_id
- **Cache**: Redis for session storage
- **Async**: Celery for n8n webhooks and audio processing
- **Storage**: S3/Cloud storage for audio files and outbox archives

---

**Generated for**: Cantril Ladder Quality of Life Measurement Platform  
**Version**: 1.0  
**Date**: 2025-12-30
