from crewai import Task
from BackEnd.Agents import NL2IOC, Elasticsearch_query_agent, Summary_Agent
from BackEnd.SplunkAgents import SPLUNK_AGENT
from BackEnd.query import Query_Elasticsearch, Get_fields_index_ELK, Get_index_ELK, QdrantSearch_ELK
from BackEnd.Spunk_tools import Get_index_SPLUNK, Get_sources_fields_SPLUNK, search_splunk


SearchQdrant = Task(
    description="""
Search the Qdrant vector database for relevant query examples and documentation.

INPUT: User query from {messages}

ACTIONS:
1. Use QdrantSearch_ELK tool to perform semantic search
2. Extract query text from the parsed intent (keywords, target, conditions)
3. Return relevant examples that can help build the final query

The search results may contain:
- Example Elasticsearch/Splunk queries
- Field mappings and documentation
- Use case patterns

Return the raw search results for use by downstream tasks.
""",
    expected_output="Qdrant search results containing relevant query examples and documentation.",
    agent=NL2IOC,
    tools=[QdrantSearch_ELK],
)

NL2IOC_task = Task(
    description="""
Parse the user's natural language query and extract structured information.

INPUT: {messages}

OUTPUT: A JSON object with this structure:
{
    "intent": "search|alert|report|investigate",
    "target": {"type": "host|ip|user|process|event|network", "value": "<value or null>"},
    "time_range": {"start": "<e.g., now-7d>", "end": "<e.g., now>"},
    "conditions": [{"field": "...", "operator": "eq|contains|gt|lt", "value": "..."}],
    "keywords": ["extracted", "keywords"],
    "original_query": "<the original user query>"
}

RULES:
- Extract time references (e.g., "last 7 days" → now-7d)
- Identify target systems/IPs/users mentioned
- Extract keywords for search (e.g., "PowerShell", "login", "failed")
- Output ONLY valid JSON, no explanations
""",
    expected_output="JSON object with parsed query intent following the defined schema.",
    agent=NL2IOC
)

Get_Index_fields_task = Task(
    description="""
Select the appropriate Elasticsearch index and retrieve its fields based on the parsed query intent.

STEPS:
1. Call Get_index_ELK() to get available indexes
2. Based on the query intent from context, select the MOST RELEVANT index:
   - Windows events (PowerShell, login, process) → "windows" or "winlogbeat"
   - Network/Firewall events → "filebeat" 
   - Linux events → "linux" or "auditbeat"
3. Call Get_fields_index_ELK(index_name="<selected_index>") to get fields
4. Return the index name and its fields

OUTPUT FORMAT:
{
    "selected_index": "<index_name>",
    "index_pattern": "<index_name>-*",
    "fields": ["field1", "field2", ...]
}

RULES:
- Select only ONE most relevant index based on query intent
- Do not fabricate index or field names
- Use exact names from the tools' output
""",
    expected_output="JSON with selected index and its available fields.",
    agent=Elasticsearch_query_agent,
    tools=[Get_fields_index_ELK, Get_index_ELK],
    context=[NL2IOC_task],
)

Query_Elasticsearch_task = Task(
    description="""
Build and execute an Elasticsearch query based on the parsed intent and available fields.

INPUTS FROM CONTEXT:
- Parsed query intent (target, conditions, time_range, keywords)
- Selected index and available fields
- Relevant examples from Qdrant search

STEPS:
1. Build a query_body using Elasticsearch DSL:
   - Use 'bool' query with must/filter/should clauses
   - Add time range filter from parsed intent
   - Add field conditions using only verified fields
   - Use 'match' for text search, 'term' for exact matches

2. Call Query_Elasticsearch with named arguments:
   Query_Elasticsearch(
       index_pattern="<index>-*",
       query_body={"bool": {...}},
       size=100,
       only_source=True
   )

EXAMPLE:
Query_Elasticsearch(
    index_pattern="windows-*",
    query_body={
        "bool": {
            "must": [{"match": {"process.name": "powershell"}}],
            "filter": [
                {"term": {"host.name": "desktop-abc"}},
                {"range": {"@timestamp": {"gte": "now-7d", "lte": "now"}}}
            ]
        }
    },
    size=100,
    only_source=True
)

Return the tool output containing the query results.
""",
    expected_output="Elasticsearch query results with saved file path.",
    context=[Get_Index_fields_task, SearchQdrant],
    tools=[Query_Elasticsearch],
    agent=Elasticsearch_query_agent
)


