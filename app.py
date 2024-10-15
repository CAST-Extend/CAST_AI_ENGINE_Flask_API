import subprocess
from flask import Flask, jsonify
from config import Config
import re
import shutil
import time
import os
import requests
import json
import pandas as pd
import logging
import tiktoken
from openai import AzureOpenAI
from datetime import datetime
import warnings
import pymongo
from pymongo import MongoClient


app = Flask(__name__)
# Load configuration from config.py
app.config.from_object(Config)

# Access configuration variables
ai_model_name = app.config['MODEL_NAME']
ai_model_version = app.config['MODEL_VERSION']
ai_model_url= app.config['MODEL_URL']
ai_model_api_key = app.config['MODEL_API_KEY']
ai_model_max_tokens = app.config['MODEL_MAX_TOKENS']

imaging_url = app.config['IMAGING_URL']
imaging_api_key = app.config['IMAGING_API_KEY']

github_token = app.config['GITHUB_TOKEN']

# Suppress specific FutureWarning
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    message="`clean_up_tokenization_spaces` was not set.*",
)

# Define OpenAI model sizes using a dictionary
ai_model_sizes = {
    "gpt-4-turbo-preview": 128000,
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "donotshare": 32768,
    "chatgpt432k": 32768,
    "mmc-tech-gpt-35-turbo": 8192,
    "mmc-tech-gpt-35-turbo-smart-latest": 8192,
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-16k": 16384,
    "codellama": 100000
}

def fix_common_json_issues(json_string):
    """
    Fix common JSON formatting issues such as unescaped newlines and quotes.

    Parameters:
    json_string (str): The input JSON string that may contain formatting issues.

    Returns:
    str: A JSON string with fixed formatting issues.
    """
    # Replace actual newlines with escaped newlines (\n) to prevent JSON parsing errors.
    # JSON requires newlines to be escaped, but they might be present as actual newlines in the input.
    json_string = json_string.replace('\n', '\\n')

    # Use a regular expression to escape double quotes that are not already escaped.
    # The regex (?<!\\)" looks for double quotes that are not preceded by a backslash, meaning they are not escaped.
    # We replace these unescaped quotes with an escaped version (\").
    json_string = re.sub(r'(?<!\\)"', r'\"', json_string)

    # Return the modified JSON string with fixed formatting.
    return json_string

# Constants like MAX_RETRIES and RETRY_DELAY should be defined outside the function
MAX_RETRIES = 3
RETRY_DELAY = 2  # Delay in seconds between retries

