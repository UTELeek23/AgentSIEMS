from crewai import Task
from BackEnd.Agents import NL2IOC, Elasticsearch_query_agent, Summary_Agent
from BackEnd.SplunkAgents import SPUNK_AGENT
from BackEnd.query import Query_Elasticsearch, Get_fields_index_ELK, Get_index_ELK, QdrantSearch_ELK
from BackEnd.Spunk_tools import Get_index_SPLUNK, Get_sources_fields_SPLUNK, search_splunk


SearchQdrant = Task(
    description=(
        "Search Qdrant for relevant Splunk queries or documentation based on the user's natural language input in {messages}. "
        "Use the QdrantVectorSearchTool to perform a vector search with the provided query. "
        "Return a list of relevant documents or example queries that can be used to construct the final Splunk query."
    ),
    expected_output="INformation from Qdrant relevant to the user's query.",
    agent=NL2IOC,
    tools=[QdrantSearch_ELK],
)

NL2IOC_task = Task(
    description=("""
        INPUT: "{messages}"
        RETURN: JSON following the defined minimal format.
        Do not add explanations or comments
        """
    ),
    expected_output="JSON array of IoC objects suitable for SIEM ingestion.",
    agent=NL2IOC
)

Get_Index_fields_task = Task(
    description=(
    """
    Your task is to build a JSON object containing all indexes and their fields from the ELK schema file.

    You MUST use the provided tools EXACTLY as described:

    ---------------------------------------------------------------------
    1) Call Get_index_ELK() with NO arguments.
       Example:
           Get_index_ELK()

       This returns a list of index names from ELK_schema.json.

    ---------------------------------------------------------------------
    2) For EACH index returned from Get_index_ELK(), call:
           Get_fields_index_ELK(index_name=<index>)

       - You MUST use named arguments.
       - Do NOT pass the entire input as a dict.
       - Do NOT invent or modify index names.

       Example:
           Get_fields_index_ELK(index_name="filebeat-2025.01.01")

    ---------------------------------------------------------------------
    3) Build the final output in this exact JSON format:

       {
         "indexes": {
            "<index_name>": {
                "fields": [...]
            }
         }
       }

    ---------------------------------------------------------------------
    IMPORTANT RULES:
    - You MUST call both tools.
    - NEVER call Get_fields_index_ELK before Get_index_ELK.
    - NEVER add, modify, or fabricate indexes or fields.
    - Only include indexes that exist in the ELK schema file.
    - Only return the final JSON — no explanations, no commentary.

    """
),

    expected_output="JSON object containing indexes and their fields from elasticsearch.",
    agent=Elasticsearch_query_agent,
    tools=[Get_fields_index_ELK, Get_index_ELK],
    context=[NL2IOC_task],
)

Query_Elasticsearch_task = Task(
    description=(
        """
        You MUST call the tool Query_Elasticsearch using named arguments only.

        The input you receive will always be a JSON object containing:
            - index_pattern
            - query_body
            - size (optional)
            - from_ (optional)
            - sort (optional)
            - only_source (optional)
            - source_includes (optional)

        When calling the tool, you MUST expand the JSON object into named parameters like:

        Query_Elasticsearch(
            index_pattern=input.index_pattern,
            query_body=input.query_body,
            size=input.size,
            from_=input.from_,
            sort=input.sort,
            only_source=input.only_source,
            source_includes=input.source_includes
        )

        Do NOT pass the entire JSON object as a single argument.
        Do NOT omit required arguments.
        Do NOT change or rewrite the query_body.

        Return the tool output as-is.
        EXAMPLE CALL:
        result_sources = Query_Elasticsearch(
                    index_pattern="windows-*",
                    query_body={
                      "bool": {
                        "must": [{"match": {"event.code": "4688"}}],
                        "filter": [{"range": {"@timestamp": {"gte": "now-7d", "lte": "now"}}}]
                      }
                    },
                    size=5,
                    only_source=True
                )
        """
    ),
    expected_output="Output from Query_Elasticsearch tool call.",
    context=[Get_Index_fields_task, SearchQdrant],
    tools=[Query_Elasticsearch],
    agent=Elasticsearch_query_agent
)


DetermineIndex_SourceAndFields = Task(
    description=(
        "Analyze the user's natural language intent from (NL2IOC_task) and determine the most appropriate Splunk index, source and fields."
        "Read the json file provided by read_file_tool, which contains the list of indexes, source, and fields. "
        "Select the most relevant index and source based on the user's scenario. "
    ),
    expected_output=(
        "Return a JSON object like: { 'index': '...', 'source': '...', 'fields': ['field1', 'field2', ...] } "
        "where 'fields' is a list of fields relevant to the selected index and source."
    ),
    agent=SPUNK_AGENT,
    context=[NL2IOC_task],
    tools=[Get_index_SPLUNK, Get_sources_fields_SPLUNK],
)

CreateValidatedSplunkQuery = Task(
    description=(
            "Ensure the query is syntactically correct and uses only the verified fields provided from earlier tasks. "
            "Select the appropriate index and source from context. Use the correct earliest and latest time from the message if available. "
            "Incorporate relevant terms or metadata from SearchQdrant to refine the query, such as adding specific keywords or patterns identified in the Qdrant vector search. "
            "Only include fields that exist in the field list. If a field does not exist, do not use it. "
            "If the natural language input is ambiguous or lacks required information, return the message: "
            "'The query cannot be created due to insufficient or unclear information.' "
            "If you need to use a 'rex' command for field extraction, ensure that the regex is as general and robust as possible. "
            "Avoid hardcoded values or over-specific patterns. Do not use 'rex' on existing fields unless explicitly required."
        "think deeply about the query you are creating, and make sure it is valid and optimized for performance. "
        "**NOTE**: Starting March 5, 2025, all new pipelines will use PCRE2 syntax by default, with no option to use RE2. All existing pipelines can continue using RE2. Starting June 5, 2025, RE2 support ends completely. All pipelines (new and existing) must use PCRE2 syntax. RE2 and PCRE accept different syntax for named capture groups."
    ),
    expected_output=(
        "A valid Splunk search query starting with 'search'. "
        "Use only verified fields and appropriate time range. "
        "Output ONLY the string SPL query — no commentary or explanation."
    ),
    agent=SPUNK_AGENT,
    context=[DetermineIndex_SourceAndFields, SearchQdrant],
)

GetSplunkData = Task(
    description=(
        "Using the validated Splunk query from the previous task, retrieve the relevant log data. "
        "Ensure that the query is executed correctly and efficiently to obtain accurate results."
    ),
    expected_output="Output from search_splunk tool call.",
    agent=SPUNK_AGENT,
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



