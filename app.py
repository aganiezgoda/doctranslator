# streamlit run app.py

import streamlit as st
import requests
import time
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
import os

# Configuration - Replace with your values or use environment variables
TRANSLATOR_ENDPOINT = os.environ.get("TRANSLATOR_ENDPOINT", "https://eastuss1.cognitiveservices.azure.com/")

# Storage configuration using Entra ID (Managed Identity)
STORAGE_ACCOUNT_URL = os.environ.get("STORAGE_ACCOUNT_URL", "https://storagean2023.blob.core.windows.net")
INPUT_CONTAINER = os.environ.get("INPUT_CONTAINER", "doctranslatorinput")
OUTPUT_CONTAINER = os.environ.get("OUTPUT_CONTAINER", "doctranslatoroutput")

# Initialize Azure credential (uses logged-in user, managed identity, or service principal)
credential = DefaultAzureCredential()

# Cognitive Services scope for getting bearer tokens
COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"

def get_translator_token():
    """Get bearer token for Translator API using Entra ID"""
    token = credential.get_token(COGNITIVE_SERVICES_SCOPE)
    return token.token

def get_blob_service_client():
    """Get BlobServiceClient using Entra ID authentication"""
    return BlobServiceClient(account_url=STORAGE_ACCOUNT_URL, credential=credential)

# Supported languages for translation
LANGUAGES = {
    "English": "en",
    "Polish": "pl",
    "German": "de",
    "French": "fr",
    "Spanish": "es",
    "Italian": "it",
    "Portuguese": "pt",
    "Dutch": "nl",
    "Norwegian (Bokmål)": "nb",
    "Swedish": "sv",
    "Danish": "da",
    "Finnish": "fi",
    "Russian": "ru",
    "Ukrainian": "uk",
    "Czech": "cs",
    "Japanese": "ja",
    "Chinese (Simplified)": "zh-Hans",
    "Chinese (Traditional)": "zh-Hant",
    "Korean": "ko",
    "Arabic": "ar",
    "Hindi": "hi",
}

def upload_to_blob(file_content, file_name, container_name):
    """Upload a file to Azure Blob Storage using Entra ID"""
    try:
        blob_service_client = get_blob_service_client()
        container_client = blob_service_client.get_container_client(container_name)
        
        # Create container if it doesn't exist
        try:
            container_client.create_container()
        except Exception:
            pass  # Container already exists
        
        # Upload the file
        blob_client = container_client.get_blob_client(file_name)
        blob_client.upload_blob(file_content, overwrite=True)
        
        return True, f"File '{file_name}' uploaded successfully"
    except Exception as e:
        return False, f"Upload failed: {str(e)}"

def start_translation(source_language, target_language):
    """Start the document translation job"""
    path = "translator/text/batch/v1.1/batches"
    constructed_url = TRANSLATOR_ENDPOINT + path
    
    # Use container URLs without SAS - Translator uses managed identity to access storage
    body = {
        "inputs": [
            {
                "source": {
                    "sourceUrl": f"{STORAGE_ACCOUNT_URL}/{INPUT_CONTAINER}",
                    "language": source_language
                },
                "targets": [
                    {
                        "targetUrl": f"{STORAGE_ACCOUNT_URL}/{OUTPUT_CONTAINER}",
                        "category": "general",
                        "language": target_language
                    }
                ]
            }
        ]
    }
    
    # Use bearer token authentication instead of API key
    token = get_translator_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    response = requests.post(constructed_url, headers=headers, json=body)
    
    if response.status_code in [200, 201, 202]:
        # Get the operation location for status checking
        operation_location = response.headers.get("Operation-Location")
        return True, operation_location
    else:
        return False, f"Translation failed: {response.status_code} - {response.text}"

