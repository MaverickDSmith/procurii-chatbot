import streamlit as st
import boto3
import os
import uuid
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Mississippi ITS Procurement Assistant",
    page_icon="📋",
    layout="wide"  # Use wide layout for better citation sidebar
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

def validate_response_integrity(text, original_length):
    """Validate that the response hasn't been corrupted or truncated"""
    issues = []

    # Check if text is suspiciously short
    if len(text) < 10 and original_length > 10:
        issues.append("Response was significantly shortened during processing")

    # Check if response starts mid-sentence (common truncation indicator)
    if text and not text[0].isupper() and text[0] not in ['(', '[', '"', "'"]:
        issues.append("Response appears to start mid-sentence")

    # Check for incomplete sentences at the end
    if text and text[-1] not in ['.', '!', '?', ')', ']', '"', "'"]:
        # This is actually common and OK, so we'll just note it
        pass

    return issues

def cleanup_response_text(text):
    """Clean up response text by removing unwanted characters and phrases"""
    import re

    # Store original for validation
    original_text = text
    original_length = len(text)

    # Remove literal \n strings (not actual newlines)
    text = text.replace('\\n', '\n')

    # Remove other escape sequences that might appear as literal text
    text = text.replace('\\t', ' ')
    text = text.replace('\\r', '')

    # Remove phrases that shouldn't be in the final output
    unwanted_phrases = [
        r'This is outlined in the search results\.?',
        r'This is also outlined in the search results\.?',
        r'This is mentioned in the search results\.?',
        r'This is also mentioned in the search results\.?',
        r'As mentioned in the search results\.?',
        r'According to the search results\.?',
        r'The search results indicate\.?',
        r'Based on the search results\.?',
        r'As shown in the search results\.?',
        r'As outlined in the search results\.?',
        r'As stated in the search results\.?',
        r'This is outlined in the table in the search results\.?',
        r'This is also outlined in the table in the search results\.?',
        r'This information is found in the search results\.?',
        r'This can be found in the search results\.?',
        r'[Tt]his is (?:also )?(?:outlined|mentioned|stated|found|shown) in (?:the )?(?:table in )?(?:the )?search results\.?',
    ]

    for phrase in unwanted_phrases:
        text = re.sub(phrase, '', text, flags=re.IGNORECASE)

    # Clean up multiple spaces
    text = re.sub(r' +', ' ', text)

    # Clean up multiple newlines (more than 2 in a row)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Remove trailing/leading whitespace from each line
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)

    cleaned_text = text.strip()

    # Validate integrity
    if st.session_state.get("debug_mode", False):
        issues = validate_response_integrity(cleaned_text, original_length)
        if issues:
            print(f"⚠️ Response validation issues: {issues}")
            print(f"Original length: {original_length}, Final length: {len(cleaned_text)}")
            print(f"First 100 chars of original: {original_text[:100]}")
            print(f"First 100 chars of cleaned: {cleaned_text[:100]}")

    return cleaned_text

def insert_citation_markers(text, citations):
    """Insert numbered citation markers [1], [2], etc. into the text"""
    # For now, append citation markers at the end of sentences
    # In a more sophisticated version, we'd use citation span data from Bedrock
    if not citations or len(citations) == 0:
        return text

    # Simple approach: add all citation numbers at the end
    citation_count = sum(len(c.get('retrievedReferences', [])) for c in citations)
    if citation_count > 0:
        markers = ' '.join([f'[{i+1}]' for i in range(citation_count)])
        # Add markers at the end if not already present
        if not any(f'[{i+1}]' in text for i in range(citation_count)):
            text = f"{text} {markers}"

    return text

