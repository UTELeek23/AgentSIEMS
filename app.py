import streamlit as st
from dotenv import load_dotenv
import os
from BackEnd.test import run_elk_agent, generate_summary_report, run_splunk_agent
import json
load_dotenv()

# Custom CSS for better styling
def apply_custom_css():
    st.markdown("""
    <style>
        /* Main container styling */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }
        
        /* Header styling */
        .main-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 2rem;
            border-radius: 15px;
            margin-bottom: 2rem;
            text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        
        .main-header h1 {
            color: white;
            margin: 0;
            font-size: 2.5rem;
        }
        
        .main-header p {
            color: rgba(255,255,255,0.9);
            margin-top: 0.5rem;
            font-size: 1.1rem;
        }
        
        /* Card styling */
        .result-card {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 1.5rem;
            margin: 1rem 0;
            border-left: 4px solid #667eea;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        
        .summary-card {
            background: linear-gradient(135deg, #f5f7fa 0%, #e4e8eb 100%);
            border-radius: 10px;
            padding: 1.5rem;
            margin: 1rem 0;
            border-left: 4px solid #28a745;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        
        /* Button styling */
        .stButton > button {
            width: 100%;
            border-radius: 10px;
            padding: 0.75rem 1.5rem;
            font-weight: 600;
            font-size: 1rem;
            transition: all 0.3s ease;
        }
        
        /* Text area styling */
        .stTextArea textarea {
            border-radius: 10px;
            border: 2px solid #e0e0e0;
            font-size: 1rem;
        }
        
        .stTextArea textarea:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2);
        }
        
        /* Expander styling */
        .streamlit-expanderHeader {
            background-color: #f0f2f6;
            border-radius: 10px;
        }
        
        /* Status messages */
        .stSuccess, .stWarning, .stError, .stInfo {
            border-radius: 10px;
        }
    </style>
    """, unsafe_allow_html=True)

def main():
    st.set_page_config(
        page_title="Agent SIEM Query",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    apply_custom_css()
    
    # Initialize session state
    if 'agent_response' not in st.session_state:
        st.session_state.agent_response = None
    if 'response_json' not in st.session_state:
        st.session_state.response_json = None
    if 'summary' not in st.session_state:
        st.session_state.summary = None
    if 'agent_type' not in st.session_state:
        st.session_state.agent_type = None
    
    # Header
    st.markdown("""
        <div class="main-header">
            <h1>🔍 Agent SIEM Query Interface</h1>
            <p>Query your security data using ELK or Splunk agents</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Query input section
    st.markdown("### 📝 Enter Your Query")
    user_input = st.text_area(
        "Query",
        height=120,
        placeholder="Enter your security query here... (e.g., 'Find all failed login attempts in the last 24 hours')",
        label_visibility="collapsed"
    )
    
    # Agent selection buttons
    st.markdown("### 🚀 Select Agent")
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        elk_clicked = st.button("🦌 Query ELK", type="primary", use_container_width=True)
    
    with col2:
        splunk_clicked = st.button("📊 Query Splunk", type="primary", use_container_width=True)
    
    # Process ELK query
    if elk_clicked:
        if user_input.strip() == "":
            st.warning("⚠️ Please enter a valid query.")
        else:
            st.session_state.summary = None  # Reset summary
            with st.spinner("🔄 Processing ELK query..."):
                st.session_state.agent_response = run_elk_agent({
                    "messages": [
                        {"role": "user", "content": user_input}
                    ]
                })
                st.session_state.response_json = json.dumps(
                    st.session_state.agent_response, 
                    ensure_ascii=False, 
                    indent=2
                )
                st.session_state.agent_type = "ELK"
            st.success("✅ ELK query completed successfully!")
    
    # Process Splunk query
    if splunk_clicked:
        if user_input.strip() == "":
            st.warning("⚠️ Please enter a valid query.")
        else:
            st.session_state.summary = None  # Reset summary
            with st.spinner("🔄 Processing Splunk query..."):
                st.session_state.agent_response = run_splunk_agent({
                    "messages": [
                        {"role": "user", "content": user_input}
                    ]
                })
                st.session_state.response_json = json.dumps(
                    st.session_state.agent_response, 
                    ensure_ascii=False, 
                    indent=2
                )
                st.session_state.agent_type = "Splunk"
            st.success("✅ Splunk query completed successfully!")
    
    # Display results if available
    if st.session_state.agent_response is not None:
        st.markdown("---")
        st.markdown(f"### 📋 Response from {st.session_state.agent_type} Agent")
        print(st.session_state.agent_response)
        # Show response in expandable section
        with st.expander("🔽 View Raw Response", expanded=True):
            st.json(st.session_state.agent_response)
        
        # Summary section
        st.markdown("---")
        st.markdown("### 📊 Summary Report")
        
        col_sum1, col_sum2, col_sum3 = st.columns([1, 1, 2])
        with col_sum1:
            generate_summary_clicked = st.button(
                "📝 Generate Summary", 
                type="secondary",
                use_container_width=True
            )
        
        if generate_summary_clicked:
            with st.spinner("🔄 Generating summary report..."):
                st.session_state.summary = generate_summary_report(st.session_state.response_json)
            st.success("✅ Summary generated!")
        
        # Display summary if available
        if st.session_state.summary is not None:
            st.markdown("""<div class="summary-card">""", unsafe_allow_html=True)
            st.markdown(st.session_state.summary)
            st.markdown("""</div>""", unsafe_allow_html=True)
        else:
            st.info("💡 Click 'Generate Summary' to create a summary report of the results.")
    
    # Footer
    st.markdown("---")
    st.markdown(
        "<p style='text-align: center; color: #888; font-size: 0.9rem;'>"
        "Agent SIEM Query Interface | Built with Streamlit 🚀"
        "</p>",
        unsafe_allow_html=True
    )

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