DetermineIndex_SourceAndFields = Task(
    description="""
Select the appropriate Splunk index and source based on the parsed query intent.

STEPS:
1. Call Get_index_SPLUNK() to get available indexes
2. Based on query intent, select the most relevant index:
   - Windows events → "wineventlog" or "sysmon"
   - Network events → "firewall" or "network"
   - Linux events → "linux" or "syslog"
3. Call Get_sources_fields_SPLUNK(index_name="<selected>") to get sources and fields
4. Select the most relevant source for the query

OUTPUT FORMAT:
{
    "index": "<selected_index>",
    "source": "<selected_source>",
    "fields": ["field1", "field2", ...]
}

RULES:
- Select only ONE index and ONE source
- Only use fields that exist in the schema
- Do not fabricate values
""",
    expected_output="JSON object with selected index, source, and available fields.",
    agent=SPLUNK_AGENT,
    context=[NL2IOC_task],
    tools=[Get_index_SPLUNK, Get_sources_fields_SPLUNK],
)

CreateValidatedSplunkQuery = Task(
    description="""
Build a valid Splunk SPL query using the selected index, source, and fields.

INPUTS FROM CONTEXT:
- Selected index and source
- Available fields list
- Parsed query intent (time_range, conditions, keywords)
- Relevant examples from Qdrant

QUERY STRUCTURE:
search index=<index> source=<source> earliest=<time> latest=now <conditions>
| fields <relevant_fields>
| table <display_fields>

RULES:
1. Always start with 'search'
2. Include index and source from context
3. Add time range: earliest=-7d (or from intent) latest=now
4. Only use fields that exist in the verified field list
5. Use PCRE2 regex syntax for rex commands: (?P<name>pattern)
6. Keep query simple and performant

EXAMPLE:
search index=wineventlog source="WinEventLog:Security" earliest=-7d latest=now EventCode=4625
| stats count by src_ip, user
| sort -count

If the query cannot be built due to missing information, return:
"ERROR: Cannot build query - <reason>"

Output ONLY the SPL query string.
""",
    expected_output="A valid Splunk SPL query string starting with 'search'.",
    agent=SPLUNK_AGENT,
    context=[DetermineIndex_SourceAndFields, SearchQdrant],
)

GetSplunkData = Task(
    description="""
Execute the validated Splunk query and retrieve log data.

STEPS:
1. Take the SPL query from CreateValidatedSplunkQuery
2. Call search_splunk(search_query="<the SPL query>")
3. Return the results

The tool will:
- Execute the query against Splunk
- Save results to a log file
- Return the file path and query info

Return the tool output as-is.
""",
    expected_output="Splunk search results with saved file path.",
    agent=SPLUNK_AGENT,
    context=[CreateValidatedSplunkQuery],
    tools=[search_splunk],
)

SummarizeData = Task(
    description="""
    Read input from previous task
    This file contains Splunk log data that needs comprehensive analysis. If you encounter any issues reading the file, report the error.

    After successfully reading the data:
    1. Analyze the structure of the data to understand available fields, data types, and patterns
    2. Extract key metrics, trends, anomalies, and significant events present in the data
    3. Identify relationships between different data points and potential causality

    Create a data-driven report that adapts to the actual content found in the logs:

    HEADERS:
     Resource: (file_path)
     Query: (query)

    The report should include:
    Overview:
    
    Summarize the overall activity recorded in the logs.
    
    Clearly state whether there are any unusual or suspicious behaviors, or if the system appears to be functioning normally.
    
    Key Metrics and Statistics:
    
    Extract and list important quantitative data such as number of events, error codes, login attempts, system uptimes, etc.
    
    Include frequency counts and percentages where appropriate.
    
    Patterns and Anomalies:
    
    Identify notable patterns or recurring events in the logs.
    
    Highlight any anomalies or outliers that deviate from normal behavior.
    
    Significant Events:
    
    Report any critical events with exact timestamps.
    
    Describe their potential impact on system operations (e.g., service downtime, unauthorized access).
    
    Security and Operational Concerns:
    
    Flag any indicators of security risks (e.g., failed login attempts, suspicious IP addresses).
    
    Mention operational warnings such as disk space issues, high CPU usage, or service errors.
    
    Contextual Recommendations:
    
    Provide actionable recommendations based on the issues or trends found in the logs.
    
    Tailor suggestions to the actual data, not assumptions.
    
    Actionable Insights:
    
    Summarize 2–5 key takeaways or next steps that stakeholders should follow up on.
    
    These should be concise, specific, and directly based on the log content.
    
    Important: Base all analysis strictly on the content of the logs provided. Do not speculate beyond the available data.

    Your analysis should be comprehensive and adaptive to what's actually in the data, rather than trying to fit information into predefined categories. Ensure nothing significant is omitted.

    Format your report in Markdown with appropriate headings, bullet points, and code blocks for any relevant examples or patterns found in the logs.
    """,
    expected_output="A data-driven Markdown report with comprehensive analysis of the actual Splunk data content",
    output_file="reports/report_{file_path}.md",
    agent=Summary_Agent,
    context=[Query_Elasticsearch_task, GetSplunkData]
)



