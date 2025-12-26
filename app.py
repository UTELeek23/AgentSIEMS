import streamlit as st
from dotenv import load_dotenv
import os
from BackEnd.test import run_elk_agent, generate_summary_report, run_splunk_agent
import json
load_dotenv()

def main():
    st.title("Agent Query Interface")
    st.write("Enter your query below:")
    
    user_input = st.text_area("Query", height=150)
    
    if st.button("ELK"):
        if user_input.strip() == "":
            st.warning("Please enter a valid query.")
        else:
            # Here you would normally call the backend function to process the input
            st.success("Your query has been submitted!")
            st.write(f"Query: {user_input}")
            Res = run_elk_agent({
                "messages": [
                    {
                        "role": "user",
                        "content": user_input
                    }
                ]
            })
            st.write("Response from Agent:")
            Res = json.dumps(Res, ensure_ascii=False)
            st.write(Res)
            summary = generate_summary_report(Res)
            st.write("Summary Report:")
            st.write(summary)
    elif st.button("Splunk"):
        if user_input.strip() == "":
            st.warning("Please enter a valid query.")
        st.success("Your query has been submitted!")
        st.write(f"Query: {user_input}")
        Res = run_splunk_agent({
            "messages": [
                {
                    "role": "user",
                    "content": user_input
                }
            ]
        })
        st.write("Response from Splunk Agent:")
        st.write(Res)
        Res = json.dumps(Res, ensure_ascii=False)
        summary = generate_summary_report(Res)
        st.write("Summary Report:")
        st.write(summary)

if __name__ == "__main__":
    main()
    # print(test_nl2ioc_agent({
    #     "messages": [
    #         {
    #             "role": "user",
    #             "content": (
    #                 "Tìm các Events liên quan đến powershell trong tuần qua trên host desktop-7a6b43i trong 7 ngày qua."
    #             )
    #         }
    #     ]
    # }))