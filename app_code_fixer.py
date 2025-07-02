import ast
import json
import logging
import pandas as pd

from app_imaging import AppImaging
from app_llm import AppLLM
from app_logger import AppLogger
from app_mongo import AppMongoDb
from utils import generate_unique_alphanumeric, get_timestamp, replace_lines

class AppCodeFixer:
    def __init__(self, app_logger: AppLogger, mongo_db: AppMongoDb, ai_model: AppLLM, imaging: AppImaging):
        self.app_logger = app_logger
        self.mongo_db = mongo_db
        self.llm = ai_model
        self.imaging = imaging
        self.first_prompt = True

    # private methods
    def __gen_code_connected_json(
        self,
        ApplicationName,
        TenantName,
        RepoName,
        ObjectID,
        PromptContent,
        json_resp,
        engine_output,
        request_id,
        mongo_db
    ):
        try:

            object_dictionary = {"objectid": ObjectID, "status": "", "message": ""}
            content_info_dictionary = {"filefullname": "", "objects":[], "originalfilecontent": ""}

            object_id = ObjectID
            logging.info("---------------------------------------------------------------------------------------------------------------------------------------")
            logging.info(f"\n Processing object_id -> {object_id}.....")

            # Initialize DataFrames to store exceptions and impacts
            exceptions = pd.DataFrame(columns=["link_type", "exception"])
            impacts = pd.DataFrame(columns=["object_type", "object_signature", "object_link_type", "object_code"])

            # Construct URL to fetch object details
            object_response, object_url = self.imaging.get_source_locations(TenantName, ApplicationName, object_id)

            # Check if object details were fetched successfully
            if object_response.status_code == 200:
                object_data = object_response.json()  # Parse object data
                object_type = object_data["typeId"]  # Get object type
                object_signature = object_data["mangling"]  # Get object signature
                object_technology = object_data.get("programmingLanguage", {}).get("name", "")

                source_locations = object_data.get("sourceLocations")
                if not source_locations:
                    object_dictionary["status"] = "failure"
                    object_dictionary["message"] = f"failed because of reason: sourceLocations not available for this object from Imaging API -> {object_url}"
                    print(object_dictionary["message"])
                    engine_output["objects"].append(object_dictionary)
                    return engine_output
                
                if object_data["external"] == "true":
                    object_dictionary["status"] = "failure"
                    object_dictionary["message"] = f"failed because of reason: It is an external object and it does not contains sourceLocations."
                    print(object_dictionary["message"])
                    engine_output["objects"].append(object_dictionary)
                    return engine_output

                source_location = object_data["sourceLocations"][0]  # Extract source location
                object_source_path = source_location["filePath"]  # Get source file path
                object_field_id = source_location["fileId"]  # Get file ID
                object_start_line = source_location["startLine"]  # Get start line number
                object_end_line = source_location["endLine"]  # Get end line number

                # fetch object code
                obj_code = self.imaging.get_source('object', TenantName, ApplicationName, object_field_id, object_start_line, object_end_line, request_id)
                if obj_code is None:
                    object_dictionary["status"] = "failure"
                    object_dictionary["message"] = f"Failed to fetch object code using Imaging API for fileId={object_field_id}, startLine={object_start_line}, endLine={object_end_line}."
                    print(object_dictionary["message"])
                    engine_output["objects"].append(object_dictionary)
                    return engine_output

                # Fetch callees for the current object
                object_callees_response, object_callees_url = self.imaging.get_callees(TenantName, ApplicationName, object_id)

                # Check if callees were fetched successfully
                if object_callees_response.status_code == 200:
                    object_exceptions = object_callees_response.json()  # Parse exceptions data
                    # Process each exception for the current object
                    for object_exception in object_exceptions:
                        link_type = object_exception.get("linkType", "").lower()  # Get link type
                        if link_type in ["raise","throw","catch"]:  # Check for relevant link types
                            new_row = pd.DataFrame( { "link_type": [object_exception.get("linkType", "")],"exception": [object_exception.get("name", "")],})
                            exceptions = pd.concat([exceptions, new_row], ignore_index=True)  # Append to exceptions DataFrame
                else:
                    logging.error(f"Failed to fetch callees using {object_callees_url}. Status code: {object_callees_response.status_code}")

                # Fetch callers for the current object
                object_callers_response, object_callers_url = self.imaging.get_callers(TenantName, ApplicationName, object_id)

                # Check if callers were fetched successfully
                if object_callers_response.status_code == 200:
                    impact_objects = object_callers_response.json()  # Parse impact objects data
                    # Process each impact object
                    for impact_object in impact_objects:
                        impact_object_id = impact_object.get("id")  # Get impact object ID
                        impact_object_response, impact_object_url = self.imaging.get_source_locations(TenantName, ApplicationName, impact_object_id)

                        # Check if impact object data was fetched successfully
                        if impact_object_response.status_code == 200:
                            impact_object_data = (impact_object_response.json())  # Parse impact object data
                            impact_object_type = impact_object_data.get("typeId", "")  # Get impact object type
                            impact_object_signature = impact_object_data.get("mangling", "")  # Get impact object signature
                            impact_object_source_locations = impact_object_data.get("sourceLocations")
                            if not impact_object_source_locations:
                                object_dictionary["status"] = "failure"
                                object_dictionary["message"] = f"failed because of reason: sourceLocations not available for impact object from Imaging API -> {impact_object_url}"
                                print(object_dictionary["message"])
                                engine_output["objects"].append(object_dictionary)
                                continue  # Skip this impact object
                            impact_object_source_location = impact_object_source_locations[0]  # Extract source location
                            impact_object_source_path = impact_object_source_location["filePath"]  # Get source file path
                            impact_object_field_id = int(impact_object_source_location["fileId"])  # Get file ID
                            impact_object_start_line = int(impact_object_source_location["startLine"])  # Get start line number
                            impact_object_end_line = int(impact_object_source_location["endLine"])  # Get end line number

                            if impact_object_data["external"] == "true":
                                object_dictionary["status"] = "failure"
                                object_dictionary["message"] = f"failed because of reason: It is an external object and it does not contains sourceLocations."
                                print(object_dictionary["message"])
                                engine_output["objects"].append(object_dictionary)
                                return engine_output

                            impact_object_full_code = self.imaging.get_source('impact object', TenantName, ApplicationName, impact_object_field_id, impact_object_start_line, impact_object_end_line, request_id)
                            if impact_object_full_code is None:
                                logging.error(f"Failed to fetch impact object code using {impact_object_url}. Status code: 404 or not found.")
                                impact_object_full_code = ""  # Or handle as needed

                        else:
                            impact_object_type = ""
                            impact_object_signature = ""
                            logging.error(f"Failed to fetch impact object data using {impact_object_url}. Status code: {impact_object_response.status_code}")

                        impact_object_link_type = impact_object.get("linkType", "")  # Get link type for impact object

                        # Handle bookmarks associated with the impact object
                        bookmarks = impact_object.get("bookmarks")
                        if not bookmarks:
                            impact_object_bookmark_code = ""
                        else:
                            bookmark = bookmarks[0]
                            impact_object_bookmark_field_id = bookmark.get("fileId", "")  # Get file ID from bookmark
                            # Calculate start and end lines for impact object code
                            impact_object_bookmark_start_line = max(int(bookmark.get("startLine", 1)) - 1, 0)
                            impact_object_bookmark_end_line = max(int(bookmark.get("endLine", 1)) - 1, 0)
                            impact_object_bookmark_code = self.imaging.get_source('impact object bookmark', TenantName, ApplicationName,impact_object_bookmark_field_id,impact_object_bookmark_start_line,impact_object_bookmark_end_line, request_id)

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
                    logging.error(f"Failed to fetch callers using {object_callers_url}. Status code: {object_callers_response.status_code}")
            else:
                logging.error(f"Failed to fetch object data using {object_url}. Status code: {object_response.status_code}")  # Skip to the next object if there is an error

            if not exceptions.empty:
                # Group exceptions by link type and aggregate unique exceptions
                grouped_exceptions = exceptions.groupby("link_type")["exception"].unique()

                # Construct exception text
                exception_text = (
                    f"Take into account that {object_type} <{object_signature}>: "
                    + "; ".join(
                        [ f"{link_type} {', '.join(exc)}" for link_type, exc in grouped_exceptions.items() ]
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
            # prompt_content = (prompt_content.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\"))

            logging.info(f"Prompt Content: {prompt_content}")

            # Prepare messages for the AI model
            messages = [{"role": "user", "content": prompt_content}]

            # Count tokens for the AI model's input
            code_token = self.llm.count_tokens(str(obj_code), request_id)
            prompt_token = self.llm.count_tokens("\n".join([json.dumps(m) for m in messages]), request_id)

            # Determine target response size
            target_response_size = int(code_token * 1.2 + 500)

            # Check if the prompt length is within acceptable limits
            if prompt_token < (self.llm.model_max_input_tokens - target_response_size) and target_response_size < self.llm.model_max_output_tokens:
            # if True:
                # Ask the AI model for a response
                response_content, ai_msg, tokens = self.llm.ask_ai_model(
                    request_id,
                    prompt_content,
                    json_resp,
                    target_response_size,
                    ObjectID
                )
                logging.info(f"Response Content: {response_content}")

                object_dictionary["prompt_tokens"] = tokens["prompt_tokens"]
                object_dictionary["completion_tokens"] = tokens["completion_tokens"]
                object_dictionary["total_tokens"] = tokens["total_tokens"]

                if response_content == None:
                    object_dictionary["status"] = "failure"
                    object_dictionary["message"] = ai_msg

                else:
                    # Check if the response indicates an update was made
                    if response_content["updated"].lower() == "yes":

                        comment_str = "//"
                        comment = f" {comment_str} This code is fixed by GEN AI \n {comment_str} AI update comment : {response_content['comment']} \n {comment_str} AI missing information : {response_content['missing_information']} \n {comment_str} AI signature impact : {response_content['signature_impact']} \n {comment_str} AI exception impact : {response_content['exception_impact']} \n {comment_str} AI enclosed code impact : {response_content['enclosed_impact']} \n {comment_str} AI other impact : {response_content['other_impact']} \n {comment_str} AI impact comment : {response_content['impact_comment']} \n"

                        end_comment = "\n// End of GEN AI fix"

                        new_code = response_content["code"]  # Extract new code from the response
                        # Convert the new_code string back to its readable format

                        readable_code = new_code
                        # readable_code = (
                        #     new_code.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
                        # )
                        start_line = object_start_line
                        end_line = object_end_line

                        # fetch object code
                        file_content = self.imaging.get_file('object', TenantName, ApplicationName, object_field_id, request_id)

                        file_content = file_content.splitlines(keepends=True)
                        # file_path = RepoName + object_source_path.split(RepoName)[-1]
                        file_path = object_source_path

                        object_dictionary["status"] = "success"
                        object_dictionary["message"] = response_content["comment"]

                        # file_fullname = RepoName + object_source_path.split(RepoName)[-1]
                        file_fullname = object_source_path

                        file_flag = False
                        if len(engine_output["contentinfo"]) > 0:
                            for i, file in enumerate(engine_output["contentinfo"]):
                                if file["filefullname"] == file_fullname:
                                    file_flag = True
                                    engine_output["contentinfo"][i]["objects"].append(object_id)
                                    engine_output["contentinfo"][i]["originalfilecontent"][1][0][f"({start_line},{end_line})"] = comment + readable_code + end_comment

                        if not file_flag:
                            content_info_dictionary["filefullname"] = file_fullname
                            content_info_dictionary["objects"].append(object_id)
                            content_info_dictionary["originalfilecontent"] = [file_content, [{f"({start_line},{end_line})" : comment + readable_code + end_comment}]]

                        if (content_info_dictionary["filefullname"] or content_info_dictionary["originalfilecontent"]):
                            engine_output["contentinfo"].append(content_info_dictionary)

                        if (response_content["signature_impact"].upper() == "YES"
                            or response_content["exception_impact"].upper() == "YES"
                            or response_content["enclosed_impact"].upper() == "YES"
                            or response_content["other_impact"].upper() == "YES"):

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

                                    # fetch object code
                                    dep_object_file_content = self.imaging.get_file('dep object', TenantName, ApplicationName, int(row["object_file_id"]), request_id)

                                    dep_object_file_content = dep_object_file_content.splitlines(keepends=True)
                                    # dep_object_file_path = RepoName + object_source_path.split(RepoName)[-1]
                                    dep_object_file_path = object_source_path

                                    object_data, contentinfo_data, engine_output = self.__check_dependent_code_json(
                                        ObjectID,
                                        row["object_type"],
                                        row["object_signature"],
                                        row["object_full_code"],
                                        parent_info,
                                        row["object_start_line"],
                                        row["object_end_line"],
                                        row["object_id"],
                                        row["object_source_path"],
                                        RepoName,
                                        dep_object_file_content,
                                        dep_object_file_path,
                                        engine_output,
                                        request_id,
                                        mongo_db
                                    )

                                    engine_output["objects"].append(object_data)

                                    if (contentinfo_data["filefullname"] or contentinfo_data["originalfilecontent"]):
                                        engine_output["contentinfo"].append(contentinfo_data)

                    else:
                        object_dictionary["status"] = "Unmodified"
                        object_dictionary["message"] = response_content["comment"]

            else:
                logging.warning("Prompt too long; skipping.")  # Warn if the prompt exceeds limits

                object_dictionary["status"] = "failure"
                object_dictionary["message"] = "failed because of reason: prompt too long"

            engine_output["objects"].append(object_dictionary)

            return engine_output
        except Exception as e:
            # Catch and print any errors that occur.
            print(f"An error occurred: {e}")
            self.app_logger.log_error("gen_code_connected_json", e, request_id)
            return engine_output
        finally:
            collection = mongo_db.get_collection("status_queue")
            # Step 2: Inputs
            new_object_id = object_dictionary['objectid']
            new_status = object_dictionary['status']

            # Step 3: Fetch the document
            doc = collection.find_one({"request_id": request_id})

            if doc:
                # Step 4: Get or initialize objects_list
                objects_list = doc.get("objects_list", {})
                
                # Step 5: Append or update object_id with status
                objects_list[new_object_id] = new_status

                # Step 6: Update the document in MongoDB
                result = collection.update_one(
                    {"request_id": request_id},
                    {"$set": {"objects_list": objects_list}}
                )

                print(f"Updated document. Modified count: {result.modified_count}")

    def __check_dependent_code_json(
        self,
        ObjectID,
        dep_object_type,
        dep_object_signature,
        dep_obj_code,
        parent_info,
        dep_object_start_line,
        dep_object_end_line,
        dep_object_id,
        object_source_path,
        RepoName,
        dep_object_file_content,
        dep_object_file_path,
        engine_output,
        request_id,
        mongo_db
    ):
        try:
            object_dictionary = {"objectid": dep_object_id, "status": "", "message": "", "dependent_info":f"this object is depenedent on ObjectID-{ObjectID}"}
            content_info_dictionary = {"filefullname": "", "objects":[], "originalfilecontent": ""}

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
            prompt_content = (
                            f"CONTEXT: {dep_object_type} <{dep_object_signature}> is dependent on code that was modified by an AI: \n"
                            f"{parent_info if parent_info else ''} \n"
                            f"TASK:\n"
                            f"Check and update if needed the following code: \n"
                            f"'''\n{dep_obj_code}\n'''"
                            f"GUIDELINES: \n"
                            f"Use the following JSON structure to respond: \n"
                            f"'''\n{json_dep_resp}\n'''\n"
                            f"\nMake sure your response is a valid JSON string.\nRespond only the JSON string, and only the JSON string. "
                            f"Do not enclose the JSON string in triple quotes, backslashes, ... Do not add comments outside of the JSON structure.\n"
            )
            
            # Clean up prompt content for formatting issues
            # prompt_content = (prompt_content.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\"))

            logging.info(f"Prompt Content: {prompt_content}")

            # Prepare messages for the AI model
            messages = [{"role": "user", "content": prompt_content}]

            # Count tokens for the AI model's input
            code_token = self.llm.count_tokens(str(dep_obj_code), request_id)
            prompt_token = self.llm.count_tokens("\n".join([json.dumps(m) for m in messages]), request_id)

            # Determine target response size
            target_response_size = int(code_token * 1.2 + 500)

            # Check if the prompt length is within acceptable limits
            if prompt_token < (self.llm.model_max_input_tokens - target_response_size) and target_response_size < self.llm.model_max_output_tokens:
            # if True:
                # Ask the AI model for a response
                response_content, ai_msg, tokens = self.llm.ask_ai_model(
                    request_id,
                    prompt_content,
                    json_dep_resp,
                    target_response_size,
                    dep_object_id
                )
                logging.info(f"Response Content: {response_content}")

                object_dictionary["prompt_tokens"] = tokens["prompt_tokens"]
                object_dictionary["completion_tokens"] = tokens["completion_tokens"]
                object_dictionary["total_tokens"] = tokens["total_tokens"]

                if response_content == None:
                    object_dictionary["status"] = "failure"
                    object_dictionary["message"] = ai_msg

                    # Append the response to the result list
                    return object_dictionary, content_info_dictionary, engine_output

                else:
                    # Check if the response indicates an update was made
                    if response_content["updated"].lower() == "yes":

                        comment_str = "//"
                        comment = f" {comment_str} This code is fixed by GEN AI \n {comment_str} AI update comment : {response_content['comment']} \n {comment_str} AI missing information : {response_content['missing_information']} \n {comment_str} AI signature impact : {response_content['signature_impact']} \n {comment_str} AI exception impact : {response_content['exception_impact']} \n {comment_str} AI enclosed code impact : {response_content['enclosed_impact']} \n {comment_str} AI other impact : {response_content['other_impact']} \n {comment_str} AI impact comment : {response_content['impact_comment']} \n"
                        end_comment = "\n// End of GEN AI fix"

                        new_code = response_content["code"]  # Extract new code from the response
                        # Convert the new_code string back to its readable format
                        readable_code = (new_code.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\"))
                        start_line = int(dep_object_start_line)
                        end_line = int(dep_object_end_line)

                        object_dictionary["status"] = "success"
                        object_dictionary["message"] = response_content["comment"]

                        # file_fullname = RepoName + object_source_path.split(RepoName)[-1]
                        file_fullname = object_source_path

                        file_flag = False
                        if len(engine_output["contentinfo"]) > 0:
                            for i, file in enumerate(engine_output["contentinfo"]):
                                if file["filefullname"] == file_fullname:
                                    file_flag = True
                                    engine_output["contentinfo"][i]["objects"].append(dep_object_id)
                                    engine_output["contentinfo"][i]["originalfilecontent"][1][0][f"({start_line},{end_line})"] = comment + readable_code + end_comment

                        if not file_flag:
                            content_info_dictionary["filefullname"] = file_fullname
                            content_info_dictionary["objects"].append(dep_object_id)
                            content_info_dictionary["originalfilecontent"] = [dep_object_file_content, [{f"({start_line},{end_line})" : comment + readable_code + end_comment}]]

                    else:
                        object_dictionary["status"] = "Unmodified"
                        object_dictionary["message"] = response_content["comment"]

                    # Append the response to the result list
                    return object_dictionary, content_info_dictionary, engine_output

            else:
                logging.warning("Prompt too long; skipping.")  # Warn if the prompt exceeds limits

                object_dictionary["status"] = "failure"
                object_dictionary["message"] = "failed because of reason: prompt too long"

                return object_dictionary, content_info_dictionary, engine_output
        except Exception as e:
            # Catch and print any errors that occur.
            print(f"An error occurred: {e}")
            self.app_logger.log_error(e, "check_dependent_code_json", request_id)
            return object_dictionary, content_info_dictionary, engine_output
        finally:
            collection = mongo_db.get_collection("status_queue")
            # Step 2: Inputs
            new_object_id = object_dictionary['objectid']
            new_status = object_dictionary['status']

            # Step 3: Fetch the document
            doc = collection.find_one({"request_id": request_id})

            if doc:
                # Step 4: Get or initialize objects_list
                objects_list = doc.get("objects_list", {})
                
                # Step 5: Append or update object_id with status
                objects_list[new_object_id] = new_status

                # Step 6: Update the document in MongoDB
                result = collection.update_one(
                    {"request_id": request_id},
                    {"$set": {"objects_list": objects_list}}
                )

                print(f"Updated document. Modified count: {result.modified_count}")

    def __resend_fullfile_to_ai(self, full_code, request_id):
        try:

            json_resp = """
            {
            "updated":"<YES/NO to state if you updated the code or not (if you believe it did not need fixing)>",
            "comment":"<explain here what you updated (or the reason why you did not update it)>",
            "code":"<the fixed code goes here (or original code if the code was not updated)>"
            }
            """

            # Construct the prompt for the AI model
            prompt_content = (
                "TASK:\n"
                "1) fix syntax errors.\n"
                "2) add only missing packages.\n"
                "3) add single line comments saying that this is fixed by Gen AI for the lines only fixed by Gen AI.\n"
                "4) do not remove already existing comments.\n"
                "5) indent the code properly.\n"
                f"'''\n{full_code}\n'''\n"  
                "GUIDELINES:\n"
                f"Use the following JSON structure to respond:\n'''\n{json_resp}\n'''\n"
                "Make sure your response is a valid JSON string.\nRespond only the JSON string, and only the JSON string.\n"
                "Do not enclose the JSON string in triple quotes, backslashes, ... Do not add comments outside of the JSON structure.\n"
            )

            # Clean up prompt content for formatting issues
            # prompt_content = (prompt_content.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\"))

            logging.info(f"Prompt Content: {prompt_content}")

            # with open("prompt_content.txt", "w") as file:
            #     file.write(prompt_content)

            # Prepare messages for the AI model
            messages = [{"role": "user", "content": prompt_content}]

            # Count tokens for the AI model's input
            code_token = self.llm.count_tokens(str(full_code), request_id)
            prompt_token = self.llm.count_tokens("\n".join([json.dumps(m) for m in messages]), request_id)

            # Determine target response size
            target_response_size = int(code_token * 1.2 + 500)

            # Check if the prompt length is within acceptable limits
            # if True:
            if prompt_token < (self.llm.model_max_input_tokens - target_response_size) and target_response_size < self.llm.model_max_output_tokens:
                # Ask the AI model for a response
                response_content, _, tokens = self.llm.ask_ai_model(
                    request_id,
                    prompt_content,
                    json_resp,
                    max_tokens=target_response_size
                )
                logging.info(f"Response Content: {response_content}")
                
                if response_content == None:
                    return full_code
                else:
                    # Check if the response indicates an update was made
                    return response_content["code"]
            else:
                return full_code

        except Exception as e:
            # Catch and print any errors that occur.
            print(f"An error occurred: {e}")
            self.app_logger.log_error(e, "resend_fullfile_to_ai", request_id)

    # Function containing the original processing logic (refactored for reuse)
    def process_request_logic(self, request_id, mongo_db):
        # Reset flag to avoid pausing on the first call
        self.llm.first_prompt = True

        try:
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
            engine_input_collection = self.mongo_db.get_collection("EngineInput")
            prompt_library_collection = self.mongo_db.get_collection("PromptLibrary")
            engine_output_collection = self.mongo_db.get_collection("EngineOutput")
            files_content_collection = self.mongo_db.get_collection("FilesContent")

            # Optionally, print some documents from the collection (this assumes the collection exists)
            engine_input_document = engine_input_collection.find_one({"request.requestid": f"{request_id}"})

            # print(engine_input_document)

            # result = []  # Initialize result list to hold processed data

            for request in engine_input_document["request"]:
                if request["requestid"] == request_id:

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
                        "createddate": get_timestamp(),
                    }

                    files_content = {
                        "requestid": RequestId,
                        "updatedcontentinfo": [],
                        "createddate": get_timestamp(),
                    }

                    objects_status_list = []

                    for requestdetail in request["requestdetail"]:
                        prompt_id = requestdetail["promptid"]

                        prompt_library_documents = prompt_library_collection.find({"issueid": int(IssueID)})

                        for prompt_library_doc in prompt_library_documents:

                            for technology in prompt_library_doc["technologies"]:
                                for prompt in technology["prompts"]:
                                    if prompt_id == prompt["promptid"]:
                                        PromptContent = prompt["prompt"]
                                        for objectdetail in requestdetail["objectdetails"]:
                                            ObjectID = objectdetail["objectid"]

                                            # Call the gen_code_connected_json function to process the request and generate code updates
                                            engine_output = self.__gen_code_connected_json(
                                                ApplicationName,
                                                TenantName,
                                                RepoName,
                                                ObjectID,
                                                PromptContent,
                                                json_resp,
                                                engine_output,
                                                request_id,
                                                mongo_db
                                            )


                        for object in engine_output['objects']:
                            objects_status_list.append(object['status'])

                        if all(item == "Unmodified" for item in objects_status_list):
                            engine_output["status"] = "Unmodified"
                        elif all(item == "failure" for item in objects_status_list):
                            engine_output["status"] = "failure"
                        elif any(item == "failure" for item in objects_status_list):
                            engine_output["status"] = "partial success"
                        else:
                            engine_output["status"] = "success"

                        for content in engine_output["contentinfo"]:
                            lines = content["originalfilecontent"][0]
                            replacements = {}
                            for key, value in content["originalfilecontent"][1][0].items():
                                tuple_value = ast.literal_eval(key)
                                replacements[tuple_value] = value.split('\n')
                                replacements[tuple_value] = [line + "\n" for line in replacements[tuple_value]]

                            # Run the function with the lines and replacements
                            modified_lines = replace_lines(self.app_logger, lines, replacements, request_id)
                            modified_lines = "".join(modified_lines)
                            modified_lines = self.__resend_fullfile_to_ai(modified_lines, request_id)
                        
                            # Generate a unique 24-character alphanumeric string
                            unique_string = generate_unique_alphanumeric(request_id, self.app_logger)
                            content["fileid"] = unique_string

                            file_path = content["filefullname"].replace('\\','/')

                            if RepoName in file_path:
                                file_path = RepoName + file_path.split(RepoName)[-1]

                            files_content_data = { "fileid":unique_string, "filepath":file_path, "updatedfilecontent": modified_lines }

                            files_content["updatedcontentinfo"].append(files_content_data)

                            # res = files_content_collection.insert_one(files_content_data)
                            # print(f"Data inserted for file - {unique_string}")

                            # with open("original_file.txt", "w") as of:
                            #     of.writelines(lines)
                            # with open("modified_file.txt", "w") as mf:
                            #     mf.writelines(modified_lines)


                        # Define the filter and update
                        filter = {"request.requestid": f"{request_id}"}  # Match document with requestid
                        update = {"$set": {"request.$[elem].status": f"{engine_output["status"] }"}}  # Update the status for the matched request
                        array_filters = [{"elem.requestid": f"{request_id}"}] # Specify array filters
                        engine_input_status_update = engine_input_collection.update_one(filter, update, array_filters=array_filters) # Perform the update

                        # Check if data already exists
                        existing_record = engine_output_collection.find_one({"requestid": engine_output["requestid"]})

                        if existing_record:
                            # Delete the existing record
                            engine_output_collection.delete_one({"requestid": engine_output["requestid"]})
                            print(f"Existing requestid - {engine_output['requestid']} deleted in engine_output_collection.")

                        # Insert the new data
                        engine_output_result = engine_output_collection.insert_one(engine_output)
                        print(f"Data inserted into engine_output_collection for requestid - {engine_output['requestid']}")

                        files_content_exist = files_content_collection.find_one({"requestid": files_content["requestid"]})

                        if files_content_exist:
                            # Delete the existing record
                            files_content_collection.delete_one({"requestid": files_content["requestid"]})
                            print(f"Existing requestid - {files_content['requestid']} deleted in files_content_collection.")
                        
                        # Insert the new data
                        files_content_result = files_content_collection.insert_one(files_content)
                        print(f"Data inserted into files_content_collection for requestid - {engine_output['requestid']}")

                    return ({
                        "Request_Id": request_id,
                        "status": "success",
                        "message" : f"Req -> {request_id} Successful.",
                        "code": 200
                    })
                
                else:
                    print(f"Req -> {request_id} Not Found or Incorrect EngineInput!")
                    self.app_logger.log_error(f"Req -> {request_id} Not Found or Incorrect EngineInput!", "process_request", request_id)
                    return ({
                        "Request_Id": request_id,
                        "status": "failed",
                        "message" : f"Req -> {request_id} Not Found or Incorrect EngineInput!",
                        "code": 404
                    })

        except Exception as e:
            # Catch and print any errors that occur.
            print(f"An error occurred: {e}")
            self.app_logger.log_error("process_request", e, request_id)
            return {
                "Request_Id": request_id,
                "status": "failed",
                "message" : f"Internal Server Error -> {e}",
                "code": 500
            }