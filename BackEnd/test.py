from crewai import Crew, Process
from BackEnd.Agents import NL2IOC, Elasticsearch_query_agent, Summary_Agent
from BackEnd.SplunkAgents import SPUNK_AGENT
from BackEnd.Task import *
from crewai_tools import FileReadTool
from dotenv import load_dotenv
import os
import json
import agentops
import requests

load_dotenv()
AGENTOPS_API_KEY = os.getenv("AGENTOPS_API_KEY")
agentops.init(api_key=AGENTOPS_API_KEY)

    
# qdrant_tool = QdrantVectorSearchTool(
#     qdrant_config=QdrantConfig(
#         qdrant_url="http://192.168.111.162:6333",
#         collection_name="ELK-doc-v1",
#         custom_embedding_fn=get_jina_embedding_query,
#         limit=3,
#         score_threshold=0.35,
#     )
# )
# ReadFile = FileReadTool(file_path="./docs/ELK_schema.json")

def run_elk_agent(input):
    """Execute ELK query pipeline using CrewAI agents."""
    tasks = [NL2IOC_task, Get_Index_fields_task, SearchQdrant, Query_Elasticsearch_task]
    crew = Crew(
        agents=[NL2IOC, Elasticsearch_query_agent], 
        tasks=tasks, 
        process=Process.sequential
    )
    
    result = crew.kickoff(input)
    return result.raw

def run_splunk_agent(input):
    """Execute Splunk query pipeline using CrewAI agents."""
    tasks = [NL2IOC_task, SearchQdrant, DetermineIndex_SourceAndFields, CreateValidatedSplunkQuery, GetSplunkData]
    crew = Crew(
        agents=[NL2IOC, SPUNK_AGENT],
        tasks=tasks,
        process=Process.sequential
    )

    result = crew.kickoff(input)
    return result.raw

def generate_summary_report(input):
    """Generate a summary report from query results using CrewAI agents."""
    print(input)
    input = json.loads(input)
    filepath = input["saved_file"]
    query = input["query"]
    input = {
        "file_path": filepath,
        "query": query
    }
    read_log = FileReadTool(file_path=filepath)
    tasks = [SummarizeData]
    tasks[0].tools = [read_log]
    crew = Crew(
        agents=[Summary_Agent], 
        tasks=tasks, 
        process=Process.sequential
    )
    
    result = crew.kickoff(input)
    return result.raw


#     print(result)
# input = {
#         "messages": [
#             {
#                 "role": "user",
#                 "content": (
#                     "Tìm các Events liên quan đến powershell trong tuần qua trên host desktop-7a6b43i trong 7 ngày qua."
#                 )
#             }
#         ]
#     }
# # if __name__ == "__main__":
#     test_nl2ioc_agent(input)