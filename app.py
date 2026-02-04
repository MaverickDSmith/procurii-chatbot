import streamlit as st
import boto3
import os
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Mississippi ITS Procurement Assistant",
    page_icon="📋",
    layout="centered"
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None

def display_citations(citations):
    """Display citations in an expandable section with source text"""
    if not citations or len(citations) == 0:
        return

    st.markdown("---")
    st.markdown("**📚 Sources Referenced:**")

    for citation in citations:
        # Extract citation details
        retrieved_references = citation.get('retrievedReferences', [])

        for reference in retrieved_references:
            location = reference.get('location', {})
            content = reference.get('content', {})
            text = content.get('text', 'Source text not available')

            # Get source location info
            s3_location = location.get('s3Location', {})
            uri = s3_location.get('uri', 'Unknown source')

            # Create a clean source name from URI
            source_name = uri.split('/')[-1] if '/' in uri else uri

            # Display citation as an expander
            with st.expander(f"📄 {source_name}", expanded=False):
                st.markdown(f"**Source:** `{uri}`")
                st.markdown("**Referenced Text:**")
                st.info(text)

# AWS Configuration - Get from environment variables or Streamlit secrets
try:
    AWS_REGION = st.secrets.get("AWS_REGION", os.getenv("AWS_REGION", "us-east-1"))
    AGENT_ID = st.secrets.get("AGENT_ID", os.getenv("AGENT_ID"))
    AGENT_ALIAS_ID = st.secrets.get("AGENT_ALIAS_ID", os.getenv("AGENT_ALIAS_ID"))
    AWS_ACCESS_KEY_ID = st.secrets.get("AWS_ACCESS_KEY_ID", os.getenv("AWS_ACCESS_KEY_ID"))
    AWS_SECRET_ACCESS_KEY = st.secrets.get("AWS_SECRET_ACCESS_KEY", os.getenv("AWS_SECRET_ACCESS_KEY"))
except:
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    AGENT_ID = os.getenv("AGENT_ID")
    AGENT_ALIAS_ID = os.getenv("AGENT_ALIAS_ID")
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

# Initialize Bedrock Agent Runtime client
@st.cache_resource
def get_bedrock_client():
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        return boto3.client(
            service_name='bedrock-agent-runtime',
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
    else:
        # Use default credentials (IAM role, profile, etc.)
        return boto3.client(
            service_name='bedrock-agent-runtime',
            region_name=AWS_REGION
        )

def invoke_bedrock_agent(prompt, session_id=None):
    """
    Invoke the Bedrock Agent with the given prompt and return response with citations
    """
    try:
        client = get_bedrock_client()

        # Prepare the request parameters
        request_params = {
            'agentId': AGENT_ID,
            'agentAliasId': AGENT_ALIAS_ID,
            'sessionId': session_id or st.session_state.session_id or 'default-session',
            'inputText': prompt
        }

        # Invoke the agent
        response = client.invoke_agent(**request_params)

        # Extract the session ID for continuity
        if 'sessionId' in response:
            st.session_state.session_id = response['sessionId']

        # Process the streaming response and collect citations
        completion = ""
        citations = []

        for event in response.get('completion', []):
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    completion += chunk['bytes'].decode('utf-8')

            # Extract citations if available
            if 'citations' in event:
                citations.extend(event['citations'])

        return {"text": completion, "citations": citations}

    except ClientError as e:
        error_message = f"AWS Error: {str(e)}"
        st.error(error_message)
        return {"text": f"Error: {error_message}", "citations": []}
    except Exception as e:
        error_message = f"Error invoking agent: {str(e)}"
        st.error(error_message)
        return {"text": f"Error: {error_message}", "citations": []}

# UI
# Custom CSS to center the title and caption
st.markdown("""
    <style>
    .main-title {
        text-align: center;
        font-size: 3rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
    .main-caption {
        text-align: center;
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 1rem;
    }
    </style>
    <div class="main-title">📋 Mississippi ITS Procurement Assistant</div>
    <div class="main-caption">Your AI-powered guide for procurement questions and guidance</div>
""", unsafe_allow_html=True)
st.divider()

# Configuration check
if not AGENT_ID or not AGENT_ALIAS_ID:
    st.warning("⚠️ Please configure your Agent ID and Agent Alias ID in the environment variables or Streamlit secrets.")
    st.info("""
    **Configuration needed:**
    - AGENT_ID
    - AGENT_ALIAS_ID
    - AWS_REGION (optional, defaults to us-east-1)
    - AWS_ACCESS_KEY_ID (optional, if not using IAM role)
    - AWS_SECRET_ACCESS_KEY (optional, if not using IAM role)
    """)
    st.stop()

# Sidebar for controls (without configuration details)
with st.sidebar:
    st.header("Mississippi ITS")
    st.markdown("**Procurement Office**")
    st.divider()

    if st.button("🔄 New Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.session_id = None
        st.rerun()

    st.divider()
    st.caption("Powered by AI • Built with Streamlit and Amazon Bedrock")

# Suggested questions for new conversations
SUGGESTED_QUESTIONS = [
    "What can you do?",
    "How do I submit a procurement request?",
    "What are the procurement guidelines?",
    "What is the approval process for purchases?",
    "What are the vendor requirements?",
    "How do I check the status of my procurement request?"
]

# Display suggested questions if no messages yet
if len(st.session_state.messages) == 0:
    st.markdown("### 💡 Suggested Questions")
    st.markdown("Get started by asking one of these common questions:")

    # Create columns for better layout
    cols = st.columns(2)
    for idx, question in enumerate(SUGGESTED_QUESTIONS):
        col = cols[idx % 2]
        with col:
            if st.button(question, key=f"suggested_{idx}", use_container_width=True):
                # Store the selected question to process it
                st.session_state.selected_question = question
                st.rerun()

    st.divider()

# Handle selected question from suggested questions
if hasattr(st.session_state, 'selected_question') and st.session_state.selected_question:
    prompt = st.session_state.selected_question
    st.session_state.selected_question = None  # Clear the selected question

    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Get agent response
    with st.spinner("Thinking..."):
        response = invoke_bedrock_agent(prompt)

    # Add assistant response to chat history with citations
    st.session_state.messages.append({
        "role": "assistant",
        "content": response["text"],
        "citations": response.get("citations", [])
    })
    st.rerun()

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        # Display citations if this is an assistant message
        if message["role"] == "assistant" and "citations" in message:
            display_citations(message["citations"])

# Chat input
if prompt := st.chat_input("Ask about procurement processes, guidelines, or requirements..."):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)

    # Get agent response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = invoke_bedrock_agent(prompt)
            st.markdown(response["text"])
            # Display citations if available
            display_citations(response.get("citations", []))

    # Add assistant response to chat history with citations
    st.session_state.messages.append({
        "role": "assistant",
        "content": response["text"],
        "citations": response.get("citations", [])
    })
