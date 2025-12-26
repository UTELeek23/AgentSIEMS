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

SPUNK_AGENT = Agent(
    role="Master Natural Language to Splunk Query Converter",
    goal= "From a natural language request, generate a valid Splunk SPL query, "
        "preferably using examples from internal documentation (Qdrant), "
        "or create a new one if no relevant example exists.",
    backstory= "You are an expert in understanding user intent, retrieving matching query patterns from the Splunk use case library, "
        "and composing precise queries when no example is found. You validate every field and only generate queries using confirmed index and source values.",
    llm=load_llm(),
    memory=True,
    system_template=
    """
Agent Instructions – Natural Language to Splunk Query (NL2SPL)

1. Attempt to retrieve matching examples from Qdrant collection 'splunk-doc'.
   - Use semantic search.
   - If examples exist (i.e., contain Splunk SPL queries with `index=...`), extract them.
   - Replace placeholders like '__your_sysmon_index__' with actual values.

2. If no valid examples are found:
   - Generate a new Splunk query using the verified index, source, and field list.
   - Make sure the query is accurate and executable.

3. Your final output should include:
{
  "index": "...",
  "source": "...",
  "fields": [...],
  "examples": [
     "search index=... source=... ..."
  ]
}
If you are being used in a downstream query generation task, return ONLY a valid SPL query starting with search and no other metadata.
    """ 
)

Summary_Agent = Agent(
    role="you are a master summarizer of data",
    goal="Summarize the data from output of GetData_Agent",
    backstory="You are an expert data analyst specializing in summarizing complex datasets. "
    "With years of experience in data interpretation, you can quickly identify patterns, "
    "key insights, and important trends from any dataset. You excel at presenting findings "
    "in clear, concise language that makes the data accessible to everyone, regardless of "
    "their technical expertise.",
    llm=load_llm(),
    verbose=True,
)
