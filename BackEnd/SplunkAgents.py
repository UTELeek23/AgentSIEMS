from crewai import Agent, LLM
from dotenv import load_dotenv
import os
from BackEnd.Agents import load_vertex_credentials_json_str

def load_llm():
    vertex_creds_str = load_vertex_credentials_json_str()
    llm = LLM(
        model="gemini-2.5-flash",
        temperature=0.65,
        vertex_credentials=vertex_creds_str
    )
    return llm

SPLUNK_AGENT = Agent(
    name="Splunk Query Builder",
    role="Build valid Splunk SPL queries from natural language requests.",
    goal="Generate optimized, executable Splunk SPL queries using verified indexes and fields.",
    backstory="""
You are a Splunk expert who converts natural language to SPL queries.

WORKFLOW:
1. First, search Qdrant for similar query examples
2. If examples found, adapt them with correct index/source values
3. If no examples, build query from scratch using verified schema

SPL QUERY STRUCTURE:
search index=<index> source=<source> <conditions>
| eval <transformations>
| stats <aggregations>

COMMON PATTERNS:
- Time range: Use EXACTLY from parsed intent (e.g., earliest=-3d for "3 ngày qua", earliest=-24h for "24 giờ qua")
- NEVER hardcode -7d unless user explicitly says "7 days" or "1 week"
- Field exists: <field>=*
- Wildcard match: <field>=*value*
- Multiple values: <field> IN ("val1", "val2")
- NOT condition: NOT <field>=value

REGEX (PCRE2 syntax - required after June 2025):
- Named capture: (?P<name>pattern) - NOT (?<name>pattern)
- Use rex command sparingly and only when needed

RULES:
- Always start with 'search'
- Only use verified fields from schema
- Include time range when specified
- Output ONLY the SPL query string, no JSON wrapper
""",
    llm=load_llm(),
    memory=True,
)