def ask_ai_model(messages, ai_model_url, ai_model_api_key, ai_model_version, ai_model_name, max_tokens):
    """
    Sends a prompt to the AI model and retrieves a valid JSON response.
    Retries the request if an invalid JSON is received.

    Parameters:
    messages (list): A list of messages (prompts) to send to the AI model.
    ai_model_url (str): The URL of the AI model endpoint.
    ai_model_api_key (str): The API key for authenticating with the AI model.
    ai_model_version (str): The version of the AI model being used.
    ai_model_name (str): The name of the AI model to use for generating completions.
    max_tokens (int): The maximum number of tokens the AI model can generate.

    Returns:
    dict or None: The JSON response from the AI model if valid, otherwise None.
    """
    

    # Prepare the payload for the AI API
    payload = {
        "model": ai_model_name,
        "messages": messages,
        "temperature": 0
    }

    # Set up headers for the API request
    headers = {
        "Authorization": f"Bearer {ai_model_api_key}",
        "Content-Type": "application/json"
    }

    # Loop for retrying the request in case of errors or invalid JSON.
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Send the request to the AI model and get the completion response.
            response = requests.post(ai_model_url, headers=headers, json=payload)
            response.raise_for_status()  # Raise an error for bad responses

            # Extract the AI model's response content (text) from the first choice.
            response_content = response.text
            
            logging.info(f"AI Response (Attempt {attempt}): {response_content}")

            # Try to parse the AI response as JSON.
            try:
                response_json = json.loads(response_content)
                ai_response = response_json["choices"][0]["message"]["content"] 
                ai_response = json.loads(ai_response) # Successfully parsed JSON, return it.
                return ai_response
            except json.JSONDecodeError as e:
                # Log the JSON parsing error and prepare for retry if needed.
                logging.error(f"JSON decoding failed on attempt {attempt}: {e}")

                if attempt < MAX_RETRIES:
                    # If attempts remain, wait for a delay before retrying.
                    logging.info(f"Retrying AI request in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
                else:
                    # If max retries reached, log an error and return None.
                    logging.error("Max retries reached. Failed to obtain valid JSON from AI.")
                    return None

        except Exception as e:
            # Log any general errors during the request, and retry if possible.
            logging.error(f"Error during AI model completion on attempt {attempt}: {e}")
            if attempt < MAX_RETRIES:
                logging.info(f"Retrying AI request in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                # If max retries reached due to persistent errors, log and return None.
                logging.error("Max retries reached due to persistent errors.")
                return None

    return None  # Return None if all attempts fail.

def count_chatgpt_tokens(ai_model_name, prompt):
    """
    Counts the number of tokens in the given prompt using the token encoding for the specified AI model.

    Parameters:
    ai_model_name (str): The name of the AI model, used to select the appropriate token encoding.
    prompt (str): The input text for which tokens will be counted.

    Returns:
    int: The number of tokens in the prompt.
    """
    
    try:
        # Try to retrieve the appropriate token encoding based on the AI model name.
        # Different models may use different tokenization methods.
        encoding = tiktoken.encoding_for_model(ai_model_name)
    except KeyError:
        # If the model name is not recognized (causing a KeyError), fall back to a default encoding.
        # 'cl100k_base' is a common fallback for models that do not have a specific encoding.
        encoding = tiktoken.get_encoding("cl100k_base")

    # Encode the prompt using the selected encoding, which converts the text into tokens.
    tokens = encoding.encode(prompt)

    # Return the total number of tokens in the prompt.
    return len(tokens)

def replace_code(file_path, start_line, end_line, new_code):
    """
    Replaces lines of code in a file between specified start and end lines with the provided new code.

    Parameters:
    file_path (str): The path to the file where code replacement is needed.
    start_line (int): The line number to start the replacement (inclusive).
    end_line (int): The line number to end the replacement (inclusive).
    new_code (str): The new code that will replace the existing code between start_line and end_line.

    Returns:
    None
    """
    
    try:
        # Open the file in read mode and read all lines into a list.
        with open(file_path, 'r') as file:
            lines = file.readlines()

        # Convert any escaped newlines (\\n) in the provided new_code to actual newlines (\n).
        formatted_code = new_code.replace(r"\\n", "\n")

        # Replace the lines between start_line and end_line with the new code.
        # We preserve all lines up to start_line-1, insert the new code split into lines,
        # then append all lines after end_line.
        updated_lines = lines[:start_line-1] + \
            formatted_code.splitlines(keepends=True) + lines[end_line:]

        # Open the file in write mode and overwrite it with the modified lines.
        with open(file_path, 'w') as file:
            file.writelines(updated_lines)

        # Print a success message indicating the range of lines that were replaced.
        print(f"Code between lines {start_line} and {end_line} replaced successfully.")

    except Exception as e:
        # Catch and print any errors that occur during file handling or code replacement.
        print(f"An error occurred: {e}")

def gen_code_connected_json(ApplicationName, TenantName, RequestId, IssueID, ObjectID, PromptContent, ai_model_name, ai_model_version,  ai_model_url, ai_model_api_key, ai_model_max_tokens, imaging_url, imaging_api_key, model_invocation_delay, json_resp, fixed_code_directory):
    
    # Set the AI model size, defaulting to 4096 if not specified
    ai_model_size = ai_model_sizes.get(ai_model_name, 4096)

    object_id = ObjectID  
    logging.info("---------------------------------------------------------------------------------------------------------------------------------------")
    logging.info(f"Processing object_id -> {object_id}.....")

    # Initialize DataFrames to store exceptions and impacts
    exceptions = pd.DataFrame(columns=['link_type', 'exception'])
    impacts = pd.DataFrame(columns=['object_type', 'object_signature', 'object_link_type', 'object_code'])

    # Construct URL to fetch object details
    object_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/objects/{object_id}?select=source-locations"
    params = {'api-key': imaging_api_key}
    object_response = requests.get(object_url, params=params)

    # Check if object details were fetched successfully
    if object_response.status_code == 200:
        object_data = object_response.json()  # Parse object data
        object_type = object_data['typeId'] # Get object type
        object_signature = object_data['mangling']  # Get object signature
        object_technology = object_data['programmingLanguage']['name']  # Get programming language
        source_location = object_data['sourceLocations'][0]  # Extract source location
        object_source_path = source_location['filePath']  # Get source file path
        object_field_id = source_location['fileId']  # Get file ID
        object_start_line = source_location['startLine']  # Get start line number
        object_end_line = source_location['endLine']  # Get end line number

        # Construct URL to fetch object code
        object_code_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/files/{object_field_id}?start-line={object_start_line}&end-line={object_end_line}"
        object_code_response = requests.get(object_code_url, params=params)

        # Check if the object code was fetched successfully
        if object_code_response.status_code == 200:
            obj_code = object_code_response.text  # Get object code
        else:
            obj_code = ""
            logging.error(f"Failed to fetch object code using {object_code_url}. Status code: {object_code_response.status_code}")

        # Fetch callees for the current object
        object_callees_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/objects/{object_id}/callees"
        object_callees_response = requests.get(object_callees_url, params=params)

        # Check if callees were fetched successfully
        if object_callees_response.status_code == 200:
            object_exceptions = object_callees_response.json()  # Parse exceptions data
            # Process each exception for the current object
            for object_exception in object_exceptions:
                link_type = object_exception.get('linkType', '').lower()  # Get link type
                if link_type in ['raise', 'throw', 'catch']:  # Check for relevant link types
                    new_row = pd.DataFrame({
                        'link_type': [object_exception.get('linkType', '')],
                        'exception': [object_exception.get('name', '')]
                    })
                    exceptions = pd.concat([exceptions, new_row], ignore_index=True)  # Append to exceptions DataFrame
        else:
            logging.error(f"Failed to fetch callees using {object_callees_url}. Status code: {object_callees_response.status_code}")

        # Fetch callers for the current object
        object_callers_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/objects/{object_id}/callers?select=bookmarks"
        object_callers_response = requests.get(object_callers_url, params=params)

        # Check if callers were fetched successfully
        if object_callers_response.status_code == 200:
            impact_objects = object_callers_response.json()  # Parse impact objects data
            # Process each impact object
            for impact_object in impact_objects:
                impact_object_id = impact_object.get('id')  # Get impact object ID
                impact_object_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/objects/{impact_object_id}?select=source-locations"
                impact_object_response = requests.get(impact_object_url, params=params)

                # Check if impact object data was fetched successfully
                if impact_object_response.status_code == 200:
                    impact_object_data = impact_object_response.json()  # Parse impact object data
                    impact_object_type = impact_object_data.get('typeId', '')  # Get impact object type
                    impact_object_signature = impact_object_data.get('mangling', '')  # Get impact object signature
                else:
                    impact_object_type = ''
                    impact_object_signature = ''
                    logging.error(f"Failed to fetch impact object data using {impact_object_url}. Status code: {impact_object_response.status_code}")

                impact_object_link_type = impact_object.get('linkType', '')  # Get link type for impact object

                # Handle bookmarks associated with the impact object
                bookmarks = impact_object.get('bookmarks')
                if not bookmarks:
                    impact_object_code = ''
                else:
                    bookmark = bookmarks[0]
                    impact_object_field_id = bookmark.get('fileId', '')  # Get file ID from bookmark
                    # Calculate start and end lines for impact object code
                    impact_object_start_line = max(int(bookmark.get('startLine', 1)) - 1, 0)
                    impact_object_end_line = max(int(bookmark.get('endLine', 1)) - 1, 0)
                    # Construct URL to fetch impact object code
                    impact_object_code_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/files/{impact_object_field_id}?start-line={impact_object_start_line}&end-line={impact_object_end_line}"
                    impact_object_code_response = requests.get(impact_object_code_url, params=params)

                    # Check if the impact object code was fetched successfully
                    if impact_object_code_response.status_code == 200:
                        impact_object_code = impact_object_code_response.text  # Get impact object code
                    else:
                        impact_object_code = ''
                        logging.error(f"Failed to fetch impact object code using {impact_object_code_url}. Status code: {impact_object_code_response.status_code}")

                # Append the impact object data to the impacts DataFrame
                new_impact_row = pd.DataFrame({
                    'object_type': [impact_object_type],
                    'object_signature': [impact_object_signature],
                    'object_link_type': [impact_object_link_type],
                    'object_code': [impact_object_code]
                })
                impacts = pd.concat([impacts, new_impact_row], ignore_index=True)
        else:
            logging.error(f"Failed to fetch callers using {object_callers_url}. Status code: {object_callers_response.status_code}")
    else:
        logging.error(f"Failed to fetch object data using {object_url}. Status code: {object_response.status_code}") # Skip to the next object if there is an error

    if not exceptions.empty:
        # Group exceptions by link type and aggregate unique exceptions
        grouped_exceptions = exceptions.groupby('link_type')['exception'].unique()

        # Construct exception text
        exception_text = f"Take into account that {object_type} <{object_signature}>: " + \
            "; ".join([f"{link_type} {', '.join(exc)}" for link_type, exc in grouped_exceptions.items()])
        logging.info(f'exception_text = {exception_text}')
    else:
        exception_text = ""  # No exceptions found

    def generate_text(impacts):
        # Generate impact analysis text from impacts DataFrame
        base_method = f"{object_type} <{object_signature}>"
        text = f"Take into account that {base_method} is used by:\n"
        for i, row in impacts.iterrows():
            text += f" {i + 1}. {row['object_type']} <{row['object_signature']}> has a <{row['object_link_type']}> dependency as found in code:\n"
            text += f"````\n\t{row['object_code']}\n````\n"
        return text

    if not impacts.empty:
        impact_text = generate_text(impacts)  # Generate impact analysis text
        logging.info(f'impact_text = {impact_text}')
    else:
        impact_text = ""  # No impacts found

    # Construct the prompt for the AI model
    prompt_content = (
        f"{PromptContent}\n"
        f"\n\nTASK:\n1/ Generate a version without the pattern occurrence(s) of the following code, "
        f"'''\n{obj_code}\n'''\n"
        f"2/ Provide an analysis of the transformation: detail what you did in the 'comment' field, forecast "
        f"impacts on code signature, exception management, enclosed objects or other areas in the "
        f"'signature_impact', 'exception_impact', 'enclosed_impact, and 'other_impact' fields respectively, "
        f"with some comments on your prognostics in the 'impact_comment' field.\n"
        f"\nGUIDELINES:\nUse the following JSON structure to respond:\n'''\n{json_resp}\n'''\n" +
        (f"\nIMPACT ANALYSIS CONTEXT:\n{impact_text}\n{exception_text}\n" if impact_text or exception_text else "") +
        "\nMake sure your response is a valid JSON string.\nRespond only the JSON string, and only the JSON string. "
        "Do not enclose the JSON string in triple quotes, backslashes, ... Do not add comments outside of the JSON structure."
    )

    # Clean up prompt content for formatting issues
    prompt_content = prompt_content.replace("\\n", "\n").replace("\\\"", "\"").replace("\\\\", "\\")

    logging.info(f"Prompt Content: {prompt_content}")

    # Prepare messages for the AI model
    messages = [{'role': 'user', 'content': prompt_content}]

    # Count tokens for the AI model's input
    code_token = count_chatgpt_tokens(ai_model_name, str(obj_code))
    prompt_token = count_chatgpt_tokens(ai_model_name, "\n".join([json.dumps(m) for m in messages]))

    # Determine target response size
    target_response_size = int(code_token * 1.2 + 500)

    # Check if the prompt length is within acceptable limits
    if prompt_token < (ai_model_size - target_response_size):
        # Ask the AI model for a response
        response_content = ask_ai_model(
            messages, ai_model_url, ai_model_api_key, ai_model_version, ai_model_name, max_tokens=target_response_size
        )
        logging.info(f"Response Content: {response_content}")
        time.sleep(model_invocation_delay)  # Delay for model invocation

        # Check if the response indicates an update was made
        if response_content['updated'].lower() == 'yes':
            # Prepare file path for the modified code
            # if SourceCodeLocation.lower() in object_source_path.lower():
            #     object_source_path = object_source_path.replace(SourceCodeLocation, '')
            #     file_path = fixed_code_directory + object_source_path
            try:
                # Copy the file
                shutil.copy(object_source_path, fixed_code_directory)
                print(f'File copied from {object_source_path} to {fixed_code_directory}')
            except FileNotFoundError:
                print("Source file not found.")
            except PermissionError:
                print("Permission denied.")
            except Exception as e:
                print(f"An error occurred: {e}")

            new_code = response_content['code']  # Extract new code from the response
            # Convert the new_code string back to its readable format
            readable_code = new_code.replace("\\n", "\n").replace("\\\"", "\"").replace("\\\\", "\\")
            start_line = object_start_line
            end_line = object_end_line

            # Replace the old code with the new code in the specified file
            replace_code(fixed_code_directory, start_line, end_line, readable_code)

        # Append the response to the result list
        return ({
            'prompt': prompt_content,
            'response': response_content,
            'source_path': object_source_path,
            'object_id': object_id,
            'line_start': object_start_line,
            'line_end': object_end_line,
            'technologies': object_technology,
            'req_id': RequestId
        })

    else:
        logging.warning("Prompt too long; skipping.")  # Warn if the prompt exceeds limits
        return ({
            'prompt': prompt_content,
            'response': "(NA prompt too long)",  # Indicate that the prompt was too long
            'source_path': object_source_path,
            'object_id': object_id,
            'line_start': object_start_line,
            'line_end': object_end_line,
            'technologies': object_technology,
            'req_id': RequestId
        })

@app.route('/')
def home():
    return "Welcome to CAST AI ENGINE"

@app.route('/ProcessRequest/<int:RequestId>')
def process_request(RequestId):

    model_invocation_delay = 10

    json_resp = '''
    {
    "updated":"<YES/NO to state if you updated the code or not (if you believe it did not need fixing)>",
    "comment":"<explain here what you updated (or the reason why you did not update it)>",
    "missing_information":"<list here information needed to finalize the code (or NA if nothing is needed or if the code was not updated)>",
    "signature_impact":"<YES/NO/UNKNOWN, to state here if the signature of the code will be updated as a consequence of changed parameter list, types, return type, etc.>",
    "exception_impact":"<YES/NO/UNKNOWN, to state here if the exception handling related to the code will be update, as a consequence of changed exception thrown or caught, etc.>",
    "enclosed_impact":"<YES/NO/UNKNOWN, to state here if the code update could impact code enclosed in it in the same source file, such as methods defined in updated class, etc.>",
    "other_impact":"<YES/NO/UNKNOWN, to state here if the code update could impact any other code referencing this code>",
    "impact_comment":"<comment here on signature, exception, enclosed, other impacts on any other code calling this one (or NA if not applicable)>",
    "code":"<the fixed code goes here (or original code if the code was not updated)>"
    }
    '''

    # Get Request Information from Mongo DB
    engine_input = {
                        "applicationid": "MER_-_CLNPAR_-_Client_Participation_Survey_Mgmt_System",
                        "tenantid": "default",
                        "repo_url": "https://github.com/mmctech/mercer-cpsm.git",
                        "request": [
                            {
                            "requestid": "66fc114c01b7b08905f87999",
                            "issueid": 1200138,
                            "requestdetail": [
                                {
                                "promptid": "670504f84594d67cd4750702",
                                "objectdetails": [
                                    {
                                    "objectid": 41140,
                                    "filefullname": "Mercer.CPSM.Modules.SurveyManagement.ProjectManagement.EditSurvey.BindControls"
                                    },
                                    {
                                    "objectid": 41661,
                                    "filefullname": "Mercer.CPSM.ListCountry.BindDDLPaging"
                                    },
                                    {
                                    "objectid": 40905,
                                    "fullfilepath": "Mercer.CPSM.ListSubmissionNotPass2ndIntegrity.BindDDLPaging"
                                    }
                                ]
                                }
                            ]
                            }
                        ],
                        "createddate": "mmddyy HH:MM:SS"
                    }

    ApplicationName = engine_input['applicationid']
    TenantName = engine_input['tenantid']
    RepoURL = engine_input['repo_url']

    # SourceCodeLocation = "C:\\ProgramData\\CAST\\AIP-Console-Standalone\\shared\\upload\\Webgoat\\main_sources\\"

    # Get the current working directory
    current_directory = os.getcwd()

    # # Get the current datetime stamp for directory and file naming
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # Define the output directory name based on the input parameters and timestamp
    # output_directory = f"{ApplicationName}"
    output_directory = os.path.abspath(ApplicationName)

    # Create the output directory; if it already exists, do nothing
    os.makedirs(output_directory, exist_ok=True)
    print(f"Directory '{output_directory}' created successfully!")

    result = []  # Initialize result list to hold processed data

    for request in engine_input['request']:
        RequestId = request['requestid']
        IssueID = request['issueid']

        # Define the directory for storing fixed source code
        fixed_code_directory = os.path.join(
            output_directory,
            f"Fixed_SourceCode_for_IssueID-{IssueID}_{timestamp}"
        )
        os.makedirs(fixed_code_directory, exist_ok=True)  # Create the directory for fixed source code
        print(f"Directory '{fixed_code_directory}' created successfully!")

        repo_url_without_protocol = RepoURL.replace("https://", "")
    
        # Construct the authenticated repo URL
        auth_repo_url = f"https://{github_token}@{repo_url_without_protocol}"

        try:
            print(f"Cloning into {fixed_code_directory}...")
            subprocess.run(["git", "clone", auth_repo_url, fixed_code_directory], check=True)
            print("Repository cloned successfully.")
        except Exception as e:
            print(f"Error during cloning: {e}")

        # Create a log filename based on the input parameters and timestamp
        filename = f'Logs_for_IssueID-{IssueID}_{timestamp}.txt'

        # Configure logging to write logs to the specified log file
        logging.basicConfig(
            filename=os.path.join(current_directory, output_directory, filename),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s: %(message)s",
            filemode='w'  # Overwrite log file each time the script runs
        )

        for requestdetail in request['requestdetail']:
            prompt_id = requestdetail['promptid']
            #fetch based on IssueID
            prompt_library = {
                                "_id": {
                                    "$oid": "670504114594d67cd4750700"
                                },
                                "applicationid": None,
                                "issueid": 1200138,
                                "issuename": "Green - Avoid instantiations inside loops",
                                "prompttype": "generic",
                                "technologies": [
                                    {
                                    "technology": "c#",
                                    "prompts": [
                                        {
                                        "promptid": "670504f84594d67cd4750702",
                                        "prompt": "Please refactor the code (written in C# language) to address the code review issue: Avoid instantiations inside loops. The intent is to initiate the variables outside the for loop.\n\nHere is a sample code that is following this practice\n\n\nint rateSetId = 0;\nstring planName= String.Empty;\nvar planDesign = null;\nfor (int i = 0; i < plans.Count; i++)\n{\n\trateSetId = plans.ElementAt(i).RateSetID;\n\tplanName = plans.ElementAt(i).RenewalsPlanName.Replace(\" -\", \"-\").Replace(\"- \", \"-\");\n\tplanDesign = new LookupManager().GetPlanDesign(planPeriodId, rateSetId, deliverableId);\n}"
                                        }
                                    ]
                                    },
                                    {
                                    "technology": "javascript",
                                    "prompts": [
                                        {
                                        "promptid": "670504114594d67cd4750708",
                                        "prompt": "\"Act as a skilled software developer and programmer.\nIn the provided code, refactor the code to fix the following code review issue.\n\nCode Review Issue: Avoid instantiations inside loops\n\nEnsure to enhance performance and maintainability. Please fix the provided code and not the example code in the prompt. Use the example code as reference to fix the actual code\""
                                        }
                                    ]
                                    }
                                ],
                                "type": "Green Deficiency",
                                "enabled": True
                                }
            for technology in prompt_library['technologies']:
                for prompt in technology['prompts']:
                    if prompt_id == prompt['promptid']:
                        PromptContent = prompt['prompt']
                        for objectdetail in requestdetail['objectdetails']:
                            ObjectID = objectdetail['objectid']

                            # Call the gen_code_connected_json function to process the request and generate code updates
                            data = gen_code_connected_json(
                                ApplicationName, TenantName, RepoURL, RequestId, IssueID, ObjectID, PromptContent,
                                ai_model_name, ai_model_version, ai_model_url, ai_model_api_key,
                                ai_model_max_tokens, imaging_url, imaging_api_key, model_invocation_delay, json_resp, fixed_code_directory
                            )

                            result.append(data)

        # Create a filename incorporating the Application Name, Request ID, Issue ID, and timestamp
        filename = output_directory + \
            f'/AI_Response_for_IssueID-{IssueID}_{timestamp}.json'

        # Write the JSON response data to the specified file with pretty formatting
        with open(filename, 'w') as json_file:
            json.dump(result, json_file, indent=4)  # Save data as formatted JSON in the file

        return jsonify(result), 200  # Return JSON response with HTTP status code

if __name__ == '__main__':
    app.run(debug=True, port=5001)
