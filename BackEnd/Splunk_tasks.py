from crewai import Task
from BackEnd.Agents import NL2IOC
from BackEnd.Spunk_tools import Get_index_SPLUNK, Get_sources_fields_SPLUNK

DetermineIndex_SourcetypeAndFields = Task(
    description=(
        "Analyze the user's natural language intent from {messages} and determine the most appropriate Splunk index, source and fields."
        "Read the json file provided by read_file_tool, which contains the list of indexes, source, and fields. "
        "Select the most relevant index and source based on the user's scenario. "
    ),
    expected_output=(
        "Return a JSON object like: { 'index': '...', 'source': '...', 'fields': ['field1', 'field2', ...] } "
        "where 'fields' is a list of fields relevant to the selected index and source."
    ),
    agent=NL2IOC,
    tools=[Get_index_SPLUNK, Get_sources_fields_SPLUNK],
)