def check_translation_status(operation_location):
    """Check the status of a translation job"""
    token = get_translator_token()
    headers = {
        "Authorization": f"Bearer {token}",
    }
    
    response = requests.get(operation_location, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        return result.get("status"), result
    else:
        return "Failed", None

def download_from_blob(file_name, container_name):
    """Download a file from Azure Blob Storage using Entra ID"""
    try:
        blob_service_client = get_blob_service_client()
        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(file_name)
        
        download_stream = blob_client.download_blob()
        return True, download_stream.readall()
    except Exception as e:
        return False, f"Download failed: {str(e)}"

def list_blobs(container_name):
    """List all blobs in a container using Entra ID"""
    try:
        blob_service_client = get_blob_service_client()
        container_client = blob_service_client.get_container_client(container_name)
        blobs = [blob.name for blob in container_client.list_blobs()]
        return blobs
    except Exception as e:
        return []

def clear_container(container_name):
    """Clear all blobs in a container using Entra ID"""
    try:
        blob_service_client = get_blob_service_client()
        container_client = blob_service_client.get_container_client(container_name)
        for blob in container_client.list_blobs():
            container_client.delete_blob(blob.name)
        return True
    except Exception:
        return False

# Streamlit UI
st.set_page_config(
    page_title="Document Translator",
    page_icon="🌐",
    layout="centered"
)

st.title("🌐 Azure Document Translator")
st.markdown("Upload a document and translate it to your desired language using Azure AI Translator.")

# File upload
uploaded_file = st.file_uploader(
    "Choose a document to translate",
    type=["pdf", "docx", "xlsx", "pptx", "txt", "html", "htm", "csv", "tsv"],
    help="Supported formats: PDF, DOCX, XLSX, PPTX, TXT, HTML, CSV, TSV"
)

# Language selection
col1, col2 = st.columns(2)

with col1:
    source_language = st.selectbox(
        "Source Language",
        options=list(LANGUAGES.keys()),
        index=list(LANGUAGES.keys()).index("Polish"),
        help="Select the language of the original document"
    )

with col2:
    # Filter out the source language from target options
    target_options = [lang for lang in LANGUAGES.keys() if lang != source_language]
    target_language = st.selectbox(
        "Target Language",
        options=target_options,
        index=target_options.index("English") if "English" in target_options else 0,
        help="Select the language to translate to"
    )

# Translate button
if st.button("🚀 Translate Document", type="primary", disabled=uploaded_file is None):
    if uploaded_file is not None:
        source_code = LANGUAGES[source_language]
        target_code = LANGUAGES[target_language]
        
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Step 1: Clear input container and upload file
        status_text.text("⏳ Preparing containers...")
        progress_bar.progress(10)
        
        clear_container(INPUT_CONTAINER)
        clear_container(OUTPUT_CONTAINER)
        
        status_text.text("⏳ Uploading document...")
        progress_bar.progress(20)
        
        file_content = uploaded_file.read()
        success, message = upload_to_blob(file_content, uploaded_file.name, INPUT_CONTAINER)
        
        if not success:
            st.error(f"❌ {message}")
        else:
            # Step 2: Start translation
            status_text.text("⏳ Starting translation...")
            progress_bar.progress(40)
            
            success, result = start_translation(source_code, target_code)
            
            if not success:
                st.error(f"❌ {result}")
            else:
                operation_location = result
                
                # Step 3: Poll for completion
                status_text.text("⏳ Translating document...")
                
                max_attempts = 60  # Max 5 minutes (60 * 5 seconds)
                attempt = 0
                
                while attempt < max_attempts:
                    status, details = check_translation_status(operation_location)
                    
                    if status == "Succeeded":
                        progress_bar.progress(90)
                        status_text.text("⏳ Downloading translated document...")
                        
                        # Get the translated file
                        output_blobs = list_blobs(OUTPUT_CONTAINER)
                        
                        if output_blobs:
                            # Find the translated version of our file
                            translated_file = None
                            for blob_name in output_blobs:
                                if uploaded_file.name in blob_name or blob_name.endswith(uploaded_file.name.split('.')[-1]):
                                    translated_file = blob_name
                                    break
                            
                            if translated_file is None:
                                translated_file = output_blobs[0]
                            
                            success, content = download_from_blob(translated_file, OUTPUT_CONTAINER)
                            
                            if success:
                                progress_bar.progress(100)
                                status_text.text("✅ Translation complete!")
                                
                                st.success(f"Document translated successfully from {source_language} to {target_language}!")
                                
                                # Download button
                                st.download_button(
                                    label="📥 Download Translated Document",
                                    data=content,
                                    file_name=f"translated_{uploaded_file.name}",
                                    mime="application/octet-stream"
                                )
                            else:
                                st.error(f"❌ {content}")
                        else:
                            st.error("❌ No translated document found in output container")
                        break
                        
                    elif status == "Failed":
                        st.error("❌ Translation failed. Please check your document and try again.")
                        if details:
                            st.json(details)
                        break
                        
                    elif status == "Cancelled":
                        st.warning("⚠️ Translation was cancelled.")
                        break
                        
                    else:
                        # Still running
                        progress = min(40 + (attempt * 0.8), 85)
                        progress_bar.progress(int(progress))
                        time.sleep(5)
                        attempt += 1
                
                if attempt >= max_attempts:
                    st.warning("⚠️ Translation is taking longer than expected. Please check back later.")

# Information section
with st.expander("ℹ️ About Document Translation"):
    st.markdown("""
    ### Supported File Formats
    - **Documents**: PDF, DOCX, PPTX, XLSX
    - **Text**: TXT, HTML, HTM
    - **Data**: CSV, TSV
    
    ### How it works
    1. Upload your document
    2. Select source and target languages
    3. Click "Translate Document"
    4. Download the translated file
    
    ### Tips
    - For best results, ensure your document has clear text (not images of text)
    - Large documents may take longer to process
    - The service preserves the original formatting where possible
    """)

# Footer
st.markdown("---")
st.markdown("Powered by [Azure AI Translator](https://azure.microsoft.com/services/cognitive-services/translator/)")
