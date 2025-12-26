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
    name="Structured Output Agent",
    role="You receive a natural-language query from the user.",
    goal="Your task is to convert it into a concise, normalized JSON object describing the query intent.",
    backstory=(
        """
        You are an expert in understanding user queries and translating them into structured JSON format.
        """
    ),
    llm=load_llm(),
)

Elasticsearch_query_agent = Agent(
    name="Elasticsearch Query Agent",
    role="You are an expert in translating structured JSON queries into Elasticsearch DSL queries.",
    goal="Convert the provided JSON query into a valid Elasticsearch DSL query.",
    backstory=(
        """
        **NOTE**: event on firewall will strored in index .ds-filebeat-*, please consider this when generating queries.
        you are proficient in Elasticsearch and can accurately map user intents to Elasticsearch queries.
        YOUR FINAL OUTPUT MUST BE A VALID JSON OBJECT REPRESENTING THE ELASTICSEARCH QUERY.
        """
    ),
    llm=load_llm(),
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
)