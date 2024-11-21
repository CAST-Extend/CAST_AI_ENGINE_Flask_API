import ast
import stat
import subprocess
from flask import Flask, jsonify
from flask_cors import CORS
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
from pymongo import MongoClient
import secrets
import string
import traceback

from pymongo.errors import ServerSelectionTimeoutError, ConfigurationError
from requests.packages.urllib3.exceptions import InsecureRequestWarning # type: ignore

# Suppress the InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


app = Flask(__name__)
CORS(app)
# Load configuration from config.py
app.config.from_object(Config)

# Access configuration variables
ai_model_name = app.config["MODEL_NAME"]
ai_model_version = app.config["MODEL_VERSION"]
ai_model_url = app.config["MODEL_URL"]
ai_model_api_key = app.config["MODEL_API_KEY"]
ai_model_max_tokens = app.config["MODEL_MAX_TOKENS"]

imaging_url = app.config["IMAGING_URL"]
imaging_api_key = app.config["IMAGING_API_KEY"]

mongo_uri = app.config["MONGODB_CONNECTION_STRING"]

# # Get the current datetime
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# Suppress specific FutureWarning
warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    message="`clean_up_tokenization_spaces` was not set.*",
)

# MongoDB connection
def get_mongo_collection(collection_name):
    # Create a MongoClient instance
    client = MongoClient(mongo_uri)

    # Example of accessing a specific database (replace 'mydatabase' with your DB name)
    db = client["ApplicationHDev"]
    return db[collection_name]


# Function to log errors to MongoDB
def log_error_to_mongo(exception, function_name):
    collection = get_mongo_collection('ExceptionLog')
    error_data = {
        "function": function_name,
        "error": str(exception),
        "trace": traceback.format_exc(),
        "timestamp": timestamp,
    }
    collection.insert_one(error_data)
    logging.error(f"Error logged to MongoDB: {error_data}")


def generate_unique_alphanumeric(length=24):
    try:
        characters = string.ascii_letters + string.digits
        return ''.join(secrets.choice(characters) for _ in range(length))
    except Exception as e:
        # Catch and print any errors that occur.
        print(f"An error occurred: {e}")
        log_error_to_mongo(e, "generate_unique_alphanumeric")


def fix_common_json_issues(json_string):
    try:
        """
        Fix common JSON formatting issues such as unescaped newlines and quotes.

        Parameters:
        json_string (str): The input JSON string that may contain formatting issues.

        Returns:
        str: A JSON string with fixed formatting issues.
        """
        # Replace actual newlines with escaped newlines (\n) to prevent JSON parsing errors.
        # JSON requires newlines to be escaped, but they might be present as actual newlines in the input.
        json_string = json_string.replace("\n", "\\n")

        # Use a regular expression to escape double quotes that are not already escaped.
        # The regex (?<!\\)" looks for double quotes that are not preceded by a backslash, meaning they are not escaped.
        # We replace these unescaped quotes with an escaped version (\").
        json_string = re.sub(r'(?<!\\)"', r"\"", json_string)

        # Return the modified JSON string with fixed formatting.
        return json_string
    except Exception as e:
        # Catch and print any errors that occur.
        print(f"An error occurred: {e}")
        log_error_to_mongo(e, "fix_common_json_issues")


# Constants like MAX_RETRIES and RETRY_DELAY should be defined outside the function
MAX_RETRIES = 3
RETRY_DELAY = 2  # Delay in seconds between retries


