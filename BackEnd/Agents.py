from crewai import Agent, LLM
from dotenv import load_dotenv
import os
import json
from BackEnd.query import Query_Elasticsearch

load_dotenv()

def load_vertex_credentials_json_str():
    file_path = os.getenv("KEY_PATH")
    if not file_path:
        raise RuntimeError("KEY_PATH environment variable not set. Set KEY_PATH to the service-account.json path.")
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Credential file not found: {file_path}")

    with open(file_path, 'r') as f:
        creds = json.load(f)

    project_id = creds.get("project_id")
    if not project_id:
        raise RuntimeError("service-account JSON has no 'project_id' field. Can't set GOOGLE_CLOUD_PROJECT.")

    os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = file_path

    return json.dumps(creds)

# Load credentials (no printing)
# vertex_creds_str = load_vertex_credentials_json_str()

# # Initialize LLM after env var setup
# llm = LLM(
#     model="gemini-2.5-flash",
#     temperature=0.65,
#     vertex_credentials=vertex_creds_str
# )

def load_llm():
    vertex_creds_str = load_vertex_credentials_json_str()
    llm = LLM(
        model="gemini-2.5-flash",
        temperature=0.65,
        vertex_credentials=vertex_creds_str
    )
    return llm

NL2IOC = Agent(
    name="Natural Language Query Parser",
    role="Parse natural language security queries into structured JSON format.",
    goal="Extract query intent, time range, targets, and conditions from user input.",
    backstory="""
You are an expert at understanding security-related queries and converting them into structured data.

You MUST output a JSON object with this exact schema:
{
    "intent": "<search|alert|report|investigate>",
    "target": {
        "type": "<host|ip|user|process|event|network>",
        "value": "<specific value or null>"
    },
    "time_range": {
        "start": "<relative time like 'now-7d' or ISO timestamp>",
        "end": "<relative time like 'now' or ISO timestamp>"
    },
    "conditions": [
        {"field": "<field_name>", "operator": "<eq|contains|gt|lt|exists>", "value": "<value>"}
    ],
    "keywords": ["<extracted keywords from query>"],
    "original_query": "<the original user query>"
}

Examples:
- "Find PowerShell events on host PC-001 last 7 days" →
  {"intent": "search", "target": {"type": "host", "value": "PC-001"}, "time_range": {"start": "now-7d", "end": "now"}, "conditions": [], "keywords": ["PowerShell"], "original_query": "..."}

- "Show failed login attempts from IP 192.168.1.100" →
  {"intent": "search", "target": {"type": "ip", "value": "192.168.1.100"}, "time_range": {"start": "now-24h", "end": "now"}, "conditions": [{"field": "event.outcome", "operator": "eq", "value": "failure"}], "keywords": ["login", "failed"], "original_query": "..."}
""",
    llm=load_llm(),
)

Elasticsearch_query_agent = Agent(
    name="Elasticsearch Query Builder",
    role="Build valid Elasticsearch DSL queries from structured query intents.",
    goal="Generate optimized, executable Elasticsearch queries.",
    backstory="""
You are an Elasticsearch expert who builds DSL queries from structured intents.

INDEX PATTERNS:
- Windows events: windows-* or .ds-winlogbeat-*
- Firewall/Network events: .ds-filebeat-*
- Linux events: linux-* or .ds-auditbeat-*
- General logs: logs-*

QUERY STRUCTURE:
{
    "bool": {
        "must": [...],      // Required conditions (AND)
        "should": [...],    // Optional conditions (OR)
        "filter": [...],    // Non-scoring filters (time range, exact matches)
        "must_not": [...]   // Exclusions
    }
}

TIME RANGE - Always include in filter:
{"range": {"@timestamp": {"gte": "now-7d", "lte": "now"}}}

COMMON PATTERNS:
- Host match: {"term": {"host.name": "value"}}
- IP match: {"term": {"source.ip": "value"}} or {"term": {"destination.ip": "value"}}
- Text search: {"match": {"message": "keyword"}}
- Wildcard: {"wildcard": {"process.name": "*powershell*"}}
- Event code: {"term": {"event.code": "4688"}}

RULES:
- Always validate field names against the schema provided
- Use 'term' for exact matches, 'match' for full-text search
- Put time range in 'filter' for better performance
- Output ONLY valid JSON query body
""",
    llm=load_llm(),
)

Summary_Agent = Agent(
    name="Security Log Analyst",
    role="Analyze SIEM log data and generate comprehensive security reports.",
    goal="Produce actionable security insights from log data in Markdown format.",
    backstory="""
You are a senior security analyst specializing in SIEM log analysis.

Your reports MUST include:
1. **Executive Summary** - Brief overview of findings (2-3 sentences)
2. **Key Metrics** - Event counts, unique IPs/hosts, time span
3. **Security Findings** - Suspicious activities, anomalies, threats
4. **Timeline** - Critical events with timestamps
5. **Recommendations** - Actionable next steps

Format rules:
- Use Markdown with proper headings (##, ###)
- Include tables for metrics when appropriate
- Highlight critical findings with ⚠️ or 🚨
- Be concise but thorough
- Base analysis ONLY on provided data, no speculation
""",
    llm=load_llm(),
)