def display_citation_sidebar(citations):
    """Display citations in a right sidebar panel"""
    if not citations or len(citations) == 0:
        st.markdown("*No citations available*")
        return

    st.markdown("### 📚 Sources")
    st.caption("Referenced documents")
    st.markdown("---")

    citation_num = 1
    for citation in citations:
        retrieved_references = citation.get('retrievedReferences', [])

        for reference in retrieved_references:
            location = reference.get('location', {})
            content = reference.get('content', {})

            # Try to extract text from different possible fields
            text = None
            if 'text' in content and content['text']:
                text = content['text'].strip()
            elif 'content' in content and content['content']:
                text = content['content'].strip()

            # Debug mode: Log when text is not found
            if st.session_state.get("debug_mode", False) and not text:
                print(f"Citation {citation_num} has no text. Content structure: {content.keys()}")

            # Skip this citation if there's no actual text content
            if not text or text == '':
                continue

            # Get source location info
            s3_location = location.get('s3Location', {})
            uri = s3_location.get('uri', 'Unknown source')
            source_name = uri.split('/')[-1] if '/' in uri else uri

            # Display numbered citation with consistent, smaller sizing
            st.markdown(f"**[{citation_num}]** {source_name}")
            with st.expander("📖 View source text", expanded=False):
                st.caption(f"Source: {uri}")
                st.markdown(f"<div style='font-size: 0.9rem; line-height: 1.4;'>{text}</div>",
                           unsafe_allow_html=True)
            st.divider()

            citation_num += 1

    # If no valid citations were found after filtering
    if citation_num == 1:
        st.markdown("*No citation text available*")

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

        # Generate or use existing session ID
        if session_id:
            current_session_id = session_id
        elif st.session_state.session_id:
            current_session_id = st.session_state.session_id
        else:
            # Generate a new UUID if somehow none exists
            current_session_id = str(uuid.uuid4())
            st.session_state.session_id = current_session_id

        # Prepare the request parameters
        request_params = {
            'agentId': AGENT_ID,
            'agentAliasId': AGENT_ALIAS_ID,
            'sessionId': current_session_id,
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
        chunk_count = 0
        raw_chunks = []  # For debugging

        for event in response.get('completion', []):
            # Handle different event types
            if 'chunk' in event:
                chunk = event['chunk']
                chunk_count += 1

                if 'bytes' in chunk:
                    decoded_chunk = chunk['bytes'].decode('utf-8')
                    completion += decoded_chunk

                    # Store first few chunks for debugging
                    if st.session_state.get("debug_mode", False) and chunk_count <= 3:
                        raw_chunks.append(decoded_chunk)

                # Check for attribution in chunk
                if 'attribution' in chunk:
                    attribution = chunk['attribution']
                    if 'citations' in attribution:
                        citations.extend(attribution['citations'])

            # Also check for citations at event level
            if 'citations' in event:
                citations.extend(event['citations'])

        # Debug logging
        if st.session_state.get("debug_mode", False):
            print(f"\n=== Response Processing Debug ===")
            print(f"Total chunks received: {chunk_count}")
            print(f"Raw response length: {len(completion)} characters")
            print(f"First 200 chars of raw response: {completion[:200]}")
            if raw_chunks:
                print(f"First chunk content: {raw_chunks[0][:100]}")

        # Store raw completion before cleanup for validation
        raw_completion = completion

        # Clean up the response text
        completion = cleanup_response_text(completion)

        # Validation: Check if cleanup removed too much
        length_diff = len(raw_completion) - len(completion)
        if st.session_state.get("debug_mode", False):
            print(f"Cleanup removed {length_diff} characters")
            if length_diff > len(raw_completion) * 0.3:  # More than 30% removed
                print(f"⚠️ WARNING: Cleanup removed more than 30% of content!")

        # Debug: Log citation count
        if st.session_state.get("debug_mode", False):
            if citations:
                print(f"Found {len(citations)} citations")
            else:
                print("No citations found in response")
            print(f"=== End Debug ===\n")

        # Final validation
        if not completion or len(completion) < 5:
            print(f"❌ ERROR: Final response is empty or too short!")
            print(f"Raw response was: {raw_completion[:500]}")
            # Return raw response if cleanup failed
            completion = raw_completion.strip() if raw_completion else "Error: Empty response received"

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
# Custom CSS to center the title and caption, and style citations
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
    /* Citation sidebar styling */
    .citation-text {
        font-size: 0.9rem;
        line-height: 1.5;
        color: #333;
    }
    .citation-source {
        font-size: 0.85rem;
        color: #666;
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
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

    st.divider()

    # Debug mode toggle (can be enabled for troubleshooting)
    if "debug_mode" not in st.session_state:
        st.session_state.debug_mode = False

    # Show debug toggle in an expander to keep UI clean
    with st.expander("⚙️ Advanced Settings"):
        st.session_state.debug_mode = st.checkbox(
            "Enable Debug Mode",
            value=st.session_state.debug_mode,
            help="Shows detailed logging in terminal for troubleshooting response issues"
        )
        if st.session_state.debug_mode:
            st.caption("⚠️ Debug output will appear in your terminal/console")

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

# Create main layout: content area on left, citation sidebar on right
col_main, col_sidebar = st.columns([7, 3])

with col_main:
    # Display chat messages
    for msg_idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            content = message["content"]

            # Check for potential issues with assistant responses
            if message["role"] == "assistant":
                # Validate response quality
                if len(content) < 20:
                    st.warning("⚠️ This response seems unusually short. There may have been an issue.")

                # Check if response starts mid-sentence
                if content and not content[0].isupper() and content[0] not in ['(', '[', '"', "'", '1', '2', '3', '4', '5', '6', '7', '8', '9', '0']:
                    st.info("ℹ️ Note: This response may have been truncated at the beginning.")

                # Add citation markers if this is an assistant message with citations
                if message.get("citations"):
                    content = insert_citation_markers(content, message["citations"])

            st.markdown(content)

with col_sidebar:
    # Display citations for the most recent assistant message with citations
    st.markdown("---")

    # Find the last assistant message with citations
    last_cited_message = None
    for message in reversed(st.session_state.messages):
        if (message["role"] == "assistant" and
            "citations" in message and
            len(message.get("citations", [])) > 0):
            last_cited_message = message
            break

    if last_cited_message:
        display_citation_sidebar(last_cited_message["citations"])

        # Debug mode: Show raw citation data
        if st.session_state.get("debug_mode", False):
            with st.expander("🔧 Debug: Raw Citation Data"):
                st.json(last_cited_message["citations"])
    else:
        st.markdown("### 📚 Sources")
        st.markdown("*Citations will appear here*")

# Chat input
if prompt := st.chat_input("Ask about procurement processes, guidelines, or requirements..."):
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

    # Rerun to update the display with the new message
    st.rerun()