def ask_ai_model(
    prompt_content,
    json_resp,
    ai_model_url,
    ai_model_api_key,
    ai_model_version,
    ai_model_name,
    max_tokens,
):
    try:
        """
        Sends a prompt to the AI model and retrieves a valid JSON response.
        Retries the request if an invalid JSON is received.

        Parameters:
        prompt_content (str): prompt to send to the AI model.
        ai_model_url (str): The URL of the AI model endpoint.
        ai_model_api_key (str): The API key for authenticating with the AI model.
        ai_model_version (str): The version of the AI model being used.
        ai_model_name (str): The name of the AI model to use for generating completions.
        max_tokens (int): The maximum number of tokens the AI model can generate.

        Returns:
        dict or None: The JSON response from the AI model if valid, otherwise None.
        """

        messages = [{"role": "user", "content": prompt_content}]

        # Prepare the payload for the AI API
        payload = {"model": ai_model_name, "messages": messages, "temperature": 0}

        # Set up headers for the API request
        headers = {
            "Authorization": f"Bearer {ai_model_api_key}",
            "Content-Type": "application/json",
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
                    ai_response = json.loads(
                        ai_response
                    )  # Successfully parsed JSON, return it.
                    return ai_response
                except json.JSONDecodeError as e:
                    # Log the JSON parsing error and prepare for retry if needed.
                    logging.error(f"JSON decoding failed on attempt {attempt}: {e}")

                    if attempt < MAX_RETRIES:
                        # If attempts remain, wait for a delay before retrying.
                        logging.info(f"Retrying AI request in {RETRY_DELAY} seconds...")
                        time.sleep(RETRY_DELAY)

                        prompt_content = (
                            f"The following text is not a valid JSON string:\n```\n{response_content}\n```\n"
                            f"When trying to parse it with json.loads() in Python script, one gets the following error:\n```\n{e}\n```\n"
                            f"It should match the following structure:\n```\n{json_resp}\n```\n"
                            "Make sure your response is a valid JSON string. Respond only with the JSON string."
                        )

                        messages = [{"role": "user", "content": prompt_content}]
                        # Prepare the payload for the AI API
                        payload = {"model": ai_model_name, "messages": messages, "temperature": 0}

                    else:
                        # If max retries reached, log an error and return None.
                        logging.error(
                            "Max retries reached. Failed to obtain valid JSON from AI."
                        )
                        return None

            except Exception as e:
                # Log any general errors during the request, and retry if possible.
                logging.error(f"Error during AI model completion on attempt {attempt}: {e}")
                if attempt < MAX_RETRIES:
                    logging.info(f"Retrying AI request in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)

                    prompt_content = (
                        f"The following text is not a valid JSON string:\n```\n{response_content}\n```\n"
                        f"When trying to parse it with json.loads() in Python script, one gets the following error:\n```\n{e}\n```\n"
                        f"It should match the following structure:\n```\n{json_resp}\n```\n"
                        "Make sure your response is a valid JSON string. Respond only with the JSON string."
                    )

                    messages = [{"role": "user", "content": prompt_content}]
                    # Prepare the payload for the AI API
                    payload = {"model": ai_model_name, "messages": messages, "temperature": 0}

                else:
                    # If max retries reached due to persistent errors, log and return None.
                    logging.error("Max retries reached due to persistent errors.")
                    return None

        return None  # Return None if all attempts fail.
    except Exception as e:
        # Catch and print any errors that occur.
        print(f"An error occurred: {e}")
        log_error_to_mongo(e, "ask_ai_model")


def count_chatgpt_tokens(ai_model_name, prompt):
    try:
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
    except Exception as e:
        # Catch and print any errors that occur.
        print(f"An error occurred: {e}")
        log_error_to_mongo(e, "count_chatgpt_tokens")


def replace_lines(lines, replacements):
    try:
        # Make a copy of the original lines to work with
        modified_lines = lines[:]
        
        # Sort the replacements by starting line in reverse order
        # to avoid shifting issues when replacing lines
        for (start, end), replacement_lines in sorted(replacements.items(), reverse=True):
            modified_lines[int(start)-1:int(end)] = replacement_lines
        
        return modified_lines
    except Exception as e:
        # Catch and print any errors that occur.
        print(f"An error occurred: {e}")
        log_error_to_mongo(e, "replace_lines")


def check_dependent_code_json(
    dep_object_type,
    dep_object_signature,
    dep_obj_code,
    parent_info,
    model_invocation_delay,
    dep_object_start_line,
    dep_object_end_line,
    dep_object_id,
    object_source_path,
    RepoName,
    dep_object_file_content,
    dep_object_file_path,
    engine_output
):
    try:
        object_dictionary = {"objectid": dep_object_id, "status": "", "message": ""}
        content_info_dictionary = {"filefullname": "", "originalfilecontent": ""}

        json_dep_resp = """
        {
        "updated":"<YES/NO to state if you updated the dependent code or not (if you believe it did not need updating)>",
        "comment":"<explain here what you updated (or NA if the dependent code does not need to be updated)>",
        "missing_information":"<list here information needed to finalize the dependent code (or NA if nothing is needed or if the dependent code was not updated)>",
        "signature_impact":"<YES/NO/UNKNOWN, to state here if the signature of the dependent code will be updated as a consequence of changed parameter list, types, return type, etc.>",
        "exception_impact":"<YES/NO/UNKNOWN, to state here if the exception handling related to the dependent code will be update, as a consequence of changed exception thrown or caugth, etc.>",
        "enclosed_impact":"<YES/NO/UNKNOWN, to state here if the dependent code update could impact further code enclosed in it in the same source file, such as methods defined in updated class, etc.>",
        "other_impact":"<YES/NO/UNKNOWN, to state here if the dependent code update could impact any other code referencing this code>",
        "impact_comment":"<comment here on signature, exception, enclosed, other impacts on any other code calling this one (or NA if not applicable)>",
        "code":"<the updated dependent code goes here (or original dependent code if the dependent code was not updated)>"
        }"""

        # Construct the prompt for the AI model
        prompt_content = f"""
                        CONTEXT: {dep_object_type} <{dep_object_signature}> is dependent on code that was modified by an AI:
                        {parent_info if parent_info else ''}
                        TASK:
                        Check and update if needed the following code:
                        '''\n{dep_obj_code}\n'''
                        GUIDELINES:
                        Use the following JSON structure to respond:
                        '''\n{json_dep_resp}\n'''
                        Make sure your response is a valid JSON string.
                        Respond only with the JSON string.
                        """

        # Clean up prompt content for formatting issues
        prompt_content = (
            prompt_content.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
        )

        logging.info(f"Prompt Content: {prompt_content}")

        # Prepare messages for the AI model
        messages = [{"role": "user", "content": prompt_content}]

        # Count tokens for the AI model's input
        code_token = count_chatgpt_tokens(ai_model_name, str(dep_obj_code))
        prompt_token = count_chatgpt_tokens(
            ai_model_name, "\n".join([json.dumps(m) for m in messages])
        )

        # Determine target response size
        target_response_size = int(code_token * 1.2 + 500)

        result = []

        # Check if the prompt length is within acceptable limits
        if prompt_token < (ai_model_max_tokens - target_response_size):
            # Ask the AI model for a response
            response_content = ask_ai_model(
                prompt_content,
                json_dep_resp,
                ai_model_url,
                ai_model_api_key,
                ai_model_version,
                ai_model_name,
                max_tokens=target_response_size,
            )
            logging.info(f"Response Content: {response_content}")
            time.sleep(model_invocation_delay)  # Delay for model invocation

            # Check if the response indicates an update was made
            if response_content["updated"].lower() == "yes":

                comment_str = "//"
                comment = f" {comment_str} This code is fixed by GEN AI \n {comment_str} AI update comment : {response_content['comment']} \n {comment_str} AI missing information : {response_content['missing_information']} \n {comment_str} AI signature impact : {response_content['signature_impact']} \n {comment_str} AI exception impact : {response_content['exception_impact']} \n {comment_str} AI enclosed code impact : {response_content['enclosed_impact']} \n {comment_str} AI other impact : {response_content['other_impact']} \n {comment_str} AI impact comment : {response_content['impact_comment']} \n"

                new_code = response_content["code"]  # Extract new code from the response
                # Convert the new_code string back to its readable format
                readable_code = (
                    new_code.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
                )
                start_line = int(dep_object_start_line)
                end_line = int(dep_object_end_line)

                object_dictionary["status"] = "success"
                object_dictionary["message"] = response_content["comment"]

                file_fullname = RepoName + object_source_path.split(RepoName)[-1]

                file_flag = False
                if len(engine_output["contentinfo"]) > 0:
                    for file in engine_output["contentinfo"]:
                        if file["filefullname"] == file_fullname:
                            file_flag = True
                            engine_output["contentinfo"][0]["originalfilecontent"][1][0][f"({start_line},{end_line})"] = comment + readable_code

                if not file_flag:
                    content_info_dictionary["filefullname"] = file_fullname
                    content_info_dictionary["originalfilecontent"] = [dep_object_file_content, [{f"({start_line},{end_line})" : comment + readable_code}]]

            else:
                object_dictionary["status"] = "failure"
                object_dictionary["message"] = response_content["comment"]

            # Append the response to the result list
            return object_dictionary, content_info_dictionary, engine_output

        else:
            logging.warning(
                "Prompt too long; skipping."
            )  # Warn if the prompt exceeds limits

            object_dictionary["status"] = "failure"
            object_dictionary["message"] = "failed because of reason: prompt too long"

            return object_dictionary, content_info_dictionary, engine_output
    except Exception as e:
        # Catch and print any errors that occur.
        print(f"An error occurred: {e}")
        log_error_to_mongo(e, "check_dependent_code_json")


def gen_code_connected_json(
    ApplicationName,
    TenantName,
    RepoName,
    RequestId,
    IssueID,
    ObjectID,
    PromptContent,
    ai_model_name,
    ai_model_version,
    ai_model_url,
    ai_model_api_key,
    ai_model_max_tokens,
    imaging_url,
    imaging_api_key,
    model_invocation_delay,
    json_resp,
    engine_output
):
    try:

        object_dictionary = {"objectid": ObjectID, "status": "", "message": ""}
        content_info_dictionary = {"filefullname": "", "originalfilecontent": ""}

        object_id = ObjectID
        logging.info(
            "---------------------------------------------------------------------------------------------------------------------------------------"
        )
        logging.info(f"Processing object_id -> {object_id}.....")

        # Initialize DataFrames to store exceptions and impacts
        exceptions = pd.DataFrame(columns=["link_type", "exception"])
        impacts = pd.DataFrame(
            columns=["object_type", "object_signature", "object_link_type", "object_code"]
        )

        # Construct URL to fetch object details
        object_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/objects/{object_id}?select=source-locations"
        params = {"api-key": imaging_api_key}
        object_response = requests.get(object_url, params=params, verify=False)

        # Check if object details were fetched successfully
        if object_response.status_code == 200:
            object_data = object_response.json()  # Parse object data
            object_type = object_data["typeId"]  # Get object type
            object_signature = object_data["mangling"]  # Get object signature
            object_technology = object_data["programmingLanguage"][
                "name"
            ]  # Get programming language
            source_location = object_data["sourceLocations"][0]  # Extract source location
            object_source_path = source_location["filePath"]  # Get source file path
            object_field_id = source_location["fileId"]  # Get file ID
            object_start_line = source_location["startLine"]  # Get start line number
            object_end_line = source_location["endLine"]  # Get end line number

            # Construct URL to fetch object code
            object_code_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/files/{object_field_id}?start-line={object_start_line}&end-line={object_end_line}"
            object_code_response = requests.get(object_code_url, params=params, verify=False)

            # Check if the object code was fetched successfully
            if object_code_response.status_code == 200:
                obj_code = object_code_response.text  # Get object code
            else:
                obj_code = ""
                logging.error(
                    f"Failed to fetch object code using {object_code_url}. Status code: {object_code_response.status_code}"
                )

            # Fetch callees for the current object
            object_callees_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/objects/{object_id}/callees"
            object_callees_response = requests.get(object_callees_url, params=params, verify=False)

            # Check if callees were fetched successfully
            if object_callees_response.status_code == 200:
                object_exceptions = object_callees_response.json()  # Parse exceptions data
                # Process each exception for the current object
                for object_exception in object_exceptions:
                    link_type = object_exception.get(
                        "linkType", ""
                    ).lower()  # Get link type
                    if link_type in [
                        "raise",
                        "throw",
                        "catch",
                    ]:  # Check for relevant link types
                        new_row = pd.DataFrame(
                            {
                                "link_type": [object_exception.get("linkType", "")],
                                "exception": [object_exception.get("name", "")],
                            }
                        )
                        exceptions = pd.concat(
                            [exceptions, new_row], ignore_index=True
                        )  # Append to exceptions DataFrame
            else:
                logging.error(
                    f"Failed to fetch callees using {object_callees_url}. Status code: {object_callees_response.status_code}"
                )

            # Fetch callers for the current object
            object_callers_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/objects/{object_id}/callers?select=bookmarks"
            object_callers_response = requests.get(object_callers_url, params=params, verify=False)

            # Check if callers were fetched successfully
            if object_callers_response.status_code == 200:
                impact_objects = object_callers_response.json()  # Parse impact objects data
                # Process each impact object
                for impact_object in impact_objects:
                    impact_object_id = impact_object.get("id")  # Get impact object ID
                    impact_object_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/objects/{impact_object_id}?select=source-locations"
                    impact_object_response = requests.get(impact_object_url, params=params, verify=False)

                    # Check if impact object data was fetched successfully
                    if impact_object_response.status_code == 200:
                        impact_object_data = (
                            impact_object_response.json()
                        )  # Parse impact object data
                        impact_object_type = impact_object_data.get(
                            "typeId", ""
                        )  # Get impact object type
                        impact_object_signature = impact_object_data.get(
                            "mangling", ""
                        )  # Get impact object signature
                        impact_object_source_location = impact_object_data["sourceLocations"][
                            0
                        ]  # Extract source location
                        impact_object_source_path = impact_object_source_location[
                            "filePath"
                        ]  # Get source file path
                        impact_object_field_id = int(impact_object_source_location[
                            "fileId"
                        ])  # Get file ID
                        impact_object_start_line = int(impact_object_source_location[
                            "startLine"
                        ])  # Get start line number
                        impact_object_end_line = int(impact_object_source_location[
                            "endLine"
                        ])  # Get end line number

                        impact_object_code_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/files/{impact_object_field_id}?start-line={impact_object_start_line}&end-line={impact_object_end_line}"
                        impact_object_code_response = requests.get(
                            impact_object_code_url, params=params, verify=False
                        )

                        # Check if the object code was fetched successfully
                        if impact_object_code_response.status_code == 200:
                            impact_object_full_code = (
                                impact_object_code_response.text
                            )  # Get object code
                        else:
                            impact_object_full_code = ""
                            logging.error(
                                f"Failed to fetch object code using {impact_object_code_url}. Status code: {impact_object_code_response.status_code}"
                            )

                    else:
                        impact_object_type = ""
                        impact_object_signature = ""
                        logging.error(
                            f"Failed to fetch impact object data using {impact_object_url}. Status code: {impact_object_response.status_code}"
                        )

                    impact_object_link_type = impact_object.get(
                        "linkType", ""
                    )  # Get link type for impact object

                    # Handle bookmarks associated with the impact object
                    bookmarks = impact_object.get("bookmarks")
                    if not bookmarks:
                        impact_object_bookmark_code = ""
                    else:
                        bookmark = bookmarks[0]
                        impact_object_bookmark_field_id = bookmark.get(
                            "fileId", ""
                        )  # Get file ID from bookmark
                        # Calculate start and end lines for impact object code
                        impact_object_bookmark_start_line = max(
                            int(bookmark.get("startLine", 1)) - 1, 0
                        )
                        impact_object_bookmark_end_line = max(int(bookmark.get("endLine", 1)) - 1, 0)
                        # Construct URL to fetch impact object code
                        impact_object_bookmark_code_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/files/{impact_object_bookmark_field_id}?start-line={impact_object_bookmark_start_line}&end-line={impact_object_bookmark_end_line}"
                        impact_object_bookmark_code_response = requests.get(
                            impact_object_bookmark_code_url, params=params, verify=False
                        )

                        # Check if the impact object code was fetched successfully
                        if impact_object_bookmark_code_response.status_code == 200:
                            impact_object_bookmark_code = (
                                impact_object_bookmark_code_response.text
                            )  # Get impact object code
                        else:
                            impact_object_bookmark_code = ""
                            logging.error(
                                f"Failed to fetch impact object code using {impact_object_bookmark_code_url}. Status code: {impact_object_bookmark_code_response.status_code}"
                            )

                    # Append the impact object data to the impacts DataFrame
                    new_impact_row = pd.DataFrame(
                        {
                            "object_id": [impact_object_id],
                            "object_type": [impact_object_type],
                            "object_signature": [impact_object_signature],
                            "object_link_type": [impact_object_link_type],
                            "object_bookmark_code": [impact_object_bookmark_code],
                            "object_source_path": [impact_object_source_path],
                            "object_file_id":[int(impact_object_field_id)],
                            "object_start_line": [int(impact_object_start_line)],
                            "object_end_line": [int(impact_object_end_line)],
                            "object_full_code": [impact_object_full_code],
                        }
                    )
                    impacts = pd.concat([impacts, new_impact_row], ignore_index=True)
            else:
                logging.error(
                    f"Failed to fetch callers using {object_callers_url}. Status code: {object_callers_response.status_code}"
                )
        else:
            logging.error(
                f"Failed to fetch object data using {object_url}. Status code: {object_response.status_code}"
            )  # Skip to the next object if there is an error

        if not exceptions.empty:
            # Group exceptions by link type and aggregate unique exceptions
            grouped_exceptions = exceptions.groupby("link_type")["exception"].unique()

            # Construct exception text
            exception_text = (
                f"Take into account that {object_type} <{object_signature}>: "
                + "; ".join(
                    [
                        f"{link_type} {', '.join(exc)}"
                        for link_type, exc in grouped_exceptions.items()
                    ]
                )
            )
            logging.info(f"exception_text = {exception_text}")
        else:
            exception_text = ""  # No exceptions found

        def generate_text(impacts):
            # Generate impact analysis text from impacts DataFrame
            base_method = f"{object_type} <{object_signature}>"
            text = f"Take into account that {base_method} is used by:\n"
            for i, row in impacts.iterrows():
                text += f" {i + 1}. {row['object_type']} <{row['object_signature']}> has a <{row['object_link_type']}> dependency as found in code:\n"
                text += f"````\n\t{row['object_bookmark_code']}\n````\n"
            return text

        if not impacts.empty:
            impact_text = generate_text(impacts)  # Generate impact analysis text
            logging.info(f"impact_text = {impact_text}")
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
            f"\nGUIDELINES:\nUse the following JSON structure to respond:\n'''\n{json_resp}\n'''\n"
            + (
                f"\nIMPACT ANALYSIS CONTEXT:\n{impact_text}\n{exception_text}\n"
                if impact_text or exception_text
                else ""
            )
            + "\nMake sure your response is a valid JSON string.\nRespond only the JSON string, and only the JSON string. "
            "Do not enclose the JSON string in triple quotes, backslashes, ... Do not add comments outside of the JSON structure.\n"
        )

        # Clean up prompt content for formatting issues
        prompt_content = (
            prompt_content.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
        )

        logging.info(f"Prompt Content: {prompt_content}")

        # Prepare messages for the AI model
        messages = [{"role": "user", "content": prompt_content}]

        # Count tokens for the AI model's input
        code_token = count_chatgpt_tokens(ai_model_name, str(obj_code))
        prompt_token = count_chatgpt_tokens(
            ai_model_name, "\n".join([json.dumps(m) for m in messages])
        )

        # Determine target response size
        target_response_size = int(code_token * 1.2 + 500)

        result = []

        # Check if the prompt length is within acceptable limits
        if prompt_token < (ai_model_max_tokens - target_response_size):
            # Ask the AI model for a response
            response_content = ask_ai_model(
                prompt_content,
                json_resp,
                ai_model_url,
                ai_model_api_key,
                ai_model_version,
                ai_model_name,
                max_tokens=target_response_size,
            )
            logging.info(f"Response Content: {response_content}")
            time.sleep(model_invocation_delay)  # Delay for model invocation

            # Check if the response indicates an update was made
            if response_content["updated"].lower() == "yes":

                comment_str = "//"
                comment = f" {comment_str} This code is fixed by GEN AI \n {comment_str} AI update comment : {response_content['comment']} \n {comment_str} AI missing information : {response_content['missing_information']} \n {comment_str} AI signature impact : {response_content['signature_impact']} \n {comment_str} AI exception impact : {response_content['exception_impact']} \n {comment_str} AI enclosed code impact : {response_content['enclosed_impact']} \n {comment_str} AI other impact : {response_content['other_impact']} \n {comment_str} AI impact comment : {response_content['impact_comment']} \n"

                new_code = response_content["code"]  # Extract new code from the response
                # Convert the new_code string back to its readable format

                readable_code = new_code
                # readable_code = (
                #     new_code.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
                # )
                start_line = object_start_line
                end_line = object_end_line

                # Construct URL to fetch object code
                file_content_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/files/{object_field_id}"
                file_content_response = requests.get(file_content_url, params=params, verify=False)

                # Check if the object code was fetched successfully
                if file_content_response.status_code == 200:
                    file_content = file_content_response.text  # Get object code
                else:
                    file_content = ""
                    logging.error(
                        f"Failed to fetch object code using {object_code_url}. Status code: {file_content_response.status_code}"
                    )            

                file_content = file_content.splitlines(keepends=True)
                file_path = RepoName + object_source_path.split(RepoName)[-1]

                object_dictionary["status"] = "success"
                object_dictionary["message"] = response_content["comment"]

                file_fullname = RepoName + object_source_path.split(RepoName)[-1]

                file_flag = False
                if len(engine_output["contentinfo"]) > 0:
                    for file in engine_output["contentinfo"]:
                        if file["filefullname"] == file_fullname:
                            file_flag = True
                            engine_output["contentinfo"][0]["originalfilecontent"][1][0][f"({start_line},{end_line})"] = comment + readable_code

                if not file_flag:
                    content_info_dictionary["filefullname"] = file_fullname
                    content_info_dictionary["originalfilecontent"] = [file_content, [{f"({start_line},{end_line})" : comment + readable_code}]]

                if (
                    content_info_dictionary["filefullname"]
                    or content_info_dictionary["originalfilecontent"]
                ):
                    engine_output["contentinfo"].append(content_info_dictionary)

                if (
                    response_content["signature_impact"].upper() == "YES"
                    or response_content["exception_impact"].upper() == "YES"
                    or response_content["enclosed_impact"].upper() == "YES"
                    or response_content["other_impact"].upper() == "YES"
                ):
                    if not impacts.empty:
                        for i, row in impacts.iterrows():
                            parent_info = f"""The {row['object_type']} <{row['object_signature']}> source code is the following:
                                            ```
                                            {row['object_full_code']}
                                            ```
                                            This source code is defined in the {object_type} <{file_path}>.
                                            The {object_type} <{file_path}> was updated by an AI the following way: [{response_content['comment']}].
                                            The AI predicted the following impacts on related code:
                                            * on signature: {response_content['signature_impact']}
                                            * on exceptions: {response_content['exception_impact']}
                                            * on enclosed objects: {response_content['enclosed_impact']}
                                            * other: {response_content['other_impact']}
                                            for the following reason: [{response_content['comment'] if response_content['impact_comment'] == 'NA' else response_content['impact_comment']}]."""
                            
                            # Construct URL to fetch object code
                            dep_object_file_content_url = f"{imaging_url}rest/tenants/{TenantName}/applications/{ApplicationName}/files/{int(row["object_file_id"])}"
                            dep_object_file_content_response = requests.get(dep_object_file_content_url, params=params, verify=False)

                            # Check if the object code was fetched successfully
                            if dep_object_file_content_response.status_code == 200:
                                dep_object_file_content = dep_object_file_content_response.text  # Get object code
                            else:
                                dep_object_file_content = ""
                                logging.error(
                                    f"Failed to fetch object code using {object_code_url}. Status code: {dep_object_file_content_response.status_code}"
                                )            

                            dep_object_file_content = dep_object_file_content.splitlines(keepends=True)
                            dep_object_file_path = RepoName + object_source_path.split(RepoName)[-1]

                            object_data, contentinfo_data, engine_output = check_dependent_code_json(
                                row["object_type"],
                                row["object_signature"],
                                row["object_full_code"],
                                parent_info,
                                model_invocation_delay,
                                row["object_start_line"],
                                row["object_end_line"],
                                row["object_id"],
                                row["object_source_path"],
                                RepoName,
                                dep_object_file_content,
                                dep_object_file_path,
                                engine_output
                            )

                            engine_output["objects"].append(object_data)

                            if (
                                contentinfo_data["filefullname"]
                                or contentinfo_data["originalfilecontent"]
                            ):
                                engine_output["contentinfo"].append(contentinfo_data)

            else:
                object_dictionary["status"] = "failure"
                object_dictionary["message"] = response_content["comment"]

        else:
            logging.warning(
                "Prompt too long; skipping."
            )  # Warn if the prompt exceeds limits

            object_dictionary["status"] = "failure"
            object_dictionary["message"] = "failed because of reason: prompt too long"

        engine_output["objects"].append(object_dictionary)

        return engine_output
    except Exception as e:
        # Catch and print any errors that occur.
        print(f"An error occurred: {e}")
        log_error_to_mongo(e, "gen_code_connected_json")


@app.route("/api-python/v1/")
def home():

    return ({
        'status': 200,
        'success' : 'Welcome to CAST Code Fix AI ENGINE.'
    })


@app.route("/api-python/v1/ProcessRequest/<string:Request_Id>")
def process_request(Request_Id):
    try:

        model_invocation_delay = 10

        json_resp = """
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
        """

        # Get Request Information from Mongo DB

        # Example of accessing a collection (replace 'mycollection' with your collection name)
        engine_input_collection = get_mongo_collection("EngineInput")
        prompt_library_collection = get_mongo_collection("PromptLibrary")
        engine_output_collection = get_mongo_collection("EngineOutput")
        files_content_collection = get_mongo_collection("FilesContent")

        # Optionally, print some documents from the collection (this assumes the collection exists)
        engine_input_document = engine_input_collection.find_one({"request.requestid":f"{Request_Id}"})

        # print(engine_input_document)

        # result = []  # Initialize result list to hold processed data

        for request in engine_input_document["request"]:
            if request["requestid"] == Request_Id:

                ApplicationName = request["applicationid"]
                TenantName = request["tenantid"]
                RepoURL = request["repourl"]
                RepoName = RepoURL.split("/")[-1].replace(".git", "")
                RequestId = request["requestid"]
                IssueID = request["issueid"]

                engine_output = {
                    "requestid": RequestId,
                    "issueid": IssueID,
                    "applicationid": ApplicationName,
                    "objects": [],
                    "contentinfo": [],
                    "status": "",
                    "createddate": timestamp,
                }

                objects_status_list = []

                for requestdetail in request["requestdetail"]:
                    prompt_id = requestdetail["promptid"]

                    prompt_library_documents = prompt_library_collection.find(
                        {"issueid": int(IssueID)}
                    )

                    for prompt_library_doc in prompt_library_documents:

                        for technology in prompt_library_doc["technologies"]:
                            for prompt in technology["prompts"]:
                                if prompt_id == prompt["promptid"]:
                                    PromptContent = prompt["prompt"]
                                    for objectdetail in requestdetail["objectdetails"]:
                                        ObjectID = objectdetail["objectid"]

                                        # Call the gen_code_connected_json function to process the request and generate code updates
                                        engine_output = gen_code_connected_json(
                                            ApplicationName,
                                            TenantName,
                                            RepoName,
                                            RequestId,
                                            IssueID,
                                            ObjectID,
                                            PromptContent,
                                            ai_model_name,
                                            ai_model_version,
                                            ai_model_url,
                                            ai_model_api_key,
                                            ai_model_max_tokens,
                                            imaging_url,
                                            imaging_api_key,
                                            model_invocation_delay,
                                            json_resp,
                                            engine_output
                                        )


                    for object in engine_output['objects']:
                        objects_status_list.append(object['status'])

                    if all(item == "success" for item in objects_status_list):
                        engine_output["status"] = "success"
                    elif all(item == "failure" for item in objects_status_list):
                        engine_output["status"] = "failure"
                    else:
                        engine_output["status"] = "partial success"

                    for content in engine_output["contentinfo"]:
                        lines = content["originalfilecontent"][0]
                        replacements = {}
                        for key, value in content["originalfilecontent"][1][0].items():
                            tuple_value = ast.literal_eval(key)
                            replacements[tuple_value] = value.split('\n')

                            replacements[tuple_value] = [line + "\n" for line in replacements[tuple_value]]

                        # Run the function with the lines and replacements
                        modified_lines = replace_lines(lines, replacements)

                        modified_lines = "".join(modified_lines)
                    
                        # Generate a unique 24-character alphanumeric string
                        unique_string = generate_unique_alphanumeric()
                        content["fileid"] = unique_string

                        files_content_data = { "requestid": RequestId, "fileid":unique_string, "updatedfilecontent": modified_lines, "createddate":timestamp }

                        res = files_content_collection.insert_one(files_content_data)
                        print(f"Data inserted for file - {unique_string}")

                        # with open("original_file.txt", "w") as of:
                        #     of.writelines(lines)
                        # with open("modified_file.txt", "w") as mf:
                        #     mf.writelines(modified_lines)


                    # Check if data already exists
                    existing_record = engine_output_collection.find_one(
                        {"requestid": engine_output["requestid"]}
                    )

                    if existing_record:
                        # Delete the existing record
                        engine_output_collection.delete_one(
                            {"requestid": engine_output["requestid"]}
                        )
                        print(
                            f"Existing requestid - {engine_output['requestid']} deleted."
                        )

                    # Insert the new data
                    result = engine_output_collection.insert_one(engine_output)
                    print(f"Data inserted for requestid - {engine_output['requestid']}")


                return ({
                    "status": "success",
                    "message" : f"Req -> {Request_Id} Successful.",
                    "code": 200
                })
            
            else:

                return ({
                    "status": "failed",
                    "message" : f"Req -> {Request_Id} Not Found or Incorrect EngineInput!",
                    "code": 404
                })

    except Exception as e:
        # Catch and print any errors that occur.
        print(f"An error occurred: {e}")
        log_error_to_mongo(e, "process_request")
        return ({
            "status": "failed",
            "message" : f"Internal Server Error -> {e}",
            "code": 500
        })


if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=8081)
