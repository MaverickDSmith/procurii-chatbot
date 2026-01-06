import streamlit as st
import boto3
import os
from botocore.exceptions import ClientError

# Page configuration
st.set_page_config(
    page_title="Bedrock Agent Chat",
    page_icon="🤖",
    layout="centered"
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None

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
    Invoke the Bedrock Agent with the given prompt
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

        # Process the streaming response
        completion = ""
        for event in response.get('completion', []):
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    completion += chunk['bytes'].decode('utf-8')

        return completion

    except ClientError as e:
        error_message = f"AWS Error: {str(e)}"
        st.error(error_message)
        return f"Error: {error_message}"
    except Exception as e:
        error_message = f"Error invoking agent: {str(e)}"
        st.error(error_message)
        return f"Error: {error_message}"

# UI
st.title("🤖 Bedrock Agent Chat")
st.caption("Powered by Amazon Bedrock")

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
    if st.button("🔄 New Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.session_id = None
        st.rerun()

    st.divider()
    st.caption("Built with Streamlit and Amazon Bedrock")

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Ask me anything..."):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)

    # Get agent response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = invoke_bedrock_agent(prompt)
            st.markdown(response)

    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": response